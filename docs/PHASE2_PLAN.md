# Phase 2: API Layer Implementation Plan

## Overview

FastAPI REST API wrapping `examina-core` for the web application.

---

## API Endpoints by Resource

### A. Authentication (`/api/v1/auth`)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/register` | POST | User registration |
| `/login` | POST | User login (JWT) |
| `/refresh` | POST | Refresh access token |
| `/me` | GET | Get current user |

### B. Courses (`/api/v1/courses`)
| Endpoint | Method | Core Module |
|----------|--------|-------------|
| `/` | GET | `Database.get_all_courses()` |
| `/{code}` | GET | `Database.get_course()` |
| `/{code}/topics` | GET | `Database.get_topics_by_course()` |
| `/{code}/core-loops` | GET | `Database.get_core_loops_by_course()` |
| `/{code}/concept-map` | GET | `ConceptGraphBuilder` |

### C. Ingestion (`/api/v1/courses/{code}/ingest`) - Background Jobs
| Endpoint | Method | Background |
|----------|--------|------------|
| `/upload` | POST | **Yes** - `ingest_materials_task` |
| `/status/{job_id}` | GET | No |

### D. Analysis (`/api/v1/courses/{code}/analyze`) - Background Jobs
| Endpoint | Method | Background |
|----------|--------|------------|
| `/start` | POST | **Yes** - `analyze_exercises_task` |
| `/status/{job_id}` | GET | No |
| `/resume` | POST | **Yes** |

### E. Learning (`/api/v1/learn`)
| Endpoint | Method | Core Module |
|----------|--------|-------------|
| `/core-loop/{id}` | GET | `Tutor.learn()` |
| `/practice` | GET | `Tutor.practice()` |
| `/practice/evaluate` | POST | `Tutor.check_answer()` |
| `/generate` | POST | `Tutor.generate()` |

### F. Quiz (`/api/v1/quiz`)
| Endpoint | Method | Core Module |
|----------|--------|-------------|
| `/sessions` | POST | `QuizEngine.create_quiz_session()` |
| `/sessions/{id}` | GET | - |
| `/sessions/{id}/answer` | POST | `QuizEngine.evaluate_answer()` |
| `/sessions/{id}/complete` | POST | `QuizEngine.complete_session()` |

### G. Progress (`/api/v1/progress`)
| Endpoint | Method | Core Module |
|----------|--------|-------------|
| `/{code}/summary` | GET | `ProgressAnalytics` |
| `/{code}/weak-areas` | GET | `MasteryAggregator.get_weak_core_loops()` |
| `/{code}/learning-path` | GET | `AdaptiveTeachingManager.get_personalized_learning_path()` |

---

## Background Jobs (Celery + Redis)

| Job | Trigger | Duration | Queue |
|-----|---------|----------|-------|
| `ingest_materials_task` | Upload PDF | Minutes | `ingestion` |
| `analyze_exercises_task` | Start analysis | Hours | `analysis` |
| `deduplicate_task` | Admin action | Minutes | `default` |

---

## Implementation Order

### Phase 2.1: Core Setup
- [ ] SQLAlchemy async models (PostgreSQL)
- [ ] JWT authentication middleware
- [ ] Dependency injection for Database, LLMManager
- [ ] Error handling and validation

### Phase 2.2: Read-Only Endpoints
- [ ] GET `/courses` - List courses
- [ ] GET `/courses/{code}` - Course details
- [ ] GET `/exercises` - List/search exercises
- [ ] GET `/progress/{code}/summary` - User progress

### Phase 2.3: Learning & Quiz
- [ ] GET `/learn/core-loop/{id}` - Get explanation
- [ ] POST `/quiz/sessions` - Create quiz
- [ ] POST `/quiz/sessions/{id}/answer` - Submit answer
- [ ] POST `/quiz/sessions/{id}/complete` - Finish quiz

### Phase 2.4: Background Jobs
- [ ] Celery + Redis setup
- [ ] POST `/ingest/upload` - PDF upload + processing
- [ ] POST `/analyze/start` - Analysis job
- [ ] GET `/jobs/{id}` - Job status polling
- [ ] WebSocket for real-time progress (optional)

### Phase 2.5: Admin & Premium
- [ ] POST `/admin/deduplicate` - Deduplication
- [ ] Subscription/payment integration
- [ ] Rate limiting per user

---

## File Structure (examina-cloud/backend)

```
backend/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── auth.py
│   │   │   ├── courses.py
│   │   │   ├── exercises.py
│   │   │   ├── learn.py
│   │   │   ├── quiz.py
│   │   │   ├── progress.py
│   │   │   └── admin.py
│   │   └── deps.py          # Auth, DB dependencies
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py      # JWT, password hashing
│   │   └── exceptions.py
│   ├── models/
│   │   ├── user.py          # SQLAlchemy User model
│   │   ├── course.py        # Course, Topic, CoreLoop
│   │   ├── exercise.py
│   │   ├── quiz.py
│   │   └── progress.py
│   ├── schemas/
│   │   ├── auth.py          # Pydantic request/response
│   │   ├── course.py
│   │   ├── exercise.py
│   │   ├── learn.py
│   │   ├── quiz.py
│   │   └── progress.py
│   ├── services/
│   │   ├── auth.py          # User management
│   │   ├── course.py        # Wraps examina-core
│   │   ├── learn.py
│   │   ├── quiz.py
│   │   └── progress.py
│   └── main.py
├── worker/
│   ├── celery_app.py
│   └── tasks/
│       ├── ingest.py
│       └── analyze.py
└── alembic/                  # DB migrations
```

---

## Key Design Decisions

1. **examina-core as dependency** - `pip install git+...`, don't duplicate
2. **Multi-tenant** - All queries scoped by `user_id`
3. **Async everywhere** - `asyncpg` + `async def` endpoints
4. **Background for long tasks** - Ingestion, analysis via Celery
5. **JWT auth** - Stateless, access + refresh tokens
