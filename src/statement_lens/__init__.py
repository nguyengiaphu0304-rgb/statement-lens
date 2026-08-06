"""Statement Lens public package interface."""

from statement_lens.history import compare_documents, compare_history, compare_json
from statement_lens.normalizer import ValidationError, normalize_document, normalize_json

__all__ = [
    "ValidationError",
    "compare_documents",
    "compare_history",
    "compare_json",
    "normalize_document",
    "normalize_json",
]
__version__ = "0.2.0"
