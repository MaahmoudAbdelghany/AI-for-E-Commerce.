"""Configurable deterministic scoring parameters for Top-3 value ranking."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScoringConfig(BaseModel):
    """Typed parameters governing value scoring, Bayesian priors, and outlier guards."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    price_weight: float = Field(default=0.55, ge=0.0, le=1.0, allow_inf_nan=False)
    rating_weight: float = Field(default=0.45, ge=0.0, le=1.0, allow_inf_nan=False)
    bayesian_prior_count: int = Field(default=25, gt=0)
    bayesian_prior_mean: float = Field(default=4.0, ge=0.0, le=5.0, allow_inf_nan=False)
    unrated_prior_rating: float = Field(default=3.4, ge=0.0, le=5.0, allow_inf_nan=False)
    price_floor_ratio: float = Field(default=0.15, gt=0.0, lt=1.0, allow_inf_nan=False)
    price_ceiling_ratio: float = Field(default=3.0, gt=1.0, allow_inf_nan=False)
    min_candidates_for_outlier_guard: int = Field(default=3, ge=1)
    top_k: int = Field(default=3, ge=1)

    @model_validator(mode="after")
    def _validate_weights_and_ratios(self) -> Self:
        weight_sum = self.price_weight + self.rating_weight
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"price_weight + rating_weight must equal 1.0 within 1e-6 (got {weight_sum})"
            )
        if self.price_floor_ratio >= self.price_ceiling_ratio:
            raise ValueError("price_floor_ratio must be strictly less than price_ceiling_ratio")
        return self
