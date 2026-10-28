"""Run the existing research engine over the session's imported data.

POST /api/research runs it; GET /api/research returns the latest run, which is
discarded as soon as the imported data changes.
"""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_store
from app.api.schemas import (
    CostComponentOut,
    CostsOut,
    DisplayParams,
    FindingOut,
    LegOut,
    OutcomeStatsOut,
    PairResultOut,
    PointLegOut,
    PointOut,
    ResearchConfigOut,
    ResearchRequest,
    ResearchResponse,
    SeriesOut,
    WindowOut,
)
from app.research import CostModel, MixedDataError, ResearchConfig, run_research
from app.research.pairs import Leg, PairSeries
from app.research.signals import Assessment, PointStatus, assess_series
from app.research.validation import OutcomeStats, PairValidation, WindowResult
from app.assumptions import cost_model
from app.store import DataKind, SessionStore

router = APIRouter(tags=["research"])

FINDING_STATUSES = frozenset({
    PointStatus.CANDIDATE_ANOMALY, PointStatus.STATISTICAL_ANOMALY, PointStatus.COST_ADJUSTED_CANDIDATE,
})
# Used to label points only when validation could not select parameters.
DEFAULT_DISPLAY_Z = 2.0


@router.post("/research", response_model=ResearchResponse)
async def run(request: ResearchRequest, store: SessionStore = Depends(get_store)) -> ResearchResponse:
    imports = store.snapshot()
    if not imports:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No data imported. Upload a CSV first.")
    try:
        costs = CostModel()
        for name, c in request.costs.items():
            costs = costs.with_component(name, c.bps_per_leg_side, c.source, c.as_of)
        config = ResearchConfig(horizon=request.horizon, costs=costs)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    try:
        response = await run_in_threadpool(_run, imports, config, store.kind.value)
    except MixedDataError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    # Kept only if the data did not change while it was computing (checked under the store lock).
    store.save_research(response.model_dump(mode="json"), imports)
    return response


@router.get("/research", response_model=ResearchResponse | None)
def latest(store: SessionStore = Depends(get_store)) -> ResearchResponse | None:
    """The latest research on the current data, or null if none has been run.

    "Not run yet" is a normal state, not a missing resource, so it is a 200 with a
    null body rather than a 404 that browsers and logs report as a failed request.
    """
    if store.research is None:
        return None
    return ResearchResponse.model_validate(store.research)


def run_with_assumptions(store: SessionStore) -> bool:
    """Run research on real data with the default settings and the assumed costs, and keep it.

    Called at startup and after each real-data upload, so real data is never shown without
    research. Synthetic sessions are left to the user. Returns True if a result was saved.
    """
    imports = store.snapshot()
    if not imports or store.kind is not DataKind.USER_UPLOADED:
        return False
    try:
        response = _run(imports, ResearchConfig(costs=cost_model()), store.kind.value)
    except MixedDataError:
        return False
    return store.save_research(response.model_dump(mode="json"), imports)


def _run(imports, config: ResearchConfig, kind: str) -> ResearchResponse:
    report = run_research(imports, config)
    series_by_pair: dict[str, list[PairSeries]] = defaultdict(list)
    for s in report.series:
        series_by_pair[s.symbol_pair].append(s)

    pairs = [_pair(v, series_by_pair[v.symbol_pair], config) for v in report.validations]
    span = report.trade_date_range
    return ResearchResponse(
        generated_at=report.generated_at,
        kind=kind,
        sources=[s.name for s in report.sources],
        observations=report.observations,
        trade_date_from=span[0] if span else None,
        trade_date_to=span[1] if span else None,
        cross_file_conflicts=report.cross_file_conflicts,
        config=ResearchConfigOut(
            price_field=config.price_field.value,
            horizon=config.horizon,
            z_thresholds=list(config.z_thresholds),
            baseline_windows=list(config.baseline_windows),
            holdout_fraction=config.holdout_fraction,
            n_folds=config.n_folds,
            min_events=config.min_events,
            min_t_stat=config.min_t_stat,
            max_expiry_gap_days=config.max_expiry_gap_days,
            min_volume=config.min_volume,
            lifecycle_buffer_days=config.lifecycle_buffer_days,
            allow_unverified_specs=config.allow_unverified_specs,
        ),
        costs=CostsOut(
            components=[
                CostComponentOut(name=c.name, known=c.known, bps_per_leg_side=c.bps_per_leg_side,
                                 source=c.source, as_of=c.as_of, label=c.label)
                for c in config.costs.components
            ],
            round_trip_bps=config.costs.round_trip_bps(),
            unknown_components=list(config.costs.unknown_components),
        ),
        pairs=pairs,
    )


