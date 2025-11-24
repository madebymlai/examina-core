#!/usr/bin/env python3
"""
Test proof keyword detection on AL exercises.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from storage.database import Database
from core.analyzer import ExerciseAnalyzer
from models.llm_manager import LLMManager
from config import Config


def test_proof_detection():
    """Test proof keyword detection."""
    print("="*80)
    print("Testing Proof Keyword Detection")
    print("="*80)

    with Database() as db:
        exercises = db.get_exercises_by_course('B006807', analyzed_only=True)

        # Find exercises with "dimostra" keyword
        proof_exercises = []
        for ex in exercises:
            if 'dimostra' in ex['text'].lower():
                proof_exercises.append(ex)

        print(f"\nFound {len(proof_exercises)} exercises with 'dimostra' keyword")

        # Test on first 3
        llm = LLMManager(provider=Config.LLM_PROVIDER)
        analyzer = ExerciseAnalyzer(llm_manager=llm, language="it")

        for i, ex in enumerate(proof_exercises[:3], 1):
            print(f"\n{'='*80}")
            print(f"Exercise {i}: {ex['id'][:50]}")
            print(f"{'='*80}")
            print(f"Text preview: {ex['text'][:400]}...")

            # Analyze
            analysis = analyzer.analyze_exercise(ex['text'], "Linear Algebra")

            print(f"\n--- Results ---")
            print(f"Exercise Type: {analysis.exercise_type}")
            print(f"Type Confidence: {analysis.type_confidence:.2f}")
            print(f"Proof Keywords Detected: {analysis.proof_keywords}")

            # Check if proof keywords were detected
            if analysis.proof_keywords:
                print("✓ PASS: Proof keywords detected")
            else:
                print("✗ FAIL: Proof keywords NOT detected despite 'dimostra' in text")

            if analysis.exercise_type in ['proof', 'hybrid']:
                print(f"✓ PASS: Exercise classified as {analysis.exercise_type}")
            else:
                print(f"⚠ WARNING: Exercise classified as {analysis.exercise_type}, expected 'proof' or 'hybrid'")


if __name__ == "__main__":
    test_proof_detection()
