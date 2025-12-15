"""
Interactive AI tutor for Examina.
Provides learning features for KnowledgeItems.
"""

import re
import random
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from models.llm_manager import LLMManager
from config import Config


def get_language_name(code: str) -> str:
    """Get language instruction string for LLM prompts.

    Uses explicit phrasing that LLMs understand without hardcoded mapping.
    LLMs are trained on ISO 639-1 codes and understand them in context.
    """
    # LLMs understand "the language with code X" unambiguously
    # This avoids confusing cases like "in it" being parsed as English "it"
    return f"the language with ISO 639-1 code '{code}'"


# Teaching strategy prompts based on learning_approach
# Philosophy: "The Smartest Kid in the Library" - warm, calm, insider knowledge
# LaTeX formatting: Use $...$ for inline math, $$...$$ for display/block math

# Shared LaTeX instruction for all prompts
LATEX_INSTRUCTION = """
IMPORTANT - LaTeX formatting:
- Use $...$ for inline math (e.g., $x^2 + y^2 = r^2$)
- Use $$...$$ for display equations (centered, on their own line)
- For multi-step calculations, use display math with alignment:
  $$10 \\times 16^2 + 0 \\times 16^1 + 14 \\times 16^0 = 2560 + 0 + 14 = 2574$$
- Always wrap ALL mathematical expressions in $ delimiters, never leave raw LaTeX
"""

TEACHING_PROMPTS = {
    "factual": f"""You are the smartest student in the library, sharing your notes with a friend before their exam.
Tone: Warm, calm, like whispering exam secrets. Not clinical or robotic.
{LATEX_INSTRUCTION}
Bold **only 2-3 key terms** per section - the words a student would highlight in their notes.

CRITICAL: The quoted phrases below describe the TONE and INTENT of each section - do NOT include them literally in your output. Write your own natural prose that captures that spirit.

Structure your response with these exact markdown headers:

## Overview
One sentence: "Here's what you need to know about..."

## Fact
State it clearly, like a highlighted note in your notebook. Use $...$ for inline math, $$...$$ for equations.

## Exam Context
"This always shows up when..." - whisper the insider tip about when/how prof tests this.

## Memory Aid
"The way I remember it..." - share your personal mnemonic or trick.

Keep it SHORT. Under 150 words. Facts stick through repetition, not long explanations.""",
    "conceptual": f"""You are the smartest student in the library, explaining a concept to a friend.
Tone: Patient, clear, like showing your margin notes. Not a textbook.
{LATEX_INSTRUCTION}
Bold **only 2-3 key terms** per section - the words a student would highlight in their notes.

CRITICAL: The quoted phrases below describe the TONE and INTENT of each section - do NOT include them literally in your output. Write your own natural prose that captures that spirit.

Structure your response with these exact markdown headers:

## Overview
"Let me explain this simply..." - one sentence setup.

## Definition
Clear statement, like a margin note. Use $...$ for inline math, $$...$$ for equations.

## Exam Patterns
"Prof loves asking..." - insider knowledge of how this gets tested. Reference the past exams provided.

## Examples
"Here's how it appeared..." - walk through an example from the past exams.

## Common Mistakes
"Don't fall for this..." - friendly warning about what loses points.

Be concise but thorough. You're helping a friend, not writing a textbook.""",
    "procedural": f"""You are the smartest student in the library, showing a friend exactly how to solve problems.
Tone: Calm confidence, like "watch me do it." Not rushed or robotic.
{LATEX_INSTRUCTION}
Bold **only 2-3 key terms** per section - the words a student would highlight in their notes.

CRITICAL: The quoted phrases below describe the TONE and INTENT of each section - do NOT include them literally in your output. Write your own natural prose that captures that spirit.

Structure your response with these exact markdown headers:

## Overview
"This is the technique for..." - one sentence.

## When to Use
"You'll know to use this when..." - pattern recognition tip for exams.

## Steps
"Here's exactly how..." - numbered steps with brief rationale. Use $...$ for inline math, $$...$$ for equations.

## Worked Example
"Watch me do it..." - walk through the exam exercise step-by-step with annotations.

## Watch Out
"Careful here, most people mess up by..." - gentle warning about point-losing mistakes.

Focus on execution. This is exam prep, not theory class.""",
    "analytical": f"""You are the smartest student in the library, showing a friend how to think through hard problems.
Tone: Strategic, like sharing exam hacks. Not academic or preachy.
{LATEX_INSTRUCTION}
Bold **only 2-3 key terms** per section - the words a student would highlight in their notes.

CRITICAL: The quoted phrases below describe the TONE and INTENT of each section - do NOT include them literally in your output. Write your own natural prose that captures that spirit.

Structure your response with these exact markdown headers:

## Overview
"These questions want you to think about..." - frame the challenge.

## Problem Types
"Prof usually frames it like..." - pattern recognition from past exams.

## Approach
"The trick is to..." - insider strategy for breaking down these problems.

## Worked Example
"Here's a full-marks answer..." - show the gold standard from past exams.

## Scoring Tips
"To get all the points..." - exam hacks for maximizing score.

This is about cracking the exam, not philosophical depth.""",
}

