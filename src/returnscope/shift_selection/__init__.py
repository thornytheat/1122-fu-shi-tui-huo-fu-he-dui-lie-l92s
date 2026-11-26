"""Next-shift scoring version selection by closed-case backtesting."""
from .algorithm import (
    choose_next_shift,
    closed_label_rows,
    compare_shift_versions,
    missed_refund_amount,
    select_shift_plan,
)
from .service import evaluate, validate

__all__ = [
    "choose_next_shift",
    "closed_label_rows",
    "compare_shift_versions",
    "evaluate",
    "missed_refund_amount",
    "select_shift_plan",
    "validate",
]


def __getattr__(name):
    if name.startswith("_"):
        raise AttributeError(name)
    from .compat import missing_attribute
    return missing_attribute(name)
