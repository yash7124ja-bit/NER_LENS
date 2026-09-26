# Protected media lifecycle

`build_router(factory, current_actor, scanner=None)` adds image quarantine to existing reports. Migrations `0008_media` and `0017_media_object_storage` create the metadata and private object reference columns. Local SQLite replay without a scanner leaves valid images **pending**; decoding and metadata removal never imply a clean scan. PostgreSQL/hosted uploads return 503 unless both a trusted scanner and private object store are configured.

## Upload and read contract

`PUT /v1/field-reports/{report_id}/media/{slot}` requires the authenticated report owner with scoped `upload_own_media` permission. Slots are integers 0–3. Required headers are `Idempotency-Key`, `X-Media-SHA256` (64 hexadecimal characters), `Content-Type` and `Content-Length`. Accepted types are `image/jpeg`, `image/png`, and `image/webp`; the decoded type must match. The request is binary, not multipart.

Each image is limited to 8 MiB and 20 million decoded pixels. Animated files are rejected. Streaming byte count is checked against both the declared length and ceiling before decoding; the server recomputes SHA-256. A valid image is re-encoded to a maximum 2048×2048 JPEG containing pixels only, with EXIF/GPS, comments and profiles removed. The original stays private in quarantine.

The response contains `media_object_id`, `field_report_id`, `slot`, `sha256`, `upload_state`, `scan_state`, `scan_reason`, `media_state`, and `request_id`. An identical blob in the same slot replays its original upload receipt. A different digest/type/length in an occupied slot returns 409. Idempotency is scoped to authenticated actor, method, path and key. Reviewers cannot upload into another user's report.

Interrupted, wrong-length, wrong-digest and undecodable attempts preserve an incomplete metadata row without raw/derivative bytes. Retry the same intended digest/type/length/slot after a transient failure. Slot metadata is immutable; correcting an incorrect declared digest requires a different slot or report. No unsuccessful attempt is marked complete.

`GET /v1/field-reports/{report_id}/media` returns current metadata and aggregate state. `report_media_state(session, report_id)` exposes the same `none|incomplete|complete` computation for report listings. Current metadata may change after scanning; the original idempotent upload receipt remains unchanged.

`GET /v1/field-reports/{report_id}/media/{slot}` requires the report owner or a scoped reviewer, and returns only the stripped JPEG derivative after `scan_state=clean`. Pending, error, rejected and incomplete media return 409. Raw bytes have no HTTP retrieval endpoint. Derivatives use `private, no-store` and `nosniff` headers. Reads and upload/scan transitions are audited; scanner worker events have a system/null actor rather than attributing the verdict to the reporter.

## Trusted scanner boundary

A deployment may inject a trusted callable `scanner(raw_bytes) -> 'clean'|'rejected'` into the router. `CLAMD_HOST` and optional `CLAMD_PORT` wire a private-network ClamAV daemon through its INSTREAM protocol; scanner failures return 503 for hosted uploads. Exceptions or unexpected values never become clean. `scan_pending(factory, scanner, storage=..., limit=20)` retries received pending/error objects from a trusted worker. The scanner cannot be selected or supplied through HTTP. Synthetic scanner callbacks exist only inside tests.

A production integration must supply and operate an approved private ClamAV service, including process isolation, limits, monitoring, updates and worker authorization. The API must reach it over a private network; do not expose ClamAV to the Internet. Decoder resource ceilings reduce exposure but this implementation does not claim OS-level sandbox isolation for Pillow.

Local Compose includes the official ClamAV container on the internal network and points `CLAMD_HOST` at it. The container may take time to load signatures; until it is ready, uploads fail closed. Run `uv run python scripts/scanner_trial.py` with `CLAMD_HOST=127.0.0.1` only when testing a loopback-published local daemon. The trial checks a clean JPEG and the standard EICAR test string against the real daemon; a CI mock verdict is not equivalent. Compose does not publish port 3310 or provision the hosted Render scanner.

## Storage and operating limits

Hosted configuration uses `MEDIA_S3_ENDPOINT`, `MEDIA_S3_BUCKET`, `MEDIA_S3_REGION`, `MEDIA_S3_ACCESS_KEY`, and `MEDIA_S3_SECRET_KEY`. The bucket must be private, have default encryption and a retention/deletion policy, and allow the backend only `PutObject`/`GetObject`/`DeleteObject` on its media prefix. No public ACL or signed browser URL is issued. Each attempt uses an opaque random object key; the database keeps hashes, state and key, not bytes. Partial writes get best-effort deletion. A crash or ambiguous database commit can still leave a private orphan, so bucket lifecycle cleanup and object-reference reconciliation must be verified before production use. Reads verify the derivative hash before serving. S3-compatible providers differ in encryption headers: configure encryption on the bucket rather than sending AWS-only SSE headers; Cloudflare R2 [encrypts objects at rest by default](https://developers.cloudflare.com/r2/reference/data-security/). If scanner or object storage fails, the hosted upload/read fails closed. Existing SQLite replay can still keep raw and derivative in private database columns for tests.

Four 8 MiB slots cap raw media at 32 MiB per report; total deployment quota is not enforced here. Add per-account quotas and an approved retention/deletion policy before collecting field data at scale. Precise EXIF may remain in the protected original until retention deletes it; the derivative contains no EXIF. Migration downgrade refuses to drop storage keys while any hosted object references remain, preventing silent data loss. Hosted clearance still requires a live ClamAV trial and verification of bucket privacy, encryption, lifecycle, and backup/recovery.

No external image URL, public object ACL, malware-clean claim, production retention guarantee, or real report photograph is fabricated by this implementation.

## Runnable checks

Set `NER_LENS_ENV_FILE` to an empty string and run `uv run pytest tests/test_media.py`. The tests verify pending fail-closed retrieval, replay/conflicts, EXIF/GPS removal, scoped access, invalid uploads, scanner verdicts, ClamAV framing, private object keys, and derivative integrity. `uv run ruff check src/ner_lens/media.py migrations/versions/0017_media_object_storage.py tests/test_media.py` checks the implementation. A real ClamAV and bucket availability trial is still required before hosted clearance is claimed.
