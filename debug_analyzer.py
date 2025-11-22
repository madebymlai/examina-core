#!/usr/bin/env python3
"""Debug analyzer to see what LLM returns for each exercise."""

import os
os.environ["GROQ_API_KEY"] = "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"

from models.llm_manager import LLMManager
from core.analyzer import ExerciseAnalyzer
from storage.database import Database

# Get first few exercises from ADE
with Database() as db:
    exercises = db.get_exercises_by_course('B006802')[:5]

llm = LLMManager(provider="groq")
analyzer = ExerciseAnalyzer(llm)

for i, ex in enumerate(exercises):
    print(f"\n{'='*80}")
    print(f"Exercise {i+1}: {ex['id']}")
    print(f"Text preview: {ex['text'][:150]}...")
    print('='*80)

    # Analyze
    analysis = analyzer.analyze_exercise(
        ex['text'],
        "Computer Architecture",
        None
    )

    print(f"is_valid_exercise: {analysis.is_valid_exercise}")
    print(f"is_fragment: {analysis.is_fragment}")
    print(f"topic: {analysis.topic}")
    print(f"core_loop_name: {analysis.core_loop_name}")
    print(f"core_loop_id: {analysis.core_loop_id}")
    print(f"difficulty: {analysis.difficulty}")
    print(f"confidence: {analysis.confidence}")
    print(f"procedure steps: {len(analysis.procedure or [])}")