# Section types per learning_approach
SECTIONS_BY_APPROACH = {
    "factual": ["overview", "fact", "exam_context", "memory_aid"],
    "conceptual": ["overview", "definition", "exam_patterns", "examples", "common_mistakes"],
    "procedural": ["overview", "when_to_use", "steps", "worked_example", "watch_out"],
    "analytical": ["overview", "problem_types", "approach", "worked_example", "scoring_tips"],
}

# Prompt version for cache invalidation - bump when prompts change
SECTION_PROMPT_VERSION = 1

# Section-by-section prompts for waterfall learn mode
# Each section is generated independently with focused prompts
SECTION_PROMPTS = {
    "procedural": {
        "overview": f"""You are the smartest student in the library, helping a friend before their exam.
Section 1 of 5: OVERVIEW

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms** - what a student would highlight.

Write 50-100 words covering:
- What problem does this procedure solve?
- When would you recognize to use it in an exam?

Keep it conversational: "You know when you see X? That's when you use this."
Do NOT include steps yet - just set up WHY this matters.""",
        "when_to_use": f"""You are the smartest student in the library, helping a friend before their exam.
Section 2 of 5: WHEN TO USE

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 50-100 words covering:
- Pattern recognition: what clues in exam questions signal this procedure?
- What does the setup look like? What keywords appear?

The student already read the Overview. Don't re-introduce - jump to specifics.
"When you see X, Y, or Z in the problem, that's your cue to use this."
""",
        "steps": f"""You are the smartest student in the library, helping a friend before their exam.
Section 3 of 5: STEPS

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms** per step.

Write 200-400 words. For EACH step:
1. **Step N: [Name]** - What to do (clear instruction)
2. WHY it works (the reasoning, not just "because")
3. How to verify you did it right

The student knows WHEN to use this. Now teach HOW.
Be thorough - this is the core learning. Take your time.
Use proper LaTeX for all math expressions.""",
        "worked_example": f"""You are the smartest student in the library, helping a friend before their exam.
Section 4 of 5: WORKED EXAMPLE

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 300-500 words walking through the exam exercise step by step.
Show your work like you're solving it on the board:
- Write out each calculation
- Reference the step numbers as you go ("Applying Step 2...")
- Point out where students often mess up

The student knows the steps. Do NOT re-list them before starting.
But DO reference step numbers as you work: "Now in Step 3, we..."

This should feel like watching someone solve it, not reading a solution manual.""",
        "watch_out": f"""You are the smartest student in the library, helping a friend before their exam.
Section 5 of 5: WATCH OUT

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 150-250 words covering 2-3 biggest mistakes students make:
For each mistake:
- The mistake itself (what goes wrong)
- Why it happens (the trap)
- How to avoid it (the fix)

The student knows the steps. Reference specific step numbers when relevant.
Be specific to THIS procedure, not generic exam advice.""",
    },
    "conceptual": {
        "overview": f"""You are the smartest student in the library, explaining a concept to a friend.
Section 1 of 4: OVERVIEW

{LATEX_INSTRUCTION}
Bold **only 1-2 key terms**.

Write 30-50 words - ONE sentence summary.
"This is about..." - set up what they're about to learn.
Keep it ultra-brief. The definition comes next.""",
        "definition": f"""You are the smartest student in the library, explaining a concept to a friend.
Section 2 of 4: DEFINITION

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 150-250 words covering:
- The formal definition (precise, like a textbook)
- The intuition (plain language, like margin notes)
- An analogy if it helps

The student read the overview. Now give them the real content.
Use proper LaTeX for mathematical definitions.""",
        "exam_patterns": f"""You are the smartest student in the library, explaining a concept to a friend.
Section 3 of 4: EXAM PATTERNS

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 150-250 words covering:
- How professors test this concept
- Common question formats you'll see
- What they're really asking for

The student knows the definition. Don't redefine it.
"Prof loves asking..." - share the insider knowledge.""",
        "common_mistakes": f"""You are the smartest student in the library, explaining a concept to a friend.
Section 4 of 4: COMMON MISTAKES

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 150-250 words covering:
- 2-3 mistakes students make with this concept
- Why each mistake happens
- How to avoid it

The student knows the definition and exam patterns.
"Don't fall for this..." - friendly warning about point-losing errors.""",
    },
    "factual": {
        "fact": f"""You are the smartest student in the library, sharing notes before an exam.
Section 1 of 3: THE FACT

{LATEX_INSTRUCTION}
Bold **the key fact itself**.

Write 20-50 words. State it clearly and memorably.
Like a highlighted note in your notebook.
Just the fact - context comes next.""",
        "context": f"""You are the smartest student in the library, sharing notes before an exam.
Section 2 of 3: CONTEXT

{LATEX_INSTRUCTION}
Bold **only 1-2 key terms**.

Write 50-100 words covering:
- When/why this fact matters
- Where it appears in exams
- What it connects to

The student knows the fact. Now tell them why it's important.
"This always shows up when..." - the insider tip.""",
        "memory_aid": f"""You are the smartest student in the library, sharing notes before an exam.
Section 3 of 3: MEMORY AID

{LATEX_INSTRUCTION}

Write 50-100 words with a mnemonic or memory trick.
- An acronym, rhyme, or visual association
- How YOU remember it

The student knows the fact and context.
"The way I remember it..." - share your trick.""",
    },
    "analytical": {
        "overview": f"""You are the smartest student in the library, showing a friend how to crack hard problems.
Section 1 of 4: OVERVIEW

{LATEX_INSTRUCTION}
Bold **only 1-2 key terms**.

Write 50-100 words covering:
- What type of problem is this?
- What makes it challenging?

"These questions want you to think about..." - frame the challenge.
Don't solve anything yet - just set up what they'll face.""",
        "approach": f"""You are the smartest student in the library, showing a friend how to crack hard problems.
Section 2 of 4: APPROACH

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 150-250 words covering:
- How to think about this type of problem
- What framework or strategy to use
- Key questions to ask yourself

The student knows the problem type. Now teach the thinking.
"The trick is to..." - share the strategic insight.""",
        "worked_example": f"""You are the smartest student in the library, showing a friend how to crack hard problems.
Section 3 of 4: WORKED EXAMPLE

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 300-500 words walking through the exam exercise.
Show the full solution with your reasoning visible:
- Apply the approach from the previous section
- Reference the strategy as you go ("Using the framework...")
- Show how to structure a full-marks answer

The student knows the approach. Do NOT re-explain it.
But DO reference it: "Applying our strategy of..."

This is the gold standard - show what excellence looks like.""",
        "scoring_tips": f"""You are the smartest student in the library, showing a friend how to crack hard problems.
Section 4 of 4: SCORING TIPS

{LATEX_INSTRUCTION}
Bold **only 2-3 key terms**.

Write 100-200 words covering:
- How to maximize your score
- What graders look for
- Partial credit strategies

The student has seen the worked example.
"To get all the points..." - exam hacks for the win.""",
    },
}