def _pair(v: PairValidation, series: list[PairSeries], config: ResearchConfig) -> PairResultOut:
    if v.final and v.final.params:
        z, window = v.final.params
        selected_by = "Selected on the development period by walk-forward validation"
    else:
        z = DEFAULT_DISPLAY_Z if DEFAULT_DISPLAY_Z in config.z_thresholds else config.z_thresholds[0]
        window = config.baseline_windows[0]
        selected_by = "Default labelling parameters; validation could not select any (not validated)"

    series_out, findings = [], []
    for s in series:
        assessed = assess_series(s, z_threshold=z, window=window, costs=config.costs)
        series_out.append(_series(s, assessed))
        for a in assessed:
            if a.point.eligible and a.status in FINDING_STATUSES:
                findings.append(FindingOut(
                    symbol_pair=s.symbol_pair, pair_id=s.pair_id, trade_date=a.point.trade_date,
                    status=a.status.value, spread_bps=a.point.spread_bps,
                    deviation_bps=a.deviation_bps, z_score=a.z_score,
                    resolution_bps=a.point.resolution_bps, round_trip_cost_bps=a.round_trip_cost_bps,
                    net_edge_bps=a.net_edge_bps, notes=list(a.notes),
                    leg_a=_leg(a.point.leg_a), leg_b=_leg(a.point.leg_b),
                ))
    findings.sort(key=lambda f: (f.trade_date, f.pair_id), reverse=True)

    return PairResultOut(
        symbol_pair=v.symbol_pair,
        verdict=v.verdict.value,
        reasons=v.reasons,
        eligible_dates=v.eligible_dates,
        development_from=v.development[0] if v.development else None,
        development_to=v.development[1] if v.development else None,
        holdout_from=v.holdout[0] if v.holdout else None,
        holdout_to=v.holdout[1] if v.holdout else None,
        folds=[_window(f) for f in v.folds],
        final=_window(v.final) if v.final else None,
        sensitivity={k: _stats(s) for k, s in v.sensitivity.items()},
        display_params=DisplayParams(z_threshold=z, baseline_window=window, selected_by=selected_by),
        findings=findings,
        series=series_out,
    )


def _series(s: PairSeries, assessed: list[Assessment]) -> SeriesOut:
    reasons: dict[str, int] = defaultdict(int)
    for p in s.points:
        for code in p.ineligible_codes:
            reasons[code] += 1
    return SeriesOut(
        pair_id=s.pair_id, symbol_pair=s.symbol_pair, contract_a=s.contract_a, contract_b=s.contract_b,
        expiry_a=s.expiry_a, expiry_b=s.expiry_b, comparison_type=s.comparison_type.value,
        expiry_gap_days=s.expiry_gap_days, aligned_dates=len(s.points),
        eligible_dates=len(s.eligible_points), dates_missing_a=s.dates_missing_a,
        dates_missing_b=s.dates_missing_b, unusable=[f"{d}: {r}" for d, r in s.unusable],
        ineligible_reasons=dict(reasons),
        points=[
            PointOut(
                trade_date=a.point.trade_date, spread_bps=a.point.spread_bps,
                resolution_bps=a.point.resolution_bps, days_to_nearer_expiry=a.point.days_to_nearer_expiry,
                eligible=a.point.eligible, ineligible_reasons=list(a.point.ineligible_reasons),
                status=a.status.value, baseline_n=a.baseline_n, baseline_mean_bps=a.baseline_mean_bps,
                baseline_std_bps=a.baseline_std_bps, deviation_bps=a.deviation_bps, z_score=a.z_score,
                round_trip_cost_bps=a.round_trip_cost_bps, net_edge_bps=a.net_edge_bps,
                notes=list(a.notes), leg_a=_point_leg(a.point.leg_a), leg_b=_point_leg(a.point.leg_b),
            )
            for a in assessed
        ],
    )


def _leg(leg: Leg) -> LegOut:
    return LegOut(
        contract_id=leg.contract_id, raw_price=str(leg.raw_price), per_gram_999=str(leg.per_gram_999),
        volume=leg.volume, spec_version_id=leg.spec_version_id, spec_status=leg.spec_status.value,
        source_file=leg.source_file, line_number=leg.line_number,
    )


def _point_leg(leg: Leg) -> PointLegOut:
    return PointLegOut(
        contract_id=leg.contract_id, raw_price=str(leg.raw_price),
        per_gram_999=str(leg.per_gram_999), volume=leg.volume,
    )


def _window(w: WindowResult) -> WindowOut:
    return WindowOut(
        label=w.label, train_from=w.train[0], train_to=w.train[1], test_from=w.test[0], test_to=w.test[1],
        z_threshold=w.params[0] if w.params else None, baseline_window=w.params[1] if w.params else None,
        train_signals=w.train_signals, signals=_stats(w.signals), controls=_stats(w.controls),
        status=w.status,
    )


def _stats(s: OutcomeStats) -> OutcomeStatsOut:
    return OutcomeStatsOut(
        n=s.n, mean_gross_bps=s.mean_gross_bps, std_gross_bps=s.std_gross_bps,
        t_stat_gross=s.t_stat_gross, hit_rate=s.hit_rate, mean_net_bps=s.mean_net_bps,
        t_stat_net=s.t_stat_net,
    )
