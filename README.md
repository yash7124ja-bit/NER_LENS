# NER LENS — local replay corridor explorer

The integrated checkpoint is a read-only FastAPI API plus the separate React client in
`../NER_LENS_FRONTEND`. It displays the existing six synthetic corridor bands, source
provenance and explicit unknown status. It does not recommend routes or assert current
road conditions. See [milestone status](docs/MILESTONES.md#current-implementation-checkpoint--14-september-2026).

## Run locally

From this repository, using Python 3.12 and [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --locked --extra dev --python 3.12
uv run python -m ner_lens.replay --initialize-only
uv run python -m uvicorn ner_lens.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Initialization applies Alembic through `0004_local_accounts` and imports the audited
synthetic replay fixture. Use `--initialize-only` to prepare the database without
writing a legacy bearer-token file. Migrations contain no accounts or credentials.

Provision a local account with explicit roles and existing database jurisdiction IDs:

```powershell
$env:NER_LENS_BOOTSTRAP_ROLES = 'regional_viewer'
# Set NER_LENS_BOOTSTRAP_JURISDICTION_IDS to the assigned jurisdiction ID(s).
uv run python -m ner_lens.identity.accounts
```

The CLI prompts for email, password (hidden) and display name. For unattended setup,
inject `NER_LENS_BOOTSTRAP_EMAIL`, `NER_LENS_BOOTSTRAP_PASSWORD`, and
`NER_LENS_BOOTSTRAP_DISPLAY_NAME` into that process's environment, then remove them.
Never commit those values. Existing accounts are preserved; differing settings are
rejected rather than silently resetting passwords or privileges. The requested
team account was provisioned in the ignored local database as a regional viewer.

In a second terminal:

```powershell
cd ../NER_LENS_FRONTEND
npm ci
npm run dev
```

Open `http://127.0.0.1:5173` and sign in. Passwords are salted scrypt hashes in the
database. Sessions use random opaque HttpOnly, SameSite=Strict cookies; only token
digests are stored server-side. Reload restores the session, logout revokes it,
and current database roles/scopes are checked for every corridor request.

Policy environment variables: `SESSION_TTL_SECONDS` (28800), `LOGIN_ATTEMPT_LIMIT`
(5 failed attempts), `LOGIN_WINDOW_SECONDS` (900), `SESSION_COOKIE_NAME`
(`ner_lens_session`), `SESSION_COOKIE_SECURE` (false only for local HTTP), and
`AUTH_ALLOWED_ORIGINS` (empty by default). The Vite proxy preserves the browser Host
so exact same-origin checks work. HTTPS deployments must enable Secure cookies and
complete the separate deployment/identity gate. Local password authentication does
not implement the specifications' future OIDC/PKCE/MFA workflow.

Legacy CLI/test bearer sessions remain supported via `python -m ner_lens.replay
--token-file .replay-token-next`. The browser does not use bearer-token entry.
No `.env` file is loaded automatically. The default database is
`sqlite:///ner_lens_replay.sqlite`, relative to the current working directory. For
an alternate disposable store set `DATABASE_URL` in the shell before both commands.
Only `NER_LENS_ENV=replay` and SQLite are supported by this local entrypoint. Existing
provider credentials are neither read nor required. Keep both servers on loopback.
The client proxies `/v1` and `/health` to port 8000; no cross-origin bearer access or
public deployment is enabled.

## Implemented API

- `POST /v1/auth/login`: validate a database account and issue a cookie session.
- `GET /v1/auth/session`: restore current profile and expiry.
- `POST /v1/auth/logout`: revoke the presented session and clear the cookie.
- `GET /health/live`: process liveness.
- `GET /health/ready`: database tables and exact migration head compatibility.
- `GET /v1/corridors`: authorized active replay corridor discovery.
- `GET /v1/corridors/{corridor_id}/state`: paginated segment geometry, synthetic
  restrictions, unknown operational status, unavailable risk and provenance.

OpenAPI is generated from the application at `/openapi.json`; `/docs` is the local
interactive reference. The checked-in snapshot is [docs/openapi/v1.json](docs/openapi/v1.json).
No review/status/route/mission/source-health API is advertised before integration.

## Validate

### External ten-minute health check

Set `BACKEND_HEALTH_URL` to the deployed backend's HTTPS `/health/ready` URL, then
run `python scripts/ping_backend.py` on an external, always-on machine. It checks
immediately and every 600 seconds, with a 30-second timeout. Ctrl+C stops it.
`--once` performs one check with exit code 0 for ready or 1 for unavailable, for an
external scheduler. No service URL or credentials are embedded in the script.

This script is not yet scheduled or pointed at a deployed service. It cannot keep
Render awake if its own host sleeps. Render's free tier has a 15-minute idle timeout,
750 shared instance hours/month, ephemeral local files, and a 30-day free Postgres
lifetime. Pings do not remove those limits or guarantee uptime. See
[Render free services](https://render.com/docs/free). The current SQLite-only backend
still needs deployment/database integration before it can safely run there.

```powershell
uv run python -m pytest -q
uv run python -m ruff check src migrations tests
uv run python -m compileall -q src
```

Tests include SQLite migration upgrade/downgrade, scoped session authorization,
clean bootstrap, pagination, explicit nulls, UTC conversion, canonical errors,
readiness, authorization audit and OpenAPI comparison. Regenerate the snapshot only
after reviewing an intended API change:

```powershell
uv run python -c "import json; from pathlib import Path; from ner_lens.app import app; Path('docs/openapi/v1.json').write_text(json.dumps(app.openapi(), indent=2) + '\n', encoding='utf-8')"
```

Frontend checks are `npm test` and `npm run build` (includes strict TypeScript).
Browser checks and the current gaps are recorded in `docs/MILESTONES.md`. PostGIS,
OIDC, operational routing, offline reports, live feeds and release certification
remain outstanding; this checkpoint does not complete the full M1 or M2 gates.
