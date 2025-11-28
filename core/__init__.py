"""
Examina Core - AI-powered exam preparation library.

Main components:
- Analyzer: Exercise analysis and procedure extraction
- Tutor: AI tutoring with adaptive explanations
- QuizEngine: Quiz generation and evaluation
- MasteryAggregator: Progress tracking with SM-2
"""

from core.analyzer import ExerciseAnalyzer, AnalysisResult
from core.tutor import Tutor
from core.quiz_engine import QuizEngine
from core.mastery_aggregator import MasteryAggregator
from core.adaptive_teaching import AdaptiveTeachingManager
from core.provider_router import ProviderRouter
from core.task_types import TaskType
from core.answer_evaluator import RecallEvaluationResult
from core.note_splitter import NoteSplitter, NoteSection

__all__ = [
    "ExerciseAnalyzer",
    "AnalysisResult",
    "Tutor",
    "QuizEngine",
    "MasteryAggregator",
    "AdaptiveTeachingManager",
    "ProviderRouter",
    "TaskType",
    "RecallEvaluationResult",
    "NoteSplitter",
    "NoteSection",
]
