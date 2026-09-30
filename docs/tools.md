# Tool reference

Generated from the code by `python docs/gen_tools_md.py` -- do not edit by hand.

74 tools. **read** tools carry `readOnlyHint`; **write** tools carry `destructiveHint`, so MCP clients ask before running them.

## Admin

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `whoami` | read | - | Identify the OAuth client this server calls SAC with. |
| `tenant_info` | read | - | Return the tenant URL, MCP server version, and configured behaviour. |
| `health_check` | read | - | Confirm the tenant is reachable and the OAuth credentials work. |

## Stories

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_stories` | read | `max_rows?`, `created_by?`, `all_tenant_content?` | List stories (from the file repository; ``/api/v1/stories`` ignores paging). |
| `get_story` | read | `story_id` | Return a single story by ID, including referenced models. |
| `search_stories` | read | `query`, `max_rows?` | Find stories whose name or description contains ``query`` (case-insensitive). |
| `list_story_models` | read | `story_id` | Return the list of models referenced by a story. |

## Resources (file repository)

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_resources` | read | `resource_type?`, `name_contains?`, `created_by?`, `filter?`, `all_tenant_content?`, `max_rows?` | List content in the SAC file repository (stories, apps, data actions, ...). |
| `get_resource` | read | `resource_id` | Fetch one repository resource by its ``resourceId``. |
| `find_by_type` | read | `resource_type`, `max_rows?` | Convenience: list every resource of one type (see ``list_resources``). |

## Models

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_models` | read | `name_contains?`, `max_rows?` | List the models (Data Export "providers") visible to the OAuth client. |
| `get_model_metadata` | read | `model_id`, `include_raw_xml?` | Describe a model: dimensions, measures, entity sets, account dimension. |
| `list_dimensions` | read | `model_id` | List a model's dimensions, whether each has a member list and a hierarchy. |
| `list_measures` | read | `model_id` | List a model's measures (e.g. ``LC_AMOUNT``). |

## Data Export

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `read_fact_data` | read | `model_id`, `filter?`, `select?`, `orderby?`, `top?`, `skip?` | Read leaf-level fact rows from a model (OData ``FactData``). |
| `read_fact_data_delta` | read | `model_id`, `delta_token`, `top?` | Deprecated alias of ``get_delta_changes`` for ``FactData``. |
| `export_fact_data_csv` | read | `model_id`, `filter?`, `select?`, `orderby?`, `max_rows?` | Read fact rows and return them as one CSV string. |
| `read_master_data` | read | `model_id`, `dimension?`, `filter?`, `top?` | Read master data for a model. |
| `list_dimension_members` | read | `model_id`, `dimension`, `top?`, `with_hierarchy?` | List the members of one dimension (``ID``, ``Description``, attributes). |
| `read_audit_data` | read | `model_id`, `filter?`, `top?` | Read the data-change audit trail of a model (``AuditData``). |

## Delta tracking

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `init_delta_tracking` | read | `model_id`, `entity?`, `top?`, `filter?` | Start change tracking on a model entity set and get a ``delta_token``. |
| `get_delta_changes` | read | `model_id`, `delta_token`, `entity?`, `top?` | Return only the rows changed since ``delta_token`` was issued. |

## Aggregation

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `read_aggregated_data` | read | `model_id`, `group_by`, `aggregates`, `filter?`, `orderby?`, `top?`, `max_scan_rows?` | Group a model's facts by dimensions and aggregate measures. |
| `top_n_by_measure` | read | `model_id`, `dimension`, `measure`, `agg?`, `direction?`, `top?`, `filter?` | Rank a dimension's members by an aggregated measure (top or bottom N). |
| `aggregate_by_dimension` | read | `model_id`, `dimension`, `measures`, `agg?`, `filter?`, `top?` | Aggregate several measures grouped by one dimension (summary table). |

## FP&A analysis

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_versions` | read | `model_id`, `version_dimension?`, `top?` | List the planning versions (categories) of a model. |
| `compare_versions` | read | `model_id`, `measure`, `group_by`, `version_a`, `version_b`, `version_dimension?`, `agg?`, `filter?`, `top?` | Compare one measure between two versions — the variance report. |
| `measure_trend` | read | `model_id`, `measure`, `time_dimension?`, `periods?`, `agg?`, `filter?` | Aggregate a measure over time and compute period-over-period change. |
| `check_data_completeness` | read | `model_id`, `dimension`, `measure`, `filter?`, `max_members?` | Report which dimension members have no fact data booked. |

## Query routing: sql_query

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `sql_query` | read | `model_id`, `query`, `top?`, `entity?`, `story_id?`, `widget_id?` | Execute a query against a SAC model, automatically choosing the best API. |

## Query routing: smart_query

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `smart_query` | read | `model_id`, `question`, `top?` | Translate a natural-language question into an OData query plan. |

