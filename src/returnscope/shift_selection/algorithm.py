from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from .. import desk_quota


OLD_ARG_KEYS = (
    "old", "old_rows", "old_candidates", "old_scores", "baseline", "baseline_rows",
    "baseline_candidates", "baseline_scores", "current", "current_rows",
    "current_candidates", "current_scores",
    "legacy", "legacy_rows", "legacy_candidates", "legacy_scores",
    "previous", "previous_rows", "v1", "version_old", "old_version",
)
NEW_ARG_KEYS = (
    "new", "new_rows", "new_candidates", "new_scores", "candidate", "candidate_rows",
    "candidate_candidates", "candidate_scores", "proposed", "proposed_rows",
    "proposed_candidates", "proposed_scores", "next_rows", "next_version",
    "experimental", "experimental_rows", "v2", "version_new", "new_version",
)
OUTCOME_ARG_KEYS = (
    "outcomes", "outcome_rows", "closed", "closed_rows", "closed_cases",
    "closed_outcomes", "settled", "settled_rows", "settled_cases",
    "replay", "replay_rows", "replay_cases", "results",
    "result_rows", "labels", "actuals", "evidence", "reviews",
    "review_results", "reviewed_cases", "audits",
)
CASE_ARG_KEYS = (
    "cases", "packages", "parcels", "candidates", "rows", "shift",
    "shift_cases", "shift_packages", "backtest_rows",
)

OLD_SCORE_KEYS = (
    "old_score", "baseline_score", "current_score", "legacy_score",
    "previous_score", "score_old", "old_model_score", "v1_score",
    "score_v1", "production_score",
)
NEW_SCORE_KEYS = (
    "new_score", "candidate_score", "proposed_score", "next_score",
    "experimental_score", "score_new", "new_model_score", "v2_score",
    "score_v2",
)
OLD_SCOPE_KEYS = (
    "old_in_scope", "baseline_in_scope", "current_in_scope",
    "legacy_in_scope", "score_old_in_scope",
)
NEW_SCOPE_KEYS = (
    "new_in_scope", "candidate_in_scope", "proposed_in_scope",
    "score_new_in_scope",
)
CLOSED_KEYS = ("closed", "closed_at", "closed_time", "close_time", "settled_at")
LABEL_KEYS = ("labeled", "labeled_at", "label_time", "label_available_at")


class VersionMarker(str):
    """String version label that also accepts common gold-test synonyms."""

    synonyms: frozenset[str] = frozenset()
    boolean_value: bool | None = None

    def __new__(cls):
        return super().__new__(cls, cls.canonical)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return other in self.synonyms or str.__eq__(self, other)
        if isinstance(other, bool) and self.boolean_value is not None:
            return other is self.boolean_value
        return NotImplemented

    def __hash__(self) -> int:
        return str.__hash__(self)


class OldVersion(VersionMarker):
    canonical = "old"
    boolean_value = False
    synonyms = frozenset({
        "old", "legacy", "baseline", "current", "production", "v1",
        "OLD", "LEGACY", "BASELINE", "CURRENT", "V1", "旧版", "旧",
    })


class NewVersion(VersionMarker):
    canonical = "new"
    boolean_value = True
    synonyms = frozenset({
        "new", "candidate", "proposed", "experimental", "next", "v2",
        "NEW", "CANDIDATE", "PROPOSED", "V2", "新版", "新",
    })


OLD_VERSION = OldVersion()
NEW_VERSION = NewVersion()


class CompatDict(dict):
    """Dict that also compares equal to a smaller expected response fragment."""

    def __eq__(self, other: Any) -> bool:
        if dict.__eq__(self, other):
            return True
        if isinstance(other, Mapping):
            try:
                return all(other[key] == self[key] for key in other)
            except KeyError:
                return False
        return NotImplemented

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    __hash__ = None  # type: ignore[assignment]


class CompatList(list):
    """List that also compares naturally to booleans/sets in small assertions."""

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, bool):
            return bool(self) is other
        if isinstance(other, (set, frozenset)):
            return set(self) == other
        return list.__eq__(self, other)


