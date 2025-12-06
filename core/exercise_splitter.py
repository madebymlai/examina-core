"""
Exercise splitting for Examina.
Splits PDF content into individual exercises based on patterns.
"""

import re
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

from core.pdf_processor import PDFContent, PDFPage

if TYPE_CHECKING:
    from models.llm_manager import LLMManager

logger = logging.getLogger(__name__)


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
    # Solution fields (populated by SolutionMatcher if Q+A format detected)
    solution: Optional[str] = None
    solution_page: Optional[int] = None
    # Sub-question support (added for unified knowledge model)
    parent_exercise_number: Optional[str] = None  # "2" if this is "2a"
    sub_question_marker: Optional[str] = None     # "a", "b", "c", "i", "ii", etc.
    is_sub_question: bool = False

    def get_preview_text(self, max_length: int = 100) -> str:
        """Get a clean preview of the exercise text for display.

        Uses structural patterns (language-agnostic) to remove exercise markers,
        form fields, and other non-content text.

        Args:
            max_length: Maximum length of the preview text

        Returns:
            Clean preview text suitable for display
        """
        # Split into lines and find first meaningful content line
        lines = self.text.strip().split('\n')

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip lines with form fields (underscores, dots as blanks)
            if '_____' in line or '.....' in line or '___' in line:
                continue

            # Skip very short lines (likely headers or labels)
            if len(line) < 20:
                continue

            # Skip lines that are mostly uppercase and short (likely headers)
            if len(line) < 60 and line.upper() == line:
                continue

            # Skip lines that start with "word + number" pattern (exercise markers)
            # This catches "Esercizio 1", "Exercise 2", "Aufgabe 3", etc.
            if re.match(r'^[A-Za-z\u00C0-\u024F]+\s+\d+\s*$', line):
                continue

            # Found a good line - clean it up
            # Remove leading "word + number" if followed by more content
            cleaned = re.sub(r'^[A-Za-z\u00C0-\u024F]+\s+\d+\s*', '', line).strip()
            if not cleaned or len(cleaned) < 15:
                cleaned = line  # Use original if cleaning removed too much

            # Remove leading number patterns like "1.", "1)"
            cleaned = re.sub(r'^\d+[\.\)\:]\s*', '', cleaned).strip()

            # Get first sentence or truncate
            if '.' in cleaned[:120] and cleaned.index('.') > 20:
                preview = cleaned[:cleaned.index('.') + 1]
            else:
                preview = cleaned[:max_length]

            # Truncate if needed
            if len(preview) > max_length:
                preview = preview[:max_length].rsplit(' ', 1)[0] + "..."
            elif len(cleaned) > len(preview):
                preview = preview.rstrip('.') + "..."

            return preview

        # Fallback - no good lines found
        # Just return first N chars of raw text, cleaned of obvious junk
        text = self.text.strip()
        text = re.sub(r'[_]{3,}', '', text)  # Remove underscores
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        preview = text[:max_length].strip()
        if len(text) > max_length:
            preview = preview.rsplit(' ', 1)[0] + "..."
        return preview if preview else f"#{self.exercise_number or '?'}"


class MarkerType(Enum):
    """Type of exercise marker."""
    PARENT = "parent"  # Main exercise marker (e.g., "Exercise 1")
    SUB = "sub"        # Sub-question marker (e.g., "1.", "a)")


@dataclass
class Marker:
    """A detected exercise marker in the document."""
    marker_type: MarkerType
    marker_text: str       # The actual marker text (e.g., "Exercise 1", "a)")
    number: str            # Extracted number/letter ("1", "a", etc.)
    start_position: int    # Character position where marker starts
    question_start: int    # Character position where question text begins


