# SAC API field notes

What SAP Analytics Cloud's public API actually does, as used by this server.
**Verified** means checked against a live tenant (September 2026);
**docs** means taken from SAP's API documentation and not yet exercised live.
Update this file whenever a live check changes an entry.

## Authentication

- 2-legged OAuth (`client_credentials`). In SAC: *System > Administration >
  App Integration* > add an OAuth client with **Client Credentials**. SAC shows
  the token URL (`*.authentication.<region>.hana.ondemand.com`, `SAC_AUTH_URL`)
  and the API URL (`*.<region>.hcs.cloud.sap`, `SAC_TENANT_URL`). Both must be in
  the same region.
- Each OAuth client is granted access per API. Without it SAC answers
  **error 3401** "OAuth Client is not allowed to interact with API" (verified
  for the Data Import API).
- `x-sap-sac-custom-auth: true` on every request makes SAC stateless (no
  session cookie), avoiding KBA 3387282 / 3566761. **Do not remove it.**
- CSRF: every non-GET needs `x-csrf-token`, fetched with `GET /api/v1/csrf` and
  header `x-csrf-token: fetch`; refetch on 403 with `x-csrf-token: required`.
- `/api/v1/scim/Me` is not available to client-credentials clients (verified).
  `whoami` decodes the token's claims instead.

## Encoding rules

- **Path segments:** percent-encode every ID (`seg()` in `client/paths.py`).
  httpx resolves `..`, so an unencoded ID can reach a different endpoint.
- **Query strings:** spaces must be `%20`. The file repository rejects the
  form-style `+` with a bare 400 (verified). Keep `$` literal in parameter names.

## Data Export Service (OData v4) -- verified

| Resource | Path | Notes |
|---|---|---|
| Model list | `/api/v1/dataexport/administration/Namespaces('sac')/Providers` | Fields `ProviderID`, `ProviderName`, `Description`, `ServiceURL`. **Ignores `$top`** (returns all). Filter on `ProviderName`; there is no `Name`. |
| Service document | `/api/v1/dataexport/providers/sac/{model}/` | Lists the model's entity sets. |
| Schema | `.../{model}/$metadata` | **EDMX XML regardless of `Accept`.** `FactData` key properties = dimensions, other properties = measures. |
| Fact rows | `.../{model}/FactData` | `$select` must include every key column (**1402**). `Data` does not exist (**3707**). |
| Aggregates | `.../{model}/FactDataAggregation` | `$select=<dims>,<measures>` returns measures aggregated over the omitted dimensions. `$filter`, `$orderby` (measures too) and `$top` work. **`$apply` is silently ignored and leaf rows come back.** |
| Dimension members | `.../{model}/<Dimension>Master` | `ID`, `Description`, attributes. `<Dimension>MasterData` does not exist. |
| Hierarchies | `.../{model}/<Dimension>MasterWithHierarchy` | Only for dimensions with hierarchies. |
| Enriched facts | `.../{model}/MasterData` | Fact rows plus `<Dimension>___<Attribute>` columns. |
| Data audit | `.../{model}/AuditData` | **3905** unless data audit is enabled on the model. |

Delta (change tracking): read with `Prefer: odata.track-changes`. The response
ends with `@odata.deltaLink` = `.../FactData?deltaid=<uuid>`; request it with
`deltaid=<uuid>` to get only changes and a new link. SAC **ignores
`$deltatoken`** and then returns the whole model.

Responses carry `@des.*` annotations (processing time, cell counts).

## File repository -- verified

`GET /api/v1/filerepository/Resources` supports `$filter`, `$top`, `$skip`,
`$select`, `$orderby`. Filterable: `resourceType`, `name`, `createdBy`,
`modifiedBy`, `createdTime`, `modifiedTime`, `folderType`. `resourceType` values:
`STORY`, `APPLICATION`, `DATAACTION`, `PLANNINGSEQUENCE` (Multi-Actions),
`MULTIACCOUNT`, `DIMENSION`, `ANALYTIC_MODEL`. `applyManagePrivilege=true`
includes every user's private content (needs the Manage permission).

`/api/v1/stories` ignores `$top`/`$filter` and returns every story on the
tenant, so list and search go through the repository.
`/api/v1/stories/{id}?include=models` works for single stories.

## Data Import Service -- docs (test client lacked access: 3401)

