# Provider integration

The backend loads the repository `.env` using python-dotenv, without interpolation
or overriding injected environment variables. This preserves literal `#` and `$`
inside quoted credentials. `NER_LENS_ENV_FILE` selects another file; an empty value
disables file loading. API, account setup, replay setup and Alembic share this boundary.
The checked-in example contains names only. Empty core settings use local replay defaults.

Provider credentials are never included in frontend builds. Render receives provider
variables separately from its production DATABASE_URL, session policy and proxy secret.
Local database settings must not replace Render's managed Postgres connection.

## Implemented use of populated settings

| Variables | Server operation | Limit |
|---|---|---|
| COPERNICUS_API_URL, COPERNICUS_API_KEY | ERA5-Land catalogue retrieval with PRIVATE-TOKEN header | Metadata access, not a rainfall download or validation of dataset licence acceptance |
| NASA_EARTHDATA_TOKEN | NASA CMR GPM IMERG catalogue search with Bearer authentication | Catalogue records, not raster rainfall values |
| SACHET_RSS_URL | RSS retrieval and publication-time validation | The portal root resolves to NDMA's published RSS endpoint; alerts remain unreviewed |
| GRAPHHOPPER_API_KEY | Routing API using configured longitude/latitude points, converted to provider latitude/longitude query order | Car baseline with unverified vehicle constraints; not a safe-route recommendation |
| MAPPLS_API_KEY | Mappls directions using static-key authentication and GeoJSON geometry | Driving baseline; entitlement or IP restrictions appear as failures |
| IMD_API_STATUS, IMD_API_URL | Permission gate and approved endpoint retrieval | `permission_required` blocks calls; an approved product still needs its specific normalization schema |
| SOURCE_ROUTE_POINTS | JSON array of longitude/latitude pairs | Deployment access check uses endpoints from the existing replay band, not live GPS |
| SOURCE_REFRESH_SECONDS | Retrieval interval, default 3600 seconds | Per process; the current deployment has one API worker |

Each configured routing provider receives one baseline request per refresh cycle.
Change the cadence to respect provider quotas. No routes are requested without points.
On each startup, collection starts in the background and continues at the configured
interval. A provider failure does not fail application liveness or imply no hazard.

## Persistence and inspection

Alembic `0005_source_snapshots` adds protected source snapshots with retrieval timestamp,
HTTP status, SHA-256, parser version, bounded raw response, parsed records and failure reason.
Secrets and authenticated query strings are excluded; credential echoes are rejected.
Only allowlisted HTTPS provider hosts are contacted, non-public DNS results are rejected,
redirects are rejected and responses are bounded to 2 MiB. Unrecognized schemas fail closed.

`GET /health/sources` returns only source names, status, timestamps, record counts and
safe reason codes. Successful checks older than two refresh intervals become stale.
The frontend's External source access card displays this persisted result. Refreshing
the card reads the database and does not trigger paid upstream requests.

Run migrations before an explicit retrieval:

```powershell
uv run python -m alembic upgrade head
uv run python -m ner_lens.sources
uv run python -m ner_lens.sources --source sachet
```

The CLI also accepts `--points` as a JSON coordinate array to override configured
baseline endpoints. It exits nonzero when any requested provider is blocked or failed.
Use `NER_LENS_ENV_FILE=''` when running tests to avoid reading real provider credentials.

## Evidence boundary

Live local checks on 14 September 2026 returned HTTP 200 for Copernicus (1 catalogue
record), NASA (10 catalogue records), SACHET (99 alert entries), GraphHopper (1 route)
and Mappls (1 route). IMD correctly reported permission_required without making a request.
Counts are retrieval results, not seeded or hardcoded UI values.

This closes environment loading and provider access gaps. Raster extraction, spatial
association of alerts, approved IMD normalization, truck constraints, operational review
and risk models are separate work. The six corridor segments remain synthetic replay;
provider availability does not change their unknown operational state. Provider terms
must be recorded before redistributing or treating these records as an approved dataset.

Provider documentation: [CDS API](https://cds.climate.copernicus.eu/how-to-api),
[NASA CMR](https://wiki.earthdata.nasa.gov/spaces/CMR/pages/50037330/CMR+Client+Partner+User+Guide),
[GraphHopper](https://docs.graphhopper.com/),
[Mappls](https://developer.mappls.com/documentation/sdk/rest-apis/mappls-routing-api/readme/),
[NDMA](https://sachet.ndma.gov.in/).
