"""Statement Lens public package interface."""

from statement_lens.history import compare_documents, compare_history, compare_json
from statement_lens.normalizer import ValidationError, normalize_document, normalize_json
from statement_lens.ratios import evaluate_ratio_json, evaluate_ratio_policy

__all__ = [
    "ValidationError",
    "compare_documents",
    "compare_history",
    "compare_json",
    "evaluate_ratio_json",
    "evaluate_ratio_policy",
    "normalize_document",
    "normalize_json",
]
__version__ = "0.3.0a1"
