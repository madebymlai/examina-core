# Restore Smart Split Implementation

## Status
Implementation was complete and tested successfully, but lost due to accidental `git checkout`. This plan contains everything needed to restore.

## What Was Working
- Smart Split detected 10 exercises from SO PDF
- Call 2 identified 5/10 with sub-questions
- Skipped Calls 3-5 for 5 standalone exercises (optimization working!)
- Found 18 total exercises (parents + subs)
- Context summaries applied to sub-questions

## Files to Modify
- `/home/laimk/git/qupled/core/exercise_splitter.py`
- `/home/laimk/git/qupled/models/llm_manager.py` (already done - default provider = deepseek)

---

## PART 1: Add New Dataclass

Add after `DetectionResult` class (around line 230):

```python
@dataclass
class ExerciseAnalysis:
    """Result from Call 2: per-exercise analysis."""
    end_pos: int  # Character position where exercise ends
    has_sub_questions: bool  # Whether exercise contains sub-questions
```

---

## PART 2: Add Call 2 Functions

### 2A: _analyze_exercise (single exercise, async)

**APPROVED PROMPT:**
```python
async def _analyze_exercise(
    exercise_num: str,
    exercise_text: str,
    start_pos: int,
    llm_manager: "LLMManager",
) -> Tuple[str, ExerciseAnalysis]:
    """Analyze a single exercise (one parallel call)."""
    prompt = f"""Identify for this exercise:
1. end_marker: LAST 40-60 characters of the ENTIRE exercise question
2. has_sub_questions: true/false

CRITICAL:
- end_marker should be at the END of all question content (INCLUDING any sub-questions), BEFORE any:
  - Form fields or blank lines for answers
  - Solutions or answer sections
  - Page headers/footers
  - Exam instructions
  - Junk text between exercises

- has_sub_questions = true if exercise contains SEPARATE tasks requiring SEPARATE answers
  - Can be marked: a), b), c), 1., 2., 3., i), ii), -, •, etc.
  - Can be unmarked: separate paragraphs asking different things
- has_sub_questions = false if exercise contains only ONE task (with its data/context)

EXERCISE:
\"\"\"
{exercise_text}
\"\"\"

Return JSON:
{{"end_marker": "last 40-60 chars verbatim", "has_sub_questions": true/false}}"""

    try:
        llm_response = llm_manager.generate(prompt, temperature=0.0)
        response_text = llm_response.text if hasattr(llm_response, 'text') else str(llm_response)

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            end_marker = data.get("end_marker", "")
            has_subs = data.get("has_sub_questions", True)  # Default True = safe fallback

            # Find end position using rfind
            end_pos = start_pos + len(exercise_text)  # Default to rough end
            clean_marker = end_marker.strip().strip("...").strip("…").strip()
            if len(clean_marker) >= 10:
                pos = _fuzzy_rfind(exercise_text, clean_marker)
                if pos >= 0:
                    end_pos = start_pos + pos + len(clean_marker)

            return exercise_num, ExerciseAnalysis(end_pos=end_pos, has_sub_questions=has_subs)

    except Exception as e:
        logger.warning(f"Exercise {exercise_num} analysis failed: {e}")

    # Fallback: assume has subs (safe), use rough end
    return exercise_num, ExerciseAnalysis(
        end_pos=start_pos + len(exercise_text),
        has_sub_questions=True
    )
```

### 2B: _analyze_boundaries (for Smart Split with ExerciseBoundary)

```python
async def _analyze_boundaries(
    boundaries: List[ExerciseBoundary],
    full_text: str,
    llm_manager: "LLMManager",
) -> Dict[str, ExerciseAnalysis]:
    """Call 2 for Smart Split: Analyze exercise boundaries in parallel."""
    if not boundaries:
        return {}

    # Pre-compute rough end positions
    rough_ends: Dict[str, int] = {}
    sorted_boundaries = sorted(boundaries, key=lambda b: b.start_pos)
    for i, boundary in enumerate(sorted_boundaries):
        if i + 1 < len(sorted_boundaries):
            rough_ends[boundary.number] = sorted_boundaries[i + 1].start_pos
        else:
            rough_ends[boundary.number] = len(full_text)

    logger.info(f"Analyzing {len(boundaries)} exercises (parallel)...")

    async def analyze_one(boundary: ExerciseBoundary) -> Tuple[str, ExerciseAnalysis]:
        start = boundary.start_pos
        end = rough_ends.get(boundary.number, len(full_text))
        exercise_text = full_text[start:end].strip()
        return await _analyze_exercise(boundary.number, exercise_text, start, llm_manager)

    tasks = [analyze_one(b) for b in boundaries]
    results = await asyncio.gather(*tasks)
    analysis_dict = dict(results)

    with_subs = sum(1 for a in analysis_dict.values() if a.has_sub_questions)
    logger.info(f"Call 2 complete: {with_subs}/{len(analysis_dict)} exercises have sub-questions")

    return analysis_dict
```

