"""
Post-processor for knowledge item validation.

Uses LLM to validate extracted items via coherence-based filtering.
Also detects synonyms for deduplication.
"""
import json
import logging
from typing import Any

from models.llm_manager import LLMManager

logger = logging.getLogger(__name__)


def detect_synonyms(
    items: list[tuple[str, str]] | list[dict],
    llm: LLMManager,
) -> list[tuple[str, str, list[str], str | None]]:
    """
    Use LLM to detect synonym groups among knowledge items using anonymous approach.

    Items are anonymized (Item_1, Item_2) so LLM judges purely on exercises, not names.
    Three LLM calls: (1) group by skill, (2) pick canonical name, (3) derive learning_approach.

    Args:
        items: Either:
            - List of (name, knowledge_type) tuples (legacy format)
            - List of dicts with keys: name, type, exercises (optional list of exercise snippets),
              learning_approach (optional)
        llm: LLMManager instance

    Returns:
        List of (canonical_name, type, member_names, learning_approach) tuples
        Example: [("moore_machine_design", "procedure", ["macchina_di_moore", "moore_design"], "procedural")]
    """
    if len(items) < 2:
        return []

    # Normalize input format
    normalized_items: list[dict] = []
    for item in items:
        if isinstance(item, tuple):
            normalized_items.append({
                "name": item[0],
                "type": item[1],
                "exercises": [],
                "learning_approach": None,
            })
        elif isinstance(item, dict):
            normalized_items.append({
                "name": item.get("name", ""),
                "type": item.get("type", "key_concept"),
                "exercises": item.get("exercises", []),
                "learning_approach": item.get("learning_approach"),
            })

    # Dedupe by name, keeping first occurrence (preserves exercises)
    seen_names: set[str] = set()
    unique_items: list[dict] = []
    for item in normalized_items:
        if item["name"] not in seen_names:
            seen_names.add(item["name"])
            unique_items.append(item)

    if len(unique_items) < 2:
        return []

    # Check if we have exercise context
    has_exercises = any(item.get("exercises") for item in unique_items)

    if not has_exercises:
        # No exercises = can't judge skill, skip synonym detection
        logger.info("No exercises provided, skipping synonym detection")
        return []

    # Build anonymous item mapping: Item_N -> actual item
    item_mapping: dict[str, dict] = {}
    for i, item in enumerate(unique_items, 1):
        item_mapping[f"Item_{i}"] = item

    # =========================================================================
    # Step 2a: Grouping - identify same-skill items (anonymous)
    # =========================================================================
    items_text = []
    for item_id, item in item_mapping.items():
        item_text = f"- {item_id}"
        if item.get("exercises"):
            exercise_snippets = [f'    "{ex}"' for ex in item["exercises"]]
            if exercise_snippets:
                item_text += "\n  Exercises:\n" + "\n".join(exercise_snippets)
        items_text.append(item_text)

    grouping_prompt = f"""Identify which items test the EXACT SAME SKILL based on their exercises.

Items (judge ONLY by exercises, not by item IDs):
{chr(10).join(items_text)}

SAME SKILL (should group):
- Both require the EXACT SAME technique to solve
- A student who masters one has automatically mastered the other
- A single flashcard could teach both equally well

DIFFERENT SKILLS (should NOT group):
- One asks to EXPLAIN/DESCRIBE, another asks to CALCULATE/APPLY
- Mastering one gives only partial mastery of the other
- They would need separate study sessions

Return JSON: {{"groups": [["Item_1", "Item_2"], ["Item_3", "Item_4"]]}}
Return {{"groups": []}} if no items test the same skill."""

    try:
        logger.info(f"Detecting synonyms among {len(unique_items)} items (anonymous approach)")
        response = llm.generate(
            prompt=grouping_prompt,
            temperature=0.0,
            json_mode=True,
        )

        if not response or not response.text:
            logger.warning("Empty response from grouping LLM call")
            return []

        logger.debug(f"Grouping raw response: {response.text[:500]}")
        result = json.loads(response.text)

        # Handle both {"groups": [...]} and direct [...] format
        if isinstance(result, dict) and "groups" in result:
            groups = result["groups"]
        elif isinstance(result, list):
            groups = result
        else:
            logger.warning(f"Unexpected grouping response format: {type(result)}")
            return []

        if not groups:
            logger.info("No synonym groups detected")
            return []

        # Log token usage for cost monitoring
        if hasattr(response, 'usage') and response.usage:
            logger.info(f"Grouping call tokens: input={response.usage.get('input_tokens', 0)}, output={response.usage.get('output_tokens', 0)}")

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse grouping response: {e}")
        return []
    except Exception as e:
        logger.warning(f"Grouping LLM call failed: {e}")
        return []

    # =========================================================================
    # Step 2b: Canonical selection - pick best name per group
    # =========================================================================
    all_results: list[tuple[str, str, list[str], str | None]] = []

    for group in groups:
        if not isinstance(group, list) or len(group) < 2:
            continue

        # Get real names for this group
        group_names = []
        group_items = []
        for item_id in group:
            if item_id in item_mapping:
                item = item_mapping[item_id]
                group_names.append(item["name"])
                group_items.append(item)

        if len(group_names) < 2:
            continue

        # Pick canonical name via LLM
        canonical_prompt = f"""Pick the most descriptive name from: {json.dumps(group_names)}

Return JSON: {{"canonical": "chosen_name"}}"""

        try:
            canonical_response = llm.generate(
                prompt=canonical_prompt,
                temperature=0.0,
                json_mode=True,
            )

            if canonical_response and canonical_response.text:
                canonical_result = json.loads(canonical_response.text)
                canonical_name = canonical_result.get("canonical", group_names[0])
                # Validate canonical is in group
                if canonical_name not in group_names:
                    canonical_name = group_names[0]
            else:
                canonical_name = group_names[0]

            # Log token usage
            if hasattr(canonical_response, 'usage') and canonical_response.usage:
                logger.debug(f"Canonical call tokens: input={canonical_response.usage.get('input_tokens', 0)}, output={canonical_response.usage.get('output_tokens', 0)}")

        except Exception as e:
            logger.warning(f"Canonical selection failed: {e}, using first name")
            canonical_name = group_names[0]

        # =====================================================================
        # Step 2c: Learning approach - derive from combined exercises
        # =====================================================================
        combined_exercises = []
        for item in group_items:
            combined_exercises.extend(item.get("exercises", []))

        learning_approach = None
        if combined_exercises:
            approach_prompt = f"""Based on these exercises, pick the most appropriate learning approach.

Exercises:
{chr(10).join(f'- "{ex}"' for ex in combined_exercises[:6])}

Options: procedural, conceptual, factual, analytical
- procedural = exercise asks to APPLY steps/calculate/solve
- conceptual = exercise asks to EXPLAIN/compare/reason why
- factual = exercise asks to RECALL specific facts/definitions
- analytical = exercise asks to ANALYZE/evaluate/critique

Return JSON: {{"learning_approach": "procedural"}}"""

            try:
                approach_response = llm.generate(
                    prompt=approach_prompt,
                    temperature=0.0,
                    json_mode=True,
                )

                if approach_response and approach_response.text:
                    approach_result = json.loads(approach_response.text)
                    learning_approach = approach_result.get("learning_approach")
                    # Validate approach
                    valid_approaches = ["procedural", "conceptual", "factual", "analytical"]
                    if learning_approach not in valid_approaches:
                        learning_approach = None

                # Log token usage
                if hasattr(approach_response, 'usage') and approach_response.usage:
                    logger.debug(f"Approach call tokens: input={approach_response.usage.get('input_tokens', 0)}, output={approach_response.usage.get('output_tokens', 0)}")

            except Exception as e:
                logger.warning(f"Learning approach derivation failed: {e}")

        # Get type from first item (all items in a group should have same effective type)
        item_type = group_items[0].get("type", "key_concept")

        all_results.append((canonical_name, item_type, group_names, learning_approach))
        logger.info(f"Synonym group: {group_names} -> canonical='{canonical_name}', approach={learning_approach}")

    return all_results


