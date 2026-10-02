"""Pure money-splitting logic. All amounts are integer cents."""

from __future__ import annotations


def to_cents(value: float) -> int:
    return int(round(float(value) * 100))


def fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) / 100:,.2f}"


def equal_shares(total: int, person_ids: list[int]) -> dict[int, int]:
    """Split total equally; leftover cents go to the first few people."""
    if not person_ids:
        return {}
    base, remainder = divmod(total, len(person_ids))
    return {pid: base + (1 if i < remainder else 0) for i, pid in enumerate(person_ids)}


def compute_balances(person_ids: list[int], expenses: list[dict]) -> dict[int, int]:
    """Positive balance = gets money back, negative = owes.

    Each expense dict needs "payer_id", "amount" and "shares" ({person_id: cents}).
    """
    bal = {pid: 0 for pid in person_ids}
    for e in expenses:
        bal[e["payer_id"]] = bal.get(e["payer_id"], 0) + e["amount"]
        for pid, share in e["shares"].items():
            bal[pid] = bal.get(pid, 0) - share
    return bal


def compute_settlements(balances: dict[int, int]) -> list[tuple[int, int, int]]:
    """Greedy settle-up: match largest debtor with largest creditor.

    Returns a list of (from_id, to_id, cents).
    """
    debtors = sorted(([pid, -amt] for pid, amt in balances.items() if amt < 0), key=lambda x: -x[1])
    creditors = sorted(([pid, amt] for pid, amt in balances.items() if amt > 0), key=lambda x: -x[1])
    result = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        pay = min(debtors[i][1], creditors[j][1])
        result.append((debtors[i][0], creditors[j][0], pay))
        debtors[i][1] -= pay
        creditors[j][1] -= pay
        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1
    return result