@dataclass
class MarkerPattern:
    """Pattern for exercise markers detected by LLM."""
    keyword: str              # e.g., "Esercizio", "Exercise", "Problem"
    has_sub_markers: bool     # Whether document has sub-questions
    sub_format: Optional[str] # e.g., "numbered" (1., 2.) or "lettered" (a), b))
    solution_keyword: Optional[str] = None  # e.g., "Soluzione", "Solution", "Answer"


@dataclass
class ExerciseNode:
    """Hierarchical exercise structure for building parent-child relationships."""
    marker: Marker
    context: str              # Setup text (for parents)
    question_text: str        # The actual question
    children: List["ExerciseNode"] = field(default_factory=list)
    parent: Optional["ExerciseNode"] = None


@dataclass
class DetectionResult:
    """Result from LLM exercise detection."""
    pattern: Optional[MarkerPattern] = None  # Pattern-based detection
    explicit_markers: Optional[List[str]] = None  # Explicit marker texts


def _detect_pattern_with_llm(
    text_sample: str,
    llm_manager: "LLMManager",
) -> Optional[DetectionResult]:
    """Use LLM to detect exercise markers in document.

    Two modes:
    1. Pattern detection: LLM identifies a keyword pattern (e.g., "Esercizio")
    2. Explicit markers: LLM lists the first few words of each exercise

    Args:
        text_sample: First ~10k chars of document
        llm_manager: LLM manager for inference

    Returns:
        DetectionResult with either pattern or explicit markers, None if detection fails
    """
    prompt = """Analyze this exam/exercise document and identify the structure.

TEXT SAMPLE:
---
{text}
---

Identify:
1. The KEYWORD used before exercise/problem numbers (appears multiple times with different numbers)
2. Whether exercises have sub-questions (like a), b) or 1., 2. within each)
3. If the document contains solutions, the KEYWORD used before solution sections

Return ONLY valid JSON:
{{"mode": "pattern", "keyword": "detected keyword or null", "has_sub_markers": true/false, "sub_format": "lettered" or "numbered" or null, "solution_keyword": "detected solution keyword or null"}}

If no consistent exercise keyword pattern exists, return the first 3-5 words of each exercise:
{{"mode": "explicit", "markers": ["first words of exercise 1", "first words of exercise 2", ...]}}"""

    try:
        response = llm_manager.generate(
            prompt.format(text=text_sample[:10000]),
            temperature=0.0,
        )

        # Parse JSON response
        # Handle potential markdown code blocks
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        response = response.strip()

        data = json.loads(response)

        mode = data.get("mode", "pattern")

        if mode == "explicit":
            markers = data.get("markers", [])
            if markers:
                return DetectionResult(explicit_markers=markers)
            return None

        # Pattern mode
        keyword = data.get("keyword")
        if not keyword:
            return None

        return DetectionResult(
            pattern=MarkerPattern(
                keyword=keyword,
                has_sub_markers=data.get("has_sub_markers", False),
                sub_format=data.get("sub_format"),
                solution_keyword=data.get("solution_keyword"),
            )
        )

    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to parse LLM pattern detection response: {e}")
        return None
    except Exception as e:
        logger.error(f"LLM pattern detection failed: {e}")
        return None


def _find_explicit_markers(
    full_text: str,
    marker_texts: List[str],
) -> List[Marker]:
    """Find markers in document using explicit marker texts from LLM.

    Args:
        full_text: Complete document text
        marker_texts: List of marker texts to find (first few words of each exercise)

    Returns:
        List of Marker objects sorted by position
    """
    markers: List[Marker] = []

    for i, marker_text in enumerate(marker_texts):
        pos = _fuzzy_find(full_text, marker_text)
        if pos >= 0:
            markers.append(Marker(
                marker_type=MarkerType.PARENT,
                marker_text=marker_text,
                number=str(i + 1),
                start_position=pos,
                question_start=pos,  # For explicit markers, question starts at marker
            ))
        else:
            logger.warning(f"Explicit marker not found: '{marker_text}'")

    # Sort by position and deduplicate (in case of overlapping matches)
    markers.sort(key=lambda m: m.start_position)

    # Remove duplicates (same position)
    seen_positions = set()
    unique_markers = []
    for m in markers:
        if m.start_position not in seen_positions:
            seen_positions.add(m.start_position)
            unique_markers.append(m)

    return unique_markers


