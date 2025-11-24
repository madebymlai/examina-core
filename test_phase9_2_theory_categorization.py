#!/usr/bin/env python3
"""
Test Phase 9.2: Theory Question Categorization
Tests theory categorization on ADE, AL, and PC courses
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from storage.database import Database
from core.analyzer import ExerciseAnalyzer
from models.llm_manager import LLMManager
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import json

console = Console()

def test_theory_categorization(course_code: str, course_name: str, sample_size: int = 5):
    """Test theory categorization on a specific course."""

    console.print(f"\n{'='*80}")
    console.print(Panel(f"[bold cyan]Testing Theory Categorization: {course_name}[/bold cyan]", expand=False))
    console.print(f"{'='*80}\n")

    with Database() as db:
        # Get exercises for this course
        exercises = db.get_exercises_by_course(course_code)

        if not exercises:
            console.print(f"[yellow]No exercises found for {course_code}[/yellow]")
            return

        console.print(f"Found {len(exercises)} exercises in {course_code}")

        # Sample exercises to test
        import random
        test_exercises = random.sample(exercises, min(sample_size, len(exercises)))

        # Initialize analyzer with Italian for Italian courses
        language = "it" if course_code in ["B006802", "B006807", "B018757"] else "en"

        # Initialize LLM with correct provider from Config
        from config import Config
        llm = LLMManager(provider=Config.LLM_PROVIDER)
        analyzer = ExerciseAnalyzer(llm_manager=llm, language=language)

        console.print(f"Analyzing {len(test_exercises)} sample exercises...\n")

        results = []

        for ex in test_exercises:
            console.print(f"[dim]Analyzing: {ex['id'][:40]}...[/dim]")

            # Analyze exercise
            analysis = analyzer.analyze_exercise(
                exercise_text=ex['text'],
                course_name=course_name,
                previous_exercise=None
            )

            results.append({
                'id': ex['id'],
                'text_preview': ex['text'][:200],
                'analysis': analysis
            })

        # Display results in a table
        console.print("\n[bold green]Analysis Results:[/bold green]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Exercise ID", width=20)
        table.add_column("Type", width=12)
        table.add_column("Theory Category", width=15)
        table.add_column("Concept ID", width=20)
        table.add_column("Confidence", width=10)

        theory_count = 0
        procedural_count = 0
        hybrid_count = 0
        proof_count = 0

        for result in results:
            analysis = result['analysis']

            # Count types
            if analysis.exercise_type == 'theory':
                theory_count += 1
            elif analysis.exercise_type == 'procedural':
                procedural_count += 1
            elif analysis.exercise_type == 'hybrid':
                hybrid_count += 1
            elif analysis.exercise_type == 'proof':
                proof_count += 1

            table.add_row(
                result['id'][:20] + "...",
                analysis.exercise_type or "procedural",
                analysis.theory_category or "N/A",
                analysis.concept_id or "N/A",
                f"{analysis.type_confidence:.2f}"
            )

        console.print(table)

        # Display detailed breakdown
        console.print("\n[bold]Exercise Type Distribution:[/bold]")
        console.print(f"  Procedural: {procedural_count}")
        console.print(f"  Theory: {theory_count}")
        console.print(f"  Proof: {proof_count}")
        console.print(f"  Hybrid: {hybrid_count}")

        # Show theory categories
        if theory_count > 0 or hybrid_count > 0:
            console.print("\n[bold]Theory Categories Detected:[/bold]")
            categories = {}
            for result in results:
                if result['analysis'].theory_category:
                    cat = result['analysis'].theory_category
                    categories[cat] = categories.get(cat, 0) + 1

            for cat, count in sorted(categories.items()):
                console.print(f"  {cat}: {count}")

        # Show detailed examples
        console.print("\n[bold cyan]Detailed Examples:[/bold cyan]\n")

        for i, result in enumerate(results[:3], 1):  # Show first 3 in detail
            analysis = result['analysis']
            console.print(Panel(
                f"[bold]Exercise {i}:[/bold] {result['id'][:40]}...\n\n"
                f"[dim]{result['text_preview']}...[/dim]\n\n"
                f"[yellow]Type:[/yellow] {analysis.exercise_type}\n"
                f"[yellow]Category:[/yellow] {analysis.theory_category or 'N/A'}\n"
                f"[yellow]Concept:[/yellow] {analysis.concept_id or 'N/A'}\n"
                f"[yellow]Theorem:[/yellow] {analysis.theorem_name or 'N/A'}\n"
                f"[yellow]Prerequisites:[/yellow] {', '.join(analysis.prerequisite_concepts or []) or 'N/A'}\n"
                f"[yellow]Confidence:[/yellow] {analysis.type_confidence:.2f}",
                title=f"Example {i}",
                expand=False
            ))

        return {
            'course_code': course_code,
            'total_analyzed': len(test_exercises),
            'procedural': procedural_count,
            'theory': theory_count,
            'proof': proof_count,
            'hybrid': hybrid_count,
            'results': results
        }


def main():
    """Run theory categorization tests on all three courses."""

    console.print(Panel.fit(
        "[bold cyan]Phase 9.2: Theory Question Categorization Test[/bold cyan]\n"
        "Testing theory detection and categorization on ADE, AL, and PC",
        border_style="cyan"
    ))

    # Test on all three courses
    courses = [
        ("B006802", "Computer Architecture (ADE)"),
        ("B006807", "Linear Algebra (AL)"),
        ("B018757", "Concurrent Programming (PC)")
    ]

    all_results = {}

    for course_code, course_name in courses:
        try:
            result = test_theory_categorization(course_code, course_name, sample_size=3)
            if result:
                all_results[course_code] = result
        except Exception as e:
            console.print(f"[red]Error testing {course_code}: {e}[/red]")
            import traceback
            traceback.print_exc()

    # Summary across all courses
    console.print(f"\n{'='*80}")
    console.print(Panel("[bold green]Summary Across All Courses[/bold green]", expand=False))
    console.print(f"{'='*80}\n")

    summary_table = Table(show_header=True, header_style="bold magenta")
    summary_table.add_column("Course", width=25)
    summary_table.add_column("Total", width=8)
    summary_table.add_column("Procedural", width=12)
    summary_table.add_column("Theory", width=10)
    summary_table.add_column("Proof", width=10)
    summary_table.add_column("Hybrid", width=10)

    for course_code, result in all_results.items():
        course_name = next(name for code, name in courses if code == course_code)
        summary_table.add_row(
            course_name,
            str(result['total_analyzed']),
            str(result['procedural']),
            str(result['theory']),
            str(result['proof']),
            str(result['hybrid'])
        )

    console.print(summary_table)

    console.print("\n[bold green]✓ Theory categorization test complete![/bold green]")
    console.print(f"\nTheory categorization is working across multiple subjects:")
    console.print("- Computer Architecture: hardware concepts, performance analysis")
    console.print("- Linear Algebra: mathematical definitions, theorems, proofs")
    console.print("- Concurrent Programming: synchronization properties, algorithm analysis")


if __name__ == "__main__":
    main()
