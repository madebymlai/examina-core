"""
Exercise splitting for Examina.
Splits PDF content into individual exercises based on patterns.
"""

import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from core.pdf_processor import PDFContent, PDFPage


@dataclass
class Exercise:
    """Represents a single exercise extracted from a PDF."""
    id: str
    text: str
    page_number: int
    exercise_number: Optional[str]
    has_images: bool
    image_data: List[bytes]
    has_latex: bool
    latex_content: Optional[str]
    source_pdf: str


class ExerciseSplitter:
    """Splits PDF content into individual exercises."""

    # Common patterns for exercise markers in Italian and English
    EXERCISE_PATTERNS = [
        r'(?:^|\n)(?:Esercizio|Exercise|Problema|Problem)\s+(\d+(?:\.\d+)?)',  # Esercizio 1, Exercise 1.2
        r'(?:^|\n)(\d+)\.\s+',  # 1. , 2. , etc.
        r'(?:^|\n)(\d+)\)',  # 1), 2), etc.
        r'(?:^|\n)Domanda\s+(\d+)',  # Domanda 1 (Question 1)
        r'(?:^|\n)Quesito\s+(\d+)',  # Quesito 1
        r'(?:^|\n)(?:Ex|Es)\.?\s*(\d+(?:\.\d+)?)',  # Ex. 1, Es 1.2
    ]

    def __init__(self):
        """Initialize exercise splitter."""
        self.patterns = [re.compile(p, re.MULTILINE | re.IGNORECASE)
                        for p in self.EXERCISE_PATTERNS]
        self.exercise_counter = 0

    def split_pdf_content(self, pdf_content: PDFContent, course_code: str) -> List[Exercise]:
        """Split PDF content into individual exercises.

        Args:
            pdf_content: Extracted PDF content
            course_code: Course code for ID generation

        Returns:
            List of extracted exercises
        """
        exercises = []
        self.exercise_counter = 0  # Reset counter for each PDF

        # Process each page
        for page in pdf_content.pages:
            page_exercises = self._split_page(page, pdf_content.file_path.name, course_code)
            exercises.extend(page_exercises)

        return exercises

    def _split_page(self, page: PDFPage, source_pdf: str, course_code: str) -> List[Exercise]:
        """Split a single page into exercises.

        Args:
            page: PDF page content
            source_pdf: Source PDF filename
            course_code: Course code

        Returns:
            List of exercises from this page
        """
        text = page.text
        if not text.strip():
            return []

        # Find all exercise markers
        markers = self._find_exercise_markers(text)

        if not markers:
            # No markers found, treat entire page as single exercise
            return [self._create_exercise(
                text=text,
                page_number=page.page_number,
                exercise_number=None,
                images=page.images,
                has_latex=page.has_latex,
                latex_content=page.latex_content,
                source_pdf=source_pdf,
                course_code=course_code
            )]

        # Split text at markers
        exercises = []
        for i, (start_pos, ex_number) in enumerate(markers):
            # Find end position (start of next exercise or end of text)
            if i + 1 < len(markers):
                end_pos = markers[i + 1][0]
            else:
                end_pos = len(text)

            exercise_text = text[start_pos:end_pos].strip()

            if exercise_text:
                # For now, assign all images from the page to each exercise
                # In a more sophisticated version, we could detect which images
                # belong to which exercise based on position
                exercises.append(self._create_exercise(
                    text=exercise_text,
                    page_number=page.page_number,
                    exercise_number=ex_number,
                    images=page.images if page.images else [],
                    has_latex=page.has_latex,
                    latex_content=page.latex_content,
                    source_pdf=source_pdf,
                    course_code=course_code
                ))

        return exercises

    def _find_exercise_markers(self, text: str) -> List[Tuple[int, str]]:
        """Find all exercise markers in text.

        Args:
            text: Text to search

        Returns:
            List of tuples (position, exercise_number)
        """
        markers = []

        for pattern in self.patterns:
            for match in pattern.finditer(text):
                position = match.start()
                # Extract exercise number (group 1)
                ex_number = match.group(1) if match.groups() else None
                markers.append((position, ex_number))

        # Remove duplicates and sort by position
        markers = list(set(markers))
        markers.sort(key=lambda x: x[0])

        return markers

    def _create_exercise(self, text: str, page_number: int,
                        exercise_number: Optional[str],
                        images: List[bytes], has_latex: bool,
                        latex_content: Optional[str], source_pdf: str,
                        course_code: str) -> Exercise:
        """Create an Exercise object.

        Args:
            text: Exercise text
            page_number: Page number
            exercise_number: Exercise number (if detected)
            images: Image data
            has_latex: Whether LaTeX was detected
            latex_content: LaTeX content
            source_pdf: Source PDF filename
            course_code: Course code

        Returns:
            Exercise object
        """
        # Generate unique ID
        exercise_id = self._generate_exercise_id(
            course_code, source_pdf, page_number, exercise_number
        )

        return Exercise(
            id=exercise_id,
            text=text,
            page_number=page_number,
            exercise_number=exercise_number,
            has_images=len(images) > 0,
            image_data=images,
            has_latex=has_latex,
            latex_content=latex_content,
            source_pdf=source_pdf
        )

    def _generate_exercise_id(self, course_code: str, source_pdf: str,
                             page_number: int, exercise_number: Optional[str]) -> str:
        """Generate a unique exercise ID.

        Args:
            course_code: Course code
            source_pdf: Source PDF filename
            page_number: Page number
            exercise_number: Exercise number

        Returns:
            Unique exercise ID
        """
        # Increment counter to ensure uniqueness
        self.exercise_counter += 1

        # Create a hash from ALL components including counter for guaranteed uniqueness
        components = f"{course_code}_{source_pdf}_{page_number}_{exercise_number or 'none'}_{self.exercise_counter}"

        # Generate hash
        hash_obj = hashlib.md5(components.encode())
        short_hash = hash_obj.hexdigest()[:12]

        # Create ID: course abbreviation + counter + hash
        course_abbrev = course_code.lower().replace('b', '').replace('0', '')[:6]
        return f"{course_abbrev}_{self.exercise_counter:04d}_{short_hash}"

    def merge_split_exercises(self, exercises: List[Exercise]) -> List[Exercise]:
        """Merge exercises that were incorrectly split.

        This is a placeholder for future enhancement where we might
        use AI to detect when an exercise was split across pages.

        Args:
            exercises: List of exercises

        Returns:
            Merged list of exercises
        """
        # For now, just return as-is
        # In Phase 3, we could use LLM to detect split exercises
        return exercises

    def validate_exercise(self, exercise: Exercise, min_length: int = 20) -> bool:
        """Validate if an exercise has sufficient content.

        Args:
            exercise: Exercise to validate
            min_length: Minimum text length

        Returns:
            True if exercise is valid
        """
        # Check minimum text length
        if len(exercise.text.strip()) < min_length:
            return False

        # Check if it's not just a header
        if len(exercise.text.split()) < 5:
            return False

        return True

    def clean_exercise_text(self, text: str) -> str:
        """Clean up exercise text.

        Args:
            text: Raw text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

        # Remove page numbers (common pattern)
        text = re.sub(r'(?:^|\n)Pagina\s+\d+(?:\n|$)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:^|\n)Page\s+\d+(?:\n|$)', '', text, flags=re.IGNORECASE)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text
