"""MCP tools for SAP Analytics Cloud Currency and Unit Conversion tables.

SAC stores exchange rates in currency conversion tables and unit-of-measure
conversion factors in unit conversion tables. They are administered separately
from models and are linked to models during model configuration.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.tools._common import compact, page_envelope, safe

_CCY = "/api/v1/currencyConversion"
_UNIT = "/api/v1/unitConversion"


def _unwrap(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        value = data.get("value") or []
        return [r for r in value if isinstance(r, dict)]
    return []


def register(server: FastMCP, client: SACClient) -> None:
    # ---- Currency conversion ---------------------------------------------

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_currency_tables() -> dict[str, Any]:
        """List currency conversion tables on the tenant."""

        data = await client.get_json(_CCY)
        return page_envelope(compact(_unwrap(data)))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_currency_table(table_id: str) -> dict[str, Any]:
        """Get the metadata for a single currency conversion table."""

        result = await client.get_json(f"{_CCY}/{table_id}")
        return result if isinstance(result, dict) else {"value": result}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_currency_rates(table_id: str, top: int = 200) -> dict[str, Any]:
        """List exchange rates stored in a currency conversion table."""

        data = await client.get_json(f"{_CCY}/{table_id}/rates", params={"$top": top})
        return page_envelope(compact(_unwrap(data)))

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def upload_currency_rates(
        table_id: str, rates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upload exchange rates to a currency conversion table.

        Each rate dict typically contains:
            - sourceCurrency: ISO currency code (e.g. ``USD``)
            - targetCurrency: ISO currency code (e.g. ``EUR``)
            - rateType: e.g. ``M`` (monthly average), ``S`` (spot)
            - validFrom: ISO date the rate becomes effective
            - rate: numeric exchange-rate value
        """

        result = await client.post_json(f"{_CCY}/{table_id}/rates", json=rates)
        if isinstance(result, dict):
            return result
        return {"result": result}

    # ---- Unit conversion -------------------------------------------------

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_unit_tables() -> dict[str, Any]:
        """List unit-of-measure conversion tables on the tenant."""

        data = await client.get_json(_UNIT)
        return page_envelope(compact(_unwrap(data)))

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_unit_table(table_id: str) -> dict[str, Any]:
        """Get the metadata for a single unit conversion table."""

        result = await client.get_json(f"{_UNIT}/{table_id}")
        return result if isinstance(result, dict) else {"value": result}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_unit_rates(table_id: str, top: int = 200) -> dict[str, Any]:
        """List conversion factors stored in a unit conversion table."""

        data = await client.get_json(f"{_UNIT}/{table_id}/rates", params={"$top": top})
        return page_envelope(compact(_unwrap(data)))

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def upload_unit_rates(
        table_id: str, rates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upload unit-of-measure conversion factors to a unit conversion table.

        Each rate dict typically contains:
            - sourceUnit / targetUnit: unit codes
            - factor: numeric conversion factor
            - validFrom: ISO date the factor becomes effective
        """

        result = await client.post_json(f"{_UNIT}/{table_id}/rates", json=rates)
        if isinstance(result, dict):
            return result
        return {"result": result}

    # ---- Model-level currency data --------------------------------------

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def read_currency_data(
        model_id: str, top: int = 200, filter: str | None = None
    ) -> dict[str, Any]:
        """Read the CurrencyData entity set for a specific model."""

        params: dict[str, Any] = {"$top": top}
        if filter:
            params["$filter"] = filter

        rows: list[dict[str, Any]] = []
        async for r in client.paginate(
            f"/api/v1/dataexport/providers/sac/{model_id}/CurrencyData",
            params=params,
            max_rows=top,
        ):
            rows.append(r)
        return page_envelope(compact(rows))
