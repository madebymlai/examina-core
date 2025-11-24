"""
Smart exercise splitter for Examina.
Combines pattern-based and LLM-based splitting for unstructured materials.
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import hashlib

from core.exercise_splitter import ExerciseSplitter, Exercise
from core.pdf_processor import PDFContent, PDFPage
from models.llm_manager import LLMManager
from config import Config


@dataclass
class DetectedExercise:
    """Exercise detected by LLM with metadata."""
    start_char: int
    end_char: int
    exercise_type: str  # 'procedural', 'theory', 'proof', 'worked_example', 'practice'
    confidence: float
    has_solution_inline: bool


@dataclass
class SplitResult:
    """Result of smart splitting operation."""
    exercises: List[Exercise]
    pattern_based_count: int
    llm_based_count: int
    total_pages: int
    llm_pages_processed: int
    total_cost_estimate: float


class SmartExerciseSplitter:
    """
    Hybrid exercise splitter combining pattern-based and LLM-based detection.

    Strategy:
    1. Try fast pattern-based splitting first (free, instant)
    2. For pages with no exercises found, use LLM detection (costs tokens)
    3. Respects cost controls (max pages, caching)
    """

    def __init__(self, llm_manager: Optional[LLMManager] = None,
                 enable_smart_detection: bool = True):
        """
        Initialize smart splitter.

        Args:
            llm_manager: LLM manager for smart detection (required if enable_smart_detection=True)
            enable_smart_detection: Enable LLM-based detection for unstructured materials
        """
        self.llm = llm_manager
        self.pattern_splitter = ExerciseSplitter()
        self.enable_smart = enable_smart_detection and llm_manager is not None

        # Load config
        self.confidence_threshold = Config.SMART_SPLIT_CONFIDENCE_THRESHOLD
        self.max_pages = Config.SMART_SPLIT_MAX_PAGES
        self.cache_enabled = Config.SMART_SPLIT_CACHE_ENABLED

        # Cache for LLM results (page_hash -> detected exercises)
        self._detection_cache = {}

        if self.enable_smart and not self.llm:
            raise ValueError("LLM manager required when enable_smart_detection=True")

    def split_pdf_content(self, pdf_content: PDFContent, course_code: str) -> SplitResult:
        """
        Split PDF content into exercises using hybrid approach.

        Args:
            pdf_content: Extracted PDF content
            course_code: Course code for ID generation

        Returns:
            SplitResult with exercises and metadata
        """
        all_exercises = []
        pattern_count = 0
        llm_count = 0
        llm_pages_processed = 0

        # Cost control: limit pages if smart detection enabled
        pages_to_process = pdf_content.pages
        if self.enable_smart and len(pages_to_process) > self.max_pages:
            print(f"⚠️  Warning: PDF has {len(pages_to_process)} pages. "
                  f"Processing only first {self.max_pages} pages to control costs.")
            print(f"   Increase with: export EXAMINA_SMART_SPLIT_MAX_PAGES={len(pages_to_process)}")
            pages_to_process = pages_to_process[:self.max_pages]

        # Phase 1: Pattern-based splitting (fast, free)
        pattern_exercises = self.pattern_splitter.split_pdf_content(
            pdf_content, course_code
        )

        # Track which pages had exercises found
        pages_with_exercises = set()
        for ex in pattern_exercises:
            pages_with_exercises.add(ex.page_number)

        pattern_count = len(pattern_exercises)
        all_exercises.extend(pattern_exercises)

        # Phase 2: LLM-based detection for pages without exercises
        if self.enable_smart:
            for page in pages_to_process:
                if page.page_number in pages_with_exercises:
                    continue  # Already found exercises with patterns

                if not page.text.strip():
                    continue  # Empty page

                # Skip instruction-only pages
                if self.pattern_splitter._is_instruction_page(page.text):
                    continue

                # Try LLM detection
                detected = self._detect_exercises_with_llm(
                    page, pdf_content.file_path.name, course_code
                )

                if detected:
                    llm_pages_processed += 1
                    llm_count += len(detected)
                    all_exercises.extend(detected)

        # Estimate cost (rough approximation)
        tokens_per_page = 1500  # Average page length
        cost_per_1k_tokens = 0.0002  # Approximate for Groq/Anthropic
        estimated_cost = (llm_pages_processed * tokens_per_page / 1000) * cost_per_1k_tokens

        return SplitResult(
            exercises=all_exercises,
            pattern_based_count=pattern_count,
            llm_based_count=llm_count,
            total_pages=len(pdf_content.pages),
            llm_pages_processed=llm_pages_processed,
            total_cost_estimate=estimated_cost
        )

    def _detect_exercises_with_llm(self, page: PDFPage, source_pdf: str,
                                   course_code: str) -> List[Exercise]:
        """
        Use LLM to detect exercise boundaries in unstructured text.

        Args:
            page: PDF page to analyze
            source_pdf: Source PDF filename
            course_code: Course code

        Returns:
            List of detected exercises
        """
        # Check cache first
        if self.cache_enabled:
            page_hash = self._hash_page(page.text)
            if page_hash in self._detection_cache:
                cached = self._detection_cache[page_hash]
                # Reconstruct Exercise objects with proper IDs
                return self._create_exercises_from_detected(
                    cached, page, source_pdf, course_code
                )

        # Build prompt
        prompt = self._build_detection_prompt(page.text)

        # Call LLM through manager (provider-agnostic)
        try:
            response = self.llm.generate(
                prompt=prompt,
                temperature=0.0,
                max_tokens=1000
            )

            # Parse JSON response
            detected = self._parse_detection_response(response.text)

            # Cache result
            if self.cache_enabled:
                page_hash = self._hash_page(page.text)
                self._detection_cache[page_hash] = detected

            # Convert to Exercise objects
            exercises = self._create_exercises_from_detected(
                detected, page, source_pdf, course_code
            )

            return exercises

        except Exception as e:
            # Graceful degradation: if LLM fails, return empty list
            print(f"⚠️  LLM detection failed for page {page.page_number}: {e}")
            return []

    def _build_detection_prompt(self, page_text: str) -> str:
        """
        Build generic prompt for exercise detection.

        IMPORTANT: This prompt is GENERIC and works for ANY:
        - Subject (CS, Math, Physics, Chemistry, Biology, etc.)
        - Language (English, Italian, Spanish, French, etc.)
        - Format (structured, unstructured, mixed)

        Args:
            page_text: Text to analyze

        Returns:
            Prompt string
        """
        # Truncate if too long (to avoid token limits)
        if len(page_text) > 4000:
            page_text = page_text[:4000] + "...[truncated]"

        prompt = f"""Does this text contain exercises, problems, worked examples, or practice questions?

