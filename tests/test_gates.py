"""M2 unit tests: invented ID rejected, bad measure repaired, wrong filter caught by the finish gate,
read-before-write enforced, loops and budget stopped. These need the WWI app on :8017 only for the Contract."""
from __future__ import annotations

import pytest

from agent.adapters.wwi import WWIBackend
from agent.config import Config
from agent.contract import Contract
from agent.facts import derive
from agent.finish import Expectation, check_numbers, finish_checks
from agent.gates import Gates
from agent.session import Call, Session
from agent.slots import PeriodSpec, resolve_period, shift_period
from datetime import date


@pytest.fixture(scope="module")
def contract():
    cfg = Config()
    return Contract(WWIBackend(cfg.wwi_url, cfg.wwi_package).contract())


@pytest.fixture()
def env(contract):
    s = Session()
    return s, Gates(contract, s, step_budget=8)


MAY_VS_APR = {"measure_id": "M01", "start": "2016-05-01", "end": "2016-06-01",
              "compare_start": "2016-04-01", "compare_end": "2016-05-01", "group_by": "sales_territory"}


def test_valid_call_passes(env):
    s, g = env
    v = g.check("analyze", MAY_VS_APR, [], 0)
    assert v.ok and v.args["date_basis"] == "order_date"


def test_invented_id_rejected(env):
    s, g = env
    v = g.check("analyze", {**MAY_VS_APR, "filters": {"customer_id": 4242}}, [], 0)
    assert not v.ok and v.gate == "grounding" and "resolve" in v.hint()


def test_id_from_resolve_or_user_text_accepted(env):
    s, g = env
    s.registry.add("customer", 950, "resolve")
    assert g.check("analyze", {**MAY_VS_APR, "filters": {"customer_id": 950}}, [], 0).ok
    s.registry.add_user_text("show item 80 please")
    assert g.check("analyze", {"measure_id": "M02", "filters": {"stock_item_id": 80}}, [], 0).ok


def test_bad_measure_gets_repair_hint(env):
    s, g = env
    v = g.check("analyze", {"measure_id": "M99"}, [], 0)
    assert not v.ok and v.gate == "schema" and "M01" in v.hint()


def test_bad_date_and_inverted_period(env):
    s, g = env
    assert not g.check("analyze", {"measure_id": "M01", "start": "May 2016", "end": "2016-06-01"}, [], 0).ok
    v = g.check("analyze", {"measure_id": "M01", "start": "2016-06-01", "end": "2016-05-01"}, [], 0)
    assert not v.ok and "before end" in v.hint()


def test_invalid_combination_m05_by_customer(env):
    s, g = env
    v = g.check("analyze", {"measure_id": "M05", "group_by": "customer_category"}, [], 0)
    assert not v.ok and "cannot be broken down" in v.hint()
    s.registry.add("customer", 950, "resolve")
    v = g.check("analyze", {"measure_id": "M05", "filters": {"customer_id": 950}}, [], 0)
    assert not v.ok and "cannot be used with M05" in v.hint()


def test_sort_by_change_needs_comparison(env):
    s, g = env
    v = g.check("analyze", {"measure_id": "M01", "sort": "change_desc"}, [], 0)
    assert not v.ok and "comparison" in v.hint()


def test_unknown_tool_and_open_page_decoy(env):
    s, g = env
    assert not g.check("delete_everything", {}, [], 0).ok
    v = g.check("open_page", {"page": "decoy-purchase-returns"}, [], 0)
    assert not v.ok and "does not exist" in v.hint()


def test_loop_detector(env):
    s, g = env
    done = Call("analyze", MAY_VS_APR, True, {})
    v = g.check("analyze", MAY_VS_APR, [done], 1)
    assert not v.ok and v.gate == "loop"


def test_step_budget(env):
    s, g = env
    assert g.check("analyze", MAY_VS_APR, [], 8).gate == "budget"


def test_read_before_write_with_fake_tool(contract):
    s = Session()
    g = Gates(contract, s, state_changing={"update_order"})
    v = g.check.__func__  # noqa: F841 - silence linter; real call below
    bad = g._read_before_write("update_order", {"id": 7}, [], confirmed=False)
    assert not bad.ok and len(bad.messages) == 2
    read = Call("related", {"entity_type": "order", "entity_id": 7}, True, {})
    still = g._read_before_write("update_order", {"id": 7}, [read], confirmed=False)
    assert not still.ok and "confirm" in still.messages[0]
    assert g._read_before_write("update_order", {"id": 7}, [read], confirmed=True).ok


