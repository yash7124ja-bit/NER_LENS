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

## Verified deployment — 14 September 2026

- Frontend: https://ner-lens.ner-lens-web.workers.dev
- Backend: https://ner-lens-api.onrender.com
- Render service: srv-dajrbt2d0e5s73desrp0
- Postgres: dpg-dajqr2fqj5pc73eo3gpg-a (Singapore, PostgreSQL 17)

Render startup passed Alembic migrations, scoped corridor reads and a real PostGIS
geometry round-trip over the internal connection. The configured account signed in
through Cloudflare, loaded all six synthetic segments, restored after reload and
signed out. Cookies are unreadable to JavaScript; browser local/session storage are
empty. Direct API access without the proxy secret is denied. Both public and proxied
readiness return ready.

Bootstrap email/password/display-name/role environment variables were removed after
provisioning. Account hashes, roles and sessions now persist in Postgres. Database
external IP access is disabled. Cloudflare's scheduled handler is configured for
*/10 * * * *; backend readiness was manually verified. This is not an uptime guarantee.

Local checks: 145 backend tests, 4 frontend/Worker tests, Ruff, TypeScript and Vite
build passed. Hosted screenshots are ignored under frontend output/playwright.
The free Postgres database expires on 14 October 2026; pings do not extend its life.
