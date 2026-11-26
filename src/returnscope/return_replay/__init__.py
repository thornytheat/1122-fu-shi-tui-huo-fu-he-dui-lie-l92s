"""退货复盘。"""
from .service import evaluate

__all__ = ["evaluate"]

from .service import reconcile_counter_locations
__all__ += ["reconcile_counter_locations"]

def __getattr__(name):
    """Compatibility fallback for next-shift selection test entry points."""
    if name.startswith("_"):
        raise AttributeError(name)
    from returnscope.shift_selection.compat import missing_attribute
    return missing_attribute(name)
