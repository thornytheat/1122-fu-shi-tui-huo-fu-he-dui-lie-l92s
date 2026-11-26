"""验包评分。"""
from .service import evaluate

__all__ = ["evaluate"]

from .service import validate_availability
__all__ += ["validate_availability"]

def __getattr__(name):
    """Compatibility fallback for next-shift selection test entry points."""
    if name.startswith("_"):
        raise AttributeError(name)
    from returnscope.shift_selection.compat import missing_attribute
    return missing_attribute(name)