---

## PART 3: Add Call 3 Functions

### 3A: _get_sub_start_markers_for_exercise (single exercise)

**APPROVED PROMPT:**
```python
async def _get_sub_start_markers_for_exercise(
    exercise_num: str,
    exercise_text: str,
    llm_manager: "LLMManager",
) -> Tuple[str, Optional[List[str]]]:
    """Call 3: Get sub-question start markers for one exercise."""
    prompt = f"""Identify sub-questions in this exercise.

Sub-questions are SEPARATE TASKS requiring SEPARATE ANSWERS:
- Can be marked: a), b), c), 1., 2., 3., i), ii), -, •, etc.
- Can be unmarked: separate paragraphs asking different things

Key distinction:
- Sub-question: asks student to DO something (produce answer, calculation, drawing)
- NOT a sub-question: GIVES INFORMATION to student

IMPORTANT: Return the EXACT first 10-15 words as they appear (copy verbatim, including markers).

EXERCISE:
\"\"\"
{exercise_text}
\"\"\"

Return JSON:
{{"sub_questions": ["exact first 10-15 words of sub 1...", "exact first 10-15 words of sub 2..."] or null}}"""

    try:
        llm_response = llm_manager.generate(prompt, temperature=0.0)
        response_text = llm_response.text if hasattr(llm_response, 'text') else str(llm_response)

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            subs = data.get("sub_questions")
            return exercise_num, subs

    except Exception as e:
        logger.warning(f"Exercise {exercise_num} sub detection failed: {e}")

    return exercise_num, None
```

### 3B: _get_sub_start_markers_parallel

```python
async def _get_sub_start_markers_parallel(
    exercises_with_subs: List[Tuple[str, str]],  # List of (exercise_num, exercise_text)
    llm_manager: "LLMManager",
) -> Dict[str, List[str]]:
    """Call 3: Get sub-question start markers in parallel."""
    if not exercises_with_subs:
        return {}

    logger.info(f"Getting sub-question start markers for {len(exercises_with_subs)} exercises in parallel (Call 3)...")

    async def process_one(item: Tuple[str, str]) -> Tuple[str, Optional[List[str]]]:
        ex_num, ex_text = item
        return await _get_sub_start_markers_for_exercise(ex_num, ex_text, llm_manager)

    tasks = [process_one(item) for item in exercises_with_subs]
    results = await asyncio.gather(*tasks)

    # Filter out None results
    results_dict = {num: subs for num, subs in results if subs}

    with_subs = len(results_dict)
    logger.info(f"Call 3 complete: found sub-questions in {with_subs}/{len(exercises_with_subs)} exercises")

    return results_dict
```

---

## PART 4: Add Call 4 Functions

### 4A: _get_sub_end_marker_for_sub (single sub-question)

**APPROVED PROMPT:**
```python
async def _get_sub_end_marker_for_sub(
    sub_id: str,
    sub_text: str,
    llm_manager: "LLMManager",
) -> Tuple[str, Optional[str]]:
    """Call 4: Get end marker for one sub-question."""
    prompt = f"""Identify where this sub-question ENDS.
Return the last 30-50 characters of the actual question (before any trailing junk like page numbers, form fields, next sub-question markers).

SUB-QUESTION:
\"\"\"
{sub_text}
\"\"\"

Return JSON:
{{"end_marker": "last 30-50 chars verbatim"}}

IMPORTANT: end_marker must be EXACT text, used to find where to trim."""

    try:
        llm_response = llm_manager.generate(prompt, temperature=0.0)
        response_text = llm_response.text if hasattr(llm_response, 'text') else str(llm_response)

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            end_marker = data.get("end_marker")
            return sub_id, end_marker

    except Exception as e:
        logger.warning(f"Sub {sub_id} end marker detection failed: {e}")

    return sub_id, None
```

### 4B: _get_sub_end_markers_parallel

```python
async def _get_sub_end_markers_parallel(
    sub_questions: List[Tuple[str, str]],  # List of (sub_id, sub_text)
    llm_manager: "LLMManager",
) -> Dict[str, str]:
    """Call 4: Get sub-question end markers in parallel."""
    if not sub_questions:
        return {}

    logger.info(f"Getting end markers for {len(sub_questions)} sub-questions in parallel (Call 4)...")

    async def process_one(item: Tuple[str, str]) -> Tuple[str, Optional[str]]:
        sub_id, sub_text = item
        return await _get_sub_end_marker_for_sub(sub_id, sub_text, llm_manager)

    tasks = [process_one(item) for item in sub_questions]
    results = await asyncio.gather(*tasks)

    # Filter out None results
    results_dict = {sub_id: marker for sub_id, marker in results if marker}

    logger.info(f"Call 4 complete: found end markers for {len(results_dict)}/{len(sub_questions)} sub-questions")

    return results_dict
```

