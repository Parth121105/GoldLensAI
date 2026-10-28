"""Synthetic validation: the engine finds injected mispricings and claims nothing on clean data.

Everything here is synthetic and generated in memory.
"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.research.synthetic_validation import cached_run, generate, summary


def test_generated_history_is_long_enough_and_labelled_synthetic():
    obs, injections = generate()
    assert {o.provenance.source_file for o in obs} == {"SYNTHETIC_validation_in_memory"}
    assert len({o.trade_date for o in obs}) > 686
    assert injections and all(10 <= abs(i.size_bps) <= 30 for i in injections)


def test_engine_catches_injected_mispricings_with_few_false_alarms():
    r = cached_run(True)
    assert all(v >= r.eligible_dates_needed for v in r.eligible_dates_by_pair.values())
    assert r.catch_rate is not None and r.catch_rate >= 0.7
    assert r.false_alarm_rate is not None and r.false_alarm_rate <= 0.02
    s = summary(r.trades)
    assert s["mean_net_bps"] > 0 and s["total_net_bps"] < s["total_gross_bps"]
    # Hedge-neutral spread P&L is not driven by the gold price.
    assert abs(s["corr_strategy_gold"]) < 0.3


def test_control_without_injections_validates_nothing():
    r = cached_run(False)
    assert r.injections_total == 0
    assert "historically_validated" not in r.verdicts.values()


def test_endpoint_is_labelled_synthetic():
    body = TestClient(create_app(frontend_dist=None)).get("/api/validation/synthetic").json()
    assert body["synthetic"] is True and "SYNTHETIC" in body["notice"]
    injected, control = body["runs"]
    assert injected["injected"] and not control["injected"]
    assert injected["round_trip_cost_bps"] == 9.6 and len(injected["cost_labels"]) == 4
