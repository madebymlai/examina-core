# Examina

AI-powered exam preparation that learns from your course materials.

## What It Does

Upload past exams, homework, or problem sets. Examina analyzes them to:

- **Discover patterns** - Identifies recurring problem types and solving procedures
- **Build knowledge** - Extracts exercises, topics, and step-by-step solutions
- **Teach adaptively** - AI tutoring that adjusts to your mastery level
- **Track progress** - Spaced repetition with mastery cascade updates
- **Generate practice** - Quizzes that prioritize weak areas

## Quick Start

```bash
# Setup
git clone https://github.com/madebymlai/examina.git
cd examina
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure (set at least one)
export DEEPSEEK_API_KEY="your-key"  # Best for bulk analysis
export GROQ_API_KEY="your-key"      # Fast, free tier available

# Initialize
python3 cli.py init
```

## Usage

```bash
# 1. Create course
python3 cli.py add-course --code ADE --name "Computer Architecture"

# 2. Upload materials (exams, homework, problem sets)
python3 cli.py ingest --course ADE --zip materials.zip

# 3. Analyze (discovers topics & procedures)
python3 cli.py analyze --course ADE

# 4. Learn a procedure
python3 cli.py learn --course ADE --loop "FSM Design"

# 5. Take adaptive quiz
python3 cli.py quiz --course ADE --questions 10 --adaptive

# 6. Check progress
python3 cli.py progress --course ADE
```

## What Can You Upload?

Any PDF with numbered exercises:
- Past exams (with or without solutions)
- Homework assignments
- Practice problem sets
- Exercise collections
- Lecture notes with worked examples

**Works with any language** - Italian, English, Spanish, French, etc.

## Features

### Analysis
- Language-agnostic exercise detection
- Multi-step procedure extraction
- Theory and proof support
- Automatic topic discovery

### Learning
- Adaptive depth based on mastery
- Prerequisite enforcement
- Real-time feedback
- Concept map visualization

### Progress
- SM-2 spaced repetition
- Mastery cascade (exercise → topic → course)
- Weak area detection
- Study suggestions

### Performance
- Provider routing (cheapest per task type)
- Pattern caching (100% hit rate on re-analysis)
- Async analysis pipeline
- 26+ exercises/second with cache

## LLM Providers

| Provider  | Best For                   | Cost                |
|-----------|----------------------------|---------------------|
| DeepSeek  | Bulk analysis, web apps    | $0.14/M tokens      |
| Groq      | CLI quizzes (30 RPM limit) | Free tier available |
| Anthropic | Premium explanations       | Higher cost         |
| Ollama    | Local, private             | Free (requires GPU) |

Set with `--profile free|pro|local` or `--provider <name>`.

## Web Version

For multi-user web deployment, see [examina-cloud](https://github.com/madebymlai/examina-cloud).

## Privacy

Your materials stay local. Content is only sent to LLM providers for generating explanations. We don't train on your data.

## License

MIT License