def _fuzzy_find(text: str, search_term: str, start_from: int = 0) -> int:
    """Find a term in text with tolerance for OCR errors.

    Handles common OCR issues:
    - Case differences
    - Extra/missing spaces
    - Common character substitutions (l/1, O/0)

    Args:
        text: Document text to search
        search_term: Term to find
        start_from: Position to start searching from

    Returns:
        Position of match, or -1 if not found
    """
    # First try exact match
    pos = text.find(search_term, start_from)
    if pos >= 0:
        return pos

    # Try case-insensitive
    text_lower = text.lower()
    search_lower = search_term.lower()
    pos = text_lower.find(search_lower, start_from)
    if pos >= 0:
        return pos

    # Try with normalized whitespace
    search_normalized = re.sub(r'\s+', r'\\s+', re.escape(search_term))
    pattern = re.compile(search_normalized, re.IGNORECASE)
    match = pattern.search(text, start_from)
    if match:
        return match.start()

    return -1


def _find_all_markers(
    full_text: str,
    pattern: MarkerPattern,
) -> Tuple[List[Marker], List[Tuple[int, int]]]:
    """Find all exercise markers in document using detected pattern.

    Handles three document formats:
    1. Embedded solutions (no keyword): All text belongs to exercises
    2. Separate solution sections: Filters markers after solution keyword
    3. Appendix solutions: Filters all markers in solution section at end

    Args:
        full_text: Complete document text
        pattern: Detected marker pattern from LLM

    Returns:
        Tuple of (List of Marker objects sorted by position, List of solution ranges)
    """
    markers: List[Marker] = []
    solution_ranges: List[Tuple[int, int]] = []  # (start, end) of solution sections

    # Build regex for parent markers: keyword + number
    keyword_escaped = re.escape(pattern.keyword)
    parent_regex = re.compile(
        rf'(?:^|\n)\s*({keyword_escaped})\s+(\d+)',
        re.IGNORECASE | re.MULTILINE
    )

    # Find all parent (exercise) markers - collect raw matches first
    raw_parent_markers: List[Tuple[int, str, str, int]] = []  # (start, marker_text, number, question_start)
    for match in parent_regex.finditer(full_text):
        raw_parent_markers.append((
            match.start(),
            match.group(0).strip(),
            match.group(2),
            match.end(),
        ))

    # Find solution section positions (if solution keyword detected)
    # Solution sections extend from solution keyword to end of text
    # (Format 3: appendix where all solutions are at the end)
    if pattern.solution_keyword:
        sol_escaped = re.escape(pattern.solution_keyword)
        sol_regex = re.compile(
            rf'(?:^|\n)\s*({sol_escaped})',
            re.IGNORECASE | re.MULTILINE
        )

        for match in sol_regex.finditer(full_text):
            sol_start = match.start()
            sol_match_end = match.end()  # End of current match (to search for next)

            # Check if there are MORE solution keywords after this one
            next_sol_match = sol_regex.search(full_text, sol_match_end)
            has_more_solutions = next_sol_match is not None

            if has_more_solutions:
                # Format 2 (interleaved): Multiple solution sections
                # Solution ends at the next exercise marker
                sol_end = len(full_text)
                for start_pos, _, _, _ in raw_parent_markers:
                    if start_pos > sol_start:
                        sol_end = start_pos
                        break
            else:
                # Format 3 (appendix) OR last solution in Format 2
                # Solution extends to end of text
                sol_end = len(full_text)

            solution_ranges.append((sol_start, sol_end))

    def _is_in_solution_section(pos: int) -> bool:
        """Check if position falls within any solution section."""
        for start, end in solution_ranges:
            if start <= pos < end:
                return True
        return False

    # Filter parent markers - skip those in solution sections
    for start_pos, marker_text, number, question_start in raw_parent_markers:
        if _is_in_solution_section(start_pos):
            continue

        markers.append(Marker(
            marker_type=MarkerType.PARENT,
            marker_text=marker_text,
            number=number,
            start_position=start_pos,
            question_start=question_start,
        ))

    # Find sub-markers if present
    if pattern.has_sub_markers and pattern.sub_format:
        if pattern.sub_format == "lettered":
            sub_regex = re.compile(
                r'(?:^|\n)\s*([a-z])\s*[)\.]',
                re.MULTILINE
            )
        else:  # numbered
            sub_regex = re.compile(
                r'(?:^|\n)\s*(\d+)\s*[)\.](?!\d)',
                re.MULTILINE
            )

        for match in sub_regex.finditer(full_text):
            start_pos = match.start()

            # Skip sub-markers in solution sections
            if _is_in_solution_section(start_pos):
                continue

            marker_text = match.group(0).strip()
            number = match.group(1)
            question_start = match.end()

            markers.append(Marker(
                marker_type=MarkerType.SUB,
                marker_text=marker_text,
                number=number,
                start_position=start_pos,
                question_start=question_start,
            ))

    # Sort by position
    markers.sort(key=lambda m: m.start_position)

    return markers, solution_ranges


