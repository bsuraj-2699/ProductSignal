"""
Data models for ProductSignal.
"""

from .feedback import FeedbackRecord, FeedbackCreate
from .classification import Classification, ClassificationCreate

__all__ = [
    "FeedbackRecord",
    "FeedbackCreate",
    "Classification",
    "ClassificationCreate",
]