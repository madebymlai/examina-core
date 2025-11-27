"""
Cross-Page Solution Matcher for Examina.

Matches exercises with their solutions when they appear on separate pages.
Language-agnostic and course-agnostic - no hardcoded words or patterns.

Supports:
- Exercise on page N, Solution on page N+1
- All exercises first, all solutions in appendix
- Interleaved with variable page gaps
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from models.llm_manager import LLMManager

logger = logging.getLogger(__name__)


@dataclass
class SolutionMatch:
    """A matched exercise-solution pair."""
    exercise_number: str
    exercise_page: int
    solution_text: str
    solution_page: int
    confidence: float  # 0.0 - 1.0


class SolutionMatcher:
    """Matches exercises with solutions across pages using structural analysis + LLM."""

    def __init__(self, llm_manager: Optional[LLMManager] = None):
        """Initialize solution matcher.

        Args:
            llm_manager: LLM manager for semantic matching (optional)
        """
        self.llm = llm_manager

    def match_solutions(
        self,
        exercise_pages: Dict[str, int],  # exercise_number -> page
        orphan_pages: List[int],
        page_texts: Dict[int, str]
    ) -> List[SolutionMatch]:
        """Match exercises with their solutions on orphan pages.

        Args:
            exercise_pages: Mapping of exercise numbers to their pages
            orphan_pages: Pages not claimed by any exercise (solution candidates)
            page_texts: Full text of each page

        Returns:
            List of solution matches
        """
        if not orphan_pages:
            logger.debug("No orphan pages - skipping solution matching")
            return []

        matches = []

        # Strategy 1: Adjacent page matching (Ex on page N, Sol on page N+1)
        for ex_num, ex_page in exercise_pages.items():
            next_page = ex_page + 1
            if next_page in orphan_pages and next_page in page_texts:
                # Check if page references this exercise number
                sol_text = page_texts[next_page]
                if self._page_references_exercise(sol_text, ex_num):
                    matches.append(SolutionMatch(
                        exercise_number=ex_num,
                        exercise_page=ex_page,
                        solution_text=sol_text,
                        solution_page=next_page,
                        confidence=0.9
                    ))
                    logger.debug(f"Adjacent match: Ex {ex_num} (p{ex_page}) → Sol (p{next_page})")

        # Track which orphans are claimed
        claimed_orphans = {m.solution_page for m in matches}
        remaining_orphans = [p for p in orphan_pages if p not in claimed_orphans]
        unmatched_exercises = [
            ex_num for ex_num in exercise_pages
            if ex_num not in {m.exercise_number for m in matches}
        ]

        # Strategy 2: Appendix pattern (all solutions at end)
        if remaining_orphans and unmatched_exercises:
            appendix_matches = self._match_appendix_pattern(
                unmatched_exercises, remaining_orphans, page_texts
            )
            matches.extend(appendix_matches)

        # Strategy 3: LLM-based matching for remaining (if LLM available)
        claimed_orphans = {m.solution_page for m in matches}
        remaining_orphans = [p for p in orphan_pages if p not in claimed_orphans]
        unmatched_exercises = [
            ex_num for ex_num in exercise_pages
            if ex_num not in {m.exercise_number for m in matches}
        ]

        if remaining_orphans and unmatched_exercises and self.llm:
            llm_matches = self._llm_match_solutions(
                unmatched_exercises, exercise_pages,
                remaining_orphans, page_texts
            )
            matches.extend(llm_matches)

        return matches

    def _page_references_exercise(self, text: str, exercise_number: str) -> bool:
        """Check if page text references a specific exercise number.

        Language-agnostic: Just looks for the number in context.

        Args:
            text: Page text
            exercise_number: Exercise number to look for

        Returns:
            True if page references this exercise
        """
        # Look for the exercise number at the start of the page (within first 500 chars)
        # This is structural, not language-specific
        first_section = text[:500]

        # Pattern: number at start of line or after common punctuation
        patterns = [
            rf'(?:^|\n)\s*{re.escape(exercise_number)}[\.\)\]:\s]',  # "3." or "3)" at line start
            rf'\b{re.escape(exercise_number)}\b',  # Number as standalone word
        ]

        for pattern in patterns:
            if re.search(pattern, first_section, re.MULTILINE):
                return True

        return False

    def _match_appendix_pattern(
        self,
        exercise_numbers: List[str],
        orphan_pages: List[int],
        page_texts: Dict[int, str]
    ) -> List[SolutionMatch]:
        """Match solutions in appendix (all solutions at end of document).

        Args:
            exercise_numbers: Unmatched exercise numbers
            orphan_pages: Candidate solution pages
            page_texts: Page texts

        Returns:
            List of matches
        """
        matches = []

        # Sort orphans (they should be at end of document)
        sorted_orphans = sorted(orphan_pages)

        for orphan_page in sorted_orphans:
            if orphan_page not in page_texts:
                continue

            text = page_texts[orphan_page]

            # Find which exercise numbers this page mentions
            for ex_num in exercise_numbers:
                if self._page_references_exercise(text, ex_num):
                    # Check if already matched
                    if ex_num not in {m.exercise_number for m in matches}:
                        matches.append(SolutionMatch(
                            exercise_number=ex_num,
                            exercise_page=-1,  # Will be filled by caller
                            solution_text=text,
                            solution_page=orphan_page,
                            confidence=0.7
                        ))
                        logger.debug(f"Appendix match: Ex {ex_num} → Sol (p{orphan_page})")

        return matches

    def _llm_match_solutions(
        self,
        exercise_numbers: List[str],
        exercise_pages: Dict[str, int],
        orphan_pages: List[int],
        page_texts: Dict[int, str]
    ) -> List[SolutionMatch]:
        """Use LLM to match exercises with solutions.

        Args:
            exercise_numbers: Unmatched exercise numbers
            exercise_pages: Exercise page mapping
            orphan_pages: Candidate solution pages
            page_texts: Page texts

        Returns:
            List of matches
        """
        if not self.llm:
            return []

        # Build context for LLM
        exercise_summaries = []
        for ex_num in exercise_numbers:
            ex_page = exercise_pages.get(ex_num, -1)
            exercise_summaries.append(f"Exercise {ex_num} (page {ex_page})")

        solution_summaries = []
        for page in sorted(orphan_pages):
            if page in page_texts:
                text_preview = page_texts[page][:300].replace('\n', ' ')
                solution_summaries.append(f"Page {page}: {text_preview}...")

        prompt = f"""Match each exercise with its solution page.

