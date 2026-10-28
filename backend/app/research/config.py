"""Research parameters. Defaults are documented conventions, not financial truths.

See docs/methodology/research.md for the reasoning behind each default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.assumptions import default_assumptions
from app.normalization import PriceField
from app.research.costs import CostModel


@dataclass(frozen=True, slots=True)
class ResearchConfig:
    # Which published price to compare. Close is MCX's last-half-hour weighted
    # average; settlement is not an executable trade price.
    price_field: PriceField = PriceField.CLOSE

    # Contracts are paired only if their expiries are at most this far apart.
    # GOLDM expires on the 5th, the others at month-end, so 0 would exclude GOLDM.
    # Default read from backend/config/assumptions.json (pairing.max_expiry_gap_days).
    max_expiry_gap_days: int = field(default_factory=lambda: default_assumptions().max_expiry_gap_days)

    # Both legs must report at least this volume (file units) on the date.
    # Volume is a liquidity proxy only; it says nothing about order-book depth.
    min_volume: int = 1

    # Exclude dates this close to the nearer expiry (staggered delivery tender
    # period is the last 3-5 trading days per MCX circulars). Default read from
    # backend/config/assumptions.json (lifecycle.expiry_buffer_days).
    lifecycle_buffer_days: int = field(default_factory=lambda: default_assumptions().expiry_buffer_days)

    allow_unverified_specs: bool = False

    # Hypothesis horizon: outcome measured this many eligible observations later.
    horizon: int = 5

    # Candidate parameter grid; values are chosen only on training data.
    z_thresholds: tuple[float, ...] = (1.5, 2.0, 2.5)
    baseline_windows: tuple[int, ...] = (10, 20)

    holdout_fraction: float = 0.3
    n_folds: int = 3

    # Minimum non-overlapping signal events before any statistic is reported.
    min_events: int = 20
    # Minimum t-statistic for the mean outcome to count as supported.
    min_t_stat: float = 2.0

    costs: CostModel = field(default_factory=CostModel)

    def __post_init__(self) -> None:
        if self.max_expiry_gap_days < 0:
            raise ValueError("max_expiry_gap_days must be >= 0")
        if self.min_volume < 0:
            raise ValueError("min_volume must be >= 0")
        if self.lifecycle_buffer_days < 0:
            raise ValueError("lifecycle_buffer_days must be >= 0")
        if self.horizon < 1:
            raise ValueError("horizon must be >= 1")
        if not self.z_thresholds or any(z <= 0 for z in self.z_thresholds):
            raise ValueError("z_thresholds must be positive")
        if not self.baseline_windows or any(w < 3 for w in self.baseline_windows):
            raise ValueError("baseline_windows must each be >= 3")
        if not 0 < self.holdout_fraction < 1:
            raise ValueError("holdout_fraction must be between 0 and 1")
        if self.n_folds < 1:
            raise ValueError("n_folds must be >= 1")
        if self.min_events < 2:
            raise ValueError("min_events must be >= 2")

    @property
    def parameter_grid(self) -> list[tuple[float, int]]:
        """(z_threshold, baseline_window) pairs in a fixed order, used for deterministic tie-breaks."""
        return [(z, w) for w in self.baseline_windows for z in self.z_thresholds]