---

## PART 5: Add Call 5 Functions

### 5A: _get_context_summary_for_parent (single parent)

**APPROVED PROMPT:**
```python
async def _get_context_summary_for_parent(
    exercise_num: str,
    parent_text: str,
    llm_manager: "LLMManager",
) -> Tuple[str, Optional[str]]:
    """Call 5: Get context summary for one parent exercise."""
    prompt = f"""Extract the shared context that sub-questions need from this parent exercise.

Good context: data values, parameters, scenario setup, definitions that sub-questions reference.
Return null if sub-questions are independent and don't need shared info.
IMPORTANT: Return context_summary in ENGLISH, even if source is another language.

PARENT EXERCISE:
\"\"\"
{parent_text}
\"\"\"

Return JSON:
{{"context_summary": "shared context in English" or null}}"""

    try:
        llm_response = llm_manager.generate(prompt, temperature=0.0)
        response_text = llm_response.text if hasattr(llm_response, 'text') else str(llm_response)

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            summary = data.get("context_summary")
            if summary and summary != "null":
                return exercise_num, summary

    except Exception as e:
        logger.warning(f"Exercise {exercise_num} context summary failed: {e}")

    return exercise_num, None
```

### 5B: _get_context_summaries_parallel

```python
async def _get_context_summaries_parallel(
    parents_with_subs: List[Tuple[str, str]],  # List of (exercise_num, parent_text)
    llm_manager: "LLMManager",
) -> Dict[str, str]:
    """Call 5: Get context summaries in parallel."""
    if not parents_with_subs:
        return {}

    logger.info(f"Getting context summaries for {len(parents_with_subs)} parents in parallel (Call 5)...")

    async def process_one(item: Tuple[str, str]) -> Tuple[str, Optional[str]]:
        ex_num, parent_text = item
        return await _get_context_summary_for_parent(ex_num, parent_text, llm_manager)

    tasks = [process_one(item) for item in parents_with_subs]
    results = await asyncio.gather(*tasks)

    # Filter out None results
    summaries_dict = {num: summary for num, summary in results if summary}

    logger.info(f"Call 5 complete: got context summaries for {len(summaries_dict)}/{len(parents_with_subs)} parents")

    return summaries_dict
```

---

## PART 6: Update Smart Split Flow

Replace Mode 2a section in `split_pdf_smart` method with:

```python
if detection.explicit_exercises:
    # Smart Split: Explicit exercises with parallel analysis
    logger.info(f"Smart Split: {len(detection.explicit_exercises)} exercises detected")
    boundaries = _find_explicit_exercises(full_text, detection.explicit_exercises)

    if second_pass_llm:
        # Call 2: Analyze exercises (end_pos + has_sub_questions, parallel)
        exercise_analysis = asyncio.run(
            _analyze_boundaries(boundaries, full_text, second_pass_llm)
        )

        # Update boundaries with accurate end positions from Call 2
        for boundary in boundaries:
            analysis = exercise_analysis.get(boundary.number)
            if analysis:
                boundary.end_pos = analysis.end_pos

        # Filter exercises that have sub-questions
        boundaries_with_subs = [
            b for b in boundaries
            if exercise_analysis.get(b.number, ExerciseAnalysis(0, True)).has_sub_questions
        ]
        standalone_count = len(boundaries) - len(boundaries_with_subs)

        if standalone_count > 0:
            logger.info(f"Skipping Calls 3-5 for {standalone_count} standalone exercises")

        # Call 3: Sub-question start markers (parallel, only for exercises with subs)
        if boundaries_with_subs:
            exercises_for_call3 = [
                (b.number, full_text[b.start_pos:exercise_analysis[b.number].end_pos])
                for b in boundaries_with_subs
            ]
            explicit_subs = asyncio.run(
                _get_sub_start_markers_parallel(exercises_for_call3, second_pass_llm)
            )
        else:
            explicit_subs = {}
    else:
        explicit_subs = {}

    exercises = _create_exercises_from_explicit_boundaries(
        boundaries, explicit_subs, full_text, pdf_content, course_code, page_lookup
    )

    # Call 4: Get end markers to trim trailing artifacts (only for exercises with subs)
    if second_pass_llm and explicit_subs:
        sub_exercises = [ex for ex in exercises if ex.is_sub_question]
        if sub_exercises:
            sub_questions_for_call4 = [
                (f"{ex.parent_exercise_number}.{ex.sub_question_marker}", ex.text)
                for ex in sub_exercises
            ]
            end_markers = asyncio.run(
                _get_sub_end_markers_parallel(sub_questions_for_call4, second_pass_llm)
            )
            # Apply end markers to trim text
            for ex in sub_exercises:
                sub_id = f"{ex.parent_exercise_number}.{ex.sub_question_marker}"
                end_marker = end_markers.get(sub_id)
                if end_marker:
                    pos = _fuzzy_rfind(ex.text, end_marker)
                    if pos >= 0:
                        ex.text = ex.text[:pos + len(end_marker)]

    # Call 5: Context summaries (parallel, only for exercises with subs)
    if second_pass_llm and boundaries_with_subs:
        parents_for_call5 = [
            (b.number, full_text[b.start_pos:exercise_analysis[b.number].end_pos])
            for b in boundaries_with_subs
        ]
        context_summaries = asyncio.run(
            _get_context_summaries_parallel(parents_for_call5, second_pass_llm)
        )
        # Apply context summaries to sub-questions
        for ex in exercises:
            if ex.is_sub_question and ex.parent_exercise_number:
                ctx = context_summaries.get(ex.parent_exercise_number)
                if ctx:
                    ex.parent_context = ctx

    # Enrich with page data and return
    exercises = self._enrich_with_page_data(exercises, pdf_content)
    logger.info(f"Extracted {len(exercises)} exercises")
    return exercises

# No explicit exercises detected - fall back to unstructured
logger.warning("No exercises detected, falling back to unstructured split")
return _split_unstructured(pdf_content, course_code)
```

