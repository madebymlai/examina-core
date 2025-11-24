"""
Generic translation detection for ANY language pair.

This module provides LLM-based translation detection that works for any language pair,
without hardcoding specific translations or language names.

Design principles:
- NO hardcoded language pairs (not limited to IT/EN)
- NO hardcoded translation dictionaries
- Uses LLM for dynamic translation detection
- Fast embedding similarity filter before expensive LLM calls
- Caches LLM results to avoid repeated API calls
- Graceful degradation if LLM unavailable

Examples (ANY language pair):
- "Moore Machine Design" ↔ "Progettazione Macchina di Moore" (EN↔IT) → True
- "Implementazione Monitor" ↔ "Monitor Implementation" (IT↔EN) → True
- "Eliminación Gaussiana" ↔ "Gaussian Elimination" (ES↔EN) → True
- "Diagonalisation" ↔ "Diagonalization" (FR↔EN) → True
- "Moore Machine" ↔ "Mealy Machine" (same lang, different concepts) → False
"""

from typing import Optional, Dict, Tuple
from dataclasses import dataclass
import hashlib


@dataclass
class LanguageInfo:
    """Information about detected language."""
    name: str  # Language name (lowercase, e.g., "english", "italian", "spanish")
    code: Optional[str] = None  # ISO 639-1 code (e.g., "en", "it", "es") - optional
    confidence: float = 1.0  # Confidence in detection (0.0 to 1.0)


@dataclass
class TranslationResult:
    """Result of translation detection."""
    is_translation: bool
    confidence: float  # 0.0 to 1.0
    reason: str
    embedding_similarity: Optional[float] = None
    detected_languages: Optional[Tuple[str, str]] = None