Text to analyze:
---
{page_text}
---

Look for:
- Numbered or unnumbered problems
- Worked examples with solutions
- Practice questions
- Problem statements (e.g., "Solve:", "Find:", "Prove:", "Calculate:", "Explain:")
- Theory questions (e.g., "Describe:", "What is:", "Why does:")
- Multi-step procedures

For each exercise/problem found, identify:
1. Start and end character positions in the text
2. Type: procedural (multi-step), theory (explanation), proof (demonstration), worked_example (with solution), or practice (problem to solve)
3. Confidence (0.0-1.0)
4. Whether it has a solution shown inline

Return ONLY valid JSON in this format (no markdown, no code fences):
{{
  "has_exercises": true/false,
  "exercises": [
    {{
      "start_char": 0,
      "end_char": 500,
      "exercise_type": "procedural",
      "confidence": 0.9,
      "has_solution_inline": false
    }}
  ]
}}

If no exercises found, return: {{"has_exercises": false, "exercises": []}}
"""
        return prompt

    def _parse_detection_response(self, response_text: str) -> List[DetectedExercise]:
        """
        Parse LLM response into DetectedExercise objects.

        Args:
            response_text: Raw LLM response

        Returns:
            List of DetectedExercise objects
        """
        # Strip markdown code fences if present (LLM sometimes adds them)
        response_text = response_text.strip()
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            response_text = '\n'.join(lines)

        # Parse JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"⚠️  Failed to parse LLM response as JSON: {e}")
            print(f"Response was: {response_text[:200]}")
            return []

        # Validate structure
        if not isinstance(data, dict) or 'has_exercises' not in data:
            print(f"⚠️  Invalid response structure: {data}")
            return []

        if not data['has_exercises']:
            return []

        # Parse exercises
        detected_exercises = []
        for ex_data in data.get('exercises', []):
            try:
                detected = DetectedExercise(
                    start_char=ex_data['start_char'],
                    end_char=ex_data['end_char'],
                    exercise_type=ex_data['exercise_type'],
                    confidence=float(ex_data['confidence']),
                    has_solution_inline=ex_data['has_solution_inline']
                )

                # Filter by confidence threshold
                if detected.confidence >= self.confidence_threshold:
                    detected_exercises.append(detected)

            except (KeyError, ValueError) as e:
                print(f"⚠️  Skipping malformed exercise entry: {e}")
                continue

        return detected_exercises

    def _create_exercises_from_detected(self, detected_list: List[DetectedExercise],
                                       page: PDFPage, source_pdf: str,
                                       course_code: str) -> List[Exercise]:
        """
        Convert DetectedExercise objects to Exercise objects.

        Args:
            detected_list: List of detected exercises
            page: PDF page
            source_pdf: Source PDF filename
            course_code: Course code

        Returns:
            List of Exercise objects
        """
        exercises = []

        for i, detected in enumerate(detected_list):
            # Extract text from detected boundaries
            exercise_text = page.text[detected.start_char:detected.end_char].strip()

            if not exercise_text:
                continue

            # Generate unique ID
            exercise_id = self._generate_exercise_id(
                course_code, source_pdf, page.page_number,
                f"llm_{i+1}", detected.confidence
            )

            # Create Exercise object
            exercise = Exercise(
                id=exercise_id,
                text=exercise_text,
                page_number=page.page_number,
                exercise_number=f"LLM-{i+1}",  # Mark as LLM-detected
                has_images=len(page.images) > 0,
                image_data=page.images if page.images else [],
                has_latex=page.has_latex,
                latex_content=page.latex_content,
                source_pdf=source_pdf
            )

            exercises.append(exercise)

        return exercises

    def _generate_exercise_id(self, course_code: str, source_pdf: str,
                             page_number: int, llm_index: str,
                             confidence: float) -> str:
        """
        Generate unique exercise ID for LLM-detected exercises.

        Args:
            course_code: Course code
            source_pdf: Source PDF filename
            page_number: Page number
            llm_index: LLM detection index
            confidence: Detection confidence

        Returns:
            Unique exercise ID
        """
        components = f"{course_code}_{source_pdf}_{page_number}_{llm_index}_{confidence:.2f}"
        hash_obj = hashlib.md5(components.encode())
        short_hash = hash_obj.hexdigest()[:12]

        course_abbrev = course_code.lower().replace('b', '').replace('0', '')[:6]
        return f"{course_abbrev}_smart_{short_hash}"

    def _hash_page(self, page_text: str) -> str:
        """
        Generate hash for page content (for caching).

        Args:
            page_text: Page text

        Returns:
            Hash string
        """
        return hashlib.md5(page_text.encode()).hexdigest()

    def validate_exercise(self, exercise: Exercise, min_length: int = 20) -> bool:
        """
        Validate if an exercise has sufficient content.

        Args:
            exercise: Exercise to validate
            min_length: Minimum text length

        Returns:
            True if exercise is valid
        """
        # Delegate to pattern splitter's validation
        return self.pattern_splitter.validate_exercise(exercise, min_length)