---

## PART 7: Delete Dead Code

After Smart Split works, delete these dead functions/code:

1. **Mode 2b and Mode 1 branches** - the elif blocks after Smart Split
2. **Dead functions:**
   - `_find_explicit_markers` (Mode 2b)
   - `_get_sub_start_markers` (old batched version)
   - `_get_sub_end_markers` (old batched version)
   - `_apply_context_summaries` (Mode 1)
   - `_find_all_markers` (Mode 1)
   - `_find_sub_markers_in_boundaries` (Mode 1)
   - `_build_hierarchy` (Mode 1)
   - `_expand_exercises` (Mode 1)
   - `_extract_solutions` (Mode 1)
   - `_extract_interleaved_solutions` (Mode 1)
   - `_extract_appendix_solutions` (Mode 1)

3. **Unused variables in split_pdf_smart:**
   - `markers: List[Marker] = []`
   - `solution_ranges: List[Tuple[int, int]] = []`
   - `pattern: Optional[MarkerPattern] = None`
   - `exercises_with_subs: List[Marker] = []`

---

## PART 8: Update Docstring

Update `split_pdf_smart` docstring to:

```python
"""Split PDF into exercises using LLM-based detection.

Smart Split Flow (parallel where possible, optimized with has_sub_questions):
1. _detect_exercises: Parent exercise start markers + has_solutions (batched)
2. _analyze_boundaries: end_pos + has_sub_questions (parallel per exercise)
3. _get_sub_start_markers_parallel: Sub-question start markers (parallel, only if has_subs)
4. _get_sub_end_markers_parallel: Sub-question end markers (parallel, only if has_subs)
5. _get_context_summaries_parallel: Context summaries (parallel, only if has_subs)

Args:
    pdf_content: Extracted PDF content
    course_code: Course code for ID generation
    llm_manager: LLM manager for Call 1 (detection)
    second_pass_llm: Optional LLM for Calls 2-5. If not provided, uses llm_manager.

Returns:
    List of extracted exercises with context
"""
```

---

## Test Command

After implementation, test with:

```bash
cd /home/laimk/git/qupled && python3 << 'EOF'
import logging
logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')

from pathlib import Path
from core.pdf_processor import PDFProcessor
from core.exercise_splitter import ExerciseSplitter
from models.llm_manager import LLMManager

pdf_path = Path("/home/laimk/git/qupled-cloud/test-data/SO-ESAMI/SOgennaio2020.pdf")
processor = PDFProcessor()
splitter = ExerciseSplitter()
llm = LLMManager()

pdf_content = processor.process_pdf(pdf_path)
exercises = splitter.split_pdf_smart(pdf_content, course_code="SO", llm_manager=llm, second_pass_llm=llm)

print(f"Result: {len(exercises)} exercises")
for i, ex in enumerate(exercises[:10]):
    sub = " (sub)" if ex.is_sub_question else ""
    ctx = " +ctx" if ex.parent_context else ""
    print(f"  {i+1}. [{ex.exercise_number}]{sub}{ctx}")
EOF
```

Expected output:
- Smart Split: 10 exercises detected
- Call 2: 5/10 have sub-questions
- Skipping Calls 3-5 for 5 standalone exercises
- 18 total exercises with subs marked and context applied
