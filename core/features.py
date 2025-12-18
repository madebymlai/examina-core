"""
Feature extraction for active learning classifier.

Extracts numerical features from item pairs for ML classification.
Key feature: embedding_similarity using sentence transformers.
"""

from dataclasses import dataclass

import numpy as np

# Lazy-loaded embedding model
_embedding_model = None


def get_embedding_model():
    """Lazy load sentence transformer model."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


def compute_embedding(text: str) -> np.ndarray:
    """Compute sentence embedding for text."""
    if not text or not text.strip():
        return np.zeros(384)  # MiniLM embedding size
    model = get_embedding_model()
    return model.encode(text, convert_to_numpy=True)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-8 or norm_b < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Compute normalized Levenshtein similarity (0-1)."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    if len(s1) < len(s2):
        s1, s2 = s2, s1

    distances = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        new_distances = [i + 1]
        for j, c2 in enumerate(s2):
            if c1 == c2:
                new_distances.append(distances[j])
            else:
                new_distances.append(1 + min(distances[j], distances[j + 1], new_distances[-1]))
        distances = new_distances

    max_len = max(len(s1), len(s2))
    return 1 - (distances[-1] / max_len)


@dataclass
class PairFeatures:
    """Features extracted from an item pair."""

    embedding_similarity: float  # KEY FEATURE - captures synonyms
    token_jaccard: float  # Word overlap
    trigram_jaccard: float  # Character 3-gram overlap
    desc_length_ratio: float  # Length similarity
    same_category: bool  # Same hierarchical category
    verb_match: bool  # Same starting verb (Bloom's taxonomy)
    name_similarity: float  # Name Levenshtein similarity

    def to_vector(self) -> np.ndarray:
        """Convert to numpy array for ML classifier."""
        return np.array(
            [
                self.embedding_similarity,
                self.token_jaccard,
                self.trigram_jaccard,
                self.desc_length_ratio,
                1.0 if self.same_category else 0.0,
                1.0 if self.verb_match else 0.0,
                self.name_similarity,
            ]
        )

    def to_list(self) -> list[float]:
        """Convert to list for JSON serialization."""
        return self.to_vector().tolist()


def extract_features(
    item_a: dict,
    item_b: dict,
    embedding_a: np.ndarray | None = None,
    embedding_b: np.ndarray | None = None,
) -> PairFeatures:
    """
    Extract features from item pair.

    Args:
        item_a, item_b: Items with 'description', 'name', 'category'
        embedding_a, embedding_b: Pre-computed embeddings (optional)

    Returns:
        PairFeatures for ML classification
    """
    desc_a = item_a.get("description", "") or ""
    desc_b = item_b.get("description", "") or ""
    name_a = item_a.get("name", "") or ""
    name_b = item_b.get("name", "") or ""

    # EMBEDDING SIMILARITY (the key feature)
    if embedding_a is None:
        embedding_a = compute_embedding(desc_a)
    if embedding_b is None:
        embedding_b = compute_embedding(desc_b)
    embedding_similarity = cosine_similarity(embedding_a, embedding_b)

    # Token Jaccard
    tokens_a = set(desc_a.lower().split())
    tokens_b = set(desc_b.lower().split())
    union_size = len(tokens_a | tokens_b)
    token_jaccard = len(tokens_a & tokens_b) / union_size if union_size > 0 else 0.0

    # 3-gram Jaccard
    trigrams_a = set(desc_a[i : i + 3] for i in range(len(desc_a) - 2)) if len(desc_a) >= 3 else set()
    trigrams_b = set(desc_b[i : i + 3] for i in range(len(desc_b) - 2)) if len(desc_b) >= 3 else set()
    trigram_union = len(trigrams_a | trigrams_b)
    trigram_jaccard = len(trigrams_a & trigrams_b) / trigram_union if trigram_union > 0 else 0.0

    # Length ratio
    len_a, len_b = len(desc_a), len(desc_b)
    max_len = max(len_a, len_b)
    desc_length_ratio = min(len_a, len_b) / max_len if max_len > 0 else 1.0

    # Category match
    cat_a = item_a.get("category")
    cat_b = item_b.get("category")
    same_category = cat_a == cat_b and cat_a is not None

    # Verb match (first word of description - Bloom's taxonomy)
    words_a = desc_a.split()
    words_b = desc_b.split()
    verb_a = words_a[0].lower() if words_a else ""
    verb_b = words_b[0].lower() if words_b else ""
    verb_match = verb_a == verb_b and verb_a != ""

    # Name similarity (Levenshtein ratio)
    name_similarity = levenshtein_ratio(name_a.lower(), name_b.lower())

    return PairFeatures(
        embedding_similarity=embedding_similarity,
        token_jaccard=token_jaccard,
        trigram_jaccard=trigram_jaccard,
        desc_length_ratio=desc_length_ratio,
        same_category=same_category,
        verb_match=verb_match,
        name_similarity=name_similarity,
    )


def should_add_to_training(
    features: PairFeatures,
    llm_confidence: float,
) -> bool:
    """
    Quality gate for global training data.

    Only learn from high-confidence LLM decisions.
    Garbage uploads -> uncertain LLM -> filtered out.
    """
    # Gate 1: LLM must be confident
    if 0.1 < llm_confidence < 0.9:
        return False  # Uncertain = garbage or edge case

    # Gate 2: Feature sanity checks
    if features.embedding_similarity < 0.2 and llm_confidence > 0.9:
        return False  # Suspicious: no similarity but "match"?

    if features.desc_length_ratio < 0.2:
        return False  # One desc is 5x longer = probably garbage

    # Gate 3: Minimum description quality
    if features.token_jaccard == 0 and features.embedding_similarity < 0.3:
        return False  # No overlap at all = likely garbage

    return True
