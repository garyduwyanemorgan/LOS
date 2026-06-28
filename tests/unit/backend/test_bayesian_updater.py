"""Unit tests for Bayesian confidence updater."""
from __future__ import annotations

import pytest

from backend.scientific_models.statistical.bayesian_updater import (
    bayesian_update_confidence,
    update_from_multiple_outcomes,
)


class TestBayesianUpdateConfidence:
    """Tests for single-observation Bayesian updates."""

    def test_success_increases_confidence(self) -> None:
        """Successful observation must increase confidence."""
        result = bayesian_update_confidence(prior=0.7, observed_success=True)
        assert result.posterior > result.prior

    def test_failure_decreases_confidence(self) -> None:
        """Failed observation must decrease confidence."""
        result = bayesian_update_confidence(prior=0.7, observed_success=False)
        assert result.posterior < result.prior

    def test_posterior_bounded_above(self) -> None:
        """Confidence must never reach 1.0 (max = 0.99)."""
        result = bayesian_update_confidence(prior=0.98, observed_success=True)
        assert result.posterior <= 0.99

    def test_posterior_bounded_below(self) -> None:
        """Confidence must never reach 0.0 (min = 0.05)."""
        result = bayesian_update_confidence(prior=0.06, observed_success=False)
        assert result.posterior >= 0.05

    def test_neutral_prior_shifts_correctly(self) -> None:
        """At 0.5 prior, a success with standard likelihoods should significantly update."""
        result = bayesian_update_confidence(
            prior=0.5,
            observed_success=True,
            likelihood_success=0.85,
            likelihood_failure=0.20,
        )
        # P(H|success) = 0.85*0.5 / (0.85*0.5 + 0.20*0.5) = 0.85/1.05 ≈ 0.81
        assert 0.75 < result.posterior < 0.90

    def test_evidence_strength_reflects_update_magnitude(self) -> None:
        """Evidence strength must equal absolute change in confidence."""
        result = bayesian_update_confidence(prior=0.6, observed_success=True)
        expected_strength = abs(result.posterior - result.prior)
        assert abs(result.evidence_strength - expected_strength) < 0.001


class TestMultipleOutcomes:
    """Tests for batch Bayesian updating."""

    def test_many_successes_raise_confidence(self) -> None:
        """Many successes must raise confidence substantially from low prior."""
        result = update_from_multiple_outcomes(prior=0.3, successes=10, failures=0)
        assert result.posterior > 0.85

    def test_many_failures_lower_confidence(self) -> None:
        """Many failures must lower confidence substantially from high prior."""
        result = update_from_multiple_outcomes(prior=0.9, successes=0, failures=10)
        assert result.posterior < 0.30

    def test_balanced_outcomes_near_prior(self) -> None:
        """Equal successes and failures with symmetric likelihoods stays near prior."""
        # symmetric: log(0.85/0.15) == -log(0.15/0.85), so balanced evidence cancels
        result = update_from_multiple_outcomes(
            prior=0.5, successes=5, failures=5,
            likelihood_success=0.85, likelihood_failure=0.15,
        )
        assert abs(result.posterior - 0.5) < 0.2

    def test_observation_count_recorded(self) -> None:
        """Total observation count must be successes + failures."""
        result = update_from_multiple_outcomes(prior=0.6, successes=3, failures=2)
        assert result.observations == 5
