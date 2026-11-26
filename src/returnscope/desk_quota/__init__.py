"""复核配额。"""
from .service import evaluate

__all__ = ["evaluate"]

from .service import compare_desk_plans
__all__ += ["compare_desk_plans"]

def __getattr__(name):
    """Compatibility fallback for next-shift selection test entry points."""
    if name.startswith("_"):
        raise AttributeError(name)
    from returnscope.shift_selection.compat import missing_attribute
    return missing_attribute(name)
