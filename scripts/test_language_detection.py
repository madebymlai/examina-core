#!/usr/bin/env python3
"""
Test script for automatic language detection feature.

Tests:
1. Language detection for procedures (core loops)
2. Language detection for topics
3. ISO code mapping
4. Caching behavior
5. Integration with database storage
"""

from core.translation_detector import TranslationDetector, LanguageInfo
from models.llm_manager import LLMManager
from config import Config

def test_language_detection():
    """Test basic language detection."""
    print("=" * 70)
    print("TEST 1: Basic Language Detection")
    print("=" * 70)

    llm = LLMManager(provider=Config.LLM_PROVIDER)
    detector = TranslationDetector(llm_manager=llm)

    test_cases = [
        # English
        ("Mealy Machine Design", "english"),
        ("Boolean Algebra Minimization", "english"),
        ("Matrix Diagonalization", "english"),

        # Italian
        ("Progettazione Macchina di Moore", "italian"),
        ("Minimizzazione Algebra Booleana", "italian"),
        ("Diagonalizzazione di Matrici", "italian"),

        # Spanish (if you want to test multi-language)
        ("Diseño de Máquina de Mealy", "spanish"),
        ("Álgebra Booleana", "spanish"),

        # German
        ("Boolesche Algebra", "german"),
    ]

    print("\nDetecting languages...\n")
    for text, expected_lang in test_cases:
        detected = detector.detect_language(text)
        status = "✓" if detected == expected_lang else "✗"
        print(f"{status} '{text}' → {detected} (expected: {expected_lang})")

    # Test cache
    print(f"\nCache stats: {detector.get_cache_stats()}")


def test_language_with_iso():
    """Test language detection with ISO codes."""
    print("\n" + "=" * 70)
    print("TEST 2: Language Detection with ISO Codes")
    print("=" * 70)

    llm = LLMManager(provider=Config.LLM_PROVIDER)
    detector = TranslationDetector(llm_manager=llm)

    test_cases = [
        ("Finite State Machine", "english", "en"),
        ("Macchina a Stati Finiti", "italian", "it"),
        ("Máquina de Estados Finitos", "spanish", "es"),
        ("Endliche Automaten", "german", "de"),
    ]

    print("\nDetecting languages with ISO codes...\n")
    for text, expected_lang, expected_iso in test_cases:
        lang_info = detector.detect_language_with_iso(text)
        lang_match = "✓" if lang_info.name == expected_lang else "✗"
        iso_match = "✓" if lang_info.code == expected_iso else "✗"

        print(f"{lang_match} {iso_match} '{text[:40]}...'")
        print(f"    → {lang_info.name} ({lang_info.code}) [confidence: {lang_info.confidence}]")


def test_translation_detection():
    """Test that translations are still detected correctly."""
    print("\n" + "=" * 70)
    print("TEST 3: Translation Detection (Cross-Language Merging)")
    print("=" * 70)

    llm = LLMManager(provider=Config.LLM_PROVIDER)
    detector = TranslationDetector(llm_manager=llm)

    translation_pairs = [
        ("Mealy Machine Design", "Progettazione Macchina di Mealy"),
        ("Boolean Algebra", "Algebra Booleana"),
        ("Matrix Diagonalization", "Diagonalizzazione di Matrici"),
        ("Finite State Machine", "Macchina a Stati Finiti"),
    ]

    print("\nTesting translation detection...\n")
    for text1, text2 in translation_pairs:
        result = detector.are_translations(text1, text2, min_embedding_similarity=0.70)
        status = "✓" if result.is_translation else "✗"
        print(f"{status} '{text1}' ↔ '{text2}'")
        print(f"    → {result.reason} (confidence: {result.confidence:.2f}, similarity: {result.embedding_similarity:.2f})")


def test_non_translations():
    """Test that similar but different concepts are NOT merged."""
    print("\n" + "=" * 70)
    print("TEST 4: Non-Translation Detection (Different Concepts)")
    print("=" * 70)

    llm = LLMManager(provider=Config.LLM_PROVIDER)
    detector = TranslationDetector(llm_manager=llm)

    different_pairs = [
        ("Mealy Machine", "Moore Machine"),
        ("Sum of Products", "Product of Sums"),
        ("NFA Design", "DFA Design"),
        ("Synchronous", "Asynchronous"),
    ]

    print("\nTesting non-translation detection (should NOT merge)...\n")
    for text1, text2 in different_pairs:
        result = detector.are_translations(text1, text2, min_embedding_similarity=0.70)
        status = "✓" if not result.is_translation else "✗"
        print(f"{status} '{text1}' vs '{text2}' → NOT translations")
        print(f"    → {result.reason} (similarity: {result.embedding_similarity if result.embedding_similarity else 'N/A'})")


def test_caching():
    """Test that caching works correctly."""
    print("\n" + "=" * 70)
    print("TEST 5: Caching Behavior")
    print("=" * 70)

    llm = LLMManager(provider=Config.LLM_PROVIDER)
    detector = TranslationDetector(llm_manager=llm)

    text = "Finite State Machine Minimization"

    print(f"\nDetecting language for: '{text}'")
    print("First call (should hit LLM)...")
    lang1 = detector.detect_language(text)
    stats1 = detector.get_cache_stats()
    print(f"  Result: {lang1}")
    print(f"  Cache size: {stats1['language_cache_size']}")

    print("\nSecond call (should use cache)...")
    lang2 = detector.detect_language(text)
    stats2 = detector.get_cache_stats()
    print(f"  Result: {lang2}")
    print(f"  Cache size: {stats2['language_cache_size']}")

    print(f"\n✓ Cache working: {lang1 == lang2 and stats1 == stats2}")


if __name__ == "__main__":
    print("\n")
    print("█" * 70)
    print("  EXAMINA: Automatic Language Detection Test Suite")
    print("█" * 70)
    print()

    try:
        test_language_detection()
        test_language_with_iso()
        test_translation_detection()
        test_non_translations()
        test_caching()

        print("\n" + "=" * 70)
        print("✓ ALL TESTS COMPLETED")
        print("=" * 70)
        print()

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
