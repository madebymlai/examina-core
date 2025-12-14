# Sub-Question Detection Problem

## The Problem

The exercise splitter uses LLM-detected regex patterns to find sub-questions. The LLM returns patterns like:
```
["([a-z])\\s*\\)", "(\\d+)\\.\\s"]
```

This matches any letter followed by `)` or any number followed by `. `. But this is too greedy - it matches things that LOOK like sub-questions but aren't.

## False Positives

### 1. Inline Conditions (Roman Numerals)
Text: "returns true if i) starts with consonant or ii) ends with vowel"

- `i)` and `ii)` are conditions within ONE question, not separate sub-questions
- Pattern `([a-z])\s*\)` matches them
- Result: Creates fake `[1.i]` sub-questions

### 2. Mathematical Notation
Text: "S(n) = 1 + S(n-1)*4"

- `n)` from `S(n)` matches the pattern
- Result: Creates fake `[5.n]` sub-questions (5 times!)

### 3. Numbered Lists in Instructions
Text: "1) write in pen 2) no calculators 3) show work"

- These are exam rules, not exercises
- Pattern `(\\d+)\\)` or `(\\d+)\\.\\s` matches them
- Result: Creates garbage exercises

## Real Sub-Questions vs False Positives

| Real Sub-Question | False Positive |
|-------------------|----------------|
| `a) Calculate X` | `i) condition one` |
| `b) Prove Y` | `ii) condition two` |
| `1. First part` | `S(n)` notation |
| `2. Second part` | `1) exam rule` |

### Key Differences

1. **Position**: Real subs typically start new lines. False positives appear mid-sentence.

2. **Sequence**: Real subs follow order (a→b→c or 1→2→3). False positives are random or roman numerals.

3. **Content**: Real subs have substantial question text after them. False positives have formula fragments or conditions.

4. **Uniqueness**: Real subs appear once each. False positives like `n)` from `S(n)` repeat many times.

## Rejected Solutions

### 1. Prompt Engineering
Added to LLM prompt:
```
CRITICAL: Sub-questions are SEPARATE TASKS, each requiring its own distinct answer.
Markers appearing mid-sentence as conditions/options for ONE task are NOT sub-questions.
```
**Rejected**: DeepSeek ignored it. Still returned same pattern.

### 2. Use Sonnet Instead
Tried Sonnet for pattern detection.
**Rejected**: Worse - returned prose before JSON, caused parse failure, 43 garbage exercises. Also expensive.

### 3. Line-Start Requirement
Only match sub-patterns at start of line: `^\s*([a-z])\s*\)`
**Rejected**: Would miss legitimate inline subs like `a) Calculate X b) Prove Y c) Explain Z`

### 4. Exclude Roman Numerals from Regex
Modify regex: `([a-hj-uw-z])\s*\)` (skip i, v, x)
**Rejected**: Would miss legitimate sub-questions using i, v, x (9th, 22nd, 24th items)

### 5. Minimum Content Length
Require >20-30 chars of text after each sub-marker.
**Rejected**: Would kill legitimate short subs like `[7.a]: FCFS` and `[7.b]: Shortest Job First`

### 6. Sequence Validation (a→b→c)
Check that letter subs start from 'a' and are sequential.
**Rejected**: Roman numerals i, ii, iii ARE sequential. Also doesn't help with `S(n)` → `n)` matches.

### 7. Duplicate Detection with Fallback
If same sub-number appears multiple times, fallback to no subs.
**Rejected**: Would incorrectly reject bullet subs (`-`, `•`) which all have same "marker".

### 8. Count Threshold for Bullets
If >10 bullet matches, reject all.
**Rejected**: Arbitrary threshold, might reject valid exams with many bullet subs.

### 9. Relative Content Check
Compare sub-question lengths to siblings.
**Rejected**: Complex, still wouldn't distinguish valid short subs from fragments.

### 10. Two-Stage Validation
For each pattern match, ask LLM "is this a real sub-question?"
**Rejected**: N extra LLM calls per document. Too expensive.

### 11. Confidence Threshold
LLM returns confidence score with patterns, skip subs if low confidence.
**Rejected**: LLMs are bad at calibrated confidence, often overconfident when wrong.

