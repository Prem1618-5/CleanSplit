"""
Balance calculation.

Design:
  - Splits table is the source of truth (who owes how much per expense, in INR).
  - Settlements subtract from outstanding balances.
  - Net per person: sum(paid_for_others) - sum(owed_to_others)
    Positive  -> others owe this person
    Negative  -> this person owes others
  - Minimum-transactions algorithm: greedy two-pointer on sorted creditor/debtor lists.
"""

from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
import models


def _to_inr(amount: float, currency: str, rate: float) -> Decimal:
    if currency == "INR":
        return Decimal(str(amount))
    if currency == "USD":
        return Decimal(str(amount)) * Decimal(str(rate))
    raise ValueError(f"Unsupported currency: {currency}")


def compute_group_balances(group_id: int, db: Session):
    """
    Returns:
      {
        "members": {user_id: {"name": str, "net": float}},
        "transactions": [{"from_id": int, "from": str, "to_id": int, "to": str, "amount": float}]
      }
    """
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    rate = Decimal(str(group.usd_inr_rate))

    members = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id
    ).all()
    user_ids = {m.user_id for m in members}
    user_names = {}
    for m in members:
        user_names[m.user_id] = m.user.name

    net = {uid: Decimal("0") for uid in user_ids}

    # Expenses
    expenses = db.query(models.Expense).filter(
        models.Expense.group_id == group_id,
        models.Expense.is_deleted == False,
    ).all()

    for exp in expenses:
        if exp.paid_by_user_id and exp.paid_by_user_id in net:
            amount_inr = _to_inr(exp.amount, exp.currency, exp.usd_inr_rate_used or 1)
            net[exp.paid_by_user_id] += amount_inr

        for split in exp.splits:
            if split.user_id in net:
                net[split.user_id] -= Decimal(str(split.amount_inr))

    # Settlements
    settlements = db.query(models.Settlement).filter(
        models.Settlement.group_id == group_id
    ).all()

    for s in settlements:
        s_amount = _to_inr(s.amount, s.currency, rate)
        if s.payer_id in net:
            net[s.payer_id] += s_amount
        if s.receiver_id in net:
            net[s.receiver_id] -= s_amount

    # Round to 2 decimal places
    net = {uid: float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
           for uid, v in net.items()}

    transactions = _minimize_transactions(net, user_names)

    return {
        "members": {
            uid: {"name": user_names.get(uid, f"User {uid}"), "net": bal}
            for uid, bal in net.items()
        },
        "transactions": transactions,
    }


def _minimize_transactions(net: dict, names: dict) -> list:
    """
    Greedy two-pointer: match highest debtor to highest creditor.
    All settled amounts are in INR (float, rounded to 2dp).
    """
    EPSILON = 0.01
    debtors = sorted(
        [(uid, -bal) for uid, bal in net.items() if bal < -EPSILON],
        key=lambda x: -x[1],
    )
    creditors = sorted(
        [(uid, bal) for uid, bal in net.items() if bal > EPSILON],
        key=lambda x: -x[1],
    )

    debtors = [[uid, debt] for uid, debt in debtors]
    creditors = [[uid, credit] for uid, credit in creditors]

    transactions = []
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debtor_id, debt = debtors[i]
        creditor_id, credit = creditors[j]

        amount = round(min(debt, credit), 2)
        if amount >= EPSILON:
            transactions.append({
                "from_id": debtor_id,
                "from": names.get(debtor_id, str(debtor_id)),
                "to_id": creditor_id,
                "to": names.get(creditor_id, str(creditor_id)),
                "amount": amount,
            })

        debtors[i][1] = round(debt - amount, 2)
        creditors[j][1] = round(credit - amount, 2)

        if debtors[i][1] < EPSILON:
            i += 1
        if creditors[j][1] < EPSILON:
            j += 1

    return transactions


