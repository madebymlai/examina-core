# Examina

AI-powered exam tutor system for mastering university courses through automated analysis of past exams.

## Overview

Examina analyzes past exam PDFs to:
- Auto-discover topics and "core loops" (resolutive algorithms/procedures)
- Build a knowledge base of exercise types and solving methods
- Provide an AI tutor for guided learning and practice
- Generate new exercises based on discovered patterns
- Track progress with spaced repetition

## Project Status

**Phase 1: Setup & Database** ✅ COMPLETED
- Project structure created
- Database schema implemented
- Basic CLI with course management

**Phase 2: PDF Processing** ✅ COMPLETED
- Extract text, images, and LaTeX from PDFs
- Split PDFs into individual exercises
- Store extracted content with intelligent merging

**Phase 3: AI Analysis** ✅ COMPLETED
- Auto-discover topics and core loops with LLM
- Extract solving procedures (step-by-step algorithms)
- Build knowledge base with RAG (vector embeddings)
- **NEW**: Confidence threshold filtering
- **NEW**: LLM response caching (100% hit rate on re-runs)
- **NEW**: Resume capability for interrupted analysis
- **NEW**: Parallel batch processing (7-8x speedup)
- **NEW**: Topic/core loop deduplication (similarity-based)

**Phase 4: AI Tutor** ✅ COMPLETED
- Learn mode with theory, procedure walkthrough, and examples
- Practice mode with interactive feedback and hints
- Exercise generation with difficulty control
- Multi-language support (Italian/English)

**Phase 5: Quiz System** (NEXT)
- Quiz with immediate feedback
- Progress tracking
- Spaced repetition algorithm (SM-2)

## Installation

### Prerequisites

- Python 3.10+
- Anthropic API key (recommended) or Groq API key or Ollama (local)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/madebymlai/Examina.git
cd Examina
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up your LLM provider:

**Option A: Anthropic Claude (Recommended - Best Quality)**
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

**Option B: Groq (Fast, Free Tier Available)**
```bash
export GROQ_API_KEY="your-api-key-here"
```

**Option C: Ollama (Local, Free)**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull embedding model (required for all providers)
ollama pull nomic-embed-text
```

5. Initialize Examina:
```bash
python3 cli.py init
```

## Quick Start

### 1. Ingest Exam PDFs

```bash
# Ingest exams from a ZIP file
python3 cli.py ingest --course ADE --zip ADE-ESAMI.zip

# View ingested exercises
python3 cli.py info --course ADE
```

### 2. Analyze with AI

```bash
# Analyze exercises to discover topics and core loops
python3 cli.py analyze --course ADE --provider anthropic --lang en

# With custom settings
python3 cli.py analyze --course ADE \
  --provider anthropic \
  --lang it \
  --parallel \
  --batch-size 10

# Resume interrupted analysis
python3 cli.py analyze --course ADE  # Automatically resumes

# Force re-analysis
python3 cli.py analyze --course ADE --force
```

**Analysis Features:**
- **Parallel Processing**: 7-8x faster (20s → 3s for 27 exercises)
- **Caching**: Zero cost on re-runs (100% cache hit rate)
- **Resume**: Automatic checkpoint recovery
- **Deduplication**: Merges similar topics/core loops (0.85 similarity)
- **Confidence Filtering**: Filters low-quality analyses (default 0.5)

### 3. Learn with AI Tutor

```bash
# Get comprehensive explanation of a core loop
python3 cli.py learn --course ADE --loop moore_machine_design --lang en

# Italian language
python3 cli.py learn --course AL --loop analisi_completa_di_matrice_parametrica --lang it
```

### 4. Practice Exercises

```bash
# Practice with interactive feedback
python3 cli.py practice --course ADE --difficulty medium --lang en

# Filter by topic
python3 cli.py practice --course PC --topic "Sincronizzazione" --lang it
```

### 5. Generate New Exercises

```bash
# Generate exercise variations
python3 cli.py generate --course ADE --loop moore_machine_design --difficulty hard --lang en
```

## Usage Examples

### View Available Courses

```bash
python3 cli.py courses
python3 cli.py courses --degree bachelor
python3 cli.py courses --degree master
```

### Get Course Information

```bash
python3 cli.py info --course ADE
python3 cli.py info --course B006802
```

### Advanced Analysis Options

```bash
# Test with limited exercises
python3 cli.py analyze --course ADE --limit 10

