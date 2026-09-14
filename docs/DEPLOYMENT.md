# Hosted replay deployment

The owner authorized GitHub publication and Cloudflare/Render deployment on
14 September 2026. Hosting remains a replay demonstration, with unknown operational
status and explicit synthetic geometry. It does not close the live-data or field gates.

## Backend

`render.yaml` describes the free Singapore API and Postgres deployment. The new
Render account must first have GitHub permission to clone the private repository.
The existing database is `ner-lens-db`; do not create a duplicate when resuming.

Build: `pip install uv && uv sync --frozen --no-dev`.
Start: `uv run --no-sync python -m ner_lens.deploy`.

Startup runs the unchanged Alembic migration chain, imports the synthetic fixture,
checks scoped corridor/geometry reads and provisions the configured account.
`NER_LENS_BOOTSTRAP_ROLES` is explicit; bootstrap scope comprises active imported
replay corridors. Remove bootstrap account secrets after initial provisioning;
future startups preserve the database account. PostgreSQL uses psycopg, PostGIS
conversion expressions and transaction advisory locking for login throttling.

Set DATABASE_URL from Render's internal connection string, SESSION_COOKIE_SECURE=true,
PROXY_SECRET to a generated shared secret, and AUTH_ALLOWED_ORIGINS to the exact
Cloudflare frontend origin. RENDER_EXTERNAL_HOSTNAME is automatically allowed.
No account credentials, connection strings or proxy secrets belong in Git.

## Frontend

The frontend repository contains a Cloudflare Worker with Vite static assets.
`npm run deploy` publishes it after the account's email is verified. Set worker
secrets BACKEND_ORIGIN (the Render HTTPS origin) and PROXY_SECRET (the same secret
as the backend). Browser requests stay same-origin; the Worker forwards cookies
and the original Origin, overwrites proxy/client identity headers and forbids caching.
Direct backend `/v1/` requests require the proxy secret as well as normal user auth.

Wrangler config includes a ten-minute scheduled health check. The check runs on
Cloudflare, outside the sleeping backend. It rejects non-ready/HTML responses.
It cannot prevent free-tier quota suspension, maintenance or database expiration.
The standalone Python script remains available for an external host.

## Verification and current blockers

Local validation passed: 60 API/identity/foundation tests, 4 frontend/Worker tests,
Ruff, TypeScript and Vite build. A real PostgreSQL round-trip has not yet passed:
external TLS access failed, so startup must verify it on Render's internal network.
Render creation was rejected because the private repository is not connected.
Cloudflare publication was rejected with error 10034 (email verification required).
Neither application is publicly live yet.

The created free database expires on 14 October 2026. Pings do not extend its life.
After the account steps, deploy and verify ready/login/reload/corridor/logout through
Cloudflare, then replace this blocker record with verified URLs and results.
