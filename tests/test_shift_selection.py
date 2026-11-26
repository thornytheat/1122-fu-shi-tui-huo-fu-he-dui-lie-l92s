from returnscope.shift_selection import choose_next_shift, closed_label_rows


def parcel(rma, category, score, amount, **changes):
    return {
        "rma": rma,
        "original_shop": "SX",
        "category": category,
        "reason": "MODEL_RISK",
        "score": score,
        "in_scope": True,
        "amount": amount,
        "arrival": 1,
        "priority": False,
        "seal": True,
    } | changes


def outcome(rma, amount, *, mismatch=True, closed=20, **changes):
    return {
        "rma": rma,
        "shop": "SX",
        "amount": amount,
        "mismatch": mismatch,
        "reviewed": False,
        "arrival": 1,
        "closed": closed,
    } | changes


def test_beneficial_category_can_use_new_score():
    old = [parcel("A", "A", 0.40, 12_000), parcel("SAFE", "C", 0.95, 20_000)]
    new = [parcel("A", "A", 0.99, 12_000), parcel("SAFE", "C", 0.95, 20_000)]
    outcomes = [outcome("A", 12_000), outcome("SAFE", 20_000, mismatch=False)]

    result = choose_next_shift(old, new, outcomes, capacity=2, as_of=20)

    assert result["accepted"] is True
    assert result["versions"]["A"] == "new"
    assert result["versions"]["C"] == "old"
    assert result["old_missed_cents"] == 12_000
    assert result["final_missed_cents"] == 0


def test_category_without_comparable_mismatch_keeps_legacy():
    old = [parcel("A", "A", 0.40, 12_000)]
    new = [parcel("A", "A", 0.99, 12_000)]
    result = choose_next_shift(old, new, [], capacity=1, as_of=20)
    assert result["versions"]["A"] == "old"
    assert result["adopted_categories"] == []


def test_mixed_quota_regression_reverts_whole_shift_to_legacy():
    old = [parcel("A", "A", 0.64, 12_000), parcel("B", "B", 0.90, 10_000)]
    new = [parcel("A", "A", 0.99, 12_000), parcel("B", "B", 0.20, 10_000)]
    outcomes = [outcome("A", 12_000), outcome("B", 10_000)]

    result = choose_next_shift(old, new, outcomes, capacity=1, as_of=20)

    assert result["accepted"] is False
    assert set(result["versions"].values()) == {"old"}
    assert result["harmed_categories"] == ["B"]
    assert result["old_missed_cents"] == 12_000
    assert result["final_missed_cents"] == 12_000


def test_closed_mismatch_without_slot_is_missed_even_if_not_historical_review():
    old = [parcel("A", "A", 0.10, 12_000)]
    new = [parcel("A", "A", 0.20, 12_000)]
    result = choose_next_shift(old, new, [outcome("A", 12_000)], capacity=1, as_of=20)
    assert result["closed_cases"] == 1
    assert result["missed_cents"] == 12_000
    assert result["missed_rows"][0]["counted_as"] == "MISSED_REFUND_WITHOUT_REVIEW_SLOT"


def test_unclosed_labels_are_filtered_inclusively_at_as_of():
    rows = [
        {"rma": "OPEN", "arrival": 1, "closed": 21},
        {"rma": "CLOSED", "arrival": 1, "closed": 20},
        {"rma": "LABEL", "arrival": 1, "labeled": 19},
    ]
    assert [row["rma"] for row in closed_label_rows(rows, as_of=20)] == ["CLOSED", "LABEL"]
