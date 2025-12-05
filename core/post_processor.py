"""
Post-processor for knowledge item validation.

Uses LLM to validate extracted items via coherence-based filtering.
Infers topics from validated knowledge items.
"""
import json
import logging
from typing import Any

from models.llm_manager import LLMManager

logger = logging.getLogger(__name__)


def filter_and_organize_knowledge(
    llm: LLMManager,
    items: list[dict],
    existing_parents: list[str],
    existing_topics: list[str],
) -> dict:
    """
    Filter extracted knowledge items and infer topics using LLM.

    Uses coherence-based filtering:
    - Identify concept clusters (1-5 topics)
    - Filter out outliers (context/scenario items)
    - Normalize parent names to existing ones
    - INFER appropriate topics and assign items to them

    Args:
        llm: LLMManager instance
        items: List of extracted knowledge items with name, type, parent_name
        existing_parents: List of parent names already in the course
        existing_topics: List of topic names already in the course

    Returns:
        {
            "valid_items": [...],      # Items that passed filtering, each with "topic" field
            "filtered_items": [...],   # Items removed (with idx for debugging)
            "filtered_indices": [...], # Indices of filtered items
            "inferred_topics": [...],  # List of topic names derived from valid items
        }
    """
    if not items:
        return {
            "valid_items": [],
            "filtered_items": [],
            "filtered_indices": [],
            "inferred_topics": [],
        }

    # Add index to each item for reliable matching (LLM may modify names)
    indexed_items = [{"idx": i, **item} for i, item in enumerate(items)]

    prompt = f"""Analyze these extracted knowledge items and cluster them into topics.

ITEMS:
{json.dumps(indexed_items, indent=2, ensure_ascii=False)}

EXISTING PARENT CONCEPTS IN COURSE:
{json.dumps(existing_parents, ensure_ascii=False) if existing_parents else "[]"}

EXISTING TOPICS IN COURSE:
{json.dumps(existing_topics, ensure_ascii=False) if existing_topics else "[]"}

TASK:
1. CLUSTER items into 1-5 DISTINCT TOPICS based on subject matter
   - Each topic should be chapter-level (e.g., "Automi a Stati Finiti", "Circuiti Logici", "Sistemi di Numerazione")
   - NOT too broad (e.g., "Computer Science" is too broad)
   - NOT too specific (e.g., "Moore Machine State Table" is too specific)
   - Prefer EXISTING TOPICS if items fit them
   - Use the same language as the items (Italian items → Italian topics)

2. AGGRESSIVELY Flag OUTLIERS using these tests:

   TEST A - Academic vs Context: "Is this item the SUBJECT of study, or just the SETTING/CONTEXT of a word problem?"
   TEST B - Textbook test: "Would this appear as a chapter heading or section title in this course's textbook?"
   TEST C - Lecture test: "Would a professor put this on a lecture slide as a concept to teach?"
   TEST D - Abstraction test: "Is this a general theoretical concept, or a specific real-world instance?"

   If ANY test fails → FILTER the item out

   Keep ONLY items where ALL tests pass

3. Normalize PARENTS - if an item suggests a parent similar to an existing one, use the existing name

4. ASSIGN each valid item to exactly ONE topic

CRITICAL: Each item has an "idx" field. You MUST return this idx unchanged for matching.

RETURN JSON:
{{
    "valid_items": [
        {{"idx": 0, "topic": "topic name for this item"}}
    ],
    "filtered_indices": [0, 1, 3],
    "inferred_topics": ["topic1", "topic2", ...]
}}

NOTE: valid_items only needs "idx" and "topic". Original item data will be matched by idx.
"""

    try:
        response = llm.generate(
            prompt=prompt,
            temperature=0.3,
            json_mode=True,
        )

        if response and response.text:
            result = json.loads(response.text)

            # Reconstruct valid_items with original data using idx
            valid_items_with_topics = []
            idx_to_topic = {item["idx"]: item["topic"] for item in result.get("valid_items", [])}

            for i, original_item in enumerate(items):
                if i in idx_to_topic:
                    valid_items_with_topics.append({
                        **original_item,
                        "topic": idx_to_topic[i],
                    })

            # Build filtered_items from filtered_indices for logging
            filtered_indices = result.get("filtered_indices", [])
            filtered_items = [
                {"name": items[i].get("name", "unknown"), "idx": i}
                for i in filtered_indices
                if i < len(items)
            ]

            # Log filtered items for debugging
            if filtered_items:
                for item in filtered_items:
                    logger.info(f"Filtered: {item.get('name')} (idx={item.get('idx')})")

            return {
                "valid_items": valid_items_with_topics,
                "filtered_items": filtered_items,
                "filtered_indices": filtered_indices,
                "inferred_topics": result.get("inferred_topics", []),
            }
        else:
            logger.warning("Post-processor got empty response, returning all items")
            fallback_topic = existing_topics[0] if existing_topics else "General"
            # Add topic field to each item for fallback
            valid_items = [{**item, "topic": fallback_topic} for item in items]
            return {
                "valid_items": valid_items,
                "filtered_items": [],
                "filtered_indices": [],
                "inferred_topics": [fallback_topic],
            }

    except json.JSONDecodeError as e:
        logger.error(f"Post-processor JSON parse error: {e}")
        fallback_topic = existing_topics[0] if existing_topics else "General"
        valid_items = [{**item, "topic": fallback_topic} for item in items]
        return {
            "valid_items": valid_items,
            "filtered_items": [],
            "filtered_indices": [],
            "inferred_topics": [fallback_topic],
        }
    except Exception as e:
        logger.error(f"Post-processor error: {e}")
        fallback_topic = existing_topics[0] if existing_topics else "General"
        valid_items = [{**item, "topic": fallback_topic} for item in items]
        return {
            "valid_items": valid_items,
            "filtered_items": [],
            "filtered_indices": [],
            "inferred_topics": [fallback_topic],
        }
