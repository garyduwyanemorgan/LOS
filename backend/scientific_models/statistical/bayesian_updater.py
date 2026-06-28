"""Bayesian confidence updating for scientific relationships and predictions.

Used by the Learning Service to update SRG confidence scores
based on observed intervention outcomes.

The Bayesian update is bounded: confidence never reaches 0 or 1,
preserving the ability to update from new evidence indefinitely.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BayesianUpdate:
    """Result of a Bayesian confidence update."""
    prior: float
    likelihood_success: float
    likelihood_failure: float
    posterior: float
    evidence_strength: float    # 0-1, how much this update moved the belief
    observations: int


def bayesian_update_confidence(
    prior: float,
    observed_success: bool,
    likelihood_success: float = 0.85,
    likelihood_failure: float = 0.20,
    min_confidence: float = 0.05,
    max_confidence: float = 0.99,
) -> BayesianUpdate:
    """
    Bayesian update of a confidence score given an intervention outcome.

    Uses Bayes' theorem:
        P(H|E) = P(E|H) · P(H) / P(E)

    where:
        H = "this scientific relationship is correct"
        E = "the intervention outcome matched prediction"

    Args:
        prior: Current confidence (0-1)
        observed_success: True if the intervention outcome matched prediction
        likelihood_success: P(outcome matches | relationship correct)
        likelihood_failure: P(outcome matches | relationship incorrect)
        min_confidence: Lower bound on confidence (prevents zero)
        max_confidence: Upper bound on confidence (prevents certainty)

    Returns:
        BayesianUpdate with posterior confidence
    """
    # Clamp prior to valid range
    prior = max(min_confidence, min(max_confidence, prior))

    if observed_success:
        # P(E|H) = likelihood_success
        # P(E|¬H) = likelihood_failure
        numerator = likelihood_success * prior
        denominator = (likelihood_success * prior) + (likelihood_failure * (1.0 - prior))
    else:
        # Failure update: swap likelihoods
        # P(failure|H) = 1 - likelihood_success
        # P(failure|¬H) = 1 - likelihood_failure
        l_h = 1.0 - likelihood_success
        l_not_h = 1.0 - likelihood_failure
        numerator = l_h * prior
        denominator = (l_h * prior) + (l_not_h * (1.0 - prior))

    posterior = numerator / denominator if denominator > 0 else prior

    # Apply bounds
    posterior = max(min_confidence, min(max_confidence, posterior))

    # Evidence strength = absolute change in confidence
    evidence_strength = abs(posterior - prior)

    return BayesianUpdate(
        prior=round(prior, 4),
        likelihood_success=likelihood_success,
        likelihood_failure=likelihood_failure,
        posterior=round(posterior, 4),
        evidence_strength=round(evidence_strength, 4),
        observations=1,
    )


def update_from_multiple_outcomes(
    prior: float,
    successes: int,
    failures: int,
    likelihood_success: float = 0.85,
    likelihood_failure: float = 0.20,
) -> BayesianUpdate:
    """
    Update confidence from a batch of past outcomes.

    Applies sequential Bayesian updates for each success and failure.

    Args:
        prior: Initial confidence
        successes: Number of times prediction was correct
        failures: Number of times prediction was incorrect
    """
    current = prior
    # Interleave successes and failures to avoid order-dependent extremes
    interleaved: list[bool] = []
    s_pool = [True] * successes
    f_pool = [False] * failures
    while s_pool or f_pool:
        if s_pool:
            interleaved.append(s_pool.pop())
        if f_pool:
            interleaved.append(f_pool.pop())
    for success in interleaved:
        result = bayesian_update_confidence(
            current, observed_success=success,
            likelihood_success=likelihood_success,
            likelihood_failure=likelihood_failure,
        )
        current = result.posterior

    return BayesianUpdate(
        prior=round(prior, 4),
        likelihood_success=likelihood_success,
        likelihood_failure=likelihood_failure,
        posterior=round(current, 4),
        evidence_strength=round(abs(current - prior), 4),
        observations=successes + failures,
    )
