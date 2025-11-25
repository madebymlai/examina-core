"""Abstract repository interface for mastery data access.

This interface enables dependency inversion - the ProgressAnalyzer
depends on this abstraction rather than concrete implementations.

Implementations:
- SQLiteMasteryRepository: For examina CLI (uses existing Database class)
- PostgresMasteryRepository: For examina-cloud (uses SQLAlchemy async)
"""

from abc import ABC, abstractmethod
from typing import List

from core.dto.mastery import ExerciseReviewData, TopicMasteryInput


class MasteryRepository(ABC):
    """Abstract repository for mastery data access.

    All methods take user_id for multi-tenant support.
    Implementations should handle their specific data sources.
    """

    @abstractmethod
    def get_reviews_for_topic(
        self,
        user_id: str,
        topic_id: str,
    ) -> List[ExerciseReviewData]:
        """Get all exercise reviews for a topic.

        Args:
            user_id: User identifier (for multi-tenant filtering)
            topic_id: Topic identifier

        Returns:
            List of ExerciseReviewData for all reviewed exercises in the topic
        """
        pass

    @abstractmethod
    def get_topic_mastery_input(
        self,
        user_id: str,
        topic_id: str,
        topic_name: str,
    ) -> TopicMasteryInput:
        """Get complete topic input for mastery calculation.

        Args:
            user_id: User identifier
            topic_id: Topic identifier
            topic_name: Topic name (included in result)

        Returns:
            TopicMasteryInput with reviews and exercise count
        """
        pass

    @abstractmethod
    def get_all_topics_for_course(
        self,
        user_id: str,
        course_code: str,
    ) -> List[TopicMasteryInput]:
        """Get all topics with mastery inputs for a course.

        Args:
            user_id: User identifier
            course_code: Course code

        Returns:
            List of TopicMasteryInput for all topics in the course
        """
        pass
