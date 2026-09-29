"""File repository tools (``/api/v1/filerepository/Resources``, OData).

The repository is the one listing endpoint that honours ``$filter``/``$top``
for content (verified live). ``/api/v1/stories`` ignores both and always
returns every story on the tenant, so story listing and search go through
here as well. Filterable fields: resourceType, name, createdBy, modifiedBy,
createdTime, modifiedTime, folderType.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import and_, eq
from sac_mcp.tools._common import collect, compact, page_envelope, safe

REPO = "/api/v1/filerepository/Resources"
_SCAN_PAGE = 500

# Values accepted by the repository's resourceType filter. Multi-Actions are
# PLANNINGSEQUENCE (verified live); folders are not listable resources.
ResourceType = Literal[
    "STORY", "APPLICATION", "DATAACTION", "PLANNINGSEQUENCE",
    "MULTIACCOUNT", "DIMENSION", "ANALYTIC_MODEL",
]


async def list_repository(
    client: SACClient,
    *,
    resource_type: str | None = None,
    name_contains: str | None = None,
    created_by: str | None = None,
    filter: str | None = None,
    all_tenant_content: bool = False,
    max_rows: int = 200,
    scan_limit: int = 5000,
) -> dict[str, Any]:
    """Query the repository; ``name_contains`` is matched case-insensitively here."""

    clauses = [filter or ""]
    if resource_type:
        clauses.append(eq("resourceType", resource_type))
    if created_by:
        clauses.append(eq("createdBy", created_by))
    params: dict[str, Any] = {}
    combined = and_(*clauses)
    if combined:
        params["$filter"] = combined
    if all_tenant_content:
        params["applyManagePrivilege"] = "true"

    if not name_contains:
        rows, more = await collect(client, REPO, params=params, max_rows=max_rows)
        return page_envelope(compact(rows), has_more=more)

    needle = name_contains.lower()
    matched: list[dict[str, Any]] = []
    scanned = 0
    while scanned < scan_limit and len(matched) <= max_rows:
        page = await client.get_json(
            REPO, params={**params, "$top": _SCAN_PAGE, "$skip": scanned}
        )
        rows = page.get("value", []) if isinstance(page, dict) else []
        scanned += len(rows)
        matched.extend(
            r for r in rows
            if needle in str(r.get("name") or "").lower()
            or needle in str(r.get("description") or "").lower()
        )
        if len(rows) < _SCAN_PAGE:
            break
    env = page_envelope(compact(matched[:max_rows]), has_more=len(matched) > max_rows)
    env["scanned"] = scanned
    if scanned >= scan_limit:
        env["note"] = f"Stopped after scanning {scanned} resources; add resource_type or created_by."
    return env


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def list_resources(
        resource_type: ResourceType | None = None,
        name_contains: str | None = None,
        created_by: str | None = None,
        filter: str | None = None,
        all_tenant_content: bool = False,
        max_rows: int = 200,
    ) -> dict[str, Any]:
        """List content in the SAC file repository (stories, apps, data actions, ...).

        Args:
            resource_type: ``STORY``, ``APPLICATION``, ``DATAACTION``,
                ``PLANNINGSEQUENCE`` (Multi-Actions), ``MULTIACCOUNT``,
                ``DIMENSION`` or ``ANALYTIC_MODEL``.
            name_contains: Case-insensitive text matched in name/description.
            created_by: Exact user ID of the creator.
            filter: Extra OData ``$filter``, e.g. ``"modifiedTime gt 2026-01-01T00:00:00Z"``.
            all_tenant_content: Include every user's private content
                (``applyManagePrivilege``; needs the Manage permission).
            max_rows: Maximum rows (default 200).
        """

        return await list_repository(
            client,
            resource_type=resource_type,
            name_contains=name_contains,
            created_by=created_by,
            filter=filter,
            all_tenant_content=all_tenant_content,
            max_rows=max_rows,
        )

    @server.tool(annotations=read)
    @safe
    async def get_resource(resource_id: str) -> dict[str, Any]:
        """Fetch one repository resource by its ``resourceId``."""

        page = await client.get_json(
            REPO, params={"$filter": eq("resourceId", resource_id), "$top": 1}
        )
        rows = page.get("value", []) if isinstance(page, dict) else []
        if not rows:
            return {"error": f"No repository resource with id {resource_id!r}", "code": "not_found"}
        return dict(rows[0])

    @server.tool(annotations=read)
    @safe
    async def find_by_type(resource_type: ResourceType, max_rows: int = 200) -> dict[str, Any]:
        """Convenience: list every resource of one type (see ``list_resources``)."""

        return await list_repository(client, resource_type=resource_type, max_rows=max_rows)