def compute_member_breakdown(group_id: int, user_id: int, db: Session):
    """
    Expense-by-expense breakdown for one member (Rohan's requirement).
    """
    expenses = db.query(models.Expense).filter(
        models.Expense.group_id == group_id,
        models.Expense.is_deleted == False,
    ).all()

    rows = []
    for exp in expenses:
        # Does this expense involve this user?
        split = next((s for s in exp.splits if s.user_id == user_id), None)
        paid_by_me = exp.paid_by_user_id == user_id

        if not split and not paid_by_me:
            continue

        amount_inr = float(_to_inr(exp.amount, exp.currency, exp.usd_inr_rate_used or 1))
        my_share_inr = float(Decimal(str(split.amount_inr))) if split else 0.0
        i_paid_inr = amount_inr if paid_by_me else 0.0
        net_effect = round(i_paid_inr - my_share_inr, 2)

        rows.append({
            "expense_id": exp.id,
            "date": exp.expense_date.isoformat(),
            "description": exp.description,
            "currency": exp.currency,
            "original_amount": exp.amount,
            "amount_inr": round(amount_inr, 2),
            "paid_by_user_id": exp.paid_by_user_id,
            "i_paid_inr": round(i_paid_inr, 2),
            "my_share_inr": round(my_share_inr, 2),
            "net_effect": net_effect,
            "split_type": exp.split_type,
        })

    net = round(sum(r["net_effect"] for r in rows), 2)
    return {"user_id": user_id, "net": net, "breakdown": rows}


def calculate_splits(
    amount: float,
    currency: str,
    split_type: str,
    split_details: dict,  # {user_id: share/pct/amount}
    usd_inr_rate: float,
) -> dict:
    """
    Returns {user_id: {"amount_inr": float, "original_amount": float, ...}}
    Used by both manual expense creation and CSV importer.
    """
    from decimal import Decimal, ROUND_HALF_UP

    rate = Decimal(str(usd_inr_rate))
    total_inr = _to_inr(amount, currency, rate)
    total_orig = Decimal(str(amount))
    n = len(split_details)
    result = {}

    if n == 0:
        raise ValueError("At least one split participant is required")

    if split_type == "equal":
        per_person_inr = total_inr / n
        per_person_orig = total_orig / n
        for uid in split_details:
            result[uid] = {
                "amount_inr": float(per_person_inr.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                "original_amount": float(per_person_orig.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            }

    elif split_type == "unequal":
        if any(Decimal(str(amt)) < 0 for amt in split_details.values()):
            raise ValueError("Unequal split amounts must be non-negative")
        for uid, amt in split_details.items():
            orig = Decimal(str(amt))
            inr = _to_inr(float(orig), currency, rate)
            result[uid] = {
                "amount_inr": float(inr.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                "original_amount": float(orig),
            }

    elif split_type == "percentage":
        total_pct = sum(Decimal(str(v)) for v in split_details.values())
        if total_pct <= 0:
            raise ValueError("Percentage split total must be positive")
        for uid, pct in split_details.items():
            if Decimal(str(pct)) < 0:
                raise ValueError("Percentage values must be non-negative")
            fraction = Decimal(str(pct)) / total_pct  # normalize even if != 100
            inr = total_inr * fraction
            orig = total_orig * fraction
            result[uid] = {
                "amount_inr": float(inr.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                "original_amount": float(orig.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                "percentage": float(Decimal(str(pct))),
            }

    elif split_type == "share":
        total_shares = sum(Decimal(str(v)) for v in split_details.values())
        if total_shares <= 0:
            raise ValueError("Share split total must be positive")
        for uid, shares in split_details.items():
            if Decimal(str(shares)) < 0:
                raise ValueError("Share values must be non-negative")
            fraction = Decimal(str(shares)) / total_shares
            inr = total_inr * fraction
            orig = total_orig * fraction
            result[uid] = {
                "amount_inr": float(inr.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                "original_amount": float(orig.quantize(Decimal("0.01"), ROUND_HALF_UP)),
                "share_count": float(Decimal(str(shares))),
            }

    else:
        raise ValueError(f"Unsupported split type: {split_type}")

    return result
