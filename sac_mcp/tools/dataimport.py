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

from sac_mcp.client.errors import SACError
from sac_mcp.client.http import SACClient
from sac_mcp.client.paths import DATA_IMPORT_ROOT, seg
from sac_mcp.tools._common import collect, page_envelope, safe

# Per SAP's Data Import API. masterFactData writes master and fact data in one
# job; privateFactData targets the caller's private version.
ImportKind = Literal["factData", "masterData", "masterFactData", "privateFactData"]
ImportMethod = Literal["Update", "Append", "CleanAndReplace", "DeleteAndUpsert", "DropAndInsert"]
_IMPORT = DATA_IMPORT_ROOT

# Keys under which SAC releases report validation failures. Shapes vary by
# release, so we probe all of them.
_FAILED_ROW_KEYS = ("failedNumberRows", "failedRows", "invalidRowCount")


def _parse_csv_rows(csv_text: str) -> list[dict[str, Any]]:
    """Convert raw CSV (with header row) into JSON rows."""

    reader = csv.DictReader(io.StringIO(csv_text))
    return [dict(r) for r in reader]


def _extract_job_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("jobID", "jobId", "id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _failed_row_count(validation: Any) -> int:
    if not isinstance(validation, dict):
        return 0
    # Check every known key and take the worst count — a release may return an
    # empty failedRows list next to a non-zero invalidRowCount.
    worst = 0
    for key in _FAILED_ROW_KEYS:
        value = validation.get(key)
        if isinstance(value, list):
            worst = max(worst, len(value))
            continue
        try:
            if value is not None:
                worst = max(worst, int(value))
        except (TypeError, ValueError):
            continue
    return worst


def job_body(
    import_method: str,
    mapping: dict[str, str] | None = None,
    default_values: dict[str, str] | None = None,
    execute_with_failed_rows: bool = False,
) -> dict[str, Any]:
    """Body for job creation: ``{Mapping?, DefaultValues?, JobSettings}`` (SAP spec)."""

    body: dict[str, Any] = {
        "JobSettings": {
            "importMethod": import_method,
            "executeWithFailedRows": execute_with_failed_rows,
        }
    }
    if mapping:
        body["Mapping"] = mapping
    if default_values:
        body["DefaultValues"] = default_values
    return body


async def run_import(
    client: SACClient,
    create_path: str,
    body: dict[str, Any],
    rows: list[dict[str, Any]],
    chunk_size: int = 50_000,
) -> dict[str, Any]:
    """Create a job at ``create_path``, upload ``rows``, validate and run it.

    Stops before running when validation rejects rows. Once the job exists,
    every failure is returned together with its ``job_id`` so the caller can
    inspect or cancel it.
    """

    created = await client.post_json(create_path, json=body)
    job_id = _extract_job_id(created)
    if job_id is None:
        return {"error": "SAC did not return a job ID for the created import job", "response": created}

    job = f"{_IMPORT}/jobs/{seg(job_id)}"
    try:
        chunk_size = max(1, chunk_size)
        for start in range(0, len(rows), chunk_size):
            await client.post_json(job, json={"Data": rows[start : start + chunk_size]})

        validation = await client.post_json(f"{job}/validate")
        failed = _failed_row_count(validation)
        if failed > 0:
            return {
                "job_id": job_id,
                "ran": False,
                "validation": validation,
                "hint": (
                    f"{failed} rows failed validation; call "
                    f"get_job_invalid_rows(job_id='{job_id}') to inspect them, "
                    f"then fix the data or cancel_job(job_id='{job_id}')."
                ),
            }

        run_result = await client.post_json(f"{job}/run")
        status = await client.get_json(f"{job}/status")
    except SACError as exc:
        return {
            "error": exc.to_tool_message(),
            "code": exc.code,
            "status": exc.status_code,
            "job_id": job_id,
            "hint": (
                f"The import job was created but did not complete; call "
                f"get_job_status(job_id='{job_id}') or cancel_job(job_id='{job_id}')."
            ),
        }

    return {
        "job_id": job_id,
        "ran": True,
        "rows_uploaded": len(rows),
        "validation": validation,
        "run": run_result,
        "job_status": status,
    }


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
            kind: ``factData`` (default), ``masterData``, ``masterFactData``
                or ``privateFactData``.
            import_method: ``Update`` (default), ``Append``, ``CleanAndReplace``,
                ``DeleteAndUpsert`` or ``DropAndInsert``.
            mapping: Source → target column mapping (optional).
            default_values: Static defaults for unmapped columns.

        Returns the created ``jobID``; pass it to :func:`upload_job_data`,
        :func:`validate_job` and :func:`run_job` in turn.
        """

        return await client.post_json(
            f"{_IMPORT}/models/{seg(model_id)}/{seg(kind)}",
            json=job_body(import_method, mapping, default_values),
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

        if rows is None:
            # csv_text path: convert to JSON rows so we get consistent validation.
            rows = _parse_csv_rows(csv_text or "")
        return await client.post_json(f"{_IMPORT}/jobs/{seg(job_id)}", json={"Data": rows})

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def validate_job(job_id: str) -> dict[str, Any]:
        """Validate an import job (does not write to the model)."""

        return await client.post_json(f"{_IMPORT}/jobs/{seg(job_id)}/validate")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def run_job(job_id: str) -> dict[str, Any]:
        """Execute a previously-validated import job. **Mutates the model.**"""

        return await client.post_json(f"{_IMPORT}/jobs/{seg(job_id)}/run")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_job_status(job_id: str) -> dict[str, Any]:
        """Return the current status of an import job."""

        return await client.get_json(f"{_IMPORT}/jobs/{seg(job_id)}/status")

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """Cancel an in-progress import job."""

        await client.delete(f"{_IMPORT}/jobs/{seg(job_id)}")
        return {"job_id": job_id, "cancelled": True}

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_recent_jobs(model_id: str, top: int = 50) -> dict[str, Any]:
        """List recent import jobs that target one model.

        SAC has no per-model job list (``/models/{id}/jobs`` is error 1305), so
        this reads ``/dataimport/jobs`` and keeps the jobs whose model ID matches.
        """

        rows: list[dict[str, Any]] = []
        async for job in client.paginate(f"{_IMPORT}/jobs", max_rows=5000):
            if model_id in (job.get("modelID"), job.get("modelId"), job.get("ModelID")):
                rows.append(job)
                if len(rows) > top:
                    break
        return page_envelope(rows[:top], has_more=len(rows) > top)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def list_all_import_jobs(top: int = 100) -> dict[str, Any]:
        """List recent import jobs across every model on the tenant.

        Use :func:`list_recent_jobs` instead when you already know the model.

        Args:
            top: Maximum number of jobs to return (default 100).
        """

        rows, more = await collect(client, f"{_IMPORT}/jobs", max_rows=top)
        return page_envelope(rows, has_more=more)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_import_metadata(model_id: str) -> dict[str, Any]:
        """Return the import column metadata for a model.

        Describes the columns (dimensions, measures, their types) that an
        import job payload must provide. Call this before building rows for
        :func:`create_import_job` / :func:`write_fact_data`.

        Args:
            model_id: Target model (provider) ID.
        """

        return await client.get_json(f"{_IMPORT}/models/{seg(model_id)}/metadata")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def get_job_invalid_rows(job_id: str, top: int = 200) -> dict[str, Any]:
        """Return rows that failed validation for an import job.

        Each row includes the rejection reason, so you can fix the source data
        and re-upload.

        Args:
            job_id: The import job ID.
            top: Maximum number of invalid rows to return (default 200).
        """

        payload = await client.get_json(
            f"{_IMPORT}/jobs/{seg(job_id)}/invalidRows", params={"$top": top}
        )
        if isinstance(payload, list):
            return page_envelope(payload[:top])
        if isinstance(payload, dict):
            rows = (
                payload.get("invalidRows")
                or payload.get("failedRows")
                or payload.get("value")
                or []
            )
            return page_envelope(list(rows)[:top])
        return page_envelope([])

    @server.tool(annotations=ToolAnnotations(destructiveHint=True))
    @safe
    async def write_fact_data(
        model_id: str,
        rows: list[dict[str, Any]] | None = None,
        csv_text: str | None = None,
        import_method: ImportMethod = "Update",
        mapping: dict[str, str] | None = None,
        default_values: dict[str, str] | None = None,
        chunk_size: int = 50_000,
    ) -> dict[str, Any]:
        """Write fact data to a model in one call. **Mutates the model.**

        Convenience wrapper over the full Data Import lifecycle:
        create job → upload data (in chunks) → validate → run. If validation
        rejects any rows the job is **not** run; inspect the failures with
        ``get_job_invalid_rows`` and either fix the data or ``cancel_job``.

        For step-by-step control (e.g. pausing for user approval between
        validate and run) use ``create_import_job`` / ``upload_job_data`` /
        ``validate_job`` / ``run_job`` individually instead.

        Args:
            model_id: Target model (provider) ID.
            rows: Fact rows as column→value dicts. Provide either this or
                ``csv_text``.
            csv_text: Raw CSV with a header row, alternative to ``rows``.
            import_method: ``Update`` (default), ``Append``, ``CleanAndReplace``,
                ``DeleteAndUpsert`` or ``DropAndInsert``.
            mapping: Source → target column mapping (optional).
            default_values: Static defaults for unmapped columns.
            chunk_size: Rows per upload request (default 50000, SAC's
                practical sweet spot).

        Returns:
            ``{"job_id": ..., "ran": bool, "validation": ..., "status": ...}``.
            ``ran`` is False when validation failures stopped the run.
        """

        if rows is None:
            if csv_text is None:
                return {"error": "Provide either rows or csv_text"}
            rows = _parse_csv_rows(csv_text)
        if not rows:
            return {"error": "No rows to import — the payload is empty"}

        return await run_import(
            client,
            f"{_IMPORT}/models/{seg(model_id)}/factData",
            job_body(import_method, mapping, default_values),
            rows,
            chunk_size,
        )
