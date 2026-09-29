"""Model catalogue tools (Data Export Administration namespace)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.metadata import describe_model
from sac_mcp.client.odata import ODataQuery, contains, or_
from sac_mcp.client.paths import des_path
from sac_mcp.tools._common import collect, compact, page_envelope, safe

_ADMIN = "/api/v1/dataexport/administration/Namespaces('sac')/Providers"


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @server.tool(annotations=read)
    @safe
    async def list_models(name_contains: str | None = None, max_rows: int = 200) -> dict[str, Any]:
        """List the models (Data Export "providers") visible to the OAuth client.

        Each row has ``ProviderID`` (the ``model_id`` other tools take),
        ``ProviderName`` and ``Description``.

        Args:
            name_contains: Case-sensitive substring matched against
                ``ProviderName`` or ``Description``, e.g. ``"FX"``.
            max_rows: Maximum models to return (default 200).
        """

        q = ODataQuery(
            filter=or_(contains("ProviderName", name_contains), contains("Description", name_contains))
            if name_contains
            else None
        )
        rows, more = await collect(client, _ADMIN, params=q.to_params(), max_rows=max_rows)
        return page_envelope(compact(rows), has_more=more)

    @server.tool(annotations=read)
    @safe
    async def get_model_metadata(model_id: str, include_raw_xml: bool = False) -> dict[str, Any]:
        """Describe a model: dimensions, measures, entity sets, account dimension.

        Parses the OData ``$metadata`` (XML). Dimensions are the key columns of
        ``FactData``; measures are the rest. Check ``notes`` — account-based
        models keep their line items as members of the Account dimension.

        Args:
            model_id: The model (provider) ID.
            include_raw_xml: Also return the raw EDMX document (large).
        """

        result = await describe_model(client, model_id)
        if include_raw_xml:
            _ctype, result["raw_metadata_xml"] = await client.get_text(
                des_path(model_id) + "$metadata", accept="application/xml"
            )
        return result

    @server.tool(annotations=read)
    @safe
    async def list_dimensions(model_id: str) -> dict[str, Any]:
        """List a model's dimensions, whether each has a member list and a hierarchy."""

        info = await describe_model(client, model_id)
        return {k: info[k] for k in ("model_id", "dimensions", "account_dimension", "notes")}

    @server.tool(annotations=read)
    @safe
    async def list_measures(model_id: str) -> dict[str, Any]:
        """List a model's measures (e.g. ``LC_AMOUNT``).

        For account-based models the financial line items are *members* of the
        account dimension, not measures — see ``account_dimension`` / ``notes``.
        """

        info = await describe_model(client, model_id)
        return {k: info[k] for k in ("model_id", "measures", "account_dimension", "notes")}
