"""Unit tests for the OData query builder."""

from __future__ import annotations

from sac_mcp.client.odata import (
    ODataQuery,
    and_,
    contains,
    eq,
    gt,
    or_,
    quote_odata_string,
    starts_with,
)


def test_quote_escapes_single_quote() -> None:
    assert quote_odata_string("O'Brien") == "'O''Brien'"


def test_eq_string_and_int() -> None:
    assert eq("Year", 2025) == "Year eq 2025"
    assert eq("Country", "DE") == "Country eq 'DE'"


def test_contains_starts_with() -> None:
    assert contains("Name", "alpha") == "contains(Name,'alpha')"
    assert starts_with("Name", "alp") == "startswith(Name,'alp')"


def test_and_or_grouping() -> None:
    assert and_(eq("a", 1), gt("b", 2)) == "(a eq 1) and (b gt 2)"
    assert or_(eq("a", 1), eq("a", 2)) == "(a eq 1) or (a eq 2)"
    assert and_(eq("a", 1)) == "a eq 1"
    assert and_() == ""


def test_query_to_params_orders_keys() -> None:
    q = ODataQuery(
        filter="Year eq 2025",
        select=["Year", "Amount"],
        orderby=["Amount desc"],
        top=50,
        skip=100,
    )
    params = q.to_params()
    assert params["$filter"] == "Year eq 2025"
    assert params["$select"] == "Year,Amount"
    assert params["$orderby"] == "Amount desc"
    assert params["$top"] == "50"
    assert params["$skip"] == "100"


def test_query_omits_unset_fields() -> None:
    assert ODataQuery().to_params() == {}