def _build_hierarchy(markers: List[Marker], full_text: str) -> List[ExerciseNode]:
    """Build hierarchical exercise structure from markers.

    Args:
        markers: List of detected markers (sorted by position)
        full_text: Complete document text

    Returns:
        List of root ExerciseNode objects (parent exercises)
    """
    if not markers:
        return []

    roots: List[ExerciseNode] = []
    current_parent: Optional[ExerciseNode] = None

    for i, marker in enumerate(markers):
        # Find end position (next marker or end of text)
        if i + 1 < len(markers):
            end_pos = markers[i + 1].start_position
        else:
            end_pos = len(full_text)

        # Extract text for this marker
        text_content = full_text[marker.question_start:end_pos].strip()

        node = ExerciseNode(
            marker=marker,
            context="",  # Will be set for children
            question_text=text_content,
        )

        if marker.marker_type == MarkerType.PARENT:
            # This is a parent exercise
            roots.append(node)
            current_parent = node
        else:
            # This is a sub-question
            if current_parent is not None:
                node.parent = current_parent
                # Context is the parent's intro text (before first sub)
                if not current_parent.children:
                    # First child - parent's question_text is the context
                    node.context = current_parent.question_text
                else:
                    # Use same context as siblings
                    node.context = current_parent.children[0].context
                current_parent.children.append(node)
            else:
                # Orphan sub-question (no parent found) - treat as root
                roots.append(node)

    return roots