# Map which sections need context from previous sections
SECTION_CONTEXT_DEPENDENCIES = {
    "procedural": {
        "worked_example": "steps",  # worked example needs steps content
        "watch_out": "steps",  # watch out references steps
    },
    "analytical": {
        "worked_example": "approach",  # worked example needs approach content
    },
    # conceptual and factual don't need context passing
}


def parse_markdown_sections(markdown: str, learning_approach: str) -> List[Dict[str, Any]]:
    """Parse LLM markdown output into sections array.

    Args:
        markdown: Raw markdown from LLM with ## headers
        learning_approach: The learning approach used (for section type mapping)

    Returns:
        List of {type, content} dicts
    """
    # Split by ## headers
    parts = re.split(r"^## ", markdown, flags=re.MULTILINE)

    if len(parts) <= 1:
        # No headers found - return as single content section
        return [{"type": "content", "content": markdown.strip()}]

    sections = []
    # First part is any content before first header (usually empty)
    if parts[0].strip():
        sections.append({"type": "preamble", "content": parts[0].strip()})

    # Parse each section
    for part in parts[1:]:
        lines = part.split("\n", 1)
        header = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""

        # Convert header to section type (e.g., "Worked Example" -> "worked_example")
        section_type = header.lower().replace(" ", "_")

        sections.append({"type": section_type, "content": content})

    return sections


