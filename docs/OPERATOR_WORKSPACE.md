# SIH operator workspace — current delivery

- Reference: `D:/SIH-2026/logistics-network-control.html`.
- Operations desk: evidence inbox/review, expiring road decisions, baseline route comparison, medicine missions and explicit one-time GPS capture for assigned reporters.
- Published authority decisions now update corridor state; risk remains separate and unapproved.
- MapLibre 6 worker bundled explicitly with Vite. Online basemap uses server `MAP_STYLE_URL`; attribution remains visible. The corridor overlay is still synthetic, not navigable road geometry.
- Super Admin maps to the persisted `system_admin` role. It can create and assign scoped user roles. Status authority is a separate database grant requiring `district_officer`. Own admin removal is rejected.
- To promote an existing account once, set `NER_LENS_SUPERADMIN_EMAIL` during deployment and remove it after the grant is confirmed. No passwords are stored in the UI.
- Twelve user stories are ingested from `data/user_stories.json` into `user_story` by Alembic-backed deployment initialization. Existing records are preserved. Explicit admin API import can update them.
- Weaviate is not configured; application records remain in PostgreSQL. No vector search claim is made.

Verification: 199 backend tests, 9 frontend tests, production build. Browser trials on a disposable database: report capture/sync/review, accepted-evidence closure, mission create/start/complete, administrator account creation. Map worker and all six rendered corridor features observed with loaded basemap; mobile viewport checked for overflow.

Still pending: real surveyed corridor/routing legality and approved policy, production malware scanning and media UI, offline tile package/full field-device trial, real backup restore drill, native Assamese review, verified dataset/model evaluation and field partner approval. These are not marked complete by this release.