| Step | Method | Path | Body |
|---|---|---|---|
| Create job | POST | `/api/v1/dataimport/models/{model}/{importType}` | `{Mapping?, DefaultValues?, JobSettings: {importMethod, executeWithFailedRows}}` |
| Upload chunk | POST | `/api/v1/dataimport/jobs/{jobId}` | `{Data: [...], DeletedData?: [...]}` |
| Validate | POST | `/api/v1/dataimport/jobs/{jobId}/validate` | -- |
| Run | POST | `/api/v1/dataimport/jobs/{jobId}/run` | optional `{overrideExecuteWithFailedRows}` |
| Status | GET | `/api/v1/dataimport/jobs/{jobId}/status` | -- |
| Invalid rows | GET | `/api/v1/dataimport/jobs/{jobId}/invalidRows` | -- |
| Delete | DELETE | `/api/v1/dataimport/jobs/{jobId}` | -- |
| List jobs | GET | `/api/v1/dataimport/jobs` | -- (there is no per-model list: **1305**) |
| Column metadata | GET | `/api/v1/dataimport/models/{model}/metadata` | -- |

- `importType`: `factData`, `masterData`, `masterFactData`, `privateFactData`.
- `importMethod`: `Update`, `Append`, `CleanAndReplace`, `DeleteAndUpsert`,
  `DropAndInsert`.
- The same job flow serves `/dataimport/currencyConversions/{id}`,
  `/dataimport/unitConversions/{id}` and
  `/dataimport/publicDimensions/{id}/publicDimensionData`. Each has
  `GET .../{id}` and `.../{id}/metadata`.
- Stored rates cannot be read back through the public API.
- Practical chunk size: ~50k rows.

## Planning

- Multi-Actions: no list endpoint (`GET /api/v1/multiActions` is 404). List
  them from the repository as `PLANNINGSEQUENCE` (verified). Run with
  `POST /api/v1/multiActions/{id}/executions` `{"parameterValues": [...]}`
  and poll `GET .../executions/{executionId}` (docs). IDs look like
  `t.TEST:CEEF...`.
- Data Actions: `/api/v1/dataactions` does not exist (404, verified). List
  them from the repository as `DATAACTION` and run them as a Multi-Action step.

## Other surfaces

| Surface | Path | Status |
|---|---|---|
| Calendar | `GET/PATCH /api/v1/calendar/events/{id}`, `POST /api/v1/calendar/events` | `GET /calendar/events` is **405**: no list API (verified) |
| Content transport | `POST /api/v1/content/jobs`, `GET /api/v1/content/jobs/{id}` | docs; `/api/v1/contentnetwork/*` is 404 (verified) |
| Activity log | `GET /api/v1/audit/activities/exportActivities` | exists, **406** on `Accept: application/json` (verified); read by content type. `/api/v1/auditing/AuditLog` is 404 |
| Monitoring | `GET /api/v1/monitoring/{modelId}` | exists, **406** on JSON-only `Accept` (verified) |
| Widget query | `GET /api/v1/widgetquery/getWidgetData?storyId=&widgetId=&type=kpiTile` | docs |
| SCIM | `/api/v1/scim/Users`, `/api/v1/scim/Groups` | Groups verified. SCIM filter syntax (`userName eq "a@b.c"`), paging via `startIndex` + `count` |

## Error numbers

SAC puts a stable number in the message ("... [3707]"); the OData `code` is a
per-request correlation ID. The server reports the number as `SAC-<n>`.

| Number | Meaning | Fix |
|---|---|---|
| 3707 | Entity set does not exist | Check `get_model_metadata` for the model's sets |
| 1402 | Key column(s) not selected | Select all dimensions, or use `FactDataAggregation` |
| 3401 | OAuth client not allowed to use this API | Grant API access in App Integration |
| 3905 | Audit data not enabled | Enable data audit in the model preferences |
| 1305 | Endpoint not valid | Wrong path, not a wrong ID |
| HTTP 405 | Operation not supported on this endpoint | e.g. no list API |
| HTTP 406 | Response format not acceptable | Send a broader `Accept` |

## Rate limits and regions

- No published hard limits. Data Export tolerates a few hundred RPS
  tenant-wide; Data Import is much stricter.
- 429 responses include `Retry-After`, which the client honours. The local
  `SAC_MAX_RPS` bucket is a second guard.
- URLs encode the region (`eu10`, `us10`, `ap12`, ...). Tenant and auth URL
  must match, or token calls fail with vague "tenant not found" errors.
