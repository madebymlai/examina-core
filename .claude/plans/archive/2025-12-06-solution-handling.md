# Solution Handling in Exercise Splitter

## Problem Statement

The smart exercise splitter detects 10 exercises from a 6-exercise exam PDF because it's creating duplicate exercises from solution sections. For example, "a)" appears both in the question and in the solution, creating duplicates.

## Document Formats to Handle

### Format 1: Embedded Solutions (No separate keyword)
```
Esercizio 1
What is 2+2?
The answer is 4.

Esercizio 2
...
```
**Handling**: Already works - all text between exercise markers belongs to that exercise.

### Format 2: Separate Solution Sections (With keyword)
```
Esercizio 1
a) Question 1a
b) Question 1b

Soluzione  <-- Solution keyword
a) Answer 1a  <-- These sub-markers should NOT create new exercises
b) Answer 1b

Esercizio 2
...
```
**Handling**: Need to detect solution keyword and skip sub-markers within solution sections.

### Format 3: Appendix Solutions (All solutions at end)
```
Esercizio 1
a) Question 1a
b) Question 1b

Esercizio 2
...

--- SOLUTIONS ---
Esercizio 1
a) Answer 1a
...
```
**Handling**: More complex - need to match solutions to exercises.

## Current State

- `split_pdf_smart()` method implemented with LLM pattern detection
- `SolutionMatcher` class exists but not integrated
- Test result: 51 → 10 exercises (still ~4 too many due to solution section duplicates)

## Proposed Approach

### Phase 1: Filter solution sub-markers (Format 2)

**Goal**: Don't create duplicate exercises from sub-markers in solution sections.

**Steps**:
1. LLM prompt already detects exercise keyword - also detect solution keyword
2. Find all positions of solution keyword in document
3. When finding sub-markers, skip those that appear after a solution keyword (until next exercise marker)
4. Result: Only questions become exercises, solutions are included in parent exercise text

### Phase 2: Extract and attach solutions (Format 2 & 3)

**Goal**: Populate `exercise.solution` field with the solution text.

**Steps**:
1. For each exercise, find the solution section that matches (by exercise number)
2. Extract solution text and attach to exercise
3. Use existing `SolutionMatcher` for appendix format

## Implementation Plan

**IMPORTANT: Language-Agnostic (per rules.md)**
- NO hardcoded keywords in prompts or code
- LLM detects BOTH exercise keyword AND solution keyword dynamically
- Examples in this plan are illustrative only

### Step 1: Update LLM prompt
Add solution keyword detection. Prompt asks LLM to identify:
1. The keyword used before exercise numbers
2. The keyword used before solution sections (if any)

Output format:
```python
{{"mode": "pattern", "keyword": "...", "solution_keyword": "..." or null, ...}}
```

### Step 2: Update MarkerPattern dataclass
```python
@dataclass
class MarkerPattern:
    keyword: str
    has_sub_markers: bool
    sub_format: Optional[str]
    solution_keyword: Optional[str] = None  # NEW
```

### Step 3: Update _find_all_markers
- Find solution section start positions
- When finding sub-markers, check if position is within a solution section
- Skip sub-markers in solution sections

### Step 4: Extract solution text (optional enhancement)
- For each exercise, find matching solution section
- Populate `exercise.solution` field

## Test Cases

1. **Embedded solutions** (no keyword): Should produce N exercises
2. **Separate solutions** (with keyword): Should produce N exercises, solutions attached
3. **Appendix solutions**: Should produce N exercises, solutions matched

## Edge Cases

- No solution keyword detected: All text belongs to exercises (current behavior)
- Multiple solution keywords: Handle each independently
- Solution keyword appears in exercise text: Use position-based matching

## Files to Modify

| File | Changes |
|------|---------|
| `core/exercise_splitter.py` | Add solution_keyword to MarkerPattern, update _find_all_markers |

## Dependencies

- None - pure enhancement to existing code
