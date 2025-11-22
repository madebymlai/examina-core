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

**Phase 1: Setup & Database** ✅ (Current)
- Project structure created
- Database schema implemented
- Basic CLI with course management

**Phase 2: PDF Processing** (Coming next)
- Extract text, images, and LaTeX from PDFs
- Split PDFs into individual exercises
- Store extracted content

**Phase 3: AI Analysis** (Planned)
- Auto-discover topics and core loops
- Extract solving procedures
- Build knowledge base with RAG

**Phase 4: AI Tutor** (Planned)
- Learn mode with guided examples
- Practice mode
- Exercise generation

**Phase 5: Quiz System** (Planned)
- Quiz with immediate feedback
- Progress tracking
- Spaced repetition

## Installation

### Prerequisites

- Python 3.10+
- Ollama (for local LLM)

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

4. Install Ollama and pull models:
```bash
# Install Ollama (Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull recommended models
ollama pull qwen2.5:14b        # Primary model for analysis
ollama pull llama3.1:8b         # Fast model for tutoring
ollama pull nomic-embed-text    # Embeddings for RAG
```

5. Initialize Examina:
```bash
python cli.py init
```

## Usage

### Basic Commands

**View available courses:**
```bash
python cli.py courses
python cli.py courses --degree bachelor
python cli.py courses --degree master
```

**Get course information:**
```bash
python cli.py info --course ADE
python cli.py info --course B006802
```

**Ingest exam PDFs (Coming in Phase 2):**
```bash
python cli.py ingest --course ADE --zip exams.zip
```

**Learn with AI tutor (Coming in Phase 4):**
```bash
python cli.py learn --course ADE --loop mealy_design
```

**Practice exercises (Coming in Phase 4):**
```bash
python cli.py practice --course ADE --topic "Sequential Circuits"
```

**Generate new exercises (Coming in Phase 4):**
```bash
python cli.py generate --course ADE --loop mealy_design --difficulty hard
```

**Take a quiz (Coming in Phase 5):**
```bash
python cli.py quiz --course ADE --questions 10
```

**View progress (Coming in Phase 5):**
```bash
python cli.py progress --course ADE
python cli.py suggest
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
├── core/                  # Core processing logic
├── models/                # LLM management
├── storage/               # Database and file storage
│   ├── database.py        # SQLite operations
│   ├── vector_store.py    # ChromaDB for RAG
│   └── file_manager.py    # File operations
└── data/                  # Data directory (git-ignored)
    ├── examina.db         # SQLite database
    ├── chroma/            # Vector embeddings
    └── files/             # PDFs and images
```

## Technology Stack

- **CLI**: Click + Rich
- **Database**: SQLite + ChromaDB
- **PDF Processing**: PyMuPDF, pdfplumber, pytesseract
- **LLM**: Ollama (local-first)
- **Embeddings**: sentence-transformers, nomic-embed-text
- **Math**: SymPy, latex2sympy2

## Contributing

This is currently a personal learning project. Contributions and suggestions are welcome!

## License

TBD

## Acknowledgments

Built with Claude Code for studying at Università degli Studi di Firenze (UNIFI).
