# Changelog

## 0.2.0 -- unreleased

Every endpoint was re-checked against a live tenant; see `docs/SAC_API_NOTES.md`.
This release contains breaking changes to the tool catalogue (87 -> 74 tools).

### Security
- IDs are percent-encoded into URL paths. Previously
  `cancel_job(job_id="../../scim/Users/X")` sent `DELETE /api/v1/scim/Users/X`.

### Fixed
- Installation: `mcp` is pinned below 2.0, which removed `FastMCP`. CI installs from `uv.lock`.
- Fact data is read from `FactData` (`Data` does not exist), dimension members
  from `<Dimension>Master`, hierarchies from `<Dimension>MasterWithHierarchy`.
- Aggregation uses `FactDataAggregation`. `sum` runs server-side; other
  operators run client-side and are labelled. SAC ignores `$apply`, so the old
  code would have returned leaf rows as totals.
- `$metadata` is parsed as XML. `get_model_metadata`, `list_dimensions`,
  `list_measures` and `smart_query` work and flag account-based models.
- Delta tracking uses SAC's `deltaid` tokens. Delta reads are capped instead of
  returning the entire model.
- `list_models(name_contains=)` filters on `ProviderName`/`Description`.
- Stories and resources are listed through the file repository.
  `list_stories` no longer times out.
- Query strings encode spaces as `%20` (the file repository rejected `+`).
- Data Import uses SAP's body shapes (`JobSettings`, `Mapping`, `Data`),
  upload path and import methods.
- Multi-Actions run through `/api/v1/multiActions/{id}/executions`.
- Calendar, content transport, activity log, monitoring, widget query,
  currency/unit tables and public dimensions point at existing endpoints.
- Exhausted retries and network failures return structured errors instead of
  tracebacks. SAC error numbers become codes (`SAC-3707`) with fix hints.
- `whoami` no longer dumps the whole model list.
- HTTP transport: CORS wraps bearer auth, so browser clients see the 401.
- Setup wizard derives the auth URL, quotes secrets, and accepts every region code.

### Changed (breaking)
- `get_multi_action_run_status(multi_action_id, execution_id)` now takes both IDs.
- `run_multi_action(multi_action_id, parameter_values)` replaces `parameters`.
- `create_import_job` / `write_fact_data` import methods are `Update`,
  `Append`, `CleanAndReplace`, `DeleteAndUpsert`, `DropAndInsert`.
- `list_resources` takes the repository's resource types. `parent_id` is
  replaced by `created_by` and `filter`.
- `list_stories` drops `include_models` (use `list_story_models`).
- `list_data_actions(name_contains, max_rows)` replaces `(top, model_id)`.
- `create_cn_import_job` / `create_cn_export_job` take a `job_definition` body.
- `list_teams` summarises members as `member_count` unless `include_members=true`.
- Collection results report `has_more`.
- `SAC_PAGE_SIZE` was never used and is removed.

### Removed (their endpoints do not exist)
`list_folders`, `run_data_action`, `list_data_action_executions`,
`get_data_action_status`, `get_currency_rates`, `get_unit_rates`,
`read_currency_data`, `read_public_dimension_master_data`,
`read_public_dimension_hierarchies`, `list_calendar_tasks`, `add_task_comment`,
`list_packages`, `list_monitored_models`, `get_model_job_history`.

### Added
- `get_public_dimension`.
- `SAC_RESPONSE_CHAR_LIMIT`: results are truncated rather than overflowing the client.
- `docs/gen_tools_md.py` regenerates `docs/tools.md` from the code.