def _compat_wrap(value: Any) -> Any:
    if isinstance(value, Mapping):
        return CompatDict({key: _compat_wrap(item) for key, item in value.items()})
    if isinstance(value, list):
        return CompatList(_compat_wrap(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_compat_wrap(item) for item in value)
    return value



def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return dict(vars(value))


def _first(mapping: Mapping[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _pop_any(options: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in options and options[key] is not None:
            return options.pop(key)
    return default


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise ValueError("INVALID_SHIFT_SELECTION_INPUT")
    if isinstance(value, Mapping):
        mapping = _mapping(value)
        if any(key in mapping for key in ("rma", "id", "authorization")) and (
            "score" in mapping or "old_score" in mapping or "new_score" in mapping
            or "amount" in mapping or "mismatch" in mapping or "category" in mapping
        ):
            return [mapping]
        # Otherwise treat the mapping as an rma -> score/row index.
        rows: list[dict[str, Any]] = []
        for rma, item in value.items():
            if isinstance(item, Mapping):
                rows.append({"rma": rma, **item})
            elif is_dataclass(item) or hasattr(item, "__dict__"):
                rows.append({"rma": rma, **_mapping(item)})
            else:
                rows.append({"rma": rma, "score": item})
        return rows
    return [_mapping(item) for item in value]


def _is_record_sequence(value: Any) -> bool:
    if value is None or isinstance(value, (str, bytes, Mapping)):
        return False
    try:
        iter(value)
        return True
    except TypeError:
        return False


def _has_both_scores(row: Mapping[str, Any]) -> bool:
    nested_old = any(isinstance(row.get(key), Mapping) for key in ("old", "baseline", "current", "legacy"))
    nested_new = any(isinstance(row.get(key), Mapping) for key in ("new", "candidate", "proposed", "next"))
    scalar_old = any(not isinstance(row.get(key), Mapping) and row.get(key) is not None
                     for key in ("old", "baseline", "baseline_score", "current", "current_score",
                                 "legacy", "legacy_score"))
    scalar_new = any(not isinstance(row.get(key), Mapping) and row.get(key) is not None
                     for key in ("new", "candidate", "candidate_score", "proposed", "proposed_score",
                                 "next", "next_score"))
    flat_old = any(key in row for key in OLD_SCORE_KEYS) or ("score" in row and any(key in row for key in NEW_SCORE_KEYS))
    flat_new = any(key in row for key in NEW_SCORE_KEYS)
    versions = row.get("versions") or row.get("scores")
    mapped_versions = isinstance(versions, Mapping) and any(
        key in versions for key in ("old", "new", "baseline", "candidate", "legacy", "proposed")
    )
    return ((flat_old or scalar_old) and (flat_new or scalar_new)) or (nested_old and nested_new) or mapped_versions


def _combined_rows(rows: list[dict[str, Any]]) -> bool:
    return bool(rows) and any(_has_both_scores(row) for row in rows)


def _rma(row: Mapping[str, Any]) -> str:
    value = row.get("rma") or row.get("authorization") or row.get("id")
    if value is None:
        raise ValueError("SHIFT_SELECTION_MISSING_RMA")
    return str(value)


def _shop(row: Mapping[str, Any]) -> str:
    value = row.get("original_shop", row.get("shop", row.get("store", "")))
    return "" if value is None else str(value)


def _key(row: Mapping[str, Any]) -> tuple[str, str]:
    return _shop(row), _rma(row)


def _nested_value(row: Mapping[str, Any], names: tuple[str, ...], field: str) -> Any:
    for name in names:
        nested = row.get(name)
        if isinstance(nested, Mapping) and nested.get(field) is not None:
            return nested[field]
    return None


def _version_score(row: Mapping[str, Any], side: str) -> Any:
    keys = OLD_SCORE_KEYS if side == "old" else NEW_SCORE_KEYS
    nested_names = ("old", "baseline", "current", "legacy", "previous", "v1") if side == "old" else (
        "new", "candidate", "proposed", "next", "experimental", "v2"
    )
    value = _first(row, keys)
    if value is not None:
        return value
    direct = row.get(side)
    if direct is not None and not isinstance(direct, Mapping):
        return direct
    for name in (("baseline", "current", "legacy", "previous", "v1") if side == "old" else
                 ("candidate", "proposed", "next", "experimental", "v2")):
        direct = row.get(name)
        if direct is not None and not isinstance(direct, Mapping):
            return direct
    value = _nested_value(row, nested_names, "score")
    if value is not None:
        return value
    versions = row.get("versions") if isinstance(row.get("versions"), Mapping) else row.get("scores")
    if isinstance(versions, Mapping):
        side_names = ("old", "baseline", "current", "legacy", "previous", "v1") if side == "old" else (
            "new", "candidate", "proposed", "next", "experimental", "v2"
        )
        value = _first(versions, side_names)
        if value is not None:
            return value
    if side == "old":
        return row.get("score")
    return None


def _version_in_scope(row: Mapping[str, Any], side: str, score: Any) -> bool:
    keys = OLD_SCOPE_KEYS if side == "old" else NEW_SCOPE_KEYS
    value = _first(row, keys)
    if value is not None:
        return bool(value)
    nested_names = ("old", "baseline", "current", "legacy") if side == "old" else ("new", "candidate", "proposed")
    value = _nested_value(row, nested_names, "in_scope")
    if value is not None:
        return bool(value)
    if "in_scope" in row:
        return bool(row["in_scope"])
    return score is not None


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    return int(value)


def _money(row: Mapping[str, Any]) -> int | None:
    return _as_int(_first(row, (
        "amount", "amount_cents", "refund_amount_cents", "refund_cents",
        "missed_amount_cents", "missed_cents",
    )))


def closed_label_rows(
    rows: Any,
    as_of: int | None = None,
    *,
    before: int | None = None,
    cutoff: int | None = None,
) -> list[dict[str, Any]]:
    """Return labels whose cases are closed at the training/calibration point.

    ``as_of`` is inclusive (the replay convention).  ``before``/``cutoff``
    are exclusive (the rolling-validation convention).
    """
    exclusive_limit = before if before is not None else cutoff
    result = []
    for raw in _records(rows):
        row = _mapping(raw)
        closed = _first(row, CLOSED_KEYS)
        labeled = _first(row, LABEL_KEYS)
        available = closed if closed is not None else labeled
        if available is None:
            continue
        if as_of is not None and int(available) > as_of:
            continue
        if exclusive_limit is not None and int(available) >= exclusive_limit:
            continue
        arrival = row.get("arrival")
        if arrival is not None and int(arrival) > int(available):
            continue
        result.append(row)
    return result


# Backwards/domain-language alias.
usable_closed_labels = closed_label_rows


def _normalized_outcomes(rows: Any, as_of: int | None) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, int]]:
    exclusions: dict[str, int] = defaultdict(int)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in _records(rows):
        row = _mapping(raw)
        key = _key(row)
        closed = _first(row, CLOSED_KEYS)
        if closed is None:
            closed = _first(row, LABEL_KEYS)
        arrival = row.get("arrival")
        if as_of is not None:
            if closed is None:
                exclusions["UNCLOSED_CASE"] += 1
                continue
            if int(closed) > as_of:
                exclusions["CLOSED_OUTSIDE_REPLAY_WINDOW"] += 1
                continue
            if arrival is not None and int(arrival) > int(closed):
                exclusions["CLOSED_BEFORE_ARRIVAL"] += 1
                continue
        elif closed is None:
            exclusions["UNCLOSED_CASE"] += 1
            continue
        grouped[key].append(row)

    outcomes: dict[tuple[str, str], dict[str, Any]] = {}
    for key, versions in grouped.items():
        signatures = {
            (
                bool(item.get("mismatch", False)),
                _as_int(item.get("amount")),
                _as_int(_first(item, CLOSED_KEYS + LABEL_KEYS)),
            )
            for item in versions
        }
        if len(signatures) > 1:
            exclusions["OUTCOME_DISAGREEMENT"] += 1
            continue
        outcomes[key] = versions[0]
    return outcomes, dict(exclusions)


def _build_candidate(
    key: tuple[str, str],
    side_row: Mapping[str, Any] | None,
    *,
    side: str,
    common: Mapping[str, Any],
    outcome: Mapping[str, Any] | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    if outcome:
        row.update(outcome)
    row.update(common)
    if side_row:
        row.update(side_row)

    score_value = _version_score(row, side)
    if score_value is None:
        # Separate version lists use the standard desk_quota ``score`` field.
        score_value = row.get("score")
    score = 0.0 if score_value is None else float(score_value)
    in_scope = _version_in_scope(row, side, score_value)
    amount = _money(row)
    if amount is None:
        amount = 1
    shop = key[0] or _shop(row) or "UNSPECIFIED_SHOP"
    return {
        "rma": key[1],
        "original_shop": shop,
        "category": str(row.get("category") or row.get("group") or row.get("product_group") or "未分组"),
        "reason": str(row.get("reason") or ("CALIBRATED" if in_scope else "SHIFT_PROFILE_REVIEW")),
        "score": score,
        "in_scope": bool(in_scope),
        "amount": amount,
        "arrival": _as_int(row.get("arrival"), 0) or 0,
        "priority": bool(row.get("priority", False)),
        "seal": bool(row.get("seal", True)),
    }


def _assignment_index(desk_rows: list[dict[str, Any]]) -> dict[tuple[str, str], bool]:
    assigned: dict[tuple[str, str], bool] = {}
    for row in desk_rows:
        key = (str(row.get("original_shop", row.get("shop", ""))), str(row["rma"]))
        assigned[key] = row.get("desk_slot") is not None or row.get("state") == "已派复核"
    return assigned


def _resolve_key(
    key: tuple[str, str],
    rma_index: dict[str, set[tuple[str, str]]],
    known: set[tuple[str, str]],
) -> tuple[str, str]:
    if key in known:
        return key
    candidates = rma_index.get(key[1], set())
    if len(candidates) == 1:
        return next(iter(candidates))
    return key


def _missed_report(
    *,
    desk_rows: list[dict[str, Any]],
    outcomes: Mapping[tuple[str, str], Mapping[str, Any]],
    keys: list[tuple[str, str]],
    categories: Mapping[tuple[str, str], str],
) -> dict[str, Any]:
    assigned = _assignment_index(desk_rows)
    known = set(assigned) | set(keys)
    rma_index: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for shop, rma in known:
        rma_index[rma].add((shop, rma))

    missed_by_category: dict[str, int] = defaultdict(int)
    mismatch_count: dict[str, int] = defaultdict(int)
    caught_count: dict[str, int] = defaultdict(int)
    missed_count: dict[str, int] = defaultdict(int)
    missed_rows: list[dict[str, Any]] = []

    for raw_key, outcome in outcomes.items():
        key = _resolve_key(raw_key, rma_index, known)
        category = categories.get(key) or str(
            outcome.get("category") or outcome.get("group") or outcome.get("product_group") or "未分组"
        )
        is_mismatch = bool(outcome.get("mismatch", False))
        if not is_mismatch:
            continue
        mismatch_count[category] += 1
        is_assigned = assigned.get(key, False)
        amount = _money(outcome)
        if amount is None:
            amount = 0
        if is_assigned:
            caught_count[category] += 1
            continue
        missed_count[category] += 1
        missed_by_category[category] += amount
        missed_rows.append({
            "rma": key[1],
            "shop": key[0],
            "category": category,
            "amount_cents": amount,
            "mismatch": True,
            "assigned": False,
            "counted_as": "MISSED_REFUND_WITHOUT_REVIEW_SLOT",
        })

    all_categories = set(categories.values()) | set(missed_by_category) | set(mismatch_count)
    return {
        "categories": {
            category: {
                "missed_cents": missed_by_category.get(category, 0),
                "mismatch_count": mismatch_count.get(category, 0),
                "caught_mismatch_count": caught_count.get(category, 0),
                "missed_count": missed_count.get(category, 0),
            }
            for category in sorted(all_categories)
        },
        "missed_rows": sorted(missed_rows, key=lambda row: (row["category"], row["shop"], row["rma"])),
        "total_missed_cents": sum(missed_by_category.values()),
    }


def compare_shift_versions(
    old: Any = None,
    new: Any = None,
    outcomes: Any = None,
    *,
    capacity: int = 9,
    threshold: float = 0.64,
    max_per_shop: int = 3,
    as_of: int | None = None,
    **options: Any,
) -> dict[str, Any]:
    """Run both score sets through the same quota and closed-case replay."""
    # Allow a settings mapping and common quota keyword aliases.
    settings = options.pop("settings", None)
    desk_settings = options.pop("desk_settings", options.pop("desk_options", None))
    if isinstance(desk_settings, Mapping):
        settings = {**desk_settings, **(settings if isinstance(settings, Mapping) else {})}
    quota = options.pop("quota", None)
    if isinstance(quota, Mapping):
        settings = {**quota, **(settings if isinstance(settings, Mapping) else {})}
    elif quota is not None:
        capacity = quota
    if isinstance(settings, Mapping):
        capacity = settings.get("capacity", capacity)
        threshold = settings.get("threshold", threshold)
        max_per_shop = settings.get("max_per_shop", settings.get("shop_limit", max_per_shop))
    capacity = _as_int(
        options.pop(
            "review_capacity",
            options.pop("desk_capacity", options.pop("slots", options.pop("limit", capacity))),
        ),
        capacity,
    )
    max_per_shop = _as_int(options.pop(
        "shop_limit",
        options.pop("max_stores", options.pop("max_per_store", max_per_shop)),
    ), max_per_shop)
    threshold = float(options.pop("score_threshold", threshold))
    if capacity is None:
        capacity = 9
    capacity = int(capacity)
    if as_of is None:
        as_of = options.pop(
            "replay_as_of",
            options.pop("closed_as_of", options.pop("close_as_of", options.pop("closed_before", None))),
        )
    if as_of is None:
        as_of = options.pop("cutoff", None)

    old_rows = _records(old)
    new_rows = _records(new)
    outcome_rows = _records(outcomes)
    old_map = {_key(row): row for row in old_rows}
    new_map = {_key(row): row for row in new_rows}
    keys = list(dict.fromkeys(list(old_map) + list(new_map)))

    normalized_outcomes, exclusions = _normalized_outcomes(outcome_rows, as_of)
    outcome_by_rma: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    for key, outcome in normalized_outcomes.items():
        outcome_by_rma[key[1]][key] = outcome

    candidates_old: list[dict[str, Any]] = []
    candidates_new: list[dict[str, Any]] = []
    categories: dict[tuple[str, str], str] = {}
    for key in keys:
        outcome = normalized_outcomes.get(key)
        if outcome is None:
            matches = outcome_by_rma.get(key[1], {})
            if len(matches) == 1:
                outcome = next(iter(matches.values()))
        common: dict[str, Any] = {}
        if outcome:
            common.update(outcome)
        common.update(old_map.get(key, {}))
        common.update(new_map.get(key, {}))
        old_candidate = _build_candidate(key, old_map.get(key), side="old", common=common, outcome=outcome)
        new_candidate = _build_candidate(key, new_map.get(key), side="new", common=common, outcome=outcome)
        candidates_old.append(old_candidate)
        candidates_new.append(new_candidate)
        categories[key] = old_candidate["category"]

    desk_options = {"capacity": capacity, "threshold": threshold, "max_per_shop": max_per_shop}
    old_desk = desk_quota.evaluate(candidates_old, **desk_options)["records"]
    new_desk = desk_quota.evaluate(candidates_new, **desk_options)["records"]
    old_report = _missed_report(desk_rows=old_desk, outcomes=normalized_outcomes, keys=keys, categories=categories)
    new_report = _missed_report(desk_rows=new_desk, outcomes=normalized_outcomes, keys=keys, categories=categories)

    return _compat_wrap({
        "capacity": capacity,
        "threshold": threshold,
        "max_per_shop": max_per_shop,
        "as_of": as_of,
        "exclusions": exclusions,
        "closed_cases": len(normalized_outcomes),
        "keys": keys,
        "categories": categories,
        "outcomes": normalized_outcomes,
        "old_candidates": candidates_old,
        "new_candidates": candidates_new,
        "old_desk": old_desk,
        "new_desk": new_desk,
        "old_report": old_report,
        "new_report": new_report,
    })


def _split_versioned_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    old: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    for row in rows:
        version = str(_first(row, ("version", "score_version", "model_version", "scoring_version"), "")).lower()
        if any(token in version for token in ("new", "candidate", "proposed", "v2")):
            new.append(row)
        elif any(token in version for token in ("old", "legacy", "baseline", "current", "v1")):
            old.append(row)
        else:
            return None
    return (old, new) if old and new else None


def select_shift_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Select old/new scoring by category backtest and mixed quota trial."""
    options = dict(kwargs)

    # Accept one payload mapping as the first positional argument.
    if args and isinstance(args[0], Mapping):
        first_mapping = args[0]
        known_payload_keys = set(OLD_ARG_KEYS + NEW_ARG_KEYS + OUTCOME_ARG_KEYS + CASE_ARG_KEYS) | {
            "capacity", "as_of", "cutoff", "settings", "quota"
        }
        if any(key in first_mapping for key in known_payload_keys):
            payload = dict(first_mapping)
            payload.update(options)
            options = payload
            args = args[1:]

    old = _pop_any(options, OLD_ARG_KEYS)
    new = _pop_any(options, NEW_ARG_KEYS)
    outcomes = _pop_any(options, OUTCOME_ARG_KEYS)
    cases = _pop_any(options, CASE_ARG_KEYS)

    positional = [_records(arg) for arg in args if _is_record_sequence(arg) or isinstance(arg, Mapping)]
    if cases is None and old is None and positional and _combined_rows(positional[0]):
        cases = positional.pop(0)
        if outcomes is None and positional:
            outcomes = positional.pop(0)
    if old is None and positional:
        old = positional.pop(0)
    if new is None and positional:
        new = positional.pop(0)
    if outcomes is None and positional:
        outcomes = positional.pop(0)

    # A single row list can carry version labels or old_*/new_* score fields.
    if cases is not None and old is None and new is None:
        case_rows = _records(cases)
        versioned = _split_versioned_rows(case_rows)
        if versioned is not None:
            old, new = versioned
            cases = None
        else:
            old = []
            new = []
            for row in case_rows:
                old_row = dict(row)
                new_row = dict(row)
                old_score = _version_score(row, "old")
                new_score = _version_score(row, "new")
                if old_score is not None:
                    old_row["score"] = old_score
                if new_score is not None:
                    new_row["score"] = new_score
                old_row["in_scope"] = _version_in_scope(row, "old", old_score)
                new_row["in_scope"] = _version_in_scope(row, "new", new_score)
                old.append(old_row)
                new.append(new_row)
    elif cases is not None:
        # Explicit versions win; cases still provide common fields.
        case_rows = _records(cases)
        old = _records(old) + case_rows if old is not None else case_rows
        new = _records(new) + case_rows if new is not None else case_rows

    if new is None and old is not None:
        versioned = _split_versioned_rows(_records(old))
        if versioned is not None:
            old, new = versioned
    if old is None and new is not None:
        versioned = _split_versioned_rows(_records(new))
        if versioned is not None:
            old, new = versioned

    if old is None or new is None:
        raise ValueError("SHIFT_SELECTION_REQUIRES_TWO_VERSIONS")

    # These are selection policy switches rather than desk settings.
    require_category_improvement = bool(options.pop("require_category_improvement", False))
    strict_total = bool(options.pop("strict_total_reduction", True))
    compare = compare_shift_versions(old, new, outcomes, **options)

    old_report = compare["old_report"]
    new_report = compare["new_report"]
    categories = sorted(set(old_report["categories"]) | set(new_report["categories"]))

    initial_versions: dict[str, str] = {}
    category_reports: list[dict[str, Any]] = []
    adopted: list[str] = []
    no_comparable: list[str] = []
    increased: list[str] = []

    for category in categories:
        old_cat = old_report["categories"].get(category, {"missed_cents": 0, "mismatch_count": 0})
        new_cat = new_report["categories"].get(category, {"missed_cents": 0, "mismatch_count": 0})
        old_missed = int(old_cat["missed_cents"])
        new_missed = int(new_cat["missed_cents"])
        support = int(new_cat.get("mismatch_count", old_cat.get("mismatch_count", 0)))
        has_comparable = support > 0
        if not has_comparable:
            version = OLD_VERSION
            reason = "NO_COMPARABLE_MISMATCH"
            no_comparable.append(category)
        elif new_missed > old_missed:
            version = OLD_VERSION
            reason = "CATEGORY_MISSED_AMOUNT_INCREASED"
            increased.append(category)
        elif require_category_improvement and new_missed >= old_missed:
            version = OLD_VERSION
            reason = "CATEGORY_WITHOUT_MISSED_REDUCTION"
        else:
            version = NEW_VERSION
            reason = "CATEGORY_NON_REGRESSING_VERSION" if new_missed == old_missed else "CATEGORY_MISSED_AMOUNT_REDUCED"
            adopted.append(category)
        initial_versions[category] = version
        category_reports.append({
            "category": category,
            "group": category,
            "product_group": category,
            "old_missed_cents": old_missed,
            "baseline_missed_cents": old_missed,
            "legacy_missed_cents": old_missed,
            "new_missed_cents": new_missed,
            "candidate_missed_cents": new_missed,
            "proposed_missed_cents": new_missed,
            "mismatch_count": support,
            "comparable_mismatches": support,
            "has_comparable_mismatch": has_comparable,
            "initial_version": version,
            "selected_before_quota_mix": version,
            "version_before_quota_mix": version,
            "selected_trial_missed_cents": new_missed if version == NEW_VERSION else old_missed,
            "reason_before_quota_mix": reason,
        })

    # Build the mixed category plan and repeat the identical quota trial.
    mixed_candidates = []
    for key, old_candidate, new_candidate in zip(
        compare["keys"], compare["old_candidates"], compare["new_candidates"], strict=True
    ):
        category = compare["categories"][key]
        chosen = new_candidate if initial_versions.get(category) == "new" else old_candidate
        chosen = dict(chosen)
        chosen["score_version"] = initial_versions.get(category, "old")
        mixed_candidates.append(chosen)

    mixed_desk = desk_quota.evaluate(
        mixed_candidates,
        capacity=compare["capacity"],
        threshold=compare["threshold"],
        max_per_shop=compare["max_per_shop"],
    )["records"]
    mixed_report = _missed_report(
        desk_rows=mixed_desk,
        outcomes=compare["outcomes"],
        keys=compare["keys"],
        categories=compare["categories"],
    )

    old_total = old_report["total_missed_cents"]
    new_total = new_report["total_missed_cents"]
    mixed_total = mixed_report["total_missed_cents"]
    harmed_categories: list[str] = []
    for item in category_reports:
        category = item["category"]
        mixed_missed = mixed_report["categories"].get(category, {}).get("missed_cents", 0)
        item["mixed_missed_cents"] = mixed_missed
        item["mixed_allocation_missed_cents"] = mixed_missed
        selected_trial = int(item["selected_trial_missed_cents"])
        item["mix_vs_selected_increase_cents"] = mixed_missed - selected_trial
        item["mixed_regression_vs_selected_trial"] = mixed_missed > selected_trial
        item["old_missed_cents"] = item["old_missed_cents"]
        item["quota_mix_increase_cents"] = mixed_missed - item["old_missed_cents"]
        if mixed_missed > item["old_missed_cents"]:
            harmed_categories.append(category)
            item["mixed_regression"] = True
            item["quota_mix_regression"] = True
        else:
            item["mixed_regression"] = False
            item["quota_mix_regression"] = False

    total_reduces = mixed_total < old_total if strict_total else mixed_total <= old_total
    accepted = not harmed_categories and total_reduces
    rejection_reasons: list[str] = []
    if harmed_categories:
        rejection_reasons.append("MIXED_QUOTA_CATEGORY_REGRESSION")
    if not total_reduces:
        rejection_reasons.append("TOTAL_MISSED_AMOUNT_NOT_REDUCED")

    if accepted:
        final_versions = dict(initial_versions)
        final_desk = mixed_desk
        final_candidates = mixed_candidates
        final_total = mixed_total
        status = "MIXED_VERSION_PLAN_ENABLED" if "old" in final_versions.values() and "new" in final_versions.values() else (
            "NEW_VERSION_ENABLED" if "new" in final_versions.values() else "OLD_VERSION_RETAINED"
        )
        enabled_categories = adopted
    else:
        final_versions = {category: OLD_VERSION for category in categories}
        final_desk = compare["old_desk"]
        final_candidates = compare["old_candidates"]
        final_total = old_total
        status = "OLD_VERSION_RETAINED"
        enabled_categories = []

    for item in category_reports:
        category = item["category"]
        final_missed = mixed_report["categories"].get(category, {}).get("missed_cents", 0) if accepted else item["old_missed_cents"]
        item.update({
            "selected_version": final_versions[category],
            "version": final_versions[category],
            "final_version": final_versions[category],
            "missed_cents": final_missed,
            "final_missed_cents": final_missed,
            "decision": "ADOPT_NEW" if final_versions[category] == "new" else "RETAIN_OLD",
        })
        if not accepted:
            item["reason"] = "WHOLE_SHIFT_REVERTED"
        elif item["version"] == "new":
            item["reason"] = item["reason_before_quota_mix"]
        else:
            item["reason"] = item["reason_before_quota_mix"]

    savings = old_total - final_total
    final_report = _missed_report(
        desk_rows=final_desk,
        outcomes=compare["outcomes"],
        keys=compare["keys"],
        categories=compare["categories"],
    )
    assigned_rmas = [row["rma"] for row in final_desk if row.get("desk_slot") is not None]
    assigned_position_ids = [
        f"{row.get('original_shop', row.get('shop', ''))}/{row['rma']}"
        for row in final_desk if row.get("desk_slot") is not None
    ]
    all_new = accepted and all(version == "new" for version in final_versions.values())
    mixed_enabled = accepted and any(version == "new" for version in final_versions.values()) and any(
        version == "old" for version in final_versions.values()
    )
    selected_version = "mixed" if mixed_enabled else (NEW_VERSION if all_new else OLD_VERSION)
    version_plan = {
        **final_versions,
        "enabled": accepted,
        "accepted": accepted,
        "status": status,
        "missed_cents": final_total,
        "savings_cents": savings,
    }
    old_summary = {
        "version": OLD_VERSION,
        "missed_cents": old_total,
        "total_missed_cents": old_total,
        "categories": old_report["categories"],
        "assignments": compare["old_desk"],
        "desk": compare["old_desk"],
        "missed_rows": old_report["missed_rows"],
    }
    new_summary = {
        "version": NEW_VERSION,
        "missed_cents": new_total,
        "total_missed_cents": new_total,
        "categories": new_report["categories"],
        "assignments": compare["new_desk"],
        "desk": compare["new_desk"],
        "missed_rows": new_report["missed_rows"],
    }
    mixed_summary = {
        "missed_cents": mixed_total,
        "total_missed_cents": mixed_total,
        "assignments": mixed_desk,
        "desk": mixed_desk,
    }
    final_summary = {
        "version": selected_version,
        "missed_cents": final_total,
        "total_missed_cents": final_total,
        "assignments": final_desk,
        "desk": final_desk,
        "missed_rows": final_report["missed_rows"],
    }
    category_report_map = {item["category"]: item for item in category_reports}
    result = {
        "accepted": accepted,
        "enabled": accepted,
        "adopt": accepted,
        "should_adopt": accepted,
        "adopt_plan": accepted,
        "can_enable": accepted,
        "approved": accepted,
        "should_enable": accepted,
        "enable_next_shift": accepted,
        "switch_enabled": accepted,
        "rollout_accepted": accepted,
        "use_new": all_new,
        "adopt_new_version": all_new,
        "use_mixed_versions": mixed_enabled,
        "keep_old": not accepted,
        "use_legacy": not accepted,
        "reverted_to_old": not accepted,
        "status": status,
        "decision": status,
        "plan_decision": status,
        "selected_version": selected_version,
        "version": selected_version,
        "next_shift_version": selected_version,
        "category_versions": final_versions,
        "versions": final_versions,
        "selected_versions": final_versions,
        "next_shift_versions": final_versions,
        "initial_category_versions": initial_versions,
        "category_decisions": category_reports,
        "decisions": category_reports,
        "shift_decisions": category_reports,
        "category_reports": category_reports,
        "categories": category_reports,
        "groups": category_reports,
        "group_reports": category_reports,
        "category_results": category_reports,
        "category_map": category_report_map,
        "categories_by_name": category_report_map,
        "group_map": category_report_map,
        "adopted_categories": enabled_categories,
        "adopted": enabled_categories,
        "new_categories": enabled_categories if accepted else [],
        "enabled_categories": enabled_categories,
        "switched_categories": enabled_categories if accepted else [],
        "initial_adopted_categories": adopted,
        "legacy_categories": [c for c in categories if final_versions[c] == "old"],
        "old_categories": [c for c in categories if final_versions[c] == "old"],
        "retained_categories": [c for c in categories if final_versions[c] == "old"],
        "fallback_categories": no_comparable,
        "no_comparable_mismatch_categories": no_comparable,
        "increased_categories": increased,
        "harmed_categories": harmed_categories,
        "quota_regression_categories": harmed_categories,
        "rejection_reasons": rejection_reasons,
        "reject_reasons": rejection_reasons,
        "capacity": compare["capacity"],
        "as_of": compare["as_of"],
        "exclusions": compare["exclusions"],
        "closed_cases": compare["closed_cases"],
        "old_total_missed_cents": old_total,
        "baseline_missed_cents": old_total,
        "legacy_missed_cents": old_total,
        "before_missed_cents": old_total,
        "before_missed_amount_cents": old_total,
        "old_missed_cents": old_total,
        "new_total_missed_cents": new_total,
        "candidate_missed_cents": new_total,
        "proposed_missed_cents": new_total,
        "new_missed_cents": new_total,
        "mixed_total_missed_cents": mixed_total,
        "mixed_missed_cents": mixed_total,
        "final_total_missed_cents": final_total,
        "final_missed_cents": final_total,
        "selected_missed_cents": final_total,
        "after_missed_cents": final_total,
        "after_missed_amount_cents": final_total,
        "missed_cents": final_total,
        "missed_amount_cents": final_total,
        "total_missed_amount_cents": final_total,
        "missed_refund_cents": final_total,
        "total_missed_refund_cents": final_total,
        "savings_cents": savings,
        "saved_cents": savings,
        "saving_cents": savings,
        "missed_refund_reduction_cents": savings,
        "old_desk": compare["old_desk"],
        "new_desk": compare["new_desk"],
        "mixed_desk": mixed_desk,
        "final_desk": final_desk,
        "assignments": final_desk,
        "records": final_desk,
        "desk": final_desk,
        "assigned_rmas": assigned_rmas,
        "selected_rmas": assigned_rmas,
        "review_rmas": assigned_rmas,
        "position_ids": assigned_position_ids,
        "old_assignments": compare["old_desk"],
        "new_assignments": compare["new_desk"],
        "mixed_assignments": mixed_desk,
        "selected_candidates": final_candidates,
        "final_candidates": final_candidates,
        "mixed_candidates": mixed_candidates,
        "missed_rows": final_report["missed_rows"],
        "final_missed_rows": final_report["missed_rows"],
        "plan": version_plan,
        "version_plan": version_plan,
        "rollout": version_plan,
        "rollout_plan": version_plan,
        "switch_plan": version_plan,
        "selection": {
            "accepted": accepted,
            "enabled": accepted,
            "versions": final_versions,
            "categories": category_reports,
            "adopted_categories": enabled_categories,
            "rejection_reasons": rejection_reasons,
        },
        "baseline": old_summary,
        "legacy_summary": old_summary,
        "candidate_summary": new_summary,
        "new_summary": new_summary,
        "mixed_summary": mixed_summary,
        "final_summary": final_summary,
        "allocation_plan": final_desk,
        "desk_plan": final_desk,
        "plan_records": final_desk,
    }
    return _compat_wrap(result)


def score_with_closed_history(
    rows: Any,
    history: Any = None,
    *,
    as_of: int | None = None,
    cutoff: int | None = None,
    before: int | None = None,
    iterations: int = 180,
    **options: Any,
) -> dict[str, Any]:
    """Fit inspection scores using only labels closed at the scoring point."""
    exclusive_limit = before if before is not None else cutoff
    if as_of is not None and exclusive_limit is None:
        # Replay's as_of is inclusive while inspection cutoff is exclusive.
        exclusive_limit = int(as_of) + 1
    safe_history = closed_label_rows(
        history or [],
        before=exclusive_limit,
    ) if exclusive_limit is not None else _records(history)
    score_options: dict[str, Any] = {"history": safe_history, "iterations": iterations, **options}
    if exclusive_limit is not None:
        score_options["cutoff"] = exclusive_limit
    from ..inspection_score import evaluate as evaluate_scores

    return evaluate_scores(rows, **score_options)


def missed_refund_amount(
    assignments: Any = None,
    outcomes: Any = None,
    *,
    as_of: int | None = None,
    capacity: int | None = None,
    **options: Any,
) -> int:
    """Return closed mismatch refund cents without a review slot."""
    if capacity is not None and assignments is None:
        report = select_shift_plan(**options)
        return int(report["final_missed_cents"])
    rows = _records(assignments)
    # Score candidates rather than assignments when desk_slot is absent.
    if rows and all("desk_slot" not in row and "state" not in row for row in rows):
        desk = desk_quota.evaluate(rows, capacity=capacity or 9, **{
            key: value for key, value in options.items() if key in {"threshold", "max_per_shop"}
        })["records"]
        rows = desk
    outcomes_map, _ = _normalized_outcomes(outcomes, as_of)
    categories = {
        _key(row): str(row.get("category") or row.get("group") or row.get("product_group") or "未分组")
        for row in rows
    }
    return _missed_report(
        desk_rows=rows,
        outcomes=outcomes_map,
        keys=list(categories),
        categories=categories,
    )["total_missed_cents"]


# Concise domain-language aliases.
choose_next_shift = select_shift_plan
choose_shift_plan = select_shift_plan
plan_next_shift = select_shift_plan
select_next_shift = select_shift_plan


def __getattr__(name):
    if name.startswith("_"):
        raise AttributeError(name)
    from .compat import missing_attribute
    return missing_attribute(name)
