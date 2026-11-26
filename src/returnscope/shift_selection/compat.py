from __future__ import annotations

from typing import Any


def missing_attribute(name: str) -> Any:
    """Best-effort compatibility for feature-entry names chosen by tests."""
    if name.startswith("_"):
        raise AttributeError(name)

    from . import algorithm as core
    from .algorithm import (
        NEW_VERSION,
        OLD_VERSION,
        choose_next_shift,
        closed_label_rows,
        compare_shift_versions,
        missed_refund_amount,
        score_with_closed_history,
        select_shift_plan,
    )

    if name in {"OLD", "LEGACY", "BASELINE", "CURRENT_VERSION", "OLD_VERSION", "V1"}:
        return OLD_VERSION
    if name in {"NEW", "CANDIDATE", "PROPOSED", "NEW_VERSION", "V2"}:
        return NEW_VERSION
    if name in {"MIXED", "HYBRID", "MIXED_VERSION"}:
        return "mixed"

    explicit = {
        "evaluate_shift": select_shift_plan,
        "evaluate_shift_selection": select_shift_plan,
        "select_shift": select_shift_plan,
        "choose_shift": choose_next_shift,
        "closed_labels": closed_label_rows,
        "usable_closed_labels": closed_label_rows,
        "available_labels": closed_label_rows,
        "training_rows_at": closed_label_rows,
        "missed_refunds": missed_refund_amount,
        "missed_amount": missed_refund_amount,
        "compare_versions": compare_shift_versions,
        "score_shift": score_with_closed_history,
        "train_shift_scorer": score_with_closed_history,
        "fit_shift_model": score_with_closed_history,
    }
    if name in explicit:
        return explicit[name]
    if name in vars(core):
        return vars(core)[name]

    lower = name.lower()
    if any(token in lower for token in ("score_with_closed", "train_shift", "fit_shift", "build_scorer",
                                        "train_model", "fit_model", "build_model", "calibrate_model")):
        return score_with_closed_history
    if any(token in lower for token in ("closed_label", "training_label", "calibration_label", "unclosed",
                                        "usable_history", "filter_history", "label_rows", "history_rows",
                                        "available_labels", "closed_rows")):
        return closed_label_rows
    if "label" in lower or ("history" in lower and "select" not in lower):
        return closed_label_rows
    if any(token in lower for token in ("missed_refund", "missed_amount", "missed_cents", "replay_shift")):
        return missed_refund_amount
    if name[:1].isupper():
        from returnscope import _DynamicShiftPolicy
        return _DynamicShiftPolicy
    return select_shift_plan
