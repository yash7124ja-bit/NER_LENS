# Local reproducible infrastructure and encrypted backups

`compose.yaml` defines web, API, PostgreSQL 17/PostGIS 3.5, and GraphHopper 11.0. Published ports bind to loopback only. This is a local HTTP prototype, not a TLS production deployment. PostgreSQL and graph data use persistent named volumes. The retained PBF is mounted read-only and is never copied, moved or removed by these files.

Set environment variables (inject secrets through your shell/secret manager; do not commit values): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`, and `GRAPHHOPPER_PBF`. The database URL must use the Compose hostname `db`, port 5432, and URL-encoded credentials corresponding to the PostgreSQL variables. `GRAPHHOPPER_PBF` should point to `D:/SIH-2026/NER_LENS_ARTIFACTS/m0/north-eastern-zone-260909.osm.pbf`. The retained extract SHA-256 is `9250938dd6e8c61ad3ca533620a86c5d286e86f60c2bc45086e173f2ace068a9`; verify it against the retained receipt before initial import.

```
docker compose config --quiet
docker compose build
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up -d
```

Browse `http://localhost:8080`. Nginx proxies `/v1/` to the API and serves the frontend; the API is separately reachable at loopback port 8000. GraphHopper imports the exact committed v3 config and three custom profiles; first graph import is resource-intensive and can take time. GraphHopper receives 3 GB Java heap and needs additional container memory. Its admin port is not published. API availability does not imply routing import has completed. Stop with `docker compose down`; omit `--volumes` to preserve database and graph state.

The backend build uses `uv sync --frozen --no-dev` and the committed lock; frontend uses `npm ci`. Upstream image manifests were resolved directly from Docker Hub's authenticated registry API on 2026-09-14 and pinned by digest:

| Component | Upstream tag | Digest |
|---|---|---|
| Python | `python:3.12-slim-bookworm` | `sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254` |
| Node | `node:22-alpine` | `sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32` |
| Nginx | `nginx:1.28-alpine` | `sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236` |
| Java | `eclipse-temurin:21-jre-jammy` | `sha256:bce52ea7da1f72e6bf5bec505e63b6eb55ba79ad1226903579f77eab1a80139a` |
| PostgreSQL/PostGIS | `postgis/postgis:17-3.5` | `sha256:01a6a70e41e6c4467c8f55f6063555ed72db2d6662cd0d571040d42eadaeb6f6` |

[PostGIS upstream image documentation](https://hub.docker.com/r/postgis/postgis/) confirms the PostgreSQL 17 data-directory layout and version pairing. [GraphHopper's official repository](https://github.com/graphhopper/graphhopper) links community Docker builds rather than publishing an official image. Accordingly, the GraphHopper build uses the official Temurin runtime and the official [11.0 release JAR](https://github.com/graphhopper/graphhopper/releases/download/11.0/graphhopper-web-11.0.jar), pinned with Docker ADD checksum `b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def`, matching the existing v3 receipt. The PostGIS image targets amd64; validate separately before using another architecture.

## Encrypted backup and restore

Install repository dependencies and PostgreSQL 17 client executables (`pg_dump`, `pg_restore`) on the execution host. Inject `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` and `BACKUP_FERNET_KEY`. Generate the key once with `cryptography.fernet.Fernet.generate_key()` in a secure provisioning flow, and retain it independently of encrypted backups. No connection URL or password is put on the child command line. Commands inherit libpq environment variables; stderr is suppressed because it can contain connection details.

```
uv run python scripts/backup_restore.py backup --source-db ner_lens --output backups/nightly-YYYYMMDD.fernet
uv run python scripts/backup_restore.py restore --archive backups/nightly-YYYYMMDD.fernet --target-db ner_lens_restore_check
```

Create the backup output directory and a distinct empty target database beforehand. The encrypted envelope authenticates both the dump and its source database name. Restore refuses the source name, never invokes `--clean`/`--create`, and uses a single transaction with exit-on-error. Source database and archive remain intact. Wrong keys or tampered archives fail before invoking PostgreSQL. Existing backup files are never overwritten. Plaintext dump bytes remain in process memory and are piped directly to pg_restore; no plaintext temporary file is created. This whole-archive method is for prototype-sized databases and requires memory substantially larger than the dump; use reviewed streaming encryption for large backups.

A nightly scheduler must invoke the backup command with injected secrets and a unique date-based output path; no persistent host schedule was installed. Monitor exit status, retain off-host encrypted copies and periodically restore into an isolated database. A successful cryptographic unit test is not a database restore drill. The CLI restores one database's objects/data without ownership/privileges; PostgreSQL cluster roles, external files and grants need separately managed provisioning.

On Windows, run `pwsh -NoProfile -File scripts/restore_drill.ps1` to repeat an isolated drill. It migrates a fresh source to the current Alembic head, inserts one jurisdiction and audit event, encrypts a backup, restores it into a second temporary PostGIS instance, checks the revision and record counts, and removes both containers and the temporary archive. The target database is created from `template0`: the PostGIS image's default database already contains a `tiger` schema and is not an empty restore target.

Validation on 2026-09-26: the drill passed at `0017_media_object_storage` with one jurisdiction and one audit event after restore. This checks a synthetic, small database; it does not establish production backup retention, off-host storage, large-volume recovery time, or deployment rollback.

