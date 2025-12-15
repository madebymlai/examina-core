"""
Examina Core - AI-powered exam preparation library.

Main components:
- Analyzer: Exercise analysis and procedure extraction
- Tutor: AI tutoring with adaptive explanations
- QuizEngine: Quiz generation and evaluation
- ReviewEngine: Answer evaluation and exercise generation
"""

from core.analyzer import ExerciseAnalyzer, AnalysisResult
from core.tutor import Tutor
from core.quiz_engine import QuizEngine
from core.provider_router import ProviderRouter
from core.task_types import TaskType
from core.answer_evaluator import RecallEvaluationResult
from core.note_splitter import NoteSplitter, NoteSection
from core.review_engine import (
    ReviewEngine,
    GeneratedExercise,
    ReviewEvaluation,
    ExerciseExample,
    score_to_quality,
    calculate_mastery,
)

__all__ = [
    "ExerciseAnalyzer",
    "AnalysisResult",
    "Tutor",
    "QuizEngine",
    "ProviderRouter",
    "TaskType",
    "RecallEvaluationResult",
    "NoteSplitter",
    "NoteSection",
    # Review Mode v2
    "ReviewEngine",
    "GeneratedExercise",
    "ReviewEvaluation",
    "ExerciseExample",
    "score_to_quality",
    "calculate_mastery",
]