def filter_and_organize_knowledge(
    llm: LLMManager,
    items: list[dict],
    existing_parents: list[str],
    existing_topics: list[str] | None = None,  # Deprecated, ignored
) -> dict:
    """
    Filter extracted knowledge items using LLM.

    Uses coherence-based filtering:
    - Filter out outliers (context/scenario items, not academic concepts)
    - Normalize parent names to existing ones

    Args:
        llm: LLMManager instance
        items: List of extracted knowledge items with name, type, parent_name
        existing_parents: List of parent names already in the course
        existing_topics: DEPRECATED - ignored, kept for backward compatibility

    Returns:
        {
            "valid_items": [...],      # Items that passed filtering
            "filtered_items": [...],   # Items removed (with idx for debugging)
            "filtered_indices": [...], # Indices of filtered items
            "inferred_topics": [],     # DEPRECATED - always empty
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

    prompt = f"""Analyze these extracted knowledge items and filter out outliers.

ITEMS:
{json.dumps(indexed_items, indent=2, ensure_ascii=False)}

EXISTING PARENT CONCEPTS IN COURSE:
{json.dumps(existing_parents, ensure_ascii=False) if existing_parents else "[]"}

TASK:
1. AGGRESSIVELY Flag OUTLIERS using these tests:

   TEST A - Academic vs Context: "Is this item the SUBJECT of study, or just the SETTING/CONTEXT of a word problem?"
   TEST B - Textbook test: "Would this appear as a chapter heading or section title in this course's textbook?"
   TEST C - Lecture test: "Would a professor put this on a lecture slide as a concept to teach?"
   TEST D - Abstraction test: "Is this a general theoretical concept, or a specific real-world instance?"

   If ANY test fails → FILTER the item out

   Keep ONLY items where ALL tests pass

