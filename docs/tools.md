# SAC-MCP Tool Catalogue

Every tool is exposed via FastMCP with a `readOnlyHint` or `destructiveHint`
annotation so MCP clients can decide whether to confirm the call. All tools
return either a `page_envelope` shape `{ "rows": [...], "row_count": N, ... }`
or a single object dict. Errors are surfaced as `{ "error": ..., "code": ..., "status": ... }`.

## Admin

| Tool | Hint | Purpose |
|------|------|---------|
| `whoami` | read | Return identity information for the bound OAuth client. |
| `tenant_info` | read | Tenant URL, region, datacenter metadata. |
| `health_check` | read | Cheap GET against `/api/v1/csrf` to confirm reachability. |

## Audit

| Tool | Hint | Purpose |
|------|------|---------|
| `query_audit_log` | read | Raw OData passthrough against `/api/v1/auditing/AuditLog`. |
| `recent_changes_for_user` | read | Audit-log entries for a user since an ISO timestamp. |

## Calendar

| Tool | Hint | Purpose |
|------|------|---------|
| `list_calendar_tasks` | read | List tasks visible to the OAuth client. |
| `update_task_status` | destructive | Mutate a task's status. |

## Content Network

| Tool | Hint | Purpose |
|------|------|---------|
| `list_packages` | read | List available content-network packages. |
| `create_cn_import_job` | destructive | Start a content-network import. |
| `create_cn_export_job` | destructive | Start a content-network export. |
| `get_cn_job_status` | read | Poll a content-network job. |

## Data Export (per-model OData v4)

| Tool | Hint | Purpose |
|------|------|---------|
| `read_fact_data` | read | Fact data via `$filter` / `$select` / `$orderby` / `$top`. |
| `read_fact_data_delta` | read | Continue a previously initialised delta read. |
| `export_fact_data_csv` | read | Same as `read_fact_data` but returns CSV. |
| `read_master_data` | read | Master/dimension members for a model. |
| `list_dimension_members` | read | Convenience wrapper around `read_master_data`. |
| `read_audit_data` | read | Per-model audit-log entries. |

## Data Import (write-back lifecycle)

| Tool | Hint | Purpose |
|------|------|---------|
| `create_import_job` | destructive | Create a fact / master data import job. |
| `upload_job_data` | destructive | Append a chunk of rows or CSV to a job. |
| `validate_job` | destructive | Validate a job (no write to model). |
| `run_job` | destructive | Execute a validated job (mutates the model). |
| `get_job_status` | read | Poll the job state. |
| `cancel_job` | destructive | Cancel an in-progress job. |
| `list_recent_jobs` | read | Recent jobs for a model. |
| `list_all_import_jobs` | read | Recent jobs across every model on the tenant. |
| `get_import_metadata` | read | Column metadata an import payload must provide. |
| `get_job_invalid_rows` | read | Rows rejected by validation, with reasons. |
| `write_fact_data` | destructive | One-shot lifecycle: create → upload (chunked) → validate → run. Stops before `run` if validation rejects rows. |

## Data Actions

Planning-model automation (copy, cross-model copy, allocation,
advanced-formula steps). Distinct from Multi-Actions, which orchestrate
several data actions plus publish/import steps. Executions are asynchronous —
poll with `get_data_action_status`.

| Tool | Hint | Purpose |
|------|------|---------|
| `list_data_actions` | read | List Data Actions (optionally filtered by model). |
| `get_data_action` | read | Detail for one Data Action, including parameter definitions. |
| `run_data_action` | destructive | Trigger an execution; returns an `executionId`. |
| `list_data_action_executions` | read | Recent executions of one Data Action. |
| `get_data_action_status` | read | Poll one execution until terminal. |

## Models

| Tool | Hint | Purpose |
|------|------|---------|
| `list_models` | read | List models visible to the OAuth client. |
| `get_model_metadata` | read | Full metadata document for a model. |
| `list_dimensions` | read | Enumerate dimensions of a model. |
| `list_measures` | read | Enumerate measures of a model. |

## Multi-Action

| Tool | Hint | Purpose |
|------|------|---------|
| `list_multi_actions` | read | List defined multi-actions. |
| `run_multi_action` | destructive | Trigger a multi-action run. |

## Resources (file repository)

| Tool | Hint | Purpose |
|------|------|---------|
| `list_resources` | read | Enumerate `/filerepository/Resources`. |
| `get_resource` | read | Fetch a single resource by ID. |

## Stories

| Tool | Hint | Purpose |
|------|------|---------|
| `list_stories` | read | Stories visible to the OAuth client. |
| `get_story` | read | Single story by ID, including referenced models. |
| `search_stories` | read | Substring match across name/description. |
| `list_story_models` | read | Models referenced by a story. |

## Teams (SCIM Groups)

| Tool | Hint | Purpose |
|------|------|---------|
| `list_teams` | read | List SCIM groups. |
| `add_member` | destructive | Add a user to a team. |
| `remove_member` | destructive | Remove a user from a team. |