EXERCISES:
{chr(10).join(exercise_summaries)}

CANDIDATE SOLUTION PAGES:
{chr(10).join(solution_summaries)}

Return JSON array of matches:
[{{"exercise_number": "1", "solution_page": 2}}, ...]

Only include matches you're confident about. Return empty array if unsure."""

        try:
            response = self.llm.generate(
                prompt=prompt,
                system="Match exam exercises with their solution pages. Be conservative - only match when confident.",
                temperature=0.0,
                max_tokens=500,
                json_mode=True
            )

            if not response.success:
                logger.warning(f"LLM matching failed: {response.error}")
                return []

            import json
            data = json.loads(response.text)
            matches_data = data if isinstance(data, list) else data.get('matches', [])

            matches = []
            for match in matches_data:
                ex_num = str(match.get('exercise_number', ''))
                sol_page = match.get('solution_page')

                if ex_num in exercise_numbers and sol_page in orphan_pages and sol_page in page_texts:
                    matches.append(SolutionMatch(
                        exercise_number=ex_num,
                        exercise_page=exercise_pages.get(ex_num, -1),
                        solution_text=page_texts[sol_page],
                        solution_page=sol_page,
                        confidence=0.6
                    ))
                    logger.debug(f"LLM match: Ex {ex_num} → Sol (p{sol_page})")

            return matches

        except Exception as e:
            logger.warning(f"LLM solution matching failed: {e}")
            return []

    def is_solution_page(
        self,
        page_text: str,
        exercise_markers: List[str]
    ) -> bool:
        """Detect if a page is a solution page using structural heuristics.

        Language-agnostic: Uses structural patterns, not hardcoded words.

        Indicators of solution pages:
        1. No exercise markers (not a new exercise)
        2. Longer paragraphs (explanatory text)
        3. References exercise numbers without defining new ones

        Args:
            page_text: Text of the page
            exercise_markers: Known exercise markers from this document

        Returns:
            True if this appears to be a solution page
        """
        # Check 1: Does this page have an exercise marker?
        for marker in exercise_markers:
            if marker.lower() in page_text.lower():
                return False  # This is an exercise page, not solution

        # Check 2: Structural analysis
        # Solution pages tend to have longer continuous text blocks
        sentences = re.split(r'[.!?]', page_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return False

        avg_sentence_len = sum(len(s) for s in sentences) / len(sentences)

        # Longer sentences suggest explanatory content (solutions)
        # This threshold is empirical but works across languages
        if avg_sentence_len > 60:
            return True

        # Check 3: References to numbers without being an exercise
        # E.g., "For problem 1..." or "解答 1..."
        number_refs = len(re.findall(r'\b\d+\b', page_text[:500]))
        has_exercise_marker = any(m.lower() in page_text.lower() for m in exercise_markers)

        if number_refs >= 2 and not has_exercise_marker:
            return True

        return False
