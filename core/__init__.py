"""
Examina Core - AI-powered exam preparation library.

Main components:
- Analyzer: Exercise analysis and procedure extraction
- Tutor: AI tutoring with adaptive explanations
- ReviewEngine: Answer evaluation and exercise generation
"""

from core.analyzer import ExerciseAnalyzer, AnalysisResult
from core.tutor import Tutor
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