class TranslationDetector:
    """Generic translation detection for ANY language pair using LLM."""

    def __init__(self, llm_manager, embedding_model=None):
        """Initialize translation detector.

        Args:
            llm_manager: LLMManager instance for language detection and translation verification
            embedding_model: Optional sentence transformer model for similarity (if None, uses compute_similarity from llm_manager)
        """
        self.llm = llm_manager
        self.embedding_model = embedding_model

        # Cache for LLM translation detection results
        # Format: {(text1, text2): TranslationResult}
        self._translation_cache: Dict[Tuple[str, str], TranslationResult] = {}

        # Cache for language detection
        # Format: {text: language_code}
        self._language_cache: Dict[str, str] = {}

    def _normalize_texts(self, text1: str, text2: str) -> Tuple[str, str]:
        """Normalize texts for comparison.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Tuple of (normalized_text1, normalized_text2)
        """
        # Lowercase and strip whitespace
        t1 = text1.lower().strip()
        t2 = text2.lower().strip()

        return t1, t2

    def _get_cache_key(self, text1: str, text2: str) -> Tuple[str, str]:
        """Get cache key for text pair (order-independent).

        Args:
            text1: First text
            text2: Second text

        Returns:
            Tuple that can be used as cache key
        """
        # Normalize first
        t1, t2 = self._normalize_texts(text1, text2)

        # Sort to make order-independent
        return tuple(sorted([t1, t2]))

    def compute_embedding_similarity(self, text1: str, text2: str) -> float:
        """Compute embedding similarity between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity score (0.0 to 1.0)
        """
        if self.embedding_model:
            # Use provided embedding model
            try:
                emb1 = self.embedding_model.encode(text1, convert_to_numpy=True)
                emb2 = self.embedding_model.encode(text2, convert_to_numpy=True)

                # Compute cosine similarity
                import numpy as np
                emb1_norm = emb1 / np.linalg.norm(emb1)
                emb2_norm = emb2 / np.linalg.norm(emb2)
                similarity = float(np.dot(emb1_norm, emb2_norm))

                # Map from [-1, 1] to [0, 1]
                return (similarity + 1) / 2
            except Exception as e:
                print(f"[WARNING] Embedding similarity failed: {e}, using fallback")

        # Fallback to string similarity
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def detect_language(self, text: str) -> str:
        """Detect language of text using LLM (generic, works for any language).

        Args:
            text: Text to analyze

        Returns:
            Language name/code (e.g., "english", "italian", "spanish", "french")
            Returns "unknown" if detection fails

        Note: For structured result with ISO code, use detect_language_with_iso()
        """
        # Check cache first
        cache_key = text.lower().strip()
        if cache_key in self._language_cache:
            return self._language_cache[cache_key]

        prompt = f"""What language is this text written in? Answer with ONLY the language name in English (lowercase, one word).

Examples:
- "Machine Learning" → english
- "Apprendimento Automatico" → italian
- "Aprendizaje Automático" → spanish
- "Apprentissage Automatique" → french
- "Maschinelles Lernen" → german

Text: "{text}"

Language:"""

        try:
            response = self.llm.generate(
                prompt=prompt,
                system="You are an expert at language detection. Respond with only the language name in lowercase.",
                temperature=0.0,  # Deterministic
                max_tokens=10
            )

            if response.success:
                language = response.text.strip().lower()
                # Cache the result
                self._language_cache[cache_key] = language
                return language
            else:
                return "unknown"

        except Exception as e:
            print(f"[WARNING] Language detection failed: {e}")
            return "unknown"

    def detect_language_with_iso(self, text: str) -> LanguageInfo:
        """Detect language with ISO code using LLM (generic, works for any language).

        Args:
            text: Text to analyze

        Returns:
            LanguageInfo with language name, ISO code, and confidence
        """
        # Detect language name first (uses cache)
        language_name = self.detect_language(text)

        if language_name == "unknown":
            return LanguageInfo(name="unknown", code=None, confidence=0.0)

        # Get ISO code using LLM (generic, no hardcoding)
        iso_code = self._get_iso_code(language_name)

        return LanguageInfo(
            name=language_name,
            code=iso_code,
            confidence=1.0
        )

    def _get_iso_code(self, language_name: str) -> Optional[str]:
        """Get ISO 639-1 code for a language name using LLM (generic, no hardcoding).

        Args:
            language_name: Language name (e.g., "english", "italian", "spanish")

        Returns:
            ISO 639-1 code (e.g., "en", "it", "es") or None if unknown
        """
        # Check cache first (avoid repeated API calls)
        cache_key = f"iso_{language_name}"
        if cache_key in self._language_cache:
            return self._language_cache[cache_key]

        prompt = f"""What is the ISO 639-1 code (2-letter code) for the language: {language_name}?

Examples:
- english → en
- italian → it
- spanish → es
- french → fr
- german → de
- portuguese → pt
- chinese → zh
- japanese → ja
- korean → ko

Answer with ONLY the 2-letter ISO code (lowercase).

ISO 639-1 code:"""

        try:
            response = self.llm.generate(
                prompt=prompt,
                system="You are an expert at ISO language codes. Respond with only the 2-letter ISO 639-1 code in lowercase.",
                temperature=0.0,  # Deterministic
                max_tokens=5
            )

            if response.success:
                iso_code = response.text.strip().lower()
                # Validate: must be exactly 2 letters
                if len(iso_code) == 2 and iso_code.isalpha():
                    # Cache the result
                    self._language_cache[cache_key] = iso_code
                    return iso_code
                else:
                    return None
            else:
                return None

        except Exception as e:
            print(f"[WARNING] ISO code detection failed: {e}")
            return None

    def are_translations(
        self,
        text1: str,
        text2: str,
        min_embedding_similarity: float = 0.70,
        use_language_detection: bool = False
    ) -> TranslationResult:
        """Detect if two texts are translations of each other (ANY language pair).

        This is a two-stage process:
        1. Fast filter: Check embedding similarity (must be >= min_embedding_similarity)
        2. LLM verification: Ask LLM if they express the same concept in different languages

        Args:
            text1: First text (any language)
            text2: Second text (any language)
            min_embedding_similarity: Minimum embedding similarity to consider (fast filter)
            use_language_detection: If True, also detect languages (slower, more accurate)

        Returns:
            TranslationResult with detection outcome
        """
        # Check cache first
        cache_key = self._get_cache_key(text1, text2)
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        # Normalize
        t1_norm, t2_norm = self._normalize_texts(text1, text2)

        # Quick check: identical texts
        if t1_norm == t2_norm:
            result = TranslationResult(
                is_translation=False,  # Same text = duplicate, not translation
                confidence=1.0,
                reason="identical_text",
                embedding_similarity=1.0
            )
            self._translation_cache[cache_key] = result
            return result

        # Stage 1: Embedding similarity filter (FAST)
        embedding_sim = self.compute_embedding_similarity(text1, text2)

        if embedding_sim < min_embedding_similarity:
            # Too dissimilar to be translations
            result = TranslationResult(
                is_translation=False,
                confidence=1.0 - embedding_sim,
                reason="low_embedding_similarity",
                embedding_similarity=embedding_sim
            )
            self._translation_cache[cache_key] = result
            return result

        # Optional: Detect languages (more accurate but slower)
        languages = None
        if use_language_detection:
            lang1 = self.detect_language(text1)
            lang2 = self.detect_language(text2)
            languages = (lang1, lang2)

            # If same language detected, probably not translation
            if lang1 == lang2 and lang1 != "unknown":
                result = TranslationResult(
                    is_translation=False,
                    confidence=0.9,
                    reason="same_language_detected",
                    embedding_similarity=embedding_sim,
                    detected_languages=languages
                )
                self._translation_cache[cache_key] = result
                return result

        # Stage 2: LLM verification (EXPENSIVE - only for high-similarity pairs)
        prompt = f"""Are these two texts translations of each other (same meaning/concept, different languages)?

Text 1: "{text1}"
Text 2: "{text2}"

Answer with ONLY "yes" or "no".

Consider them translations if they express the SAME concept, procedure, or topic in different languages, even if not word-for-word translations.

Examples that should be "yes":
- "Moore Machine Design" vs "Progettazione Macchina di Moore" (English/Italian)
- "Monitor Implementation" vs "Implementazione Monitor" (English/Italian)
- "Gaussian Elimination" vs "Eliminación Gaussiana" (English/Spanish)
- "Boolean Algebra" vs "Algèbre Booléenne" (English/French)

Examples that should be "no":
- "Moore Machine" vs "Mealy Machine" (same language, different concepts)
- "Design" vs "Implementation" (same language, different operations)
- "Sum of Products" vs "Product of Sums" (opposite operations)

Answer:"""

        try:
            response = self.llm.generate(
                prompt=prompt,
                system="You are an expert at detecting translations across all languages. Respond with only 'yes' or 'no'.",
                temperature=0.0,  # Deterministic
                max_tokens=5
            )

            if response.success:
                answer = response.text.strip().lower()
                is_translation = answer.startswith("yes")

                result = TranslationResult(
                    is_translation=is_translation,
                    confidence=0.95 if is_translation else 0.90,
                    reason="llm_verified" if is_translation else "llm_rejected",
                    embedding_similarity=embedding_sim,
                    detected_languages=languages
                )

                # Cache the result
                self._translation_cache[cache_key] = result
                return result
            else:
                # LLM failed - conservative fallback (assume not translation)
                result = TranslationResult(
                    is_translation=False,
                    confidence=0.5,
                    reason="llm_unavailable",
                    embedding_similarity=embedding_sim,
                    detected_languages=languages
                )
                self._translation_cache[cache_key] = result
                return result

        except Exception as e:
            print(f"[WARNING] LLM translation detection failed: {e}")
            # Conservative fallback
            result = TranslationResult(
                is_translation=False,
                confidence=0.5,
                reason="llm_error",
                embedding_similarity=embedding_sim,
                detected_languages=languages
            )
            self._translation_cache[cache_key] = result
            return result

    def get_preferred_text(
        self,
        text1: str,
        text2: str,
        preferred_languages: Optional[list] = None
    ) -> str:
        """Get preferred text when merging translations.

        Priority:
        1. Preferred language (if specified)
        2. English (more universal)
        3. Shorter text
        4. Alphabetically first

        Args:
            text1: First text
            text2: Second text
            preferred_languages: List of preferred language names (e.g., ['english', 'en'])

        Returns:
            The preferred text (text1 or text2)
        """
        if preferred_languages:
            lang1 = self.detect_language(text1)
            lang2 = self.detect_language(text2)

            # Check if either is in preferred languages
            lang1_preferred = any(pref in lang1.lower() for pref in preferred_languages)
            lang2_preferred = any(pref in lang2.lower() for pref in preferred_languages)

            if lang1_preferred and not lang2_preferred:
                return text1
            elif lang2_preferred and not lang1_preferred:
                return text2

        # Default preference: shorter is better (usually more concise)
        if len(text1) < len(text2):
            return text1
        elif len(text2) < len(text1):
            return text2

        # If same length, alphabetically first
        return text1 if text1 < text2 else text2

    def clear_cache(self):
        """Clear all caches."""
        self._translation_cache.clear()
        self._language_cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns:
            Dict with cache sizes
        """
        return {
            "translation_cache_size": len(self._translation_cache),
            "language_cache_size": len(self._language_cache),
        }
