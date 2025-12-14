# Optimize LLM Call Flow with Parallel Execution

## Summary
Restructure exercise splitting to use parallel LLM calls per exercise, with `has_sub_questions` flag in Call 2 to skip unnecessary calls for standalone exercises. Reduces round trips from ~17 sequential to ~5 parallel.

## Files to Modify
- `/home/laimk/git/examina/core/exercise_splitter.py` - all changes

## Final Flow

```
CALL 1: _detect_exercises (batched)
  Input:  First 30k chars of document
  Output: Parent start markers + has_solutions

CALL 2: _analyze_exercises (parallel per exercise)
  Input:  Full text of each exercise
  Output: end_marker + has_sub_questions

         ┌─── has_sub_questions=true ───┐
         │                              │
         ▼                              │
CALL 3: _get_sub_start_markers          │ has_sub_questions=false
  (parallel per parent with subs)       │ → SKIP Calls 3, 4, 5
  Output: sub start_markers             │
         │                              │
         ▼                              │
CALL 4: _get_sub_end_markers            │
  (parallel per sub-question)           │
  Output: sub end_markers (rfind)       │
         │                              │
         ▼                              │
CALL 5: _get_context_summaries          │
  (parallel per parent with subs)       │
  Output: context_summary               │
```

## Example: 5 exercises, 2 have subs (6 sub-questions)

| Call | Purpose | Count | Mode |
|------|---------|-------|------|
| 1 | Parent starts + has_solutions | 1 | batched |
| 2 | Parent ends + has_sub_questions | 5 | parallel |
| 3 | Sub start markers | 2 | parallel (skip 3) |
| 4 | Sub end markers | 6 | parallel |
| 5 | Context summaries | 2 | parallel |

**Round trips: 5** (vs ~17 sequential before)

## Steps

### Step 1: Create async helper for parallel calls
```python
async def _call_llm_parallel(
    items: List[T],
    prompt_fn: Callable[[T], str],
    llm_manager: "LLMManager",
) -> List[str]:
    """Run LLM calls in parallel for multiple items."""
    async def call_one(item):
        prompt = prompt_fn(item)
        return llm_manager.generate(prompt, temperature=0.0)

    return await asyncio.gather(*[call_one(item) for item in items])
```

### Step 2: Update Call 2 to parallel + has_sub_questions

**New function:**
```python
async def _analyze_exercises(
    parent_markers: List[Marker],
    full_text: str,
    llm_manager: "LLMManager",
) -> Dict[str, ExerciseAnalysis]:
    """Call 2: Analyze each exercise in parallel.

    Returns dict mapping exercise number to:
      - end_pos: int
      - has_sub_questions: bool
    """
```

**Prompt per exercise:**
```
For this exercise, identify:
1. end_marker: LAST 40-60 characters of the question
2. has_sub_questions: true if contains sub-parts (a), b), c) or 1., 2., 3.)

EXERCISE:
"""
{exercise_text}
"""

Return JSON:
{"end_marker": "...", "has_sub_questions": true/false}
```

### Step 3: Update Call 3 to parallel + filter by has_subs

**Modify `_get_sub_start_markers`:**
- Take list of exercises where has_sub_questions=true
- Run parallel calls, one per exercise
- Return dict of exercise_number → sub_markers[]

### Step 4: Update Call 4 to parallel per sub-question

**Modify `_get_sub_end_markers`:**
- Take list of sub-questions (not exercises)
- Run parallel calls, one per sub-question
- Use rfind for end marker detection

### Step 5: Update Call 5 to parallel + filter by has_subs

**Modify `_get_context_summaries`:**
- Only run for parents where has_sub_questions=true
- Run parallel calls, one per parent

### Step 6: Update main split_with_llm method

```python
# Call 1: Detect parent exercises (batched)
detection = _detect_exercises(full_text[:30000], llm_manager)

# Call 2: Analyze exercises (parallel)
analysis = await _analyze_exercises(parent_markers, full_text, llm_manager)

# Filter exercises with subs
exercises_with_subs = [m for m in parent_markers if analysis[m.number].has_sub_questions]

if exercises_with_subs:
    # Call 3: Get sub start markers (parallel)
    sub_markers = await _get_sub_start_markers(exercises_with_subs, full_text, llm_manager)

    # Call 4: Get sub end markers (parallel)
    all_subs = flatten(sub_markers.values())
    await _get_sub_end_markers(all_subs, llm_manager)

    # Call 5: Get context summaries (parallel)
    contexts = await _get_context_summaries(exercises_with_subs, llm_manager)
```

### Step 7: Add logging for optimization visibility
```python
logger.info(f"Call 2: {len(exercises_with_subs)}/{len(parent_markers)} exercises have sub-questions")
if standalone := len(parent_markers) - len(exercises_with_subs):
    logger.info(f"Skipping Calls 3-5 for {standalone} standalone exercises")
```

### Step 8: Clean up old batched functions
- Remove old batched `_get_parent_end_markers` (replaced by parallel Call 2)
- Update/remove any dead code paths

### Step 9: Test
- Test with SO-2019 PDF (has sub-questions)
- Test with PDF that has standalone exercises
- Verify call counts and wall time improvement
- Verify accuracy unchanged

## Edge Cases
- has_sub_questions defaults to True if LLM returns null (safe fallback)
- All exercises have subs → no skip, same call count as before
- No exercises have subs → skip Calls 3, 4, 5 entirely
- LLM rate limits → asyncio.Semaphore to limit concurrency
- Very large documents → may need chunking

## Dependencies
- Step 1 must be done first (async helper)
- Steps 2-5 can be done in order (each builds on previous)
- Step 6 integrates everything
- Step 8 cleanup after Step 6 works
- Step 9 after all implementation
