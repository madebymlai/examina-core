"""Database-agnostic answer evaluation.

This module provides answer evaluation logic that can be used with any LLM backend.
Supports two modes:
- QUIZ: Structured scoring with JSON output (is_correct, score, feedback)
- LEARN: Pedagogical feedback focused on learning (hints, encouragement)

Extracted from examina-cloud/backend/app/api/v1/quiz.py and learn.py to enable:
- Reuse across CLI and web
- Consistent evaluation behavior
- Clean separation of evaluation logic from data access
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class EvaluationMode(Enum):
    """Mode for answer evaluation."""
    QUIZ = "quiz"      # Structured scoring with JSON output
    LEARN = "learn"    # Pedagogical feedback, hints, encouragement


@dataclass(frozen=True)
class EvaluationResult:
    """Result of answer evaluation.

    Attributes:
        is_correct: Whether the answer is substantially correct (QUIZ mode)
        score: Score from 0.0 to 1.0 (QUIZ mode)
        feedback: Feedback text explaining the evaluation
        hint: Optional hint if answer was wrong and hints requested (LEARN mode)
    """
    is_correct: Optional[bool]
    score: Optional[float]
    feedback: str
    hint: Optional[str] = None


class LLMInterface(Protocol):
    """Protocol for LLM generation.

    Any LLM manager implementing this interface can be used with AnswerEvaluator.
    """

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The prompt to send to the LLM
            model: Optional model override
            system: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            json_mode: Whether to request JSON output

        Returns:
            The generated text response
        """
        ...