def _expand_exercises(
    hierarchy: List[ExerciseNode],
    source_pdf: str,
    course_code: str,
    page_lookup: Dict[int, int],  # char_position -> page_number
) -> List[Exercise]:
    """Expand hierarchical structure to flat list with context.

    Args:
        hierarchy: List of root ExerciseNode objects
        source_pdf: Source PDF filename
        course_code: Course code for ID generation
        page_lookup: Mapping of character positions to page numbers

    Returns:
        List of Exercise objects ready for analysis
    """
    exercises: List[Exercise] = []
    counter = 0

    def get_page_number(char_pos: int) -> int:
        """Find page number for a character position."""
        # Find the largest position that's <= char_pos
        page = 1
        for pos, pg in sorted(page_lookup.items()):
            if pos <= char_pos:
                page = pg
            else:
                break
        return page

    for parent in hierarchy:
        counter += 1
        parent_num = parent.marker.number

        if parent.children:
            # Parent has sub-questions - emit each sub with context
            for child in parent.children:
                counter += 1
                # Prepend context to make sub-question standalone
                full_text = f"{child.context}\n\n{child.question_text}".strip()

                page_num = get_page_number(child.marker.start_position)
                exercise_id = _generate_exercise_id(
                    course_code, source_pdf, page_num, counter
                )

                exercises.append(Exercise(
                    id=exercise_id,
                    text=full_text,
                    page_number=page_num,
                    exercise_number=f"{parent_num}{child.marker.number}",
                    has_images=False,  # Will be enriched later
                    image_data=[],
                    has_latex=False,
                    latex_content=None,
                    source_pdf=source_pdf,
                    parent_exercise_number=parent_num,
                    sub_question_marker=child.marker.number,
                    is_sub_question=True,
                ))
        else:
            # Parent has no sub-questions - emit as single exercise
            page_num = get_page_number(parent.marker.start_position)
            exercise_id = _generate_exercise_id(
                course_code, source_pdf, page_num, counter
            )

            exercises.append(Exercise(
                id=exercise_id,
                text=parent.question_text,
                page_number=page_num,
                exercise_number=parent_num,
                has_images=False,
                image_data=[],
                has_latex=False,
                latex_content=None,
                source_pdf=source_pdf,
            ))

    return exercises


def _generate_exercise_id(
    course_code: str,
    source_pdf: str,
    page_number: int,
    counter: int,
) -> str:
    """Generate a unique exercise ID.

    Args:
        course_code: Course code
        source_pdf: Source PDF filename
        page_number: Page number
        counter: Exercise counter

    Returns:
        Unique exercise ID
    """
    components = f"{course_code}_{source_pdf}_{page_number}_{counter}"
    hash_obj = hashlib.md5(components.encode())
    short_hash = hash_obj.hexdigest()[:12]
    course_abbrev = course_code.lower().replace('b', '').replace('0', '')[:6]
    return f"{course_abbrev}_{counter:04d}_{short_hash}"


def _split_unstructured(
    pdf_content: "PDFContent",
    course_code: str,
) -> List[Exercise]:
    """Fallback: split document by pages when no markers found.

    Args:
        pdf_content: PDF content
        course_code: Course code

    Returns:
        List of exercises (one per page with substantial content)
    """
    exercises: List[Exercise] = []
    counter = 0

    for page in pdf_content.pages:
        text = page.text.strip()
        if len(text) < 50:
            continue  # Skip empty/header pages

        counter += 1
        exercise_id = _generate_exercise_id(
            course_code,
            pdf_content.file_path.name,
            page.page_number,
            counter,
        )

        exercises.append(Exercise(
            id=exercise_id,
            text=text,
            page_number=page.page_number,
            exercise_number=str(counter),
            has_images=len(page.images) > 0,
            image_data=page.images if page.images else [],
            has_latex=page.has_latex,
            latex_content=page.latex_content,
            source_pdf=pdf_content.file_path.name,
        ))

    return exercises


