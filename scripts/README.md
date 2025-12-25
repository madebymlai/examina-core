# Qupled Scripts

This directory contains development, testing, and debugging scripts.

## Testing Scripts

### Unit Tests
- `test_sm2.py` - SM-2 algorithm unit tests
- `test_quiz_manager.py` - Quiz manager tests
- `test_dynamic_opposites.py` - LLM-based opposite detection tests

### Feature Tests
- `test_multi_procedure_analyzer.py` - Multi-procedure extraction tests
- `test_exercise_type_detection.py` - Exercise type classifier tests
- `test_enhanced_learn.py` - Enhanced learning mode tests
- `test_phase9_*.py` - Phase 9 (theory/proof) tests
- `test_full_pipeline.py` - End-to-end pipeline tests

### Performance Tests
- `test_batch_performance.py` - Batch analysis performance
- `benchmark_batch.py` - Batch processing benchmarks
- `test_confidence_filter*.py` - Confidence threshold tests

## Debug Scripts
- `debug_analyzer.py` - Debug exercise analyzer
- `debug_splitter.py` - Debug PDF splitter
- `inspect_db.py` - Inspect database contents
- `inspect_exercises.py` - Inspect exercise data
- `inspect_theory_*.py` - Inspect theory/proof data

## Demo Scripts
- `demo_semantic_matcher.py` - Semantic similarity demo
- `demo_sm2.py` - Spaced repetition demo

## Validation Scripts
- `validate_multi_procedure.py` - Validate multi-procedure extraction
- `run_phase9_5_tests.sh` - Run Phase 9.5 test suite

## Other
- `study_context.py` - Study context utilities

## Usage

Most scripts can be run directly:
```bash
python3 scripts/test_dynamic_opposites.py
python3 scripts/inspect_db.py
```

For shell scripts:
```bash
bash scripts/run_phase9_5_tests.sh
```