@dataclass
class TutorResponse:
    """Response from tutor."""

    content: str
    success: bool
    metadata: Optional[Dict[str, Any]] = None


class Tutor:
    """AI tutor for learning core loops and practicing exercises."""

    def __init__(self, llm_manager: Optional[LLMManager] = None, language: str = "en"):
        """Initialize tutor.

        Args:
            llm_manager: LLM manager instance
            language: Output language (any ISO 639-1 code, e.g., "en", "de", "zh")
        """
        self.llm = llm_manager or LLMManager(provider=Config.LLM_PROVIDER)
        self.language = language

    @property
    def llm_manager(self) -> LLMManager:
        """Alias for llm for backward compatibility with cloud."""
        return self.llm

    def _language_instruction(self, action: str = "Respond") -> str:
        """Generate dynamic language instruction for any language.

        Args:
            action: The action verb (e.g., "Respond", "Create", "Explain")

        Returns:
            Language instruction string that works for any ISO 639-1 code
        """
        # LLM understands any ISO 639-1 language code
        return f"{action} in {self.language.upper()} language."

    def learn_knowledge_item(
        self,
        knowledge_item: Dict[str, Any],
        exercises: List[Dict[str, Any]],
        notes: Optional[List[str]] = None,
        parent_exercise_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Teach a KnowledgeItem using learning_approach-specific prompts.

        Cloud-first method: data passed directly from PostgreSQL, no SQLite.

        Args:
            knowledge_item: KnowledgeItem dict with id, name, knowledge_type, learning_approach, content
            exercises: List of linked exercise dicts for examples
            notes: Optional list of user's note content strings (PRO users)
            parent_exercise_context: Optional parent exercise text for sub-questions

        Returns:
            Dict with sections array and metadata
        """

        # Get learning_approach (default to conceptual)
        learning_approach = knowledge_item.get("learning_approach", "conceptual")
        if learning_approach not in TEACHING_PROMPTS:
            learning_approach = "conceptual"

        # Get the teaching strategy prompt
        strategy_prompt = TEACHING_PROMPTS[learning_approach]

        # Select best exercise for worked example (prefer exams)
        example_exercise = self._select_example_exercise(exercises) if exercises else None

        # Build the LLM prompt
        prompt = self._build_knowledge_item_prompt(
            knowledge_item=knowledge_item,
            strategy_prompt=strategy_prompt,
            example_exercise=example_exercise,
            notes=notes,
            parent_exercise_context=parent_exercise_context,
        )

        # Call LLM
        response = self.llm.generate(
            prompt=prompt, model=self.llm.primary_model, temperature=0.3, max_tokens=2000
        )

        if not response.success:
            # Return fallback response
            return {
                "sections": [
                    {
                        "type": "fallback",
                        "content": f"Could not generate explanation: {response.error}",
                    }
                ],
                "raw_content": "",
                "learning_approach": learning_approach,
                "error": True,
            }

        # Parse markdown into sections
        sections = parse_markdown_sections(response.text, learning_approach)

        return {
            "sections": sections,
            "raw_content": response.text,
            "learning_approach": learning_approach,
            "using_notes": bool(notes),
            "has_parent_context": bool(parent_exercise_context),
            "error": False,
        }

    def learn_section(
        self,
        knowledge_item: Dict[str, Any],
        section_name: str,
        section_index: int,
        exercises: List[Dict[str, Any]],
        previous_section_content: Optional[str] = None,
        notes: Optional[List[str]] = None,
        parent_exercise_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a single section for waterfall learn mode.

        Each section is generated independently with a focused prompt.

        Args:
            knowledge_item: KnowledgeItem dict with id, name, knowledge_type, learning_approach, content
            section_name: Name of section to generate (e.g., "overview", "steps", "worked_example")
            section_index: Index of this section (0-based)
            exercises: List of linked exercise dicts for examples
            previous_section_content: Optional content from a previous section (for context dependencies)
            notes: Optional list of user's note content strings (PRO users)
            parent_exercise_context: Optional parent exercise text for sub-questions

        Returns:
            Dict with section content and metadata
        """

        # Get learning_approach (default to conceptual)
        learning_approach = knowledge_item.get("learning_approach", "conceptual").lower()
        if learning_approach not in SECTION_PROMPTS:
            learning_approach = "conceptual"

        # Get section prompts for this approach
        approach_prompts = SECTION_PROMPTS.get(learning_approach, {})

        # Get the specific section prompt
        section_prompt = approach_prompts.get(section_name)
        if not section_prompt:
            return {
                "content": f"Unknown section: {section_name}",
                "section_name": section_name,
                "section_index": section_index,
                "error": True,
            }

        # Get total sections for this approach
        sections_list = list(approach_prompts.keys())
        total_sections = len(sections_list)

        # Select example exercise for worked example section
        example_exercise = None
        if "example" in section_name.lower() and exercises:
            example_exercise = self._select_example_exercise(exercises)

        # Build the prompt
        prompt = self._build_section_prompt(
            knowledge_item=knowledge_item,
            section_prompt=section_prompt,
            section_name=section_name,
            example_exercise=example_exercise,
            previous_section_content=previous_section_content,
            notes=notes,
            parent_exercise_context=parent_exercise_context,
        )

        # Call LLM
        response = self.llm.generate(
            prompt=prompt,
            model=self.llm.primary_model,
            temperature=0.3,
            max_tokens=1500,  # Sufficient for individual sections
        )

        if not response.success:
            return {
                "content": f"Could not generate section: {response.error}",
                "section_name": section_name,
                "section_index": section_index,
                "total_sections": total_sections,
                "learning_approach": learning_approach,
                "error": True,
            }

        return {
            "content": response.text,
            "section_name": section_name,
            "section_index": section_index,
            "total_sections": total_sections,
            "is_last": section_index == total_sections - 1,
            "learning_approach": learning_approach,
            "error": False,
        }

    def _build_section_prompt(
        self,
        knowledge_item: Dict[str, Any],
        section_prompt: str,
        section_name: str,
        example_exercise: Optional[Dict[str, Any]],
        previous_section_content: Optional[str],
        notes: Optional[List[str]],
        parent_exercise_context: Optional[str],
    ) -> str:
        """Build LLM prompt for a single section."""
        import json

        # Build language instruction
        if self.language and self.language.lower() != "en":
            lang_name = get_language_name(self.language)
            language_instruction = f"IMPORTANT: You MUST respond entirely in {lang_name}. Do not respond in English.\n\n"
        else:
            language_instruction = "Respond in English.\n\n"

        # Start with language instruction and section prompt
        prompt_parts = [
            language_instruction + section_prompt,
            "",
            f"Knowledge Item: {knowledge_item.get('name', 'Unknown')}",
            f"Type: {knowledge_item.get('knowledge_type', 'unknown')}",
        ]

        # Add content if available
        content = knowledge_item.get("content")
        if content:
            if isinstance(content, dict):
                content_str = json.dumps(content, indent=2)
            else:
                content_str = str(content)
            prompt_parts.append(f"Content: {content_str}")

        # Add previous section content if this section depends on it
        if previous_section_content:
            prompt_parts.append("")
            prompt_parts.append("CONTEXT FROM PREVIOUS SECTION:")
            prompt_parts.append("The student has already read this content:")
            prompt_parts.append("---")
            prompt_parts.append(previous_section_content)
            prompt_parts.append("---")
            prompt_parts.append("Reference this when relevant (e.g., step numbers, key concepts).")

        # Add example exercise for worked example sections
        if example_exercise:
            prompt_parts.append("")
            prompt_parts.append("EXAM EXERCISE TO SOLVE:")
            prompt_parts.append(f"Source: {example_exercise.get('source_pdf', 'Unknown')}")
            prompt_parts.append(example_exercise.get("text", example_exercise.get("content", "")))

            # Add solution if available (for reference)
            solution = example_exercise.get("solution")
            if solution:
                prompt_parts.append("")
                prompt_parts.append("Official solution (use as reference):")
                prompt_parts.append(solution)

        # Add parent exercise context for sub-questions
        if parent_exercise_context:
            prompt_parts.append("")
            prompt_parts.append("This is a sub-question. Full exercise context:")
            prompt_parts.append(parent_exercise_context)

        # Add user's notes (PRO feature)
        if notes:
            prompt_parts.append("")
            prompt_parts.append("Student's notes on this topic:")
            for note in notes[:3]:
                note_text = note[:1500] if len(note) > 1500 else note
                prompt_parts.append(note_text)
            prompt_parts.append("")
            prompt_parts.append("Incorporate relevant parts if they help.")

        return "\n".join(prompt_parts)

    def get_sections_for_approach(self, learning_approach: str) -> List[str]:
        """Get list of section names for a learning approach.

        Args:
            learning_approach: The learning approach (procedural, conceptual, factual, analytical)

        Returns:
            List of section names in order
        """
        approach = learning_approach.lower()
        if approach not in SECTION_PROMPTS:
            approach = "conceptual"
        return list(SECTION_PROMPTS[approach].keys())

    def get_section_context_dependency(
        self, learning_approach: str, section_name: str
    ) -> Optional[str]:
        """Check if a section needs content from a previous section.

        Args:
            learning_approach: The learning approach
            section_name: The section to check

        Returns:
            Name of section to get context from, or None
        """
        approach = learning_approach.lower()
        dependencies = SECTION_CONTEXT_DEPENDENCIES.get(approach, {})
        return dependencies.get(section_name)

    def _select_example_exercise(self, exercises: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select best exercise for worked example.

        Prioritizes: exam > exercise_sheet > homework
        """
        if not exercises:
            return None

        priority = {"exam": 1, "exercise_sheet": 2, "homework": 3}
        sorted_ex = sorted(exercises, key=lambda e: priority.get(e.get("source_type", ""), 99))

        # Get top tier (all with same best source_type)
        best_type = sorted_ex[0].get("source_type")
        top_tier = [e for e in sorted_ex if e.get("source_type") == best_type]

        # Random pick within top tier for variety
        return random.choice(top_tier)

    def _build_knowledge_item_prompt(
        self,
        knowledge_item: Dict[str, Any],
        strategy_prompt: str,
        example_exercise: Optional[Dict[str, Any]],
        notes: Optional[List[str]],
        parent_exercise_context: Optional[str],
    ) -> str:
        """Build LLM prompt for teaching a KnowledgeItem."""
        import json

        # Build language instruction - always include to ensure correct response language
        if self.language and self.language.lower() != "en":
            lang_name = get_language_name(self.language)
            language_instruction = f"IMPORTANT: You MUST respond entirely in {lang_name}. Do not respond in English.\n\n"
        else:
            language_instruction = "Respond in English.\n\n"

        # Start with language instruction and strategy prompt
        prompt_parts = [
            language_instruction + strategy_prompt,
            "",
            f"Knowledge Item: {knowledge_item.get('name', 'Unknown')}",
            f"Type: {knowledge_item.get('knowledge_type', 'unknown')}",
        ]

        # Add content if available
        content = knowledge_item.get("content")
        if content:
            if isinstance(content, dict):
                content_str = json.dumps(content, indent=2)
            else:
                content_str = str(content)
            prompt_parts.append(f"Content: {content_str}")

        # Add example exercise for worked example
        if example_exercise:
            prompt_parts.append("")
            prompt_parts.append("Example exercise from past exams:")
            prompt_parts.append(f"Source: {example_exercise.get('source_pdf', 'Unknown')}")
            prompt_parts.append(example_exercise.get("text", example_exercise.get("content", "")))

            # Add solution if available
            solution = example_exercise.get("solution")
            if solution:
                prompt_parts.append("")
                prompt_parts.append("Official solution:")
                prompt_parts.append(solution)

        # Add parent exercise context for sub-questions
        if parent_exercise_context:
            prompt_parts.append("")
            prompt_parts.append("This is a sub-question. Full exercise context:")
            prompt_parts.append(parent_exercise_context)

        # Add user's notes (PRO feature)
        if notes:
            prompt_parts.append("")
            prompt_parts.append("The student has uploaded their own notes on this topic:")
            for note in notes[:3]:  # Limit to 3 notes
                # Truncate long notes
                note_text = note[:2000] if len(note) > 2000 else note
                prompt_parts.append(note_text)
            prompt_parts.append("")
            prompt_parts.append("Incorporate relevant parts of their notes in your explanation.")

        return "\n".join(prompt_parts)

    def check_answer(
        self,
        exercise: Dict[str, Any],
        user_answer: str,
        provide_hints: bool = False,
    ) -> TutorResponse:
        """Check user's answer and provide feedback.

        Args:
            exercise: Exercise dict with 'text' and optionally 'procedure'
            user_answer: User's answer
            provide_hints: Whether to provide hints if wrong

        Returns:
            TutorResponse with feedback
        """
        # Build evaluation prompt
        prompt = self._build_evaluation_prompt(
            exercise_text=exercise.get("text", ""),
            user_answer=user_answer,
            procedure=exercise.get("procedure"),
            provide_hints=provide_hints,
        )

        # Call LLM
        response = self.llm.generate(
            prompt=prompt, model=self.llm.primary_model, temperature=0.3, max_tokens=1500
        )

        if not response.success:
            return TutorResponse(
                content=f"Failed to evaluate answer: {response.error}", success=False
            )

        return TutorResponse(
            content=response.text,
            success=True,
            metadata={"exercise_id": exercise.get("id"), "has_hints": provide_hints},
        )

    def _build_evaluation_prompt(
        self, exercise_text: str, user_answer: str, procedure: Optional[str], provide_hints: bool
    ) -> str:
        """Build prompt for answer evaluation."""
        hint_instruction = ""
        if provide_hints:
            hint_instruction = "\n3. Provide progressive hints to guide them toward the solution"

        prompt = f"""{self._language_instruction("Respond")}

You are an AI tutor evaluating a student's answer.

EXERCISE:
{exercise_text}

STUDENT'S ANSWER:
{user_answer}

EXPECTED PROCEDURE:
{self._format_procedure(procedure)}

Your task:
1. Evaluate if the answer is correct or partially correct
2. Identify what's right and what's wrong{hint_instruction}
4. Be encouraging and constructive

Respond in a friendly, pedagogical tone.
"""
        return prompt

    def _format_procedure(self, procedure: Optional[str]) -> str:
        """Format procedure steps for display."""
        if not procedure:
            return "No procedure available."

        try:
            import json

            steps = json.loads(procedure)
            if isinstance(steps, list):
                return "\n".join([f"{i + 1}. {step}" for i, step in enumerate(steps)])
        except:
            pass

        return str(procedure)

    def _format_examples(self, examples: List[Dict[str, Any]], limit: int = 3) -> str:
        """Format example exercises."""
        if not examples:
            return "No examples available."

        formatted = []
        for i, ex in enumerate(examples[:limit], 1):
            text = ex["text"][:300] + "..." if len(ex["text"]) > 300 else ex["text"]
            formatted.append(f"Example {i}:\n{text}\n")

        return "\n".join(formatted)