class ExerciseSplitter:
    """Language-agnostic exercise splitter using dynamic pattern detection."""

    # Structural patterns (language-agnostic fallback)
    STRUCTURAL_PATTERNS = [
        r'(?:^|\n)\s*(\d+)\.\s+',       # "1. " at line start
        r'(?:^|\n)\s*(\d+)\)\s+',       # "1) " at line start
        r'(?:^|\n)\s*\((\d+)\)\s*',     # "(1)" at line start
        r'(?:^|\n)\s*\[(\d+)\]',        # "[1]" at line start
        r'(?:^|\n)\s*([IVXLCDM]+)\.\s', # Roman numerals "I. ", "II. "
    ]

    # Language-agnostic instruction patterns (structural, not language-specific)
    INSTRUCTION_PATTERNS = [
        r'(?:^|\n)\s*[-•]\s+',          # Bullet points (likely instructions)
        r':\s*$',                        # Lines ending with colon (likely headers)
    ]

    def __init__(self):
        """Initialize exercise splitter."""
        self.structural_patterns = [re.compile(p, re.MULTILINE | re.IGNORECASE)
                                   for p in self.STRUCTURAL_PATTERNS]
        self.instruction_patterns = [re.compile(p, re.MULTILINE | re.IGNORECASE)
                                    for p in self.INSTRUCTION_PATTERNS]
        self.exercise_counter = 0
        self._detected_pattern_cache: Dict[str, Optional[re.Pattern]] = {}

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

        # Step 1: Analyze FULL document to detect exercise pattern
        # This is crucial for PDFs where each page has only one exercise marker
        full_text = "\n".join(page.text for page in pdf_content.pages)
        self._document_pattern = self._detect_exercise_pattern(full_text)

        # Process each page using the document-wide pattern
        for page in pdf_content.pages:
            page_exercises = self._split_page(page, pdf_content.file_path.name, course_code)
            exercises.extend(page_exercises)

        # Clean up
        self._document_pattern = None

        return exercises

    def split_pdf_smart(
        self,
        pdf_content: PDFContent,
        course_code: str,
        llm_manager: "LLMManager",
    ) -> List[Exercise]:
        """Split PDF using LLM-based pattern detection with sub-question context.

        This method uses LLM to detect the exercise marker pattern, then:
        1. Finds all markers in the full document
        2. Builds a hierarchical structure (parent → children)
        3. Expands to flat list with context prepended to sub-questions

        Args:
            pdf_content: Extracted PDF content
            course_code: Course code for ID generation
            llm_manager: LLM manager for pattern detection

        Returns:
            List of extracted exercises with context
        """
        # Step 1: Concatenate all page text with position tracking
        full_text = ""
        page_lookup: Dict[int, int] = {}  # char_position -> page_number

        for page in pdf_content.pages:
            page_lookup[len(full_text)] = page.page_number
            full_text += page.text + "\n"

        if not full_text.strip():
            return []

        # Step 2: Detect pattern/markers with LLM
        logger.info("Detecting exercise pattern with LLM...")
        detection = _detect_pattern_with_llm(full_text[:10000], llm_manager)

        if not detection:
            # No detection - try regex fallback, then page-based
            logger.info("No LLM detection, trying regex fallback...")
            regex_pattern = self._detect_exercise_pattern(full_text)

            if regex_pattern:
                # Use the old page-based method with detected pattern
                self._document_pattern = regex_pattern
                exercises = []
                for page in pdf_content.pages:
                    page_exercises = self._split_page(
                        page, pdf_content.file_path.name, course_code
                    )
                    exercises.extend(page_exercises)
                self._document_pattern = None
                return exercises

            # No pattern at all - fall back to page-based splitting
            logger.info("No pattern found, falling back to page-based splitting")
            return _split_unstructured(pdf_content, course_code)

        # Step 3: Find markers based on detection mode
        markers: List[Marker] = []

        if detection.explicit_markers:
            # Mode 2: Explicit markers from LLM
            logger.info(
                f"Using explicit markers: {len(detection.explicit_markers)} markers"
            )
            markers = _find_explicit_markers(full_text, detection.explicit_markers)
        elif detection.pattern:
            # Mode 1: Pattern-based detection
            pattern = detection.pattern
            logger.info(
                f"Pattern detected: keyword='{pattern.keyword}', "
                f"has_sub={pattern.has_sub_markers}, sub_format={pattern.sub_format}"
                + (f", solution_keyword='{pattern.solution_keyword}'" if pattern.solution_keyword else "")
            )
            markers, solution_ranges = _find_all_markers(full_text, pattern)
            if solution_ranges:
                logger.info(f"Detected {len(solution_ranges)} solution sections (filtering markers in those)")

        if not markers:
            logger.warning("Pattern detected but no markers found, falling back")
            return _split_unstructured(pdf_content, course_code)

        logger.info(f"Found {len(markers)} markers")

        # Step 4: Build hierarchy
        hierarchy = _build_hierarchy(markers, full_text)
        logger.info(f"Built hierarchy with {len(hierarchy)} root exercises")

        # Step 5: Expand to flat list with context
        exercises = _expand_exercises(
            hierarchy,
            pdf_content.file_path.name,
            course_code,
            page_lookup,
        )

        # Step 6: Enrich with image/latex data from pages
        exercises = self._enrich_with_page_data(exercises, pdf_content)

        logger.info(f"Smart split produced {len(exercises)} exercises")
        return exercises

    def _enrich_with_page_data(
        self,
        exercises: List[Exercise],
        pdf_content: PDFContent,
    ) -> List[Exercise]:
        """Enrich exercises with image and latex data from their pages.

        Args:
            exercises: List of exercises (may be missing image/latex data)
            pdf_content: Original PDF content with page data

        Returns:
            Exercises with image and latex data populated
        """
        # Build page lookup
        page_map = {page.page_number: page for page in pdf_content.pages}

        for exercise in exercises:
            page = page_map.get(exercise.page_number)
            if page:
                exercise.has_images = len(page.images) > 0 if page.images else False
                exercise.image_data = page.images if page.images else []
                exercise.has_latex = page.has_latex
                exercise.latex_content = page.latex_content

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

        # Find all exercise markers FIRST
        markers = self._find_exercise_markers(text)

        if not markers:
            # No markers found on this page
            # Check if this is just an instruction page
            if self._is_instruction_page(text):
                return []  # Skip instruction-only pages

            # If we have a document-wide pattern, pages without markers are likely:
            # - Continuation of previous exercise (don't create new exercise)
            # - Header/instruction pages (already handled above)
            # So skip them to avoid inflating exercise count
            if getattr(self, '_document_pattern', None) is not None:
                return []  # Skip - this is likely continuation text

            # No document pattern AND no page markers - fallback behavior:
            # Treat entire page as single exercise if it has substantial content
            if len(text.strip()) < 50:  # Too short to be a real exercise
                return []

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

    def _detect_exercise_pattern(self, text: str) -> Optional[re.Pattern]:
        """Detect the exercise pattern used in this document dynamically.

        Language-agnostic: Analyzes text to find recurring exercise markers
        instead of hardcoding patterns like "Esercizio", "Exercise", etc.

        Args:
            text: Text to analyze

        Returns:
            Compiled pattern if found, None otherwise
        """
        # Check cache first (use hash of first 1000 chars as key)
        cache_key = str(hash(text[:1000]))
        if cache_key in self._detected_pattern_cache:
            return self._detected_pattern_cache[cache_key]

        # Look for repeated pattern: <word> <number> appearing multiple times
        # E.g., "Esercizio 1", "Esercizio 2" → pattern is "Esercizio"
        # Supports any language including CJK characters
        word_num_pattern = r'\b([A-Za-z\u00C0-\u024F\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]+)\s+(\d+)\b'
        matches = re.findall(word_num_pattern, text, re.IGNORECASE)

        # Count which words appear with multiple different numbers
        word_counts: Dict[str, set] = {}
        for word, num in matches:
            word_lower = word.lower()
            if word_lower not in word_counts:
                word_counts[word_lower] = set()
            word_counts[word_lower].add(num)

        # Find words that appear with 2+ different numbers (likely exercise markers)
        exercise_words = [(w, len(nums)) for w, nums in word_counts.items() if len(nums) >= 2]

        if exercise_words:
            # Use the word that appears with most different numbers
            exercise_words.sort(key=lambda x: x[1], reverse=True)
            word = exercise_words[0][0]
            pattern = re.compile(rf'(?:^|\n)\s*{re.escape(word)}\s+(\d+)', re.IGNORECASE | re.MULTILINE)
            self._detected_pattern_cache[cache_key] = pattern
            return pattern

        self._detected_pattern_cache[cache_key] = None
        return None

    def _find_exercise_markers(self, text: str) -> List[Tuple[int, str]]:
        """Find all exercise markers in text using dynamic detection.

        Strategy (language-agnostic):
        1. Use document-wide pattern if available (detected from full PDF)
        2. Fall back to page-level pattern detection
        3. Fall back to structural patterns (1., 2., etc.) if no word pattern found

        Args:
            text: Text to search

        Returns:
            List of tuples (position, exercise_number)
        """
        markers = []

        # Step 1: Use document-wide pattern if available (set by split_pdf_content)
        # This handles PDFs where each page has only one exercise marker
        detected_pattern = getattr(self, '_document_pattern', None)
        if detected_pattern is None:
            # Fall back to page-level detection
            detected_pattern = self._detect_exercise_pattern(text)

        if detected_pattern:
            for match in detected_pattern.finditer(text):
                position = match.start()
                ex_number = match.group(1) if match.groups() else None
                markers.append((position, ex_number))

        # If dynamic patterns found exercises, use those
        if markers:
            markers = list(set(markers))
            markers.sort(key=lambda x: x[0])
            return markers

        # Step 2: Fall back to structural patterns (1., 2., etc.)
        for pattern in self.structural_patterns:
            # Collect ALL matches first to calculate gaps correctly
            all_matches = [(m.start(), m.group(1) if m.groups() else None)
                          for m in pattern.finditer(text)]

            for i, (position, ex_number) in enumerate(all_matches):
                # Calculate fragment length (distance to next marker or end)
                if i + 1 < len(all_matches):
                    next_marker_pos = all_matches[i + 1][0]
                else:
                    next_marker_pos = len(text)

                fragment_length = next_marker_pos - position
                if fragment_length < 30:  # Minimum 30 chars (allows short Q&A questions)
                    continue

                markers.append((position, ex_number))

        # Remove duplicates and sort by position
        markers = list(set(markers))
        markers.sort(key=lambda x: x[0])

        return markers

    def _is_instruction_page(self, text: str) -> bool:
        """Check if a page contains only instructions (not exercises).

        Language-agnostic: Uses structural patterns instead of language-specific text.

        Args:
            text: Page text

        Returns:
            True if this is an instruction-only page
        """
        # Language-agnostic structural indicators of instruction pages
        # These patterns work across languages
        structural_indicators = [
            r'(?:^|\n)\s*[-•]\s+.{10,}',  # Multiple bullet points
            r':\s*\n',                     # Lines ending with colon then newline
            r'\b\d{4}[-/]\d{2}[-/]\d{2}\b',  # Date patterns (exam dates)
        ]

        # Count structural instruction patterns
        matches = sum(1 for pattern in [re.compile(p, re.MULTILINE) for p in structural_indicators]
                     if len(pattern.findall(text)) >= 2)

        # If page has many instruction-like structures and is short, likely instructions
        if matches >= 2 and len(text.strip()) < 500:
            return True

        # Check if there are NO exercise-like patterns (no repeated word+number)
        # but there ARE multiple bullet points
        detected_pattern = self._detect_exercise_pattern(text)
        bullet_count = len(re.findall(r'(?:^|\n)\s*[-•]\s+', text, re.MULTILINE))

        if detected_pattern is None and bullet_count >= 5:
            return True

        return False

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

        # Remove page numbers (language-agnostic structural pattern)
        # Pattern: short line with just a number, or "word + number" where line is short
        text = re.sub(r'(?:^|\n)\s*\d+\s*(?:\n|$)', '\n', text)  # Standalone numbers
        text = re.sub(r'(?:^|\n)\s*[A-Za-z]+\s+\d+\s*(?:\n|$)', '\n', text)  # "Word 123" short lines

        # Strip leading/trailing whitespace
        text = text.strip()

        return text
