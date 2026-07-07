"""Sanity tests: the FastMCP server wires up cleanly with all tools."""

from __future__ import annotations

import pytest

from sac_mcp.config import get_settings
from sac_mcp.server import build_server


@pytest.mark.asyncio
async def test_all_tools_registered_with_correct_hints() -> None:
    server = build_server(get_settings())
    tools = await server.list_tools()
    names = {t.name for t in tools}

    # Coverage spot-check across every surface.
    expected = {
        # Admin
        "whoami", "tenant_info", "health_check",
        # Audit
        "query_audit_log",
        # Calendar
        "list_calendar_tasks", "update_task_status",
        # Content network
        "list_packages", "create_cn_import_job", "get_cn_job_status",
        # Data export
        "read_fact_data", "read_master_data", "read_audit_data",
        # Data import
        "create_import_job", "upload_job_data", "validate_job", "run_job",
        "get_job_status", "cancel_job", "write_fact_data", "get_job_invalid_rows",
        "list_all_import_jobs", "get_import_metadata",
        # Data actions
        "list_data_actions", "get_data_action", "run_data_action",
        "list_data_action_executions", "get_data_action_status",
        # FP&A analysis
        "list_versions", "compare_versions", "measure_trend",
        "check_data_completeness",
        # Models
        "list_models", "get_model_metadata", "list_dimensions", "list_measures",
        # Multi-action
        "list_multi_actions", "run_multi_action",
        # Resources
        "list_resources", "get_resource",
        # Stories
        "list_stories", "get_story", "search_stories",
        # Teams
        "list_teams", "add_member", "remove_member",
        # Users
        "list_users", "create_user", "deactivate_user",
        # Public dimensions
        "list_public_dimensions", "read_public_dimension_master_data",
        "read_public_dimension_hierarchies",
        # Currency / unit conversion
        "list_currency_tables", "get_currency_table", "get_currency_rates",
        "upload_currency_rates", "list_unit_tables", "get_unit_table",
        "get_unit_rates", "upload_unit_rates", "read_currency_data",
        # Delta / difference tracking
        "init_delta_tracking", "get_delta_changes",
        # Widget query + sql query + plan-only smart query
        "get_widget_data", "list_story_widgets", "sql_query", "smart_query",
        # Aggregation (server-side)
        "read_aggregated_data", "top_n_by_measure", "aggregate_by_dimension",
        # Monitoring
        "list_monitored_models", "get_model_monitoring", "get_model_job_history",
    }
    missing = expected - names
    assert not missing, f"missing tools: {missing}"

    by_name = {t.name: t for t in tools}
    # Read-only hints
    assert by_name["list_models"].annotations.readOnlyHint is True
    assert by_name["read_fact_data"].annotations.readOnlyHint is True
    # Destructive hints
    assert by_name["run_job"].annotations.destructiveHint is True
    assert by_name["create_import_job"].annotations.destructiveHint is True
    assert by_name["write_fact_data"].annotations.destructiveHint is True
    assert by_name["run_data_action"].annotations.destructiveHint is True
    assert by_name["deactivate_user"].annotations.destructiveHint is True
    assert by_name["upload_currency_rates"].annotations.destructiveHint is True
    assert by_name["upload_unit_rates"].annotations.destructiveHint is True
    # Read-only hints on new surfaces
    assert by_name["list_public_dimensions"].annotations.readOnlyHint is True
    assert by_name["init_delta_tracking"].annotations.readOnlyHint is True
    assert by_name["smart_query"].annotations.readOnlyHint is True
    assert by_name["sql_query"].annotations.readOnlyHint is True
    assert by_name["get_widget_data"].annotations.readOnlyHint is True
    assert by_name["read_aggregated_data"].annotations.readOnlyHint is True
    assert by_name["top_n_by_measure"].annotations.readOnlyHint is True
    assert by_name["aggregate_by_dimension"].annotations.readOnlyHint is True
    assert by_name["list_monitored_models"].annotations.readOnlyHint is True
    assert by_name["get_model_monitoring"].annotations.readOnlyHint is True
    assert by_name["get_model_job_history"].annotations.readOnlyHint is True
    assert by_name["list_data_actions"].annotations.readOnlyHint is True
    assert by_name["get_data_action_status"].annotations.readOnlyHint is True
    assert by_name["get_job_invalid_rows"].annotations.readOnlyHint is True
    assert by_name["get_import_metadata"].annotations.readOnlyHint is True
    assert by_name["compare_versions"].annotations.readOnlyHint is True
    assert by_name["check_data_completeness"].annotations.readOnlyHint is True


@pytest.mark.asyncio
async def test_resources_and_prompts_registered() -> None:
    server = build_server(get_settings())
    res = await server.list_resources()
    assert {str(r.uri) for r in res} >= {"sac://tenant/info", "sac://catalog/models"}

    prompts = await server.list_prompts()
    assert {p.name for p in prompts} >= {"explore_tenant", "plan_writeback", "audit_drilldown"}
