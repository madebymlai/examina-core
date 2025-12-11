"""
Test exercise splitter with real PDF files using actual LLM.
"""
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add examina to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pdf_processor import PDFProcessor
from core.exercise_splitter import ExerciseSplitter
from models.llm_manager import LLMManager

# LLM provider to use for testing
LLM_PROVIDER = "deepseek"


@dataclass
class ExpectedResult:
    """Expected results for a PDF test."""
    total: int
    parents: int
    subs: int
    with_solutions: int


@dataclass
class PDFTestCase:
    """Test case for a PDF file."""
    path: str
    course_code: str
    expected: ExpectedResult
    description: str


def test_pdf(test_case: PDFTestCase) -> bool:
    """Test a single PDF file with exact expected values."""
    print(f"\n{'='*60}")
    print(f"Testing: {Path(test_case.path).name}")
    print(f"  {test_case.description}")
    print("=" * 60)

    # Process PDF
    processor = PDFProcessor()
    pdf_content = processor.process_pdf(Path(test_case.path))

    print(f"  Pages: {len(pdf_content.pages)}")
    print(f"  Total text: {sum(len(p.text) for p in pdf_content.pages)} chars")

    # Initialize LLM with deepseek provider
    llm = LLMManager(provider=LLM_PROVIDER)
    print(f"  LLM: {llm.provider} / {llm.fast_model}")

    # Split with smart splitter
    splitter = ExerciseSplitter()
    exercises = splitter.split_pdf_smart(pdf_content, test_case.course_code, llm)

    # Count results
    parents = [e for e in exercises if not e.is_sub_question]
    subs = [e for e in exercises if e.is_sub_question]
    with_solutions = [e for e in exercises if e.solution]

    actual = ExpectedResult(
        total=len(exercises),
        parents=len(parents),
        subs=len(subs),
        with_solutions=len(with_solutions),
    )

    # Compare with expected
    exp = test_case.expected
    errors = []

    if actual.total != exp.total:
        errors.append(f"total: got {actual.total}, expected {exp.total}")
    if actual.parents != exp.parents:
        errors.append(f"parents: got {actual.parents}, expected {exp.parents}")
    if actual.subs != exp.subs:
        errors.append(f"subs: got {actual.subs}, expected {exp.subs}")
    if actual.with_solutions != exp.with_solutions:
        errors.append(f"with_solutions: got {actual.with_solutions}, expected {exp.with_solutions}")

    # Print results
    print(f"\n  Results:")
    print(f"    Total:          {actual.total} (expected {exp.total})")
    print(f"    Parents:        {actual.parents} (expected {exp.parents})")
    print(f"    Subs:           {actual.subs} (expected {exp.subs})")
    print(f"    With solutions: {actual.with_solutions} (expected {exp.with_solutions})")

    # Show first few exercises
    print(f"\n  Sample exercises:")
    for i, ex in enumerate(exercises[:5]):
        preview = ex.text[:80].replace("\n", " ").strip()
        sol_marker = " [+sol]" if ex.solution else ""
        sub_marker = f" (sub of {ex.parent_exercise_number})" if ex.is_sub_question else ""
        print(f"    {i+1}. [{ex.exercise_number}]{sub_marker}{sol_marker}: {preview}...")

    if errors:
        print(f"\n  ✗ FAIL:")
        for err in errors:
            print(f"    - {err}")
        return False
    else:
        print(f"\n  ✓ PASS: All counts match exactly")
        return True


# Test cases with exact expected values
TEST_CASES = [
    PDFTestCase(
        path="/home/laimk/git/examina-cloud/test-data/ADE-ESAMI/Prova intermedia 2024-01-29 - SOLUZIONI v4.pdf",
        course_code="ADE",
        expected=ExpectedResult(total=10, parents=3, subs=7, with_solutions=9),
        description="ADE exam with 2 main exercises, sub-questions, and solutions",
    ),
    PDFTestCase(
        path="/home/laimk/git/examina-cloud/test-data/ADE-ESAMI/Compito - Prima Prova Intermedia 10-02-2020 - Soluzioni.pdf",
        course_code="ADE",
        expected=ExpectedResult(total=15, parents=1, subs=14, with_solutions=0),
        description="ADE exam: Ex1 (3 subs), Ex2 (3 subs), Ex3 (3 subs), Ex4 (5 subs), Ex5 (standalone)",
    ),
    PDFTestCase(
        path="/home/laimk/git/examina-cloud/test-data/AL-ESAMI/20120612 - appello.pdf",
        course_code="AL",
        expected=ExpectedResult(total=8, parents=0, subs=8, with_solutions=0),
        description="AL exam with combined format (1a, 1b, 2a, 2b, etc.)",
    ),
    PDFTestCase(
        path="/home/laimk/git/examina-cloud/test-data/SO-ESAMI/SOfebbraio2020.pdf",
        course_code="SO",
        expected=ExpectedResult(total=19, parents=5, subs=14, with_solutions=0),
        description="SO exam with 5 main exercises and 14 sub-questions",
    ),
]


if __name__ == "__main__":
    passed = 0
    failed = 0

    for test_case in TEST_CASES:
        if Path(test_case.path).exists():
            if test_pdf(test_case):
                passed += 1
            else:
                failed += 1
        else:
            print(f"\n⚠ Skipping (not found): {test_case.path}")

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
