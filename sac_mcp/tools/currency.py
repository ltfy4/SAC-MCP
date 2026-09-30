"""Currency and unit conversion tables (SAP Data Import API).

SAC manages rate tables through ``/api/v1/dataimport/currencyConversions`` and
``/api/v1/dataimport/unitConversions``: list, describe, and write rates with
an import job. The old ``/api/v1/currencyConversion`` paths and the
``CurrencyData`` export entity do not exist (404 / not in the service
document), and the public API offers no endpoint to *read* stored rates.
Requires Data Import access for the OAuth client (otherwise error 3401).
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import DATA_IMPORT_ROOT, seg
from sac_mcp.tools._common import collect, page_envelope, safe
from sac_mcp.tools.dataimport import ImportMethod, job_body, run_import

_ROOTS = {
    "currency": f"{DATA_IMPORT_ROOT}/currencyConversions",
    "unit": f"{DATA_IMPORT_ROOT}/unitConversions",
}
TableKind = Literal["currency", "unit"]


def register(server: FastMCP, client: SACClient) -> None:
    read = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
    write = ToolAnnotations(destructiveHint=True, openWorldHint=True)

    async def _list(kind: TableKind, top: int) -> dict[str, Any]:
        rows, more = await collect(client, _ROOTS[kind], max_rows=top)
        return page_envelope(rows, has_more=more)

    async def _get(kind: TableKind, table_id: str) -> dict[str, Any]:
        base = f"{_ROOTS[kind]}/{seg(table_id)}"
        return {
            "table": await client.get_json(base),
            "metadata": await client.get_json(f"{base}/metadata"),
        }

    async def _upload(
        kind: TableKind, table_id: str, rates: list[dict[str, Any]], method: str
    ) -> dict[str, Any]:
        if not rates:
            return {"error": "No rates to import — the payload is empty"}
        return await run_import(
            client, f"{_ROOTS[kind]}/{seg(table_id)}", job_body(method), rates
        )

    @server.tool(annotations=read)
    @safe
    async def list_currency_tables(top: int = 100) -> dict[str, Any]:
        """List currency conversion (exchange-rate) tables."""

        return await _list("currency", top)

    @server.tool(annotations=read)
    @safe
    async def get_currency_table(table_id: str) -> dict[str, Any]:
        """Describe one currency table and the columns its rate import expects."""

        return await _get("currency", table_id)

    @server.tool(annotations=write)
    @safe
    async def upload_currency_rates(
        table_id: str, rates: list[dict[str, Any]], import_method: ImportMethod = "Update"
    ) -> dict[str, Any]:
        """Write exchange rates into a currency table. **Mutates the tenant.**

        Runs create job → upload → validate → run; stops before running if any
        row fails validation. Columns follow ``get_currency_table``'s metadata.
        """

        return await _upload("currency", table_id, rates, import_method)

    @server.tool(annotations=read)
    @safe
    async def list_unit_tables(top: int = 100) -> dict[str, Any]:
        """List unit-of-measure conversion tables."""

        return await _list("unit", top)

    @server.tool(annotations=read)
    @safe
    async def get_unit_table(table_id: str) -> dict[str, Any]:
        """Describe one unit conversion table and the columns its import expects."""

        return await _get("unit", table_id)

    @server.tool(annotations=write)
    @safe
    async def upload_unit_rates(
        table_id: str, rates: list[dict[str, Any]], import_method: ImportMethod = "Update"
    ) -> dict[str, Any]:
        """Write conversion factors into a unit table. **Mutates the tenant.**"""

        return await _upload("unit", table_id, rates, import_method)
