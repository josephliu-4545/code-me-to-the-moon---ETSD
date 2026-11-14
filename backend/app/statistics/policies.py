from dataclasses import dataclass


@dataclass(frozen=True)
class AnnualAggregationPolicy:
    minimum_represented_months: int = 9
    minimum_valid_slot_coverage: float = 0.70
    require_all_quarters: bool = True
    exclude_partial_calendar_years_from_inference: bool = True
    minimum_observation_spatial_coverage: float | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_represented_months <= 12:
            raise ValueError("minimum represented months must be between 1 and 12")
        if not 0 <= self.minimum_valid_slot_coverage <= 1:
            raise ValueError("minimum valid slot coverage must be between 0 and 1")
        if self.minimum_observation_spatial_coverage is not None and not (
            0 <= self.minimum_observation_spatial_coverage <= 100
        ):
            raise ValueError("spatial coverage threshold must be between 0 and 100")


@dataclass(frozen=True)
class TrendPolicy:
    minimum_slope_years: int = 3
    minimum_significance_years: int = 8
    alpha: float = 0.05
    minimum_adjacent_residual_pairs: int = 6
    material_lag1_rho: float = 0.30

    def __post_init__(self) -> None:
        if self.minimum_slope_years < 3:
            raise ValueError("minimum slope years must be at least 3")
        if self.minimum_significance_years < self.minimum_slope_years:
            raise ValueError("significance threshold must not precede slope threshold")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be between 0 and 1")
        if self.minimum_adjacent_residual_pairs < 2:
            raise ValueError("minimum adjacent pairs must be at least 2")
        if not 0 <= self.material_lag1_rho <= 1:
            raise ValueError("material rho must be between 0 and 1")

