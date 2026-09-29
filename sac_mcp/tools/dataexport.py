"""Data Export Service tools — read fact, master and audit data via OData v4.

Entity sets per model (verified against a live tenant, service document at
``/api/v1/dataexport/providers/sac/{model}/``):

* ``FactData``                     — leaf-level fact rows
* ``FactDataAggregation``          — facts aggregated over the ``$select``-ed columns
* ``MasterData``                   — fact rows enriched with every dimension attribute
* ``<Dimension>Master``            — members of one dimension (``ID``, ``Description``, attributes)
* ``<Dimension>MasterWithHierarchy`` — the same, with hierarchy parent columns
* ``AuditData``                    — only when data audit is enabled on the model
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import ODataQuery
from sac_mcp.client.paths import des_path
from sac_mcp.tools._common import as_csv, collect, compact, page_envelope, safe
from sac_mcp.tools.difference import delta_read

_READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)


def _clean_select(select: list[str] | None) -> list[str]:
    """Strip whitespace — "Entity, Amount" produces a malformed-URI error in SAC."""

    return [c.strip() for c in (select or []) if c and c.strip()]


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=_READ)
    @safe
    async def read_fact_data(
        model_id: str,
        filter: str | None = None,
        select: list[str] | None = None,
        orderby: list[str] | None = None,
        top: int = 100,
        skip: int | None = None,
    ) -> dict[str, Any]:
        """Read leaf-level fact rows from a model (OData ``FactData``).

        Args:
            model_id: The model (provider) ID, e.g. from ``list_models``.
            filter: OData ``$filter``, e.g. ``"Version eq 'public.Actual' and Date eq '202401'"``.
            select: Columns to return. SAC requires **every** dimension (key)
                column when selecting — to keep only some dimensions, use
                ``read_aggregated_data`` instead, which sums over the others.
            orderby: Sort columns, e.g. ``["LC_AMOUNT desc"]``.
            top: Maximum rows to return (default 100).
            skip: Skip the first N rows server-side.

        Returns ``{"rows", "row_count", "has_more"}``.
        """

        q = ODataQuery(filter=filter, select=_clean_select(select), orderby=orderby or [], skip=skip)
        rows, more = await collect(
            client, des_path(model_id, "FactData"), params=q.to_params(), max_rows=top
        )
        return page_envelope(compact(rows), has_more=more)

    @server.tool(annotations=_READ)
    @safe
    async def read_fact_data_delta(
        model_id: str, delta_token: str, top: int = 1000
    ) -> dict[str, Any]:
        """Deprecated alias of ``get_delta_changes`` for ``FactData``.

        Returns the rows changed since ``delta_token`` (from ``init_delta_tracking``)
        plus a new ``delta_token`` for the next call.
        """

        return await delta_read(client, model_id, "FactData", delta_token, top)

    @server.tool(annotations=_READ)
    @safe
    async def export_fact_data_csv(
        model_id: str,
        filter: str | None = None,
        select: list[str] | None = None,
        orderby: list[str] | None = None,
        max_rows: int = 5000,
    ) -> dict[str, Any]:
        """Read fact rows and return them as one CSV string.

        More compact than JSON for wide tables. The same ``select`` rule as
        ``read_fact_data`` applies (all dimension columns, or none).
        """

        q = ODataQuery(filter=filter, select=_clean_select(select), orderby=orderby or [])
        rows, more = await collect(
            client, des_path(model_id, "FactData"), params=q.to_params(), max_rows=max_rows
        )
        return {"row_count": len(rows), "has_more": more, "csv": as_csv(rows)}

    @server.tool(annotations=_READ)
    @safe
    async def read_master_data(
        model_id: str,
        dimension: str | None = None,
        filter: str | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Read master data for a model.

        With ``dimension`` (e.g. ``"Account"``) returns that dimension's members
        from ``<Dimension>Master``: ``ID``, ``Description`` and its attributes.
        Without it, reads ``MasterData`` — fact rows enriched with every
        dimension attribute (columns named ``<Dimension>___<Attribute>``).

        Args:
            model_id: The model (provider) ID.
            dimension: Dimension name as used in fact data, e.g. ``"Version"``.
            filter: OData ``$filter``, e.g. ``"startswith(ID,'CE')"``.
            top: Maximum rows (default 200).
        """

        entity = f"{dimension}Master" if dimension else "MasterData"
        q = ODataQuery(filter=filter)
        rows, more = await collect(
            client, des_path(model_id, entity), params=q.to_params(), max_rows=top
        )
        return page_envelope(compact(rows), has_more=more)

    @server.tool(annotations=_READ)
    @safe
    async def list_dimension_members(
        model_id: str,
        dimension: str,
        top: int = 200,
        with_hierarchy: bool = False,
    ) -> dict[str, Any]:
        """List the members of one dimension (``ID``, ``Description``, attributes).

        Args:
            model_id: The model (provider) ID.
            dimension: Dimension name, e.g. ``"Account"`` or ``"Entity"``.
                ``list_dimensions`` shows the names.
            top: Maximum members (default 200).
            with_hierarchy: Read ``<Dimension>MasterWithHierarchy`` to include
                parent/hierarchy columns (only for dimensions with hierarchies).
        """

        entity = f"{dimension}MasterWithHierarchy" if with_hierarchy else f"{dimension}Master"
        rows, more = await collect(client, des_path(model_id, entity), max_rows=top)
        return page_envelope(compact(rows), has_more=more)

    @server.tool(annotations=_READ)
    @safe
    async def read_audit_data(
        model_id: str,
        filter: str | None = None,
        top: int = 200,
    ) -> dict[str, Any]:
        """Read the data-change audit trail of a model (``AuditData``).

        Requires data audit to be enabled in the model's preferences; otherwise
        SAC answers with error 3905.
        """

        q = ODataQuery(filter=filter)
        rows, more = await collect(
            client, des_path(model_id, "AuditData"), params=q.to_params(), max_rows=top
        )
        return page_envelope(compact(rows), has_more=more)