### 12. Conservative Default
Only detect subs when structure is very obvious.
**Rejected**: Creates more false positives of unsplit standalone exercises. Loses functionality.

### 13. Pattern + Position Hybrid
Pattern must match AND pass position checks (not inside parens, not after "if/or/where").
**Rejected**: Would reject legitimate `(a)`, `(b)`, `(c)` format subs. Complex, language-specific.

### 14. Document Type Detection
Detect "Solutions" files and handle differently.
**Rejected**: Problem isn't caused by Solutions files. `i)` conditions and `S(n)` can appear anywhere.

### 15. Fallback Chain
Try detection → if garbage → retry stricter → if still garbage → no subs.
**Rejected**: Still needs to define "garbage" which brings back all the heuristic problems.

### 16. User Correction
Show detected subs, let user fix mistakes.
**Rejected**: Bad UX. Users expect it to work. Doesn't scale for bulk uploads.

## Potential Solutions

### A. Exclude Roman Numerals
Modify regex to skip letters commonly used as roman numerals:
```python
# Instead of: ([a-z])\s*\)
# Use: ([a-hj-uw-z])\s*\)  # excludes i, v, x
```

**Pros**: Simple, catches the `i)`, `ii)` case
**Cons**: Would miss legitimate sub-questions using i, v, x (rare but possible)

### B. Duplicate Detection
If same sub-number appears multiple times, something is wrong:
```python
sub_counts = Counter(ex.exercise_number for ex in exercises if ex.is_sub_question)
invalid_parents = {num.split('.')[0] for num, count in sub_counts.items() if count > 1}
# Remove subs for those parents
```

**Pros**: Catches the `[5.n]` × 5 case
**Cons**: Doesn't catch single false positives like `[1.i]`

### C. Sequence Validation
Real sub-questions follow predictable sequences:
```python
# Valid: a, b, c, d or 1, 2, 3, 4
# Invalid: i, ii, iii (roman) or n, x, e (random)

def is_valid_sequence(markers):
    letters = [m for m in markers if m.isalpha()]
    if letters:
        # Check if it's a→b→c progression
        expected = 'abcdefgh'[:len(letters)]
        return ''.join(sorted(letters)) == expected
    return True
```

**Pros**: Catches both roman numerals AND random letters
**Cons**: Complex, might have edge cases

### D. Position-Based Validation
Only accept sub-markers that appear at line start:
```python
# Instead of searching whole text
# Search with line-start anchor
pattern = r'^\s*([a-z])\s*[).]'  # ^ = line start
```

**Pros**: Most robust - real subs ARE at line start
**Cons**: Would miss legitimate inline subs like "a) X b) Y c) Z"

### E. Minimum Content Threshold
Real sub-questions have substantial content after them:
```python
def validate_sub(match_pos, text, next_match_pos):
    content_between = text[match_pos:next_match_pos]
    # Real sub has at least 20 chars of actual question
    return len(content_between.strip()) >= 20
```

**Pros**: Catches fragments like `n)` from `S(n)`
**Cons**: Threshold is arbitrary, might filter short but valid subs

### F. Hybrid Approach
Combine multiple validators:
```python
def validate_sub_questions(exercises):
    # 1. Check for duplicates
    if has_duplicates(exercises):
        return remove_subs_for_affected_parents(exercises)

    # 2. Check sequence (a→b→c)
    if not valid_sequence(exercises):
        return remove_invalid_subs(exercises)

    # 3. Check minimum content
    exercises = [ex for ex in exercises if has_enough_content(ex)]

    return exercises
```

## Recommendation

**Hybrid approach (F)** with:
1. Duplicate detection (catches `[5.n]` × 5)
2. Sequence validation (catches roman numerals `i, ii, iii`)
3. Optional: minimum content check

This is deterministic (no LLM reliance) and handles the known failure cases without being overly strict.

## Test Cases

Should pass:
- SO exams with a), b), c) sub-questions
- AL exams with 1., 2., 3. sub-questions
- ADE exams with numbered sub-questions

Should now work:
- ADE 2020 Solutions (was: 17 garbage exercises, should be: ~5 clean exercises)

## Open Questions

1. Are there legitimate exams where sub-questions use i, v, x as letters (not roman)?
2. Are there exams with very short sub-questions (< 20 chars)?
3. How do we handle exams where sub-question format changes mid-exam?
