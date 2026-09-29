"""Model schema discovery for the Data Export Service.

SAC serves ``$metadata`` as EDMX/CSDL **XML** (it ignores ``Accept:
application/json``), so it has to be parsed as XML. In the ``FactData``
entity type the key properties are the model's dimensions and the remaining
properties are its measures — SAC enforces the same split when it rejects a
``$select`` that omits a key column (error 1402).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

from sac_mcp.client.paths import des_path

if TYPE_CHECKING:
    from sac_mcp.client.http import SACClient

_NUMERIC_EDM = {
    "Edm.Double", "Edm.Decimal", "Edm.Single",
    "Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Byte",
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_edmx(xml_text: str) -> dict[str, Any]:
    """Return ``{"entity_types": {name: {keys, properties}}, "entity_sets": {set: type}}``."""

    root = ET.fromstring(xml_text)
    types: dict[str, dict[str, Any]] = {}
    sets: dict[str, str] = {}
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "EntityType":
            keys = [
                ref.attrib["Name"]
                for key in el
                if _local(key.tag) == "Key"
                for ref in key
                if _local(ref.tag) == "PropertyRef" and "Name" in ref.attrib
            ]
            props = {
                p.attrib["Name"]: p.attrib.get("Type", "")
                for p in el
                if _local(p.tag) == "Property" and "Name" in p.attrib
            }
            types[el.attrib.get("Name", "")] = {"keys": keys, "properties": props}
        elif tag == "EntitySet" and "Name" in el.attrib:
            sets[el.attrib["Name"]] = el.attrib.get("EntityType", "").rsplit(".", 1)[-1]
    return {"entity_types": types, "entity_sets": sets}


def split_fact_type(schema: dict[str, Any]) -> tuple[list[str], list[str]]:
    """``(dimensions, measures)`` of the model's FactData entity type."""

    types: dict[str, dict[str, Any]] = schema.get("entity_types", {})
    type_name = schema.get("entity_sets", {}).get("FactData")
    fact = types.get(type_name or "")
    if fact is None:  # fall back to the most FactData-looking type
        candidates = [t for n, t in types.items() if n.startswith("FactData") and "Aggr" not in n]
        fact = candidates[0] if candidates else next(iter(types.values()), None)
    if fact is None:
        return [], []
    props: dict[str, str] = fact["properties"]
    keys: list[str] = fact["keys"]
    if keys:
        return list(keys), [p for p in props if p not in keys]
    measures = [p for p, t in props.items() if t in _NUMERIC_EDM]
    return [p for p in props if p not in measures], measures


def _split_sample_row(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    measures = [
        k for k, v in row.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool) and not k.startswith("@")
    ]
    dims = [k for k in row if k not in measures and not k.startswith("@")]
    return dims, measures


async def describe_model(client: SACClient, model_id: str) -> dict[str, Any]:
    """Dimensions, measures and entity sets of one model."""

    service = await client.get_json(des_path(model_id))
    set_names = [
        str(v.get("name")) for v in (service or {}).get("value", []) if isinstance(v, dict)
    ] if isinstance(service, dict) else []

    notes: list[str] = []
    source = "metadata"
    try:
        _ctype, xml_text = await client.get_text(
            des_path(model_id) + "$metadata", accept="application/xml"
        )
        dims, measures = split_fact_type(parse_edmx(xml_text))
    except ET.ParseError:
        dims, measures = [], []
    if not dims and not measures:
        # Unreadable $metadata: infer from one fact row (numbers = measures).
        source = "sample_row"
        sample = await client.get_json(des_path(model_id, "FactData"), params={"$top": 1})
        rows = sample.get("value", []) if isinstance(sample, dict) else []
        if rows and isinstance(rows[0], dict):
            dims, measures = _split_sample_row(rows[0])
        notes.append("Schema inferred from a sample row; $metadata could not be parsed.")

    dimensions = [
        {
            "name": d,
            "members_entity_set": f"{d}Master" if f"{d}Master" in set_names else None,
            "has_hierarchy": f"{d}MasterWithHierarchy" in set_names,
        }
        for d in dims
    ]
    account = next((d for d in dims if "account" in d.lower()), None)
    if account:
        notes.append(
            f"Account-based model: line items are members of '{account}' "
            f"(list_dimension_members(model_id, '{account}')). Filter to one account "
            "before summing a measure, or totals mix unrelated accounts."
        )
    return {
        "model_id": model_id,
        "dimensions": dimensions,
        "measures": measures,
        "account_dimension": account,
        "entity_sets": set_names,
        "schema_source": source,
        "notes": notes,
    }
