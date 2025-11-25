"""Ports (interfaces) for examina-core dependency inversion.

These abstract interfaces define how examina-core accesses data,
allowing different implementations for different environments
(SQLite for CLI, PostgreSQL for web, etc.).
"""

from .mastery_repository import MasteryRepository

__all__ = [
    "MasteryRepository",
]