def test_gates_off_lets_everything_through(contract):
    g = Gates(contract, Session(), enabled=False)
    assert g.check("analyze", {"measure_id": "M99"}, [], 0).ok


# ------------------------------------------------------------------ finish gate
def _applied(**kw):
    base = {"measure_id": "M01", "date_basis": "order_date", "start": "2016-05-01", "end": "2016-06-01",
            "group_by": "none", "filters": {"customer_id": None, "status": "all"}, "sort": "value_desc", "top_n": 10,
            "scenario_id": "base"}
    base.update(kw)
    return base


def test_finish_gate_catches_wrong_filter(contract):
    exp = Expectation("analyze", request={"measure_id": "M01", "start": "2016-05-01", "end": "2016-06-01", "filters": {}})
    ok = Call("analyze", {}, True, {"total": 5}, applied=_applied())
    assert finish_checks(exp, [ok], contract, 1, 8).ok
    wrong = Call("analyze", {}, True, {"total": 5}, applied=_applied(filters={"customer_id": 5, "status": "all"}))
    rep = finish_checks(exp, [wrong], contract, 1, 8)
    assert not rep.ok and "customer_id" in rep.violations[0].message
    wrong_period = Call("analyze", {}, True, {"total": 5}, applied=_applied(start="2016-04-01", end="2016-05-01"))
    assert not finish_checks(exp, [wrong_period], contract, 1, 8).ok


def test_finish_gate_requires_a_call_and_detects_loops(contract):
    exp = Expectation("analyze", request={"measure_id": "M01"})
    assert finish_checks(exp, [], contract, 0, 8).violations[0].code == "no_call"
    c = Call("analyze", {"measure_id": "M01"}, True, {}, applied=_applied(start=None, end=None))
    rep = finish_checks(exp, [c, c], contract, 2, 8)
    assert any(v.code == "loop" for v in rep.violations)
    assert any(v.code == "budget" for v in finish_checks(exp, [c], contract, 9, 8).violations)


def test_faithfulness_numbers(contract):
    data = {"measure": {"id": "M01", "name": "Orders created", "unit": "orders"}, "dimension": {"id": "none", "additive": None},
            "applied": _applied(compare_start="2016-04-01", compare_end="2016-05-01"),
            "total_baseline": 1951, "total_current": 2047, "change": 96, "pct_change": 4.92}
    call = Call("analyze", {}, True, data, applied=data["applied"])
    facts = derive([call], contract)
    assert not check_numbers("Orders rose by 96 (4.92%) to 2,047 from 1,951.", facts, [call], "orders in May 2016?")
    bad = check_numbers("Orders rose by 97 to 2,100.", facts, [call], "orders in May 2016?")
    assert bad and "97" in bad[0].message and "2,100" in bad[0].message


# ------------------------------------------------------------------ calendar maths (done in code, never by the LLM)
def test_period_resolution():
    ref, mx = date(2016, 5, 31), date(2016, 6, 21)
    assert resolve_period(PeriodSpec(kind="month", year=2016, month=5), ref, mx) == ("2016-05-01", "2016-06-01")
    assert resolve_period(PeriodSpec(kind="quarter", year=2016, quarter=1), ref, mx) == ("2016-01-01", "2016-04-01")
    assert resolve_period(PeriodSpec(kind="month_range", year=2016, month=1, end_month=3), ref, mx) == ("2016-01-01", "2016-04-01")
    assert resolve_period(PeriodSpec(kind="last_month"), ref, mx) == ("2016-04-01", "2016-05-01")
    assert resolve_period(PeriodSpec(kind="year", year=2016), ref, mx) == ("2016-01-01", "2016-06-21")
    assert resolve_period(PeriodSpec(kind="last_n_months", n=3), ref, mx) == ("2016-03-01", "2016-06-01")
    assert shift_period("2016-05-01", "2016-06-01", "previous_period") == ("2016-04-01", "2016-05-01")
    assert shift_period("2016-01-01", "2016-04-01", "previous_period") == ("2015-10-01", "2016-01-01")
    assert shift_period("2016-05-01", "2016-06-01", "same_period_last_year") == ("2015-05-01", "2015-06-01")
