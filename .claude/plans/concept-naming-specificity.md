# Concept Naming Specificity Fix

## Summary
Fix the analyzer prompt to produce specific concept names instead of broad categories. Currently generating generic names because NAMING section says "textbook chapter" which is too broad. The fix is simple: clarify that names should be TECHNIQUES from a textbook INDEX, not problem scenarios.

## Files to Modify
- `core/analyzer.py` - Update NAMING section in `_build_analysis_prompt` method (lines 324-328)

## Steps
1. Update NAMING section (lines 324-328) to add: "Name the TECHNIQUE or CONCEPT being tested, not the problem scenario", "Ask: What would a student study to solve this?", "The name should appear in a textbook INDEX for this subject area"
2. Test by re-analyzing a course with force=True and verify concept names are technique-based

## Edge Cases
- Word problems with elaborate scenarios - the INDEX guidance helps focus on technique
- Sub-questions already handled well by existing parent_context logic (lines 251-253)

## Dependencies
- Step 2 depends on Step 1
