# Examina Core

Lightweight business logic for AI-powered exam preparation.

## Architecture

```
examina (this repo)   - Core logic, no heavy deps
    ↓ imported by
examina-cloud         - Web platform (FastAPI + React + PostgreSQL)
examina-cli           - Local CLI (ChromaDB, vector search)
```

**Rule**: Cloud and CLI import from core, never reimplement.

## Modules

| Module | Purpose |
|--------|---------|
| `core/analyzer.py` | Exercise analysis, knowledge extraction |
| `core/tutor.py` | Adaptive explanations |
| `core/quiz_engine.py` | Quiz generation |
| `core/review_engine.py` | Answer evaluation |
| `core/sm2.py` | Spaced repetition algorithm |
| `core/pdf_processor.py` | PDF text extraction |
| `core/exercise_splitter.py` | Exercise detection |

## Installation

```bash
pip install git+https://github.com/madebymlai/examina.git
```

## Usage

```python
from core.analyzer import ExerciseAnalyzer, generate_item_description
from core.tutor import Tutor
from core.quiz_engine import QuizEngine
from models.llm_manager import LLMManager

llm = LLMManager()

# Analyze exercise
analyzer = ExerciseAnalyzer(llm_manager=llm, language="en")
result = analyzer.analyze_exercise(
    exercise_text="Prove that the sum of two even numbers is even.",
    course_name="Discrete Math"
)

# Generate explanation
tutor = Tutor(llm_manager=llm, language="en")
explanation = await tutor.explain_concept(
    knowledge_item_name="even_number_properties",
    exercises=[...]
)
```

## LLM Providers

| Provider | Best For |
|----------|----------|
| DeepSeek | Analysis, reasoning |
| Groq | Fast responses |
| Anthropic | Premium explanations |

## Related

- [examina-cloud](https://github.com/madebymlai/examina-cloud) - Web platform
- [examina-cli](https://github.com/madebymlai/examina-cli) - Local CLI
