"""Content Network tools — package import / export jobs."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import safe


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_packages(visibility: str = "private", top: int = 100) -> dict[str, Any]:
        """List Content Network packages visible to this tenant.

        Args:
            visibility: ``private`` or ``public``.
            top: Page size.
        """

        return await client.get_json(
            "/api/v1/contentnetwork/packages",
            params={"visibility": visibility, "$top": top},
        )

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def create_cn_import_job(
        package_id: str, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a Content Network *import* job for a given package.

        Returns the job ID — poll with :func:`get_cn_job_status`.
        """

        body: dict[str, Any] = {"packageId": package_id}
        if options:
            body["options"] = options
        return await client.post_json("/api/v1/contentnetwork/imports", json=body)

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def create_cn_export_job(
        package_name: str,
        resources: list[dict[str, Any]],
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a Content Network *export* job.

        Args:
            package_name: Name of the package to publish.
            resources: List of ``{"resourceId": ..., "resourceType": ...}`` dicts.
            description: Optional description for the package.
        """

        body: dict[str, Any] = {"name": package_name, "resources": resources}
        if description:
            body["description"] = description
        return await client.post_json("/api/v1/contentnetwork/exports", json=body)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_cn_job_status(job_id: str) -> dict[str, Any]:
        """Return the current status of a Content Network job."""

        return await client.get_json(f"/api/v1/contentnetwork/jobs/{job_id}")
