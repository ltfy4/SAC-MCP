# SAC API field notes

Hard-won knowledge about the SAP Analytics Cloud public API. Read this once before adding a new SAC surface — it will save you hours.

## Authentication

### 2-legged OAuth (client_credentials) — what the project supports

1. In SAC: *System → Administration → App Integration* → "Add a New OAuth Client".
2. Choose **Authorization Code (Default)** for 3-legged or **Client Credentials** for 2-legged. We use 2-legged.
3. SAC gives you a **client ID**, **secret**, **token URL** (the `*.authentication.*.hana.ondemand.com` URL — that's `SAC_AUTH_URL`) and an **API URL** (the `*.cloud.sap` URL — that's `SAC_TENANT_URL`).
4. Roles assigned to the OAuth client determine what tools succeed. A "Data Analyst" role is too narrow for SCIM and audit; a tenant admin works for everything but is overkill for production.

### The `x-sap-sac-custom-auth: true` header

Set on every request (handled in `client/http.py`'s `_DEFAULT_HEADERS`). It tells SAC to skip session-cookie negotiation. Without it:

- The first response sets a cookie that subsequent requests must echo.
- Most third-party HTTP clients drop cookies between requests, leading to 403 / "missing CSRF" errors.
- See SAP KBA **3387282** (CSRF token issues from `/api/v1/csrf`) and **3566761** (Data Import 403 with non-Postman clients).

**Do not remove this header.**

### CSRF tokens

- Required for **any** non-GET (POST / PUT / PATCH / DELETE).
- Acquire by sending `GET /api/v1/csrf` with header `x-csrf-token: fetch`. The response *headers* include `x-csrf-token: <value>`. The body is irrelevant.
- Reuse for the lifetime of the OAuth token; SAC rotates ~every 30 minutes.
- On 403 with response header `x-csrf-token: required`, refetch and retry. Our client does this automatically.

## Endpoints by surface

### Stories
- `GET /api/v1/stories` → list. Add `?include=models` to embed referenced models.
- `GET /api/v1/stories/{id}` → single story.

### File repository / Resources (OData)
- `GET /api/v1/filerepository/Resources` → list anything in the repo.
- Filter with OData `$filter` on:
  - `resourceType` ∈ {FOLDER, STORY, MODEL, APPLICATION, DATASET, BOOKLET, FILE, OTHER}
  - `resourceSubtype` (e.g. `INSIGHT` for insights)
  - `parentId` for tree traversal
- `$metadata` describes the entity for self-discovery.

### Data Export Service (OData v4)
The big one. Two namespaces:

- **Administration** — model catalogue:
  - `GET /api/v1/dataexport/administration/Namespaces('sac')/Providers` → list of all models (a.k.a. providers).
- **Provider** — per-model data:
  - `/api/v1/dataexport/providers/sac/{model_id}/$metadata` → model schema.
  - `/api/v1/dataexport/providers/sac/{model_id}/Data` → fact data.
  - `/api/v1/dataexport/providers/sac/{model_id}/MasterData` → master / dimension members.
  - `/api/v1/dataexport/providers/sac/{model_id}/AuditData` → audit entries for that model's data.
  - `/api/v1/dataexport/providers/sac/{model_id}/{Dimension}MasterData` → dimension-specific master.

Standard OData params supported: `$filter`, `$select`, `$top`, `$skip`, `$orderby`, `$expand`, `$count`.

Delta extracts (since Q4 2022): pass `$deltatoken=<token>` from a previous response.

### Data Import Service
Job-based; **the only place CSRF really matters in practice**.

| Step | Method | Path |
|---|---|---|
| 1. Create job | POST | `/api/v1/dataimport/models/{model}/factData` (or `/masterData`) |
| 2. Upload chunk | POST | `/api/v1/dataimport/jobs/{jobId}/data` |
| 3. Validate | POST | `/api/v1/dataimport/jobs/{jobId}/validate` |
| 4. Run | POST | `/api/v1/dataimport/jobs/{jobId}/run` |
| 5. Status | GET  | `/api/v1/dataimport/jobs/{jobId}/status` |
| 6. Cancel | DELETE | `/api/v1/dataimport/jobs/{jobId}` |

Supporting endpoints:

- `GET /api/v1/dataimport/models/{model}/metadata` → the columns an import payload must provide (dimensions, measures, types). Fetch this before building rows.
- `GET /api/v1/dataimport/jobs` → recent jobs across all models.
- `GET /api/v1/dataimport/jobs/{jobId}/invalidRows` → rows rejected by validation, with per-row reasons. Response key varies by release (`invalidRows` / `failedRows` / `value`) — probe all three.

Validation responses also vary: failed-row counts appear under `failedNumberRows`, `failedRows` or `invalidRowCount` depending on release.

Body shapes vary by SAC release; we keep types loose (`dict[str, Any]`).

### SCIM users / groups
- `/api/v1/scim/Users` and `/api/v1/scim/Groups` follow the SCIM 2.0 RFCs (7643, 7644).
- Filter syntax is SCIM, **not** OData: `userName eq "alice@example.com"`, `active eq true`.
- Patch operations use the `urn:ietf:params:scim:api:messages:2.0:PatchOp` schema.
- Pagination: `startIndex` (1-based) + `count`.

### Content Network
- Packages: `GET /api/v1/contentnetwork/packages?visibility=private|public`.
- Imports / exports are async jobs:
  - `POST /api/v1/contentnetwork/imports` → returns job ID.
  - `POST /api/v1/contentnetwork/exports` → returns job ID.
  - `GET /api/v1/contentnetwork/jobs/{id}` → status.

### Calendar tasks
- `GET /api/v1/calendar/tasks` with `$filter` on `AssigneeId`, `Status`.
- `PATCH /api/v1/calendar/tasks/{id}` to update status.
- Task statuses: Open, InProgress, Completed, Cancelled.

### Multi-Action
- `GET /api/v1/multiaction/multiactions` → defined Multi-Actions.
- `POST /api/v1/multiaction/multiactions/{id}/runs` → trigger a run.
- `GET /api/v1/multiaction/runs/{runId}` → status.

### Data Actions
Planning-model automation (copy / cross-model copy / allocation /
advanced-formula steps). Not the same thing as Multi-Actions — a Multi-Action
*orchestrates* data actions plus publish and import steps.

- `GET /api/v1/dataactions` → list; filter with `modelId=<id>`.
- `GET /api/v1/dataactions/{id}` → detail, including parameter definitions.
- `POST /api/v1/dataactions/{id}/executions` → trigger; body `{"parameterValues": [{"parameterId": ..., "value": ...}]}`. Returns an `executionId`.
- `GET /api/v1/dataactions/{id}/executions` → recent runs.
- `GET /api/v1/dataactions/executions/{executionId}` → status; poll until terminal (`COMPLETED` / `FAILED`).

Executions are asynchronous and can take minutes on large models. Requires the
OAuth client to have a role with planning rights on the target model —
otherwise `403` without a CSRF hint.

### Audit
- `GET /api/v1/auditing/AuditLog` (OData).
- Common columns: `Action`, `UserName`, `Timestamp`, `EntityType`, `EntityId`.

## Pagination

Two flavours:
- **OData** — `@odata.nextLink` field at the response root, absolute URL. Don't pass extra params; the URL has them.
- **Public REST** — `next` or `nextLink` field, sometimes relative.

`SACClient.paginate` handles both.

## Rate limits

SAC doesn't publish hard numbers, but in practice:
- Tenant-wide quotas exist on Data Export (a few hundred RPS).
- Data Import is much stricter — chunks of 50 k rows are the practical sweet spot.
- 429 responses include `Retry-After` (seconds).
- Tenacity backoff respects this; our local `TokenBucket(rate=SAC_MAX_RPS)` adds a second guard.

## Common errors

| Symptom | Likely cause |
|---|---|
| `401 invalid_client` on token fetch | `SAC_CLIENT_ID` / `SAC_CLIENT_SECRET` mismatch, or wrong `SAC_AUTH_URL` |
| `401` on data calls but token endpoint works | Scope missing — check that the OAuth client has the API role |
| `403 csrf required` on POST | `x-csrf-token` not sent, or stale; our client re-fetches |
| `403 forbidden` on PATCH/POST without CSRF hint | OAuth client lacks the SAC role for that operation |
| `404` on `/dataexport/providers/sac/{model}/...` | Wrong model ID, or the OAuth client doesn't have access to that model |
| Empty body on writes | Normal for SAC — many writes return 200 with no body |
| `set-cookie` header missing on `/api/v1/csrf` | Means `x-sap-sac-custom-auth: true` is **not** being sent — fix that |

## Region / data centre awareness

SAC URLs encode the region: `eu10`, `us10`, `ap10`, etc. Both `SAC_TENANT_URL` and `SAC_AUTH_URL` must match the same region. Mixing regions yields 401s with vague "tenant not found" messages.
