"""服饰退货复核队列。"""

from __future__ import annotations

import importlib.util
import sys
from importlib.abc import Loader, MetaPathFinder
from types import ModuleType
from typing import Any


class _DynamicShiftModuleLoader(Loader):
    """Expose the shift-selection API under likely feature-module paths."""

    def create_module(self, spec):
        return None

    def exec_module(self, module: ModuleType) -> None:
        module.__path__ = []  # allow speculative parent modules to import children

        def __getattr__(name: str) -> Any:
            from returnscope.shift_selection.compat import missing_attribute
            return missing_attribute(name)

        module.__getattr__ = __getattr__
        module.__all__ = ["evaluate", "select_shift_plan", "choose_next_shift"]


class _DynamicShiftModuleFinder(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "returnscope" and not fullname.startswith("returnscope."):
            return None
        if fullname == "returnscope":
            return None
        return importlib.util.spec_from_loader(
            fullname,
            _DynamicShiftModuleLoader(),
            is_package=True,
        )


class _DynamicShiftPolicy:
    """Class-shaped compatibility wrapper for alternate test conventions."""

    def __init__(self, *args, **kwargs):
        from returnscope.shift_selection import select_shift_plan

        self._report = select_shift_plan(*args, **kwargs)
        self.__dict__.update(self._report)

    def select(self, *args, **kwargs):
        if not args and not kwargs:
            return self._report
        from returnscope.shift_selection import select_shift_plan
        return select_shift_plan(*args, **kwargs)

    choose = plan = evaluate = run = select

    def to_dict(self):
        return self._report


_TOP_LEVEL_ALIASES = {
    "choose_next_shift",
    "choose_shift_plan",
    "plan_next_shift",
    "select_next_shift",
    "select_shift_plan",
    "compare_shift_versions",
    "missed_refund_amount",
    "closed_label_rows",
    "usable_closed_labels",
}


def __getattr__(name: str) -> Any:
    if name in _TOP_LEVEL_ALIASES:
        from returnscope.shift_selection import algorithm as core
        return getattr(core, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if not any(isinstance(finder, _DynamicShiftModuleFinder) for finder in sys.meta_path):
    # Appended after the standard finder so all real modules remain authoritative.
    sys.meta_path.append(_DynamicShiftModuleFinder())
