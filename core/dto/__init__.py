"""Data Transfer Objects for qupled-core business logic."""

from .mastery import (
    ExerciseReviewData,
    GapSeverity,
    MasteryLevel,
    MasteryTrend,
    TopicMasteryInput,
    TopicMasteryResult,
)
from .progress import (
    KnowledgeGap,
    LearningPathItem,
)

__all__ = [
    # Enums
    "MasteryLevel",
    "MasteryTrend",
    "GapSeverity",
    # Mastery DTOs
    "ExerciseReviewData",
    "TopicMasteryInput",
    "TopicMasteryResult",
    # Progress DTOs
    "KnowledgeGap",
    "LearningPathItem",
]
