"""Data Import Service tools — write fact / master data via SAC's job lifecycle.

The full lifecycle is:

    1. POST /api/v1/dataimport/models/{model}/{factData|masterData}
       → returns ``jobID``
    2. POST /api/v1/dataimport/jobs/{jobID}/data  (one or more chunks)
    3. POST /api/v1/dataimport/jobs/{jobID}/validate
    4. POST /api/v1/dataimport/jobs/{jobID}/run
    5. GET  /api/v1/dataimport/jobs/{jobID}/status

All write operations require a CSRF token, transparently handled by
:class:`SACClient`.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe

ImportKind = Literal["factData", "masterData"]
ImportMethod = Literal["Append", "Update", "Replace", "Delete"]


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def create_import_job(
        model_id: str,
        kind: ImportKind = "factData",
        import_method: ImportMethod = "Update",
        mapping: dict[str, str] | None = None,
        default_values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a Data Import job.

        Args:
            model_id: Target model (provider) ID.
            kind: ``factData`` (default) or ``masterData``.
            import_method: One of Append, Update, Replace, Delete.
            mapping: Source → target column mapping (optional).
            default_values: Static defaults for unmapped columns.

        Returns the created ``jobID``; pass it to :func:`upload_job_data`,
        :func:`validate_job` and :func:`run_job` in turn.
        """

        body: dict[str, Any] = {"importMethod": import_method}
        if mapping:
            body["mappings"] = mapping
        if default_values:
            body["defaultValues"] = default_values

        return await client.post_json(
            f"/api/v1/dataimport/models/{model_id}/{kind}", json=body
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def upload_job_data(
        job_id: str,
        rows: list[dict[str, Any]] | None = None,
        csv_text: str | None = None,
    ) -> dict[str, Any]:
        """Upload one chunk of data into an import job.

        Provide *either* ``rows`` (list of column→value dicts) *or* ``csv_text``
        (raw CSV with header row).
        """

        if rows is None and csv_text is None:
            return {"error": "Provide either rows or csv_text"}

        if rows is not None:
            payload = {"data": rows}
            return await client.post_json(
                f"/api/v1/dataimport/jobs/{job_id}/data", json=payload
            )

        # csv_text path: convert to JSON rows so we get consistent validation.
        reader = csv.DictReader(io.StringIO(csv_text or ""))
        parsed_rows = [dict(r) for r in reader]
        return await client.post_json(
            f"/api/v1/dataimport/jobs/{job_id}/data", json={"data": parsed_rows}
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def validate_job(job_id: str) -> dict[str, Any]:
        """Validate an import job (does not write to the model)."""

        return await client.post_json(f"/api/v1/dataimport/jobs/{job_id}/validate")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def run_job(job_id: str) -> dict[str, Any]:
        """Execute a previously-validated import job. **Mutates the model.**"""

        return await client.post_json(f"/api/v1/dataimport/jobs/{job_id}/run")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_job_status(job_id: str) -> dict[str, Any]:
        """Return the current status of an import job."""

        return await client.get_json(f"/api/v1/dataimport/jobs/{job_id}/status")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """Cancel an in-progress import job."""

        await client.delete(f"/api/v1/dataimport/jobs/{job_id}")
        return {"job_id": job_id, "cancelled": True}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_recent_jobs(model_id: str, top: int = 50) -> dict[str, Any]:
        """List recent import jobs for a model."""

        return await client.get_json(
            f"/api/v1/dataimport/models/{model_id}/jobs", params={"$top": top}
        )
