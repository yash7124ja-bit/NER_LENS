# Weaviate story search

`WEAVIATE_REST_ENDPOINT` and `WEAVIATE_API` are loaded from backend `.env` locally and Render environment variables in deployment. An endpoint without a scheme is normalized to HTTPS. `WEAVIATE_STORY_COLLECTION` optionally overrides the default `NERLensUserStory` collection. The supplied gRPC endpoint is not needed by this REST/GraphQL integration.

Only SIH user-story content is indexed: ID, role, title, story, acceptance criteria, status and verification notes. Accounts, credentials, reports, photos and GPS observations are not sent. Deterministic object UUIDs make reindexing safe to retry without duplicate objects. PostgreSQL remains authoritative: search returns IDs that are resolved back to current application records.

The index uses BM25 keyword search with no generated embeddings. It does not claim semantic matching, RAG, risk prediction or an LLM decision. Gemini is not used by this feature.

Super Admin can reindex via the user-story panel or `POST /v1/admin/user-stories/reindex?corridor_id=...`. Readers can use `GET /v1/user-stories/search?corridor_id=...&q=...`. The API checks corridor scope before searching. Partial indexing, malformed configuration and upstream failures return explicit failure rather than pretending search succeeded.

Verified against the configured cluster: 12 stories indexed; query `medicine delivery` returns SIH-06 and SIH-05. Mock-transport tests cover retry IDs, query escaping, partial failure and configuration validation.
