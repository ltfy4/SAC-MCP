"""Prompt: guided Data Import job lifecycle."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sac_mcp.client.http import SACClient


def register(server: FastMCP, _client: SACClient) -> None:
    @server.prompt()
    def plan_writeback(model_id: str) -> str:
        """Step the user through a safe Data Import to ``model_id``."""

        return (
            f"To write data into SAC model `{model_id}` safely, follow this "
            "sequence and confirm each step with the user:\n\n"
            f"1. Inspect the model: `get_model_metadata(model_id='{model_id}')` "
            f"and the import columns: `get_import_metadata(model_id='{model_id}')`.\n"
            "2. Understand existing master data so your import respects the "
            f"dimension members: `list_dimension_members(model_id='{model_id}', dimension=...)`.\n"
            "3. Create the job (no data written yet): "
            f"`create_import_job(model_id='{model_id}', kind='factData', "
            "import_method='Update')`.\n"
            "4. Upload the rows in chunks ≤ 50k: `upload_job_data(job_id=..., rows=[...])`.\n"
            "5. Validate: `validate_job(job_id=...)`. Show the user the summary; "
            "inspect rejects with `get_job_invalid_rows(job_id=...)`.\n"
            "6. Only after explicit user approval: `run_job(job_id=...)`.\n"
            "7. Poll `get_job_status(job_id=...)` until terminal.\n\n"
            "If anything looks wrong, call `cancel_job(job_id=...)`.\n\n"
            "Shortcut: once the user has approved the exact rows and import "
            f"method, `write_fact_data(model_id='{model_id}', rows=[...])` "
            "performs the whole lifecycle in one call and stops before `run` "
            "if validation rejects any rows."
        )
