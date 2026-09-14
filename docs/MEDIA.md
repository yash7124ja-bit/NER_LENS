# Protected media lifecycle

`build_router(factory, current_actor, scanner=None)` adds image quarantine to existing reports. Migration `0008_media` follows `0007_route_comparisons`; import media models in Alembic metadata. Default configuration deliberately leaves every valid image **pending** because no trusted malware scanner is configured. Decoding and metadata removal do not imply a clean scan.

## Upload and read contract

`PUT /v1/field-reports/{report_id}/media/{slot}` requires the authenticated report owner with scoped `upload_own_media` permission. Slots are integers 0–3. Required headers are `Idempotency-Key`, `X-Media-SHA256` (64 hexadecimal characters), `Content-Type` and `Content-Length`. Accepted types are `image/jpeg`, `image/png`, and `image/webp`; the decoded type must match. The request is binary, not multipart.

Each image is limited to 8 MiB and 20 million decoded pixels. Animated files are rejected. Streaming byte count is checked against both the declared length and ceiling before decoding; the server recomputes SHA-256. A valid image is re-encoded to a maximum 2048×2048 JPEG containing pixels only, with EXIF/GPS, comments and profiles removed. The original stays private in quarantine.

The response contains `media_object_id`, `field_report_id`, `slot`, `sha256`, `upload_state`, `scan_state`, `scan_reason`, `media_state`, and `request_id`. An identical blob in the same slot replays its original upload receipt. A different digest/type/length in an occupied slot returns 409. Idempotency is scoped to authenticated actor, method, path and key. Reviewers cannot upload into another user's report.

Interrupted, wrong-length, wrong-digest and undecodable attempts preserve an incomplete metadata row without raw/derivative bytes. Retry the same intended digest/type/length/slot after a transient failure. Slot metadata is immutable; correcting an incorrect declared digest requires a different slot or report. No unsuccessful attempt is marked complete.

`GET /v1/field-reports/{report_id}/media` returns current metadata and aggregate state. `report_media_state(session, report_id)` exposes the same `none|incomplete|complete` computation for report listings. Current metadata may change after scanning; the original idempotent upload receipt remains unchanged.

`GET /v1/field-reports/{report_id}/media/{slot}` requires the report owner or a scoped reviewer, and returns only the stripped JPEG derivative after `scan_state=clean`. Pending, error, rejected and incomplete media return 409. Raw bytes have no HTTP retrieval endpoint. Derivatives use `private, no-store` and `nosniff` headers. Reads and upload/scan transitions are audited; scanner worker events have a system/null actor rather than attributing the verdict to the reporter.

## Trusted scanner boundary

A deployment may inject a trusted callable `scanner(raw_bytes) -> 'clean'|'rejected'` into the router. Exceptions or unexpected values become `error`, never clean. `scan_pending(factory, scanner, limit=20)` retries received pending/error objects from a trusted worker. The scanner cannot be selected or supplied through HTTP. There is no shipped mock or decoder-based production clean verdict. Synthetic scanner callbacks exist only inside tests.

A production integration must supply and operate its approved scanner, including process isolation, limits, monitoring, updates and authorization for the worker. Pending objects remain unavailable until that integration is real. Decoder resource ceilings reduce exposure but this implementation does not claim OS-level sandbox isolation for Pillow.

## Storage and operating limits

Raw and derivative bytes use private database columns so uploads do not depend on ephemeral application disks. Four 8 MiB slots cap raw storage at 32 MiB per report; total deployment quota is not enforced here. This is suitable for a bounded pilot only. Add per-account quotas and an approved retention/deletion policy before collecting field data at scale. Move bytes to an encrypted quarantine/object store when database capacity or backup cost warrants it, retaining the same digest and scan-state contract. Precise EXIF may remain in the inaccessible original until retention deletes it; the derivative contains no EXIF.

No external image URL, public object ACL, malware-clean claim, production retention guarantee, or real report photograph is fabricated by this implementation.

## Runnable checks

Set `NER_LENS_ENV_FILE` to an empty string and run `uv run pytest tests/test_media.py`. Four tests migrate a disposable database up/down and verify pending fail-closed retrieval, identical replay/conflicts, EXIF/GPS removal, owner/reviewer and cross-jurisdiction access, length limits, partial retry, invalid SVG/image/type/digest, and scanner rejected/error behavior. `uv run ruff check src/ner_lens/media.py migrations/versions/0008_media.py tests/test_media.py` checks the implementation.
