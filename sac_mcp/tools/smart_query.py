"""Plan-only natural-language query helper for SAC models.

Translates a natural-language question into an OData ``$filter`` / ``$orderby``
plan against the SAC Data Export Service. The tool returns the plan; it does
not execute the query. The caller (or LLM) reviews the plan and chooses
whether to invoke ``read_fact_data`` with the suggested arguments — that
explicit confirmation step is the safety story.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sac_mcp.client.errors import SACError
from sac_mcp.client.http import SACClient
from sac_mcp.client.odata import and_, eq, quote_odata_string
from sac_mcp.tools._common import safe

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_QUARTER_RE = re.compile(r"\bQ([1-4])\b", re.IGNORECASE)
_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"january|february|march|april|june|july|august|september|october|"
    r"november|december)\b",
    re.IGNORECASE,
)
_TOP_RE = re.compile(r"\btop\s+(\d+)\b", re.IGNORECASE)
_HIGH_RE = re.compile(r"\b(highest|largest|biggest|most|best)\b", re.IGNORECASE)
_LOW_RE = re.compile(r"\b(lowest|smallest|least|worst|bottom)\b", re.IGNORECASE)
_AGG_RE = re.compile(r"\b(sum|total|average|avg|mean)\b", re.IGNORECASE)

_MONTH_MAP = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

_DIMENSION_HINTS = ("year", "quarter", "month", "country", "region", "customer")


def _parse_metadata(payload: Any) -> tuple[list[str], list[str]]:
    """Extract dimension and measure names from a $metadata payload.

    SAC's $metadata can be returned as XML (CSDL EDMX) or JSON (depending on
    the Accept header negotiated by the client). We accept both.
    """
    dimensions: list[str] = []
    measures: list[str] = []

    if isinstance(payload, dict):
        # JSON CSDL form. The schema is permissive — walk it defensively.
        for key in ("dimensions", "Dimensions"):
            for d in payload.get(key, []) or []:
                name = d.get("name") or d.get("Name") if isinstance(d, dict) else None
                if name:
                    dimensions.append(str(name))
        for key in ("measures", "Measures"):
            for m in payload.get(key, []) or []:
                name = m.get("name") or m.get("Name") if isinstance(m, dict) else None
                if name:
                    measures.append(str(name))
        if not dimensions and not measures:
            for ent in payload.get("EntityType", []) or []:
                if not isinstance(ent, dict):
                    continue
                for prop in ent.get("Property", []) or []:
                    if not isinstance(prop, dict):
                        continue
                    name = prop.get("Name") or prop.get("name")
                    role = (prop.get("Role") or prop.get("role") or "").lower()
                    if not name:
                        continue
                    if role == "measure":
                        measures.append(str(name))
                    else:
                        dimensions.append(str(name))
        return dimensions, measures

    if isinstance(payload, str):
        root = ET.fromstring(payload)
        for prop in root.iter():
            tag = prop.tag.rsplit("}", 1)[-1]
            if tag != "Property":
                continue
            name = prop.attrib.get("Name")
            if not name:
                continue
            role = (prop.attrib.get("Role") or "").lower()
            sap_aggregation = prop.attrib.get(
                "{http://www.sap.com/Protocols/SAPData}aggregation-role", ""
            ).lower()
            if role == "measure" or sap_aggregation == "measure":
                measures.append(name)
            else:
                dimensions.append(name)
        return dimensions, measures

    raise ValueError(f"Unsupported $metadata payload type: {type(payload).__name__}")


def _find_dim(dims: list[str], *needles: str) -> str | None:
    lower = {d.lower(): d for d in dims}
    for n in needles:
        for low, original in lower.items():
            if n in low:
                return original
    return None


def _build_plan(
    question: str, dimensions: list[str], measures: list[str], top: int
) -> dict[str, Any]:
    q = question.strip()
    clauses: list[str] = []
    rationale_parts: list[str] = []

    year_match = _YEAR_RE.search(q)
    if year_match:
        year_dim = _find_dim(dimensions, "year")
        year_value = year_match.group(0)
        if year_dim:
            clauses.append(eq(year_dim, year_value))
            rationale_parts.append(
                f"Mapped year '{year_value}' to dimension {year_dim} as a string literal "
                f"(SAC OData treats period dimension members as strings)."
            )

    quarter_match = _QUARTER_RE.search(q)
    if quarter_match:
        q_dim = _find_dim(dimensions, "quarter")
        if q_dim:
            qval = f"Q{quarter_match.group(1)}"
            clauses.append(eq(q_dim, qval))
            rationale_parts.append(f"Mapped quarter '{qval}' to dimension {q_dim}.")

    month_match = _MONTH_RE.search(q)
    if month_match:
        m_dim = _find_dim(dimensions, "month")
        if m_dim:
            mnum = _MONTH_MAP.get(month_match.group(1).lower())
            if mnum:
                clauses.append(eq(m_dim, mnum))
                rationale_parts.append(
                    f"Mapped month '{month_match.group(1)}' → '{mnum}' on {m_dim}."
                )

    for keyword in ("country", "region", "customer"):
        dim = _find_dim(dimensions, keyword)
        if not dim:
            continue
        named = _extract_named_entity(q, keyword)
        if named:
            clauses.append(f"{dim} eq {quote_odata_string(named)}")
            rationale_parts.append(
                f"Mapped literal '{named}' to {dim} as an exact-match filter "
                f"(quoted via quote_odata_string)."
            )

    suggested_filter = and_(*clauses) if clauses else None

    orderby: list[str] = []
    requested_top: int | None = None
    top_match = _TOP_RE.search(q)
    if top_match:
        requested_top = int(top_match.group(1))

    high = _HIGH_RE.search(q)
    low = _LOW_RE.search(q)
    if (high or low or requested_top) and measures:
        target_measure = _pick_measure(q, measures)
        direction = "asc" if low and not high else "desc"
        orderby.append(f"{target_measure} {direction}")
        rationale_parts.append(
            f"Detected ranking intent → orderby {target_measure} {direction}."
        )

    effective_top = requested_top if requested_top is not None else top

    suggested_select: list[str] = []
    if _AGG_RE.search(q):
        suggested_select = list(measures)
        rationale_parts.append(
            "Aggregation intent detected (sum/total/average) but the Data Export "
            "OData service does not aggregate — selecting all measures so the "
            "caller can aggregate client-side."
        )

    next_call: dict[str, Any] = {
        "model_id": "",  # filled by caller
        "filter": suggested_filter,
        "select": suggested_select,
        "orderby": orderby,
        "top": effective_top,
    }

    return {
        "available_dimensions": dimensions,
        "available_measures": measures,
        "suggested_filter": suggested_filter,
        "suggested_select": suggested_select,
        "suggested_orderby": orderby,
        "rationale": " ".join(rationale_parts) or "No filters or ordering inferred.",
        "next_call": next_call,
    }


def _extract_named_entity(question: str, keyword: str) -> str | None:
    pattern = re.compile(
        rf"\b{keyword}\s+(?:is\s+|=\s*|of\s+|in\s+|named\s+)?['\"]?([A-Z][\w\s\-]{{1,40}}?)['\"]?(?=[\s.,?!]|$)",
        re.IGNORECASE,
    )
    m = pattern.search(question)
    if m:
        return m.group(1).strip()
    return None


def _pick_measure(question: str, measures: list[str]) -> str:
    q_low = question.lower()
    for m in measures:
        if m.lower() in q_low:
            return m
    return measures[0]


def register(server: FastMCP, client: SACClient) -> None:
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @safe
    async def smart_query(
        model_id: str, question: str, top: int = 100
    ) -> dict[str, Any]:
        """Translate a natural-language question into an OData query plan.

        This tool **does not execute** the query — it only returns a plan. The
        caller (or LLM) reviews the plan and decides whether to invoke
        ``read_fact_data`` with the values from ``next_call``. This explicit
        confirmation step is intentional: the rule-based mapping is best-effort
        and may misinterpret the question.

        Mapping rules (rule-based, no second LLM call):
          - Year / quarter / month words → eq filter on the matching dimension.
          - Country / region / customer literals → eq filter using
            ``quote_odata_string``.
          - "top N" / "highest" / "largest" → orderby measure desc, top=N.
          - "sum" / "total" / "average" → all measures placed in ``select``;
            the Data Export OData service does not aggregate server-side, so
            this surfaces an honest limitation in ``rationale``.

        Args:
            model_id: SAC model ID to plan against.
            question: Natural-language question (English).
            top: Default row cap if the question doesn't specify one.

        Returns:
            A dict with ``available_dimensions``, ``available_measures``,
            ``suggested_filter``, ``suggested_select``, ``suggested_orderby``,
            ``rationale``, and ``next_call`` (a kwargs dict ready to pass to
            ``read_fact_data``).
        """
        try:
            metadata = await client.get_json(
                f"/api/v1/dataexport/providers/sac/{model_id}/$metadata"
            )
        except SACError:
            raise
        except Exception as exc:
            return {
                "error": f"Failed to fetch $metadata: {exc}",
                "code": "metadata_fetch_failed",
                "model_id": model_id,
            }

        try:
            dimensions, measures = _parse_metadata(metadata)
        except (ET.ParseError, ValueError, KeyError, TypeError) as exc:
            return {
                "error": f"Failed to parse $metadata: {exc}",
                "code": "metadata_parse_failed",
                "model_id": model_id,
            }

        plan = _build_plan(question, dimensions, measures, top)
        plan["model_id"] = model_id
        plan["next_call"]["model_id"] = model_id
        return plan