## Users (SCIM Users)

| Tool | Hint | Purpose |
|------|------|---------|
| `list_users` | read | List SCIM users. |
| `create_user` | destructive | Create a new SCIM user. |
| `deactivate_user` | destructive | Deactivate a SCIM user. |

## Public Dimensions

Tenant-wide shared dimensions (cost centres, products, organisational
hierarchies). Live under `/api/v1/dataexport/providers/sac_public_dimensions`.

| Tool | Hint | Purpose |
|------|------|---------|
| `list_public_dimensions` | read | List all public dimensions on the tenant. |
| `read_public_dimension_master_data` | read | Members of one public dimension (`$filter`/`$select`/`$orderby`/`$top`/`$skip`). |
| `read_public_dimension_hierarchies` | read | Members plus hierarchy node references. |

## Currency & Unit Conversion

Tenant-level currency and unit-of-measure conversion tables, plus per-model
currency data.

| Tool | Hint | Purpose |
|------|------|---------|
| `list_currency_tables` | read | List currency conversion tables. |
| `get_currency_table` | read | Get one currency table's metadata. |
| `get_currency_rates` | read | List exchange rates in a table. |
| `upload_currency_rates` | destructive | Upload exchange rates (sourceCurrency / targetCurrency / rateType / validFrom / rate). |
| `list_unit_tables` | read | List unit-of-measure conversion tables. |
| `get_unit_table` | read | Get one unit table's metadata. |
| `get_unit_rates` | read | List unit conversion factors. |
| `upload_unit_rates` | destructive | Upload unit conversion factors. |
| `read_currency_data` | read | Read the per-model `CurrencyData` OData entity. |

## Difference / Delta Tracking

Use SAC's OData v4 delta extension (`Prefer: odata.track-changes` plus
`$deltatoken`) to fetch only the rows that changed since a baseline call.

| Tool | Hint | Purpose |
|------|------|---------|
| `init_delta_tracking` | read | Establish a baseline read; returns rows + a `delta_token`. |
| `get_delta_changes` | read | Fetch only the rows changed since the previous `delta_token`. |

## Widget Query

Programmatic access to widget data inside SAC stories. Currently only
`kpiTile` widget types are returned by the public Widget Query API.

| Tool | Hint | Purpose |
|------|------|---------|
| `get_widget_data` | read | Fetch the rendered values from a story widget (kpiTile only). |
| `list_story_widgets` | read | Best-effort list of widget descriptors embedded in a story. |

## Aggregation (server-side)

Server-side GROUP BY + measure aggregation via the OData v4 `$apply` operator.
Requests hit `/api/v1/dataexport/providers/sac/{model_id}/Aggregation` and
return already-aggregated rows — no client-side aggregation needed.

| Tool | Hint | Parameters | Purpose |
|------|------|-----------|---------|
| `read_aggregated_data` | read | `model_id`, `group_by`, `aggregates`, `filter?`, `orderby?`, `top=200` | Generic GROUP BY + aggregate. `aggregates` is a list of `{column, op, alias}` dicts; `op` is one of `sum`, `average`, `min`, `max`, `countdistinct`, `count`. |
| `top_n_by_measure` | read | `model_id`, `dimension`, `measure`, `agg="sum"`, `direction="desc"`, `top=10`, `filter?` | Convenience: top or bottom N members of a dimension ranked by one aggregated measure. |
| `aggregate_by_dimension` | read | `model_id`, `dimension`, `measures`, `agg="sum"`, `filter?`, `top=200` | One dimension, multiple measures — returns a summary table. |

## Monitoring

Answers "is my data fresh", "when did this model last load", "how big is this model".
Endpoint family: `/api/v1/monitoring/models/...`.
Key fields: `size`, `rowCount`, `lastImportTime`, `lastModifiedBy`, `lastModifiedTime`.

| Tool | Hint | Parameters | Purpose |
|------|------|-----------|---------|
| `list_monitored_models` | read | `top=200`, `filter?` | All models with monitoring metadata; optional OData `$filter`. |
| `get_model_monitoring` | read | `model_id` | Monitoring detail for one model (size, row count, timestamps). |
| `get_model_job_history` | read | `model_id`, `top=50`, `since_iso?` | Recent import/refresh jobs for a model; optionally filtered by start time. |

## Smart Query

| Tool | Hint | Purpose |
|------|------|---------|
| `smart_query` | read | Translates a natural-language question into a query plan. When aggregation intent is detected (`sum`/`total`/`average`/`count`) returns a `read_aggregated_data` plan with `next_tool="read_aggregated_data"`; otherwise returns a `read_fact_data` plan. Never executes the query. |
| `sql_query` | read | Accepts a SQL-like query string; routes automatically. Queries with explicit aggregate functions (`SUM(col)`, `COUNT(col)`, etc.) go to the Aggregation entity for server-side GROUP BY. With `story_id`+`widget_id` the Widget Query API is preferred. Everything else uses OData. |
