"""
Database management for Examina.
Handles SQLite operations and schema management.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import Config


class Database:
    """Manages SQLite database operations for Examina."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Uses Config.DB_PATH if not provided.
        """
        self.db_path = db_path or Config.DB_PATH
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Establish database connection."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.conn:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
            self.close()

    def initialize(self):
        """Create all tables and indexes."""
        if not self.conn:
            self.connect()

        self._create_tables()
        self._create_indexes()
        self.conn.commit()

    def _create_tables(self):
        """Create all database tables."""

        # Courses table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                original_name TEXT,
                acronym TEXT,
                degree_level TEXT,
                degree_program TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Topics table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_code) REFERENCES courses(code),
                UNIQUE(course_code, name)
            )
        """)

        # Core loops table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS core_loops (
                id TEXT PRIMARY KEY,
                topic_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                procedure TEXT NOT NULL,
                difficulty_avg REAL DEFAULT 0.0,
                exercise_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            )
        """)

        # Exercises table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id TEXT PRIMARY KEY,
                course_code TEXT NOT NULL,
                topic_id INTEGER,
                core_loop_id TEXT,
                source_pdf TEXT,
                page_number INTEGER,
                exercise_number TEXT,
                text TEXT NOT NULL,
                has_images BOOLEAN DEFAULT 0,
                image_paths TEXT,
                latex_content TEXT,
                difficulty TEXT,
                variations TEXT,
                solution TEXT,
                analyzed BOOLEAN DEFAULT 0,
                analysis_metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_code) REFERENCES courses(code),
                FOREIGN KEY (topic_id) REFERENCES topics(id),
                FOREIGN KEY (core_loop_id) REFERENCES core_loops(id)
            )
        """)

        # Student progress table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS student_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL,
                core_loop_id TEXT NOT NULL,
                total_attempts INTEGER DEFAULT 0,
                correct_attempts INTEGER DEFAULT 0,
                mastery_score REAL DEFAULT 0.0,
                last_practiced TIMESTAMP,
                next_review TIMESTAMP,
                review_interval INTEGER DEFAULT 1,
                common_mistakes TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_code) REFERENCES courses(code),
                FOREIGN KEY (core_loop_id) REFERENCES core_loops(id),
                UNIQUE(course_code, core_loop_id)
            )
        """)

        # Quiz sessions table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_sessions (
                id TEXT PRIMARY KEY,
                course_code TEXT NOT NULL,
                quiz_type TEXT NOT NULL,
                topic_id INTEGER,
                core_loop_id TEXT,
                total_questions INTEGER,
                time_limit INTEGER,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                total_correct INTEGER DEFAULT 0,
                score REAL,
                time_spent INTEGER,
                FOREIGN KEY (course_code) REFERENCES courses(code),
                FOREIGN KEY (topic_id) REFERENCES topics(id),
                FOREIGN KEY (core_loop_id) REFERENCES core_loops(id)
            )
        """)

        # Quiz answers table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                exercise_id TEXT NOT NULL,
                question_number INTEGER,
                student_answer TEXT,
                is_correct BOOLEAN,
                score REAL,
                mistakes TEXT,
                hint_used BOOLEAN DEFAULT 0,
                hints_requested INTEGER DEFAULT 0,
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                time_spent INTEGER,
                FOREIGN KEY (session_id) REFERENCES quiz_sessions(id),
                FOREIGN KEY (exercise_id) REFERENCES exercises(id)
            )
        """)

        # Generated exercises table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS generated_exercises (
                id TEXT PRIMARY KEY,
                course_code TEXT NOT NULL,
                core_loop_id TEXT NOT NULL,
                based_on_exercise_ids TEXT,
                difficulty TEXT,
                variations TEXT,
                text TEXT NOT NULL,
                solution_outline TEXT,
                common_mistakes TEXT,
                times_used INTEGER DEFAULT 0,
                avg_student_score REAL,
                flagged_for_review BOOLEAN DEFAULT 0,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_code) REFERENCES courses(code),
                FOREIGN KEY (core_loop_id) REFERENCES core_loops(id)
            )
        """)

    def _create_indexes(self):
        """Create database indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_exercises_course ON exercises(course_code)",
            "CREATE INDEX IF NOT EXISTS idx_exercises_core_loop ON exercises(core_loop_id)",
            "CREATE INDEX IF NOT EXISTS idx_exercises_topic ON exercises(topic_id)",
            "CREATE INDEX IF NOT EXISTS idx_topics_course ON topics(course_code)",
            "CREATE INDEX IF NOT EXISTS idx_core_loops_topic ON core_loops(topic_id)",
            "CREATE INDEX IF NOT EXISTS idx_progress_course ON student_progress(course_code)",
            "CREATE INDEX IF NOT EXISTS idx_progress_core_loop ON student_progress(core_loop_id)",
            "CREATE INDEX IF NOT EXISTS idx_quiz_sessions_course ON quiz_sessions(course_code)",
            "CREATE INDEX IF NOT EXISTS idx_quiz_answers_session ON quiz_answers(session_id)",
        ]

        for index_sql in indexes:
            self.conn.execute(index_sql)

    # Course operations
    def add_course(self, code: str, name: str, original_name: str = None,
                   acronym: str = None, degree_level: str = None,
                   degree_program: str = None):
        """Add a new course to the database.

        Args:
            code: Course code (e.g., "B006802")
            name: English course name
            original_name: Original language name (Italian)
            acronym: Course acronym
            degree_level: "bachelor" or "master"
            degree_program: "L-31" or "LM-18"
        """
        self.conn.execute("""
            INSERT OR IGNORE INTO courses
            (code, name, original_name, acronym, degree_level, degree_program)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, name, original_name, acronym, degree_level, degree_program))

    def get_course(self, code: str) -> Optional[Dict[str, Any]]:
        """Get course information by code."""
        cursor = self.conn.execute(
            "SELECT * FROM courses WHERE code = ?", (code,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_courses(self) -> List[Dict[str, Any]]:
        """Get all courses."""
        cursor = self.conn.execute("SELECT * FROM courses ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

    # Topic operations
    def add_topic(self, course_code: str, name: str, description: str = None) -> int:
        """Add a new topic to a course.

        Returns:
            Topic ID
        """
        cursor = self.conn.execute("""
            INSERT OR IGNORE INTO topics (course_code, name, description)
            VALUES (?, ?, ?)
        """, (course_code, name, description))

        if cursor.lastrowid == 0:
            # Topic already exists, fetch its ID
            cursor = self.conn.execute(
                "SELECT id FROM topics WHERE course_code = ? AND name = ?",
                (course_code, name)
            )
            return cursor.fetchone()[0]
        return cursor.lastrowid

    def get_topics_by_course(self, course_code: str) -> List[Dict[str, Any]]:
        """Get all topics for a course."""
        cursor = self.conn.execute("""
            SELECT * FROM topics
            WHERE course_code = ?
            ORDER BY name
        """, (course_code,))
        return [dict(row) for row in cursor.fetchall()]

    # Core loop operations
    def add_core_loop(self, loop_id: str, topic_id: int, name: str,
                      procedure: List[str], description: str = None) -> str:
        """Add a new core loop.

        Args:
            loop_id: Unique identifier for the core loop
            topic_id: Parent topic ID
            name: Name of the core loop
            procedure: List of procedure steps
            description: Optional description

        Returns:
            Core loop ID
        """
        procedure_json = json.dumps(procedure)
        self.conn.execute("""
            INSERT OR REPLACE INTO core_loops
            (id, topic_id, name, description, procedure, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (loop_id, topic_id, name, description, procedure_json))
        return loop_id

    def get_core_loop(self, loop_id: str) -> Optional[Dict[str, Any]]:
        """Get core loop by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM core_loops WHERE id = ?", (loop_id,)
        )
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result['procedure'] = json.loads(result['procedure'])
            return result
        return None

    def get_core_loops_by_topic(self, topic_id: int) -> List[Dict[str, Any]]:
        """Get all core loops for a topic."""
        cursor = self.conn.execute("""
            SELECT * FROM core_loops
            WHERE topic_id = ?
            ORDER BY name
        """, (topic_id,))
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result['procedure'] = json.loads(result['procedure'])
            results.append(result)
        return results

    def update_core_loop_stats(self, loop_id: str):
        """Update exercise count and average difficulty for a core loop."""
        cursor = self.conn.execute("""
            SELECT COUNT(*) as count, AVG(
                CASE difficulty
                    WHEN 'easy' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'hard' THEN 3
                    ELSE 2
                END
            ) as avg_diff
            FROM exercises
            WHERE core_loop_id = ?
        """, (loop_id,))

        row = cursor.fetchone()
        if row:
            self.conn.execute("""
                UPDATE core_loops
                SET exercise_count = ?, difficulty_avg = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (row[0], row[1] or 0.0, loop_id))

    # Exercise operations
    def add_exercise(self, exercise_data: Dict[str, Any]) -> str:
        """Add a new exercise.

        Args:
            exercise_data: Dictionary with exercise information

        Returns:
            Exercise ID
        """
        # Convert lists/dicts to JSON strings
        if 'image_paths' in exercise_data and isinstance(exercise_data['image_paths'], list):
            exercise_data['image_paths'] = json.dumps(exercise_data['image_paths'])
        if 'variations' in exercise_data and isinstance(exercise_data['variations'], list):
            exercise_data['variations'] = json.dumps(exercise_data['variations'])
        if 'analysis_metadata' in exercise_data and isinstance(exercise_data['analysis_metadata'], dict):
            exercise_data['analysis_metadata'] = json.dumps(exercise_data['analysis_metadata'])

        self.conn.execute("""
            INSERT INTO exercises
            (id, course_code, topic_id, core_loop_id, source_pdf, page_number,
             exercise_number, text, has_images, image_paths, latex_content,
             difficulty, variations, solution, analyzed, analysis_metadata)
            VALUES
            (:id, :course_code, :topic_id, :core_loop_id, :source_pdf, :page_number,
             :exercise_number, :text, :has_images, :image_paths, :latex_content,
             :difficulty, :variations, :solution, :analyzed, :analysis_metadata)
        """, exercise_data)

        return exercise_data['id']

    def get_exercise(self, exercise_id: str) -> Optional[Dict[str, Any]]:
        """Get exercise by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
        )
        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Parse JSON fields
            if result.get('image_paths'):
                result['image_paths'] = json.loads(result['image_paths'])
            if result.get('variations'):
                result['variations'] = json.loads(result['variations'])
            if result.get('analysis_metadata'):
                result['analysis_metadata'] = json.loads(result['analysis_metadata'])
            return result
        return None

    def get_exercises_by_core_loop(self, core_loop_id: str) -> List[Dict[str, Any]]:
        """Get all exercises for a core loop."""
        cursor = self.conn.execute("""
            SELECT * FROM exercises
            WHERE core_loop_id = ?
            ORDER BY created_at
        """, (core_loop_id,))

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            if result.get('image_paths'):
                result['image_paths'] = json.loads(result['image_paths'])
            if result.get('variations'):
                result['variations'] = json.loads(result['variations'])
            if result.get('analysis_metadata'):
                result['analysis_metadata'] = json.loads(result['analysis_metadata'])
            results.append(result)
        return results

    def get_exercises_by_course(self, course_code: str) -> List[Dict[str, Any]]:
        """Get all exercises for a course."""
        cursor = self.conn.execute("""
            SELECT * FROM exercises
            WHERE course_code = ?
            ORDER BY created_at
        """, (course_code,))

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            if result.get('image_paths'):
                result['image_paths'] = json.loads(result['image_paths'])
            if result.get('variations'):
                result['variations'] = json.loads(result['variations'])
            if result.get('analysis_metadata'):
                result['analysis_metadata'] = json.loads(result['analysis_metadata'])
            results.append(result)
        return results