# Sequential mode for debugging
python3 cli.py analyze --course ADE --sequential

# Custom batch size for rate limits
python3 cli.py analyze --course ADE --batch-size 5
```

## Academic Context

Examina is designed for UNIFI Computer Science programs:

### Bachelor's Degree (L-31)
17 courses including:
- Linear Algebra (AL)
- Computer Architecture (ADE)
- Operating Systems (SO)
- Databases (BDSI)
- Computer Networks (RC)
- Concurrent Programming (PC)
- And more...

### Master's Degree (LM-18) - Software: Science and Technology
13 courses including:
- Distributed Programming (DP)
- Software Architectures (SAM)
- Penetration Testing (PT)
- Computer and Network Security (CNS)
- And more...

## Architecture

```
examina/
├── cli.py                  # CLI interface
├── config.py              # Configuration
├── study_context.py       # Course metadata
├── core/
│   ├── analyzer.py        # AI exercise analysis + parallel processing
│   ├── tutor.py           # AI tutor (learn, practice, generate)
│   └── splitter.py        # Exercise splitting logic
├── models/
│   └── llm_manager.py     # Multi-provider LLM + caching
├── storage/
│   ├── database.py        # SQLite operations + migrations
│   ├── vector_store.py    # ChromaDB for RAG
│   └── file_manager.py    # File operations
└── data/                  # Data directory (git-ignored)
    ├── examina.db         # SQLite database
    ├── chroma/            # Vector embeddings
    ├── cache/             # LLM response cache
    └── files/             # PDFs and images
```

## Technology Stack

- **CLI**: Click + Rich
- **Database**: SQLite + ChromaDB (vector store)
- **PDF Processing**: PyMuPDF, pdfplumber, pytesseract
- **LLM**: Anthropic Claude Sonnet 4.5 (primary), Groq, Ollama
- **Embeddings**: sentence-transformers, nomic-embed-text
- **Math**: SymPy, latex2sympy2
- **Concurrency**: ThreadPoolExecutor for parallel analysis

## Configuration

Edit `config.py` or use environment variables:

```bash
# LLM Provider
export EXAMINA_LLM_PROVIDER=anthropic  # or groq, ollama

# Models
export ANTHROPIC_MODEL=claude-sonnet-4-20250514
export GROQ_MODEL=llama-3.3-70b-versatile

# Analysis Settings
export EXAMINA_LANGUAGE=en  # or it
export EXAMINA_MIN_CONFIDENCE=0.5  # Confidence threshold (0.0-1.0)

# Cache Settings
export EXAMINA_CACHE_ENABLED=true
export EXAMINA_CACHE_TTL=3600  # seconds
```

## Performance Benchmarks

**Analysis Speed (27 exercises):**
- Sequential: ~20 seconds (1.7 ex/s)
- Parallel (batch=10): ~3 seconds (13.2 ex/s)
- **Speedup: 7.76x**

**Caching Benefits:**
- First run: ~26s (cache cold)
- Second run: ~0.01s (cache warm)
- **Speedup: 5000x on re-runs**

**Cost Savings:**
- Cached re-analysis: $0 (zero API calls)
- Resume on failure: Saves partial progress

## Tested Courses

✅ Computer Architecture (ADE) - 27 exercises, 11 topics, 21 core loops
✅ Linear Algebra (AL) - 38 exercises, 2 topics, 4 core loops
✅ Concurrent Programming (PC) - 26 exercises, 6 topics, 14 core loops

## Contributing

This is currently a personal learning project. Contributions and suggestions are welcome!

## License

TBD

## Acknowledgments

Built with Claude Code for studying at Università degli Studi di Firenze (UNIFI).

---

**Next Phase**: Quiz System with spaced repetition (SM-2), progress tracking, and mastery analytics.