## Data Import

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `create_import_job` | write | `model_id`, `kind?`, `import_method?`, `mapping?`, `default_values?` | Create a Data Import job. |
| `upload_job_data` | write | `job_id`, `rows?`, `csv_text?` | Upload one chunk of data into an import job. |
| `validate_job` | write | `job_id` | Validate an import job (does not write to the model). |
| `run_job` | write | `job_id` | Execute a previously-validated import job. **Mutates the model.** |
| `get_job_status` | read | `job_id` | Return the current status of an import job. |
| `cancel_job` | write | `job_id` | Cancel an in-progress import job. |
| `list_recent_jobs` | read | `model_id`, `top?` | List recent import jobs that target one model. |
| `list_all_import_jobs` | read | `top?` | List recent import jobs across every model on the tenant. |
| `get_import_metadata` | read | `model_id` | Return the import column metadata for a model. |
| `get_job_invalid_rows` | read | `job_id`, `top?` | Return rows that failed validation for an import job. |
| `write_fact_data` | write | `model_id`, `rows?`, `csv_text?`, `import_method?`, `mapping?`, `default_values?`, `chunk_size?` | Write fact data to a model in one call. **Mutates the model.** |

## Multi-Actions

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_multi_actions` | read | `name_contains?`, `max_rows?` | List Multi-Actions (file-repository resources of type ``PLANNINGSEQUENCE``). |
| `run_multi_action` | write | `multi_action_id`, `parameter_values?` | Trigger a Multi-Action run. **This writes to planning models.** |
| `get_multi_action_run_status` | read | `multi_action_id`, `execution_id` | Return the status of one Multi-Action execution. |

## Data Actions

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_data_actions` | read | `name_contains?`, `max_rows?` | List Data Actions (file-repository resources of type ``DATAACTION``). |
| `get_data_action` | read | `data_action_id` | Return the repository entry (name, owner, timestamps) of one Data Action. |

## Currency & unit tables

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_currency_tables` | read | `top?` | List currency conversion (exchange-rate) tables. |
| `get_currency_table` | read | `table_id` | Describe one currency table and the columns its rate import expects. |
| `upload_currency_rates` | write | `table_id`, `rates`, `import_method?` | Write exchange rates into a currency table. **Mutates the tenant.** |
| `list_unit_tables` | read | `top?` | List unit-of-measure conversion tables. |
| `get_unit_table` | read | `table_id` | Describe one unit conversion table and the columns its import expects. |
| `upload_unit_rates` | write | `table_id`, `rates`, `import_method?` | Write conversion factors into a unit table. **Mutates the tenant.** |

## Public dimensions

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_public_dimensions` | read | `top?` | List the public (shared) dimensions on the tenant. |
| `get_public_dimension` | read | `dimension_id` | Describe one public dimension and the columns its member import expects. |

## Users (SCIM)

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_users` | read | `filter?`, `start_index?`, `count?` | List SCIM users. Supports raw SCIM ``filter`` syntax. |
| `get_user` | read | `user_id` | Return one SCIM user by internal ID. |
| `create_user` | write | `user_name`, `display_name?`, `email?`, `active?`, `extra?` | Create a new SCIM user. |
| `update_user` | write | `user_id`, `patch` | PATCH a SCIM user. ``patch`` is a SCIM PatchOp body (``Operations`` list). |
| `deactivate_user` | write | `user_id` | Mark a user inactive (preferred over delete to preserve audit trail). |

## Teams (SCIM)

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `list_teams` | read | `filter?`, `start_index?`, `count?`, `include_members?` | List SCIM groups (teams). |
| `get_team` | read | `team_id` | Return one team / group by ID. |
| `add_member` | write | `team_id`, `user_id` | Add a user to a team. |
| `remove_member` | write | `team_id`, `user_id` | Remove a user from a team. |

## Calendar

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `get_calendar_task` | read | `task_id` | Return one calendar event (task or process) by its event ID. |
| `update_task_status` | write | `task_id`, `status` | Set the status of a calendar event. **Mutates the tenant.** |

## Content transport

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `create_cn_import_job` | write | `job_definition` | Start a content **import** job. **Mutates the tenant.** |
| `create_cn_export_job` | write | `job_definition` | Start a content **export** job (publish content to a package). |
| `get_cn_job_status` | read | `job_id` | Return the status of a content import/export job. |

## Audit log

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `query_audit_log` | read | `filter?`, `top?`, `orderby?` | Export activity-log entries (who did what, when). |
| `recent_changes_for_user` | read | `username`, `since_iso`, `top?` | Activity-log entries for one user since an ISO timestamp. |

## Monitoring

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `get_model_monitoring` | read | `model_id` | Return monitoring information (size, row count, last changes) for one model. |

## Widget query

| Tool | Kind | Parameters (`?` = optional) | Description |
|---|---|---|---|
| `get_widget_data` | read | `story_id`, `widget_id`, `type?` | Fetch data from a specific widget in a SAC story. |
| `list_story_widgets` | read | `story_id` | List widget metadata embedded in a SAC story (best effort). |