class AnswerEvaluator:
    """Database-agnostic answer evaluator.

    Provides two evaluation modes:
    - QUIZ: Returns structured JSON with is_correct, score, feedback
    - LEARN: Returns pedagogical feedback with optional hints

    Usage:
        evaluator = AnswerEvaluator(llm_manager)
        result = evaluator.evaluate(
            question="What is 2+2?",
            student_answer="4",
            mode=EvaluationMode.QUIZ,
            expected_solution="4",
        )
    """

    def __init__(self, llm: LLMInterface):
        """Initialize with LLM interface.

        Args:
            llm: LLM manager implementing generate() method
        """
        self._llm = llm

    # ==================== PUBLIC METHODS ====================

    def evaluate(
        self,
        question: str,
        student_answer: str,
        mode: EvaluationMode = EvaluationMode.QUIZ,
        expected_solution: Optional[str] = None,
        provide_hints: bool = False,
    ) -> EvaluationResult:
        """Evaluate a student answer.

        Args:
            question: The question text
            student_answer: The student's answer
            mode: QUIZ for scoring, LEARN for pedagogical feedback
            expected_solution: Expected solution (optional but improves accuracy)
            provide_hints: Whether to include hints in LEARN mode

        Returns:
            EvaluationResult with feedback and optionally score
        """
        if mode == EvaluationMode.QUIZ:
            return self._evaluate_quiz(
                question=question,
                student_answer=student_answer,
                expected_solution=expected_solution,
            )
        else:
            return self._evaluate_learn(
                question=question,
                student_answer=student_answer,
                expected_solution=expected_solution,
                provide_hints=provide_hints,
            )

    # ==================== PRIVATE METHODS ====================

    def _evaluate_quiz(
        self,
        question: str,
        student_answer: str,
        expected_solution: Optional[str],
    ) -> EvaluationResult:
        """Evaluate in QUIZ mode with structured scoring.

        Returns JSON with is_correct, score, feedback.
        Falls back to keyword matching if JSON parsing fails.
        """
        solution_text = expected_solution or "No solution provided"

        prompt = f"""Evaluate this student answer to a quiz question.

Question: {question}

Expected Solution: {solution_text}

Student Answer: {student_answer}

Provide a JSON response with:
- "is_correct": true/false (true if answer is substantially correct)
- "score": 0.0 to 1.0 (0 = completely wrong, 1 = perfect)
- "feedback": brief feedback explaining the evaluation

Respond ONLY with valid JSON, no other text."""

        try:
            response = self._llm.generate(prompt)
            return self._parse_quiz_response(
                response=response,
                student_answer=student_answer,
                expected_solution=expected_solution,
            )
        except Exception:
            # Fallback to simple keyword comparison
            return self._fallback_quiz_evaluation(
                student_answer=student_answer,
                expected_solution=expected_solution,
            )

    def _evaluate_learn(
        self,
        question: str,
        student_answer: str,
        expected_solution: Optional[str],
        provide_hints: bool,
    ) -> EvaluationResult:
        """Evaluate in LEARN mode with pedagogical feedback.

        Returns encouraging feedback with optional hints.
        """
        hint_instruction = ""
        if provide_hints and expected_solution:
            hint_instruction = (
                f"\n\nIf the answer is wrong, provide a hint to guide the "
                f"student towards the correct answer. The expected solution "
                f"is: {expected_solution}"
            )

        prompt = f"""Evaluate this student's practice answer.

Question: {question}

Student Answer: {student_answer}
{hint_instruction}

Provide helpful, encouraging feedback. If the answer is correct, acknowledge it. \
If incorrect, explain what's missing or wrong without giving away the full solution \
unless hints are requested.

Keep your response concise (2-4 sentences)."""

        try:
            feedback = self._llm.generate(prompt)
            return EvaluationResult(
                is_correct=None,  # LEARN mode doesn't score
                score=None,
                feedback=feedback,
                hint=None,  # Hint is embedded in feedback if requested
            )
        except Exception as e:
            return EvaluationResult(
                is_correct=None,
                score=None,
                feedback=f"Unable to evaluate answer: {str(e)}",
                hint=None,
            )

    def _parse_quiz_response(
        self,
        response: str,
        student_answer: str,
        expected_solution: Optional[str],
    ) -> EvaluationResult:
        """Parse JSON response from quiz evaluation.

        Falls back to keyword matching if JSON parsing fails.
        """
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)

        if json_match:
            try:
                evaluation = json.loads(json_match.group())
                return EvaluationResult(
                    is_correct=evaluation.get('is_correct', False),
                    score=float(evaluation.get('score', 0.0)),
                    feedback=evaluation.get('feedback', 'Answer evaluated.'),
                )
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        # Fallback: use response as feedback, do simple matching
        is_correct = self._simple_keyword_match(
            student_answer=student_answer,
            expected_solution=expected_solution,
        )
        return EvaluationResult(
            is_correct=is_correct,
            score=0.7 if is_correct else 0.0,
            feedback=response if response else "Answer evaluated.",
        )

    def _fallback_quiz_evaluation(
        self,
        student_answer: str,
        expected_solution: Optional[str],
    ) -> EvaluationResult:
        """Fallback evaluation when LLM fails.

        Uses keyword matching with more sophisticated scoring.
        """
        if not expected_solution:
            return EvaluationResult(
                is_correct=False,
                score=0.5,
                feedback="Answer recorded. Manual review may be needed.",
            )

        answer_lower = student_answer.lower()
        solution_lower = expected_solution.lower()

        # Count matching keywords (words > 3 chars)
        solution_words = [w for w in solution_lower.split()[:10] if len(w) > 3]
        if solution_words:
            matches = sum(1 for word in solution_words if word in answer_lower)
            score = min(matches / max(len(solution_words), 5), 1.0)
        else:
            score = 0.5

        is_correct = score >= 0.5

        return EvaluationResult(
            is_correct=is_correct,
            score=score,
            feedback="Answer recorded. Manual review may be needed.",
        )

    @staticmethod
    def _simple_keyword_match(
        student_answer: str,
        expected_solution: Optional[str],
    ) -> bool:
        """Simple keyword matching for fallback evaluation."""
        if not expected_solution:
            return False

        answer_lower = student_answer.lower()
        solution_lower = expected_solution.lower()

        # Check if any of first 5 solution words appear in answer
        solution_words = solution_lower.split()[:5]
        return any(word in answer_lower for word in solution_words if word)
