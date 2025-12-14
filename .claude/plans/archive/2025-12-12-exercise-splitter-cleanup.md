# Exercise Splitter LLM Call Cleanup

## Summary
Refactor exercise_splitter.py to have clear, consistent naming for LLM calls. Remove dead pattern-mode code, eliminate "explicit" prefix (since explicit is the only mode), and separate context summaries from end markers. This makes the codebase cleaner and easier to maintain.

## Files to Modify
- `/home/laimk/git/examina/core/exercise_splitter.py` - all changes

## Current State (Confusing)
| Function | Purpose | Issue |
|----------|---------|-------|
| `_detect_pattern_with_llm` | Parent starts + has_solutions | Name says "pattern" but it's explicit mode |
| `_get_parent_end_markers` | Parent ends | OK |
| `_get_per_exercise_sub_patterns` | Sub patterns (regex) | DEAD CODE - never called |
| `_get_explicit_sub_questions` | Sub starts | "explicit" prefix redundant |
| `_get_explicit_end_markers` | Sub ends | "explicit" prefix redundant |
| `_get_second_pass_results` | End markers + context summaries | Duplicate of Call 4, mixed concerns |
| `_apply_second_pass_results` | Apply above | Goes with above |

## Target State (Clean)
| Call | Function | Purpose |
|------|----------|---------|
| 1 | `_detect_exercises` | Parent starts + has_solutions |
| 2 | `_get_parent_end_markers` | Parent ends (uses rfind) |
| 3 | `_get_sub_start_markers` | Sub starts |
| 4 | `_get_sub_end_markers` | Sub ends (uses rfind) |
| 5 | `_get_context_summaries` | Parent context for children |
| 6 | `_detect_solutions` | Solution boundaries (future, if has_solutions) |

## Steps

### Step 1: Remove dead code
- Delete `_get_per_exercise_sub_patterns` function (~lines 947-1075)
- Delete any imports/references only used by this function

### Step 2: Rename Call 1
- Rename `_detect_pattern_with_llm` → `_detect_exercises`
- Update docstring to remove "pattern" references
- Update all call sites

### Step 3: Rename Call 3
- Rename `_get_explicit_sub_questions` → `_get_sub_start_markers`
- Remove "explicit mode" from docstring
- Update all call sites

### Step 4: Rename Call 4
- Rename `_get_explicit_end_markers` → `_get_sub_end_markers`
- Remove "explicit mode" from docstring
- Update all call sites

### Step 5: Split _get_second_pass_results
- Extract context summary logic into new `_get_context_summaries` function
- Remove end_marker logic (already handled by Call 4)
- Update `_apply_second_pass_results` → `_apply_context_summaries`
- Update call sites

### Step 6: Clean up comments
- Remove "explicit mode" comments throughout
- Remove "pattern mode" references
- Update section headers (e.g., "SECOND-PASS" → "CONTEXT SUMMARIES")
- Update "Sonnet call 1" comments to use consistent numbering

### Step 7: Update DetectionResult dataclass
- Remove deprecated `sub_patterns` field if still present
- Clean up docstrings

### Step 8: Test
- Run existing tests to ensure nothing broke
- Test with SO-2019 PDF (known good test case)

## Edge Cases
- What if `_get_second_pass_results` is called somewhere else? → Search for all usages first
- What if tests reference old function names? → Update test files too
- What if there are type hints referencing old names? → Update those

## Dependencies
- Step 5 depends on Steps 3, 4 (need to understand what's duplicate)
- Step 6 depends on Steps 1-5 (clean up after main refactoring)
- Step 8 depends on all previous steps
