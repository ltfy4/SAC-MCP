"""Content transport tools (``/api/v1/content/jobs``).

The ``/api/v1/contentnetwork/...`` paths do not exist (404). SAP's content
transport API runs imports and exports as jobs at ``/api/v1/content/jobs``;
the job type and content selection are part of the job definition body.
There is no public endpoint that lists Content Network packages.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import seg
from sac_mcp.tools._common import safe

_JOBS = "/api/v1/content/jobs"


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
    write = ToolAnnotations(destructiveHint=True, openWorldHint=True)

    async def _create(job_definition: dict[str, Any]) -> dict[str, Any]:
        if not job_definition:
            return {"error": "job_definition is empty", "code": "invalid_input"}
        result = await client.post_json(_JOBS, json=job_definition)
        return result if isinstance(result, dict) else {"result": result}

    @server.tool(annotations=write)
    @safe
    async def create_cn_import_job(job_definition: dict[str, Any]) -> dict[str, Any]:
        """Start a content **import** job. **Mutates the tenant.**

        Args:
            job_definition: The import job body as defined by SAP's content
                transport API (package reference, import options).

        Returns the job; poll it with ``get_cn_job_status``.
        """

        return await _create(job_definition)

    @server.tool(annotations=write)
    @safe
    async def create_cn_export_job(job_definition: dict[str, Any]) -> dict[str, Any]:
        """Start a content **export** job (publish content to a package).

        Args:
            job_definition: The export job body as defined by SAP's content
                transport API (package name, resources to include).
        """

        return await _create(job_definition)

    @server.tool(annotations=read)
    @safe
    async def get_cn_job_status(job_id: str) -> dict[str, Any]:
        """Return the status of a content import/export job."""

        return await client.get_json(f"{_JOBS}/{seg(job_id)}")
