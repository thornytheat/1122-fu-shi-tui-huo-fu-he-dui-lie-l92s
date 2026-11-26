from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .algorithm import closed_label_rows, select_shift_plan


@dataclass(frozen=True, slots=True)
class ShiftSelectionRejection:
    line: int
    field: str
    code: str


def validate(rows: Iterable[Mapping[str, Any]] | None = None, **options: Any) -> dict[str, Any]:
    """Validate closed labels and return a non-throwing evidence envelope."""
    if rows is None:
        return {"accepted_count": 0, "rejected_count": 0, "records": [], "errors": []}
    accepted = []
    errors = []
    for line, raw in enumerate(rows, 1):
        if not isinstance(raw, Mapping):
            errors.append(asdict(ShiftSelectionRejection(line, "shift_selection", "EXPECTED_OBJECT")))
            continue
        closed = raw.get("closed", raw.get("labeled"))
        if closed is not None and type(closed) is not int:
            errors.append(asdict(ShiftSelectionRejection(line, "shift_selection.closed", "EXPECTED_INTEGER")))
            continue
        accepted.append(dict(raw))
    as_of = options.get("as_of", options.get("cutoff"))
    records = closed_label_rows(accepted, as_of=as_of) if as_of is not None else accepted
    return {
        "records": records,
        "accepted_count": len(accepted),
        "closed_count": len(records),
        "rejected_count": len(errors),
        "errors": errors,
    }


def evaluate(rows: Any = None, *args: Any, **options: Any) -> dict[str, Any]:
    """Service-shaped entry point.

    ``evaluate(old_rows, new_rows, outcomes, capacity=..., as_of=...)`` and
    ``evaluate(combined_rows, outcomes, capacity=..., as_of=...)`` are both
    accepted.
    """
    if rows is None:
        return select_shift_plan(*args, **options)
    return select_shift_plan(rows, *args, **options)


def __getattr__(name):
    if name.startswith("_"):
        raise AttributeError(name)
    from .compat import missing_attribute
    return missing_attribute(name)