2. Normalize PARENTS - if an item suggests a parent similar to an existing one, use the existing name

CRITICAL: Each item has an "idx" field. You MUST return this idx unchanged for matching.

RETURN JSON:
{{
    "valid_indices": [0, 2, 4],
    "filtered_indices": [1, 3]
}}

NOTE: Just return the indices of valid vs filtered items.
"""

    try:
        response = llm.generate(
            prompt=prompt,
            temperature=0.3,
            json_mode=True,
        )

        if response and response.text:
            result = json.loads(response.text)

            # Get valid indices from result
            valid_indices = set(result.get("valid_indices", range(len(items))))
            filtered_indices = result.get("filtered_indices", [])

            # If LLM only returned filtered_indices, compute valid_indices
            if "valid_indices" not in result and filtered_indices:
                filtered_set = set(filtered_indices)
                valid_indices = {i for i in range(len(items)) if i not in filtered_set}

            # Build valid_items (original items that passed)
            valid_items = [items[i] for i in range(len(items)) if i in valid_indices]

            # Build filtered_items for logging
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
                "valid_items": valid_items,
                "filtered_items": filtered_items,
                "filtered_indices": list(filtered_indices),
                "inferred_topics": [],  # Deprecated
            }
        else:
            logger.warning("Post-processor got empty response, returning all items")
            return {
                "valid_items": items,
                "filtered_items": [],
                "filtered_indices": [],
                "inferred_topics": [],
            }

    except json.JSONDecodeError as e:
        logger.error(f"Post-processor JSON parse error: {e}")
        return {
            "valid_items": items,
            "filtered_items": [],
            "filtered_indices": [],
            "inferred_topics": [],
        }
    except Exception as e:
        logger.error(f"Post-processor error: {e}")
        return {
            "valid_items": items,
            "filtered_items": [],
            "filtered_indices": [],
            "inferred_topics": [],
        }
