#!/usr/bin/env python3
"""
Full pipeline test for Phase 9.1: Exercise Type Detection

Tests the complete workflow:
1. Analyze exercises with type detection
2. Store results in database
3. Query by exercise type
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from storage.database import Database
from core.analyzer import ExerciseAnalyzer
from models.llm_manager import LLMManager
from config import Config


def update_exercise_with_type_info(db, exercise_id, analysis):
    """Update exercise in database with type information."""
    # Prepare theory_metadata JSON
    theory_metadata_json = None
    if analysis.theory_metadata:
        theory_metadata_json = json.dumps(analysis.theory_metadata)

    # Update exercise
    db.conn.execute("""
        UPDATE exercises
        SET exercise_type = ?,
            theory_metadata = ?
        WHERE id = ?
    """, (analysis.exercise_type, theory_metadata_json, exercise_id))


def test_full_pipeline():
    """Test full pipeline with database storage."""
    print("="*80)
    print("Phase 9.1: Full Pipeline Test with Database Storage")
    print("="*80)

    with Database() as db:
        # Get a few exercises from each course
        ade_exercises = db.get_exercises_by_course('B006802', analyzed_only=True)[:3]
        al_exercises = db.get_exercises_by_course('B006807', analyzed_only=True)[:3]

        print(f"\nTesting on {len(ade_exercises)} ADE + {len(al_exercises)} AL exercises")

        # Initialize analyzer
        llm = LLMManager(provider=Config.LLM_PROVIDER)
        analyzer = ExerciseAnalyzer(llm_manager=llm, language="it")

        # Process exercises
        all_exercises = [
            ('B006802', 'Computer Architecture', ade_exercises),
            ('B006807', 'Linear Algebra', al_exercises)
        ]

        updated_count = 0

        for course_code, course_name, exercises in all_exercises:
            print(f"\n--- Processing {course_name} ({course_code}) ---")

            for i, ex in enumerate(exercises, 1):
                print(f"\n[{i}/{len(exercises)}] Analyzing {ex['id'][:40]}...")

                # Analyze
                analysis = analyzer.analyze_exercise(ex['text'], course_name)

                print(f"  Type: {analysis.exercise_type} (confidence: {analysis.type_confidence:.2f})")

                if analysis.proof_keywords:
                    print(f"  Proof keywords: {analysis.proof_keywords}")

                # Update database
                update_exercise_with_type_info(db, ex['id'], analysis)
                updated_count += 1

        db.conn.commit()

        print(f"\n{'='*80}")
        print(f"Updated {updated_count} exercises in database")
        print(f"{'='*80}")

        # Query by type
        print("\nQuerying exercises by type...")
        cursor = db.conn.execute("""
            SELECT exercise_type, COUNT(*)
            FROM exercises
            WHERE exercise_type IS NOT NULL
            GROUP BY exercise_type
        """)

        print("\nExercise Type Distribution:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")

        # Show some examples
        print("\n--- Sample Exercises by Type ---")

        for ex_type in ['procedural', 'theory', 'proof', 'hybrid']:
            cursor = db.conn.execute("""
                SELECT id, text, course_code
                FROM exercises
                WHERE exercise_type = ?
                LIMIT 1
            """, (ex_type,))

            row = cursor.fetchone()
            if row:
                print(f"\n{ex_type.upper()}:")
                print(f"  ID: {row[0][:40]}")
                print(f"  Course: {row[2]}")
                print(f"  Text: {row[1][:150]}...")


if __name__ == "__main__":
    test_full_pipeline()
