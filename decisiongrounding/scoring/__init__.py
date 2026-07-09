"""Deterministic scoring, metric aggregation, and the crossover artifact."""

from .metrics import (
    ArmMetrics,
    adherence_variance,
    aggregate,
    mean_ci,
    recall_rate,
    summarize,
    t_critical_95,
)
from .scorer import Score, score
from .snr import signal_to_noise

__all__ = [
    "Score",
    "score",
    "signal_to_noise",
    "ArmMetrics",
    "aggregate",
    "adherence_variance",
    "recall_rate",
    "mean_ci",
    "summarize",
    "t_critical_95",
]
