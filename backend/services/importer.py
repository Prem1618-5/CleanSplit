"""
CSV Importer — Anomaly Detection + Staging Engine

Anomaly catalogue covered by expenses_export.csv:
  1  DUPLICATE_EXACT         Marina Bites rows 5-6 (same date/desc/amount/payer)
  2  DUPLICATE_SIMILAR       Thalassa dinner rows 25-26 (same date, ~desc, diff amount, diff payer)
  3  AMOUNT_COMMA            Row 7 "1,200" — comma in number
  4  AMOUNT_WHITESPACE       Row 29 " 1450 " — leading/trailing space
  5  AMOUNT_ZERO             Row 31 Swiggy ₹0
  6  AMOUNT_NEGATIVE         Row 24 parasailing refund -30 USD
  7  DATE_FORMAT_EU          Rows 14-29 use DD/MM/YYYY (vs YYYY-MM-DD in rows 1-13)
  8  DATE_NO_YEAR            Row 27 "Mar 14" — month name, no year
  9  DATE_AMBIGUOUS          Row 34 "04/05/2026" — April 5 or May 4?
 10  MISSING_CURRENCY        Row 28 — empty currency field
 11  MISSING_PAID_BY         Row 13 — empty paid_by
 12  NAME_VARIANT_CASE       Rows 9,27 "priya"/"rohan " — wrong case / trailing space
 13  NAME_VARIANT_SUFFIX     Row 11 "Priya S" — surname initial, fuzzy matches Priya
 14  NON_MEMBER              Row 22 "Dev's friend Kabir" in split_with
 15  DEPARTED_MEMBER         Row 36 Meera in April-2 groceries (Meera left end of March)
 16  SETTLEMENT              Row 14 "Rohan paid Aisha back" + Row 38 "Sam deposit share"
 17  PERCENTAGE_SUM          Rows 15,32 — percentages sum to 110%, not 100%
 18  SPLIT_TYPE_CONFLICT     Row 42 — split_type=equal but split_details has 1:1:1:1 shares

Policy per anomaly:
  SEVERITY info    → auto-fix silently, log for report
  SEVERITY warning → auto-fix with user notification; user may reject fix → row skipped
  SEVERITY error   → row staged as NEEDS_REVIEW; user must approve or reject before commit

Resolution options per row:  "approve" | "reject" | (override values in parsed_data)
"""

import json
import re
from datetime import date, datetime
from dateutil import parser as dateutil_parser
from typing import Optional
import pandas as pd

# ── canonical name mapping ────────────────────────────────────────────────────
CANONICAL = {
    "aisha": "Aisha",
    "rohan": "Rohan",
    "priya": "Priya",
    "meera": "Meera",
    "dev": "Dev",
    "sam": "Sam",
    "priya s": "Priya",       # name variant — needs confirmation
    "priya s.": "Priya",
}

KNOWN_MEMBERS = {"Aisha", "Rohan", "Priya", "Meera", "Dev", "Sam"}

SETTLEMENT_KEYWORDS = {"paid back", "deposit", "settlement", "repay", "reimburse", "returned"}

# ── date parsing ──────────────────────────────────────────────────────────────

def _parse_date(raw: str, row_num: int, inferred_year: int = 2026):
    """
    Returns (date_obj, anomalies_list).
    Tries formats in priority order; flags ambiguous cases.
    """
    anomalies = []
    raw = raw.strip()

    if not raw:
        anomalies.append({
            "type": "MISSING_DATE",
            "severity": "error",
            "raw": raw,
            "message": "Date is empty.",
            "default_action": "reject",
        })
        return None, anomalies

    # Try ISO first
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
        return d, anomalies
    except ValueError:
        pass

    # "Mar 14" — month name, no year
    match = re.match(r"^([A-Za-z]{3})\s+(\d{1,2})$", raw)
    if match:
        try:
            d = datetime.strptime(f"{match.group(1)} {match.group(2)} {inferred_year}", "%b %d %Y").date()
            anomalies.append({
                "type": "DATE_NO_YEAR",
                "severity": "warning",
                "raw": raw,
                "message": f"No year in date. Inferred {inferred_year}-{d.month:02d}-{d.day:02d} from context.",
                "default_action": "auto_fix",
                "resolved_value": d.isoformat(),
            })
            return d, anomalies
        except ValueError:
            pass

    # DD/MM/YYYY
    try:
        d = datetime.strptime(raw, "%d/%m/%Y").date()
        # Check for ambiguity: if day <= 12, could also be MM/DD/YYYY
        parts = raw.split("/")
        day_val, mon_val = int(parts[0]), int(parts[1])
        if day_val <= 12 and day_val != mon_val:
            alt_d = datetime.strptime(f"{parts[1]}/{parts[0]}/{parts[2]}", "%d/%m/%Y").date()
            anomalies.append({
                "type": "DATE_AMBIGUOUS",
                "severity": "warning",
                "raw": raw,
                "message": (
                    f"Ambiguous date: could be {d.isoformat()} (DD/MM) or "
                    f"{alt_d.isoformat()} (MM/DD). Defaulting to DD/MM (European format "
                    f"matches rest of this section)."
                ),
                "default_action": "auto_fix",
                "resolved_value": d.isoformat(),
                "alternative_value": alt_d.isoformat(),
            })
        else:
            anomalies.append({
                "type": "DATE_FORMAT_EU",
                "severity": "info",
                "raw": raw,
                "message": f"DD/MM/YYYY format normalised to {d.isoformat()}.",
                "default_action": "auto_fix",
                "resolved_value": d.isoformat(),
            })
        return d, anomalies
    except ValueError:
        pass

    # Fallback: dateutil
    try:
        d = dateutil_parser.parse(raw, dayfirst=True, yearfirst=False).date()
        anomalies.append({
            "type": "DATE_FORMAT_EU",
            "severity": "warning",
            "raw": raw,
            "message": f"Non-standard date format. Parsed as {d.isoformat()}.",
            "default_action": "auto_fix",
            "resolved_value": d.isoformat(),
        })
        return d, anomalies
    except Exception:
        pass

    anomalies.append({
        "type": "DATE_UNPARSEABLE",
        "severity": "error",
        "raw": raw,
        "message": f"Cannot parse date: {raw!r}",
        "default_action": "reject",
    })
    return None, anomalies


# ── amount parsing ────────────────────────────────────────────────────────────

def _parse_amount(raw: str):
    """Returns (float|None, anomalies)."""
    anomalies = []
    original = raw

    raw = raw.strip()
    if raw != original:
        anomalies.append({
            "type": "AMOUNT_WHITESPACE",
            "severity": "info",
            "raw": original,
            "message": f"Leading/trailing whitespace stripped from amount.",
            "default_action": "auto_fix",
            "resolved_value": raw,
        })

    if "," in raw:
        raw_no_comma = raw.replace(",", "")
        anomalies.append({
            "type": "AMOUNT_COMMA",
            "severity": "info",
            "raw": raw,
            "message": f"Comma in amount removed: {raw!r} → {raw_no_comma!r}",
            "default_action": "auto_fix",
            "resolved_value": raw_no_comma,
        })
        raw = raw_no_comma

    try:
        val = float(raw)
    except ValueError:
        anomalies.append({
            "type": "AMOUNT_INVALID",
            "severity": "error",
            "raw": raw,
            "message": f"Cannot parse amount: {raw!r}",
            "default_action": "reject",
        })
        return None, anomalies

    if val == 0:
        anomalies.append({
            "type": "AMOUNT_ZERO",
            "severity": "warning",
            "raw": raw,
            "message": "Amount is zero. Row will be skipped unless user approves inclusion.",
            "default_action": "reject",
        })

    if val < 0:
        anomalies.append({
            "type": "AMOUNT_NEGATIVE",
            "severity": "warning",
            "raw": raw,
            "message": (
                f"Negative amount ({val}). Treated as refund: the split is reversed — "
                f"each participant effectively receives their share back."
            ),
            "default_action": "auto_fix",
            "resolved_value": str(val),
        })

    return val, anomalies


# ── name normalisation ────────────────────────────────────────────────────────

def _normalize_name(raw: str):
    """Returns (canonical_name|None, anomaly|None, is_non_member)."""
    original = raw
    stripped = raw.strip()
    key = stripped.lower()

    if key in CANONICAL:
        canonical = CANONICAL[key]
        anomaly = None
        if original != canonical:
            known_member_keys = {name.lower() for name in KNOWN_MEMBERS}
            anomaly = {
                "type": "NAME_VARIANT_CASE" if key in known_member_keys else "NAME_VARIANT_SUFFIX",
                "severity": "info" if key in known_member_keys else "warning",
                "raw": original,
                "message": f"Name normalised: {original!r} → {canonical!r}",
                "default_action": "auto_fix",
                "resolved_value": canonical,
            }
        return canonical, anomaly, canonical not in KNOWN_MEMBERS

    # Non-member check (e.g. "Dev's friend Kabir")
    return stripped, {
        "type": "NON_MEMBER",
        "severity": "warning",
        "raw": stripped,
        "message": (
            f"{stripped!r} is not a recognised group member. Their share will be "
            f"redistributed equally among the remaining participants."
        ),
        "default_action": "auto_fix",
        "resolved_value": None,
    }, True


def _parse_names_list(raw: str):
    """
    Parse semicolon-separated name list.
    Returns (canonical_names, removed_non_members, anomalies).
    """
    anomalies = []
    canonical_names = []
    removed = []

    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        canon, anom, is_non_member = _normalize_name(part)
        if anom:
            anomalies.append(anom)
        if is_non_member:
            removed.append(part)
        else:
            canonical_names.append(canon)

    return canonical_names, removed, anomalies


# ── split_details parsing ─────────────────────────────────────────────────────

def _parse_split_details(raw: str, split_type: str, names: list):
    """
    Parse split_details field.
    Returns (details_dict {name: value}, anomalies).
    For equal splits, returns {} (computed later from name list).
    """
    anomalies = []
    if split_type == "equal" or not raw or not raw.strip():
        return {}, anomalies

    details = {}
    # Format: "Name val; Name val" or "Name val%, ..."
    # Handles: "Rohan 700; Priya 400" or "Aisha 30%; Rohan 30%"
    for part in re.split(r"[;,]", raw):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^(.+?)\s+([\d.]+)\s*%?$", part)
        if match:
            name_raw = match.group(1).strip()
            val = float(match.group(2))
            canon, anom, is_non_member = _normalize_name(name_raw)
            if anom:
                anomalies.append(anom)
            if not is_non_member:
                details[canon] = val
        else:
            anomalies.append({
                "type": "SPLIT_DETAIL_UNPARSEABLE",
                "severity": "warning",
                "raw": part,
                "message": f"Cannot parse split detail: {part!r}. Skipped.",
                "default_action": "auto_fix",
            })

    if split_type == "percentage":
        total = sum(details.values())
        if abs(total - 100) > 0.5:
            anomalies.append({
                "type": "PERCENTAGE_SUM",
                "severity": "warning",
                "raw": raw,
                "message": (
                    f"Percentages sum to {total:.1f}%, not 100%. "
                    f"Auto-normalising: each percentage divided by {total:.1f}."
                ),
                "default_action": "auto_fix",
                "resolved_value": {k: round(v / total * 100, 4) for k, v in details.items()},
            })

    return details, anomalies


# ── settlement detection ──────────────────────────────────────────────────────

def _is_settlement(row: dict) -> bool:
    desc_lower = row.get("description", "").lower()
    notes_lower = row.get("notes", "").lower()
    split_type = row.get("split_type", "").strip()

    keyword_match = any(kw in desc_lower or kw in notes_lower for kw in SETTLEMENT_KEYWORDS)
    no_split_type = not split_type

    # Row 14: "Rohan paid Aisha back" — no split_type, settlement keyword
    # Row 38: "Sam deposit share" — split_type=equal but desc is deposit
    return keyword_match or no_split_type


# ── duplicate detection ───────────────────────────────────────────────────────

STOP_WORDS = {"at", "the", "a", "an", "for", "and", "in", "on", "of", "-"}


def _desc_words(s: str) -> set:
    """Tokenise description into significant lowercase words."""
    words = re.findall(r"[a-z0-9]+", s.lower())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def _desc_similarity(a: str, b: str) -> float:
    """Jaccard similarity on word sets. 1.0 = identical, 0.0 = no overlap."""
    wa, wb = _desc_words(a), _desc_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _find_duplicates(rows: list):
    """
    Returns set of (row_idx_a, row_idx_b, dup_type) tuples.
    dup_type: "exact" | "similar"

    Exact:   same date, same payer, same amount (±1), description similarity ≥ 0.6
    Similar: same date, close amount (±5%), description similarity ≥ 0.5, different payer
    """
    duplicates = set()

    def _norm_name(s):
        return s.strip().lower()

    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            if a.get("_date") != b.get("_date"):
                continue
            a_amt = a.get("_amount") or 0
            b_amt = b.get("_amount") or 0
            sim = _desc_similarity(a.get("description", ""), b.get("description", ""))
            same_payer = _norm_name(a.get("paid_by", "")) == _norm_name(b.get("paid_by", ""))
            same_amount = abs(a_amt - b_amt) < 1
            close_amount = a_amt > 0 and b_amt > 0 and abs(a_amt - b_amt) / max(a_amt, b_amt) < 0.05

            if sim >= 0.6 and same_payer and same_amount:
                duplicates.add((i, j, "exact"))
            elif sim >= 0.5 and not same_payer and close_amount:
                duplicates.add((i, j, "similar"))

    return duplicates


# ── departed member check ─────────────────────────────────────────────────────

MEMBER_DATES = {
    # From the CSV narrative:
    "Meera": {"joined": date(2026, 2, 1), "left": date(2026, 3, 31)},
    "Sam": {"joined": date(2026, 4, 8), "left": None},
    "Dev": {"joined": None, "left": None},  # guest / external
}


def _check_departed_members(expense_date: date, split_names: list):
    """
    Returns anomalies for members whose tenure doesn't cover the expense date.
    """
    anomalies = []
    if expense_date is None:
        return anomalies

    for name, tenure in MEMBER_DATES.items():
        if name not in split_names:
            continue
        if tenure["left"] and expense_date > tenure["left"]:
            anomalies.append({
                "type": "DEPARTED_MEMBER",
                "severity": "warning",
                "raw": name,
                "message": (
                    f"{name} left on {tenure['left'].isoformat()} but is listed in a "
                    f"{expense_date.isoformat()} expense. Auto-removed from split."
                ),
                "default_action": "auto_fix",
                "resolved_value": "removed",
            })
        if tenure["joined"] and expense_date < tenure["joined"]:
            anomalies.append({
                "type": "NOT_YET_MEMBER",
                "severity": "warning",
                "raw": name,
                "message": (
                    f"{name} joined on {tenure['joined'].isoformat()} but is listed in a "
                    f"{expense_date.isoformat()} expense. Auto-removed from split."
                ),
                "default_action": "auto_fix",
                "resolved_value": "removed",
            })
    return anomalies


# ── main parse function ───────────────────────────────────────────────────────

def parse_csv(file_bytes: bytes, usd_inr_rate: float = 85.0):
    """
    Parse raw CSV bytes.
    Returns list of staging row dicts.
    Each dict has: raw_data, parsed_data, status, anomalies.
    """
    import io
    df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]

    staging = []

    # Pre-pass: collect parsed dates + amounts for duplicate detection
    pre = []
    for idx, row in df.iterrows():
        raw_date = str(row.get("date", "")).strip()
        raw_amount = str(row.get("amount", "")).strip()
        d, _ = _parse_date(raw_date, idx)
        a, _ = _parse_amount(raw_amount)
        pre.append({
            "_date": d,
            "_amount": a,
            "description": str(row.get("description", "")),
            "paid_by": str(row.get("paid_by", "")),
        })

    dup_pairs = _find_duplicates(pre)
    dup_flagged = {}  # idx -> list of (partner_idx, dup_type)
    for i, j, dt in dup_pairs:
        dup_flagged.setdefault(i, []).append((j, dt))
        dup_flagged.setdefault(j, []).append((i, dt))

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-indexed + header
        # Keep the source value intact for the anomaly log. Individual parsers
        # normalise only after they have recorded whitespace or format issues.
        raw = {k: str(v) for k, v in row.items()}
        anomalies = []

        # ── date ──────────────────────────────────────────────────────────────
        expense_date, date_anoms = _parse_date(raw.get("date", ""), row_num)
        anomalies.extend(date_anoms)

        # ── amount ────────────────────────────────────────────────────────────
        amount, amt_anoms = _parse_amount(raw.get("amount", ""))
        anomalies.extend(amt_anoms)

        # ── currency ──────────────────────────────────────────────────────────
        currency = raw.get("currency", "").strip().upper()
        if not currency:
            currency = "INR"
            anomalies.append({
                "type": "MISSING_CURRENCY",
                "severity": "warning",
                "raw": "",
                "message": "Currency missing. Defaulted to INR.",
                "default_action": "auto_fix",
                "resolved_value": "INR",
            })

        # ── paid_by ───────────────────────────────────────────────────────────
        paid_by_raw = raw.get("paid_by", "")
        paid_by = None
        if not paid_by_raw.strip():
            anomalies.append({
                "type": "MISSING_PAID_BY",
                "severity": "error",
                "raw": "",
                "message": "No payer recorded. Cannot compute balances without a payer. Row needs review.",
                "default_action": "review",
            })
        else:
            canon, name_anom, is_non_member = _normalize_name(paid_by_raw)
            paid_by = canon
            if name_anom:
                anomalies.append(name_anom)

        # ── split_with ────────────────────────────────────────────────────────
        split_with_raw = raw.get("split_with", "")
        split_names, removed_non_members, sw_anoms = _parse_names_list(split_with_raw)
        anomalies.extend(sw_anoms)

        # ── departed/future members ───────────────────────────────────────────
        if expense_date:
            dep_anoms = _check_departed_members(expense_date, split_names)
            anomalies.extend(dep_anoms)
            # remove departed from split_names
            departed_names = {a["raw"] for a in dep_anoms}
            split_names = [n for n in split_names if n not in departed_names]

        # ── split_type ────────────────────────────────────────────────────────
        split_type = raw.get("split_type", "").strip().lower()

        # ── split_details ─────────────────────────────────────────────────────
        details_raw = raw.get("split_details", "").strip()
        split_details, sd_anoms = _parse_split_details(details_raw, split_type, split_names)
        anomalies.extend(sd_anoms)

        # split_type=equal but has share details that are all 1 → conflict but harmless
        if split_type == "equal" and details_raw:
            anomalies.append({
                "type": "SPLIT_TYPE_CONFLICT",
                "severity": "info",
                "raw": details_raw,
                "message": (
                    "split_type is 'equal' but split_details contains share values (all 1:1:1:1). "
                    "This is effectively equal. Treating as equal split."
                ),
                "default_action": "auto_fix",
                "resolved_value": "equal",
            })

        # ── settlement detection ──────────────────────────────────────────────
        is_settlement = _is_settlement(raw)
        if is_settlement:
            anomalies.append({
                "type": "SETTLEMENT",
                "severity": "error",
                "raw": raw.get("description", ""),
                "message": (
                    f"Row looks like a settlement/payment, not a shared expense. "
                    f"(Keywords: {', '.join(SETTLEMENT_KEYWORDS & set(raw.get('description','').lower().split() + raw.get('notes','').lower().split()))} "
                    f"| split_type: {raw.get('split_type','empty')}). "
                    f"Recommend importing as a settlement record instead."
                ),
                "default_action": "review",
            })

        # ── duplicates ────────────────────────────────────────────────────────
        if idx in dup_flagged:
            for partner_idx, dup_type in dup_flagged[idx]:
                partner_row = partner_idx + 2
                if dup_type == "exact":
                    msg = (
                        f"Exact duplicate of row {partner_row} (same date, description, amount, payer). "
                        f"Recommend keeping earlier row and rejecting this one."
                    )
                    default = "reject" if idx > partner_idx else "approve"
                else:
                    msg = (
                        f"Similar to row {partner_row}: same date and description but different "
                        f"payer or amount. Both rows need user review — keep one, reject the other."
                    )
                    default = "review"
                anomalies.append({
                    "type": f"DUPLICATE_{dup_type.upper()}",
                    "severity": "error",
                    "raw": raw.get("description", ""),
                    "message": msg,
                    "partner_row": partner_row,
                    "default_action": default,
                })

        # ── determine row status ──────────────────────────────────────────────
        has_error = any(
            a["severity"] == "error" or a.get("default_action") == "review"
            for a in anomalies
        )
        has_reject = any(a.get("default_action") == "reject" for a in anomalies)

        if has_reject:
            status = "rejected"
        elif has_error:
            status = "needs_review"
        elif anomalies:
            status = "auto_fixed"
        else:
            status = "clean"

        parsed = {
            "date": expense_date.isoformat() if expense_date else None,
            "description": raw.get("description", "").strip(),
            "paid_by": paid_by,
            "amount": amount,
            "currency": currency,
            "split_type": split_type or "equal",
            "split_names": split_names,
            "split_details": split_details,
            "notes": raw.get("notes", "").strip(),
            "is_settlement": is_settlement,
            "usd_inr_rate": usd_inr_rate,
        }

        staging.append({
            "row_number": row_num,
            "raw_data": json.dumps(raw),
            "parsed_data": json.dumps(parsed),
            "status": status,
            "anomalies": json.dumps(anomalies),
        })

    return staging


def generate_report(session_rows: list) -> dict:
    """Aggregate anomaly counts for the import report."""
    total = len(session_rows)
    clean = sum(1 for r in session_rows if r["status"] == "clean")
    auto_fixed = sum(1 for r in session_rows if r["status"] == "auto_fixed")
    needs_review = sum(1 for r in session_rows if r["status"] == "needs_review")
    rejected = sum(1 for r in session_rows if r["status"] == "rejected")
    approved = sum(1 for r in session_rows if r["status"] == "approved")

    all_anomaly_types = {}
    for r in session_rows:
        for a in json.loads(r.get("anomalies") or "[]"):
            t = a["type"]
            all_anomaly_types[t] = all_anomaly_types.get(t, 0) + 1

    return {
        "total_rows": total,
        "clean": clean,
        "auto_fixed": auto_fixed,
        "needs_review": needs_review,
        "rejected": rejected,
        "approved": approved,
        "anomaly_counts": all_anomaly_types,
    }


def render_import_report_markdown(
    session_rows: list,
    filename: str = "expenses_export.csv",
    session_status: str = "staged",
    usd_inr_rate: float = 85.0,
) -> str:
    """Render a human-readable report from the same staged rows used by the API."""

    def load_json(value, fallback):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback
        return value if value is not None else fallback

    def cell(value) -> str:
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")

    ordered_rows = sorted(session_rows, key=lambda row: row.get("row_number", 0))
    summary_rows = [
        {"status": row.get("status", ""), "anomalies": row.get("anomalies", "[]")}
        for row in ordered_rows
    ]
    summary = generate_report(summary_rows)

    lines = [
        "# Import Report",
        "",
        "> Generated by CleanSplit using `backend/services/importer.py` against the CSV without manual edits.",
        "",
        f"- Source file: `{filename}`",
        f"- Session status: `{session_status}`",
        f"- USD to INR rate: `{usd_inr_rate}`",
        f"- CSV rows processed: **{summary['total_rows']}**",
        f"- Clean: **{summary['clean']}**",
        f"- Auto-fixed: **{summary['auto_fixed']}**",
        f"- Needs review: **{summary['needs_review']}**",
        f"- Rejected: **{summary['rejected']}**",
        f"- Approved: **{summary['approved']}**",
        "",
        "## Anomaly Summary",
        "",
        "| Anomaly | Occurrences |",
        "|---|---:|",
    ]

    for anomaly_type, count in sorted(summary["anomaly_counts"].items()):
        lines.append(f"| `{cell(anomaly_type)}` | {count} |")

    lines.extend([
        "",
        "## Row-Level Actions",
        "",
        "Each entry records what the importer detected and the row outcome at report generation time.",
        "",
        "| CSV row | Description | Anomaly | Severity | Detected problem | Importer policy | Current outcome |",
        "|---:|---|---|---|---|---|---|",
    ])

    for row in ordered_rows:
        anomalies = load_json(row.get("anomalies"), [])
        if not anomalies:
            continue
        raw_data = load_json(row.get("raw_data"), {})
        description = raw_data.get("description", "")
        status = row.get("status", "")

        for anomaly in anomalies:
            default_action = anomaly.get("default_action", "review")
            if status == "rejected":
                outcome = "Row rejected"
            elif status == "approved":
                outcome = "Reviewer approved row"
            elif status == "needs_review":
                outcome = "Awaiting reviewer decision"
            elif status == "auto_fixed":
                outcome = "Automatic correction staged"
            else:
                outcome = "No row-level change"

            policy = default_action.replace("_", " ")
            resolved = anomaly.get("resolved_value")
            if resolved is not None:
                policy += f"; resolved value: {cell(resolved)}"

            lines.append(
                "| {row_number} | {description} | `{anomaly_type}` | {severity} | {message} | {policy} | {outcome} |".format(
                    row_number=row.get("row_number", ""),
                    description=cell(description),
                    anomaly_type=cell(anomaly.get("type", "UNKNOWN")),
                    severity=cell(anomaly.get("severity", "")),
                    message=cell(anomaly.get("message", "")),
                    policy=cell(policy),
                    outcome=cell(outcome),
                )
            )

    lines.extend([
        "",
        "## Interpretation",
        "",
        "`needs_review` means the app deliberately stopped before writing that row to the expense tables. "
        "A reviewer must approve or reject it. `auto_fixed` means the original value and correction are both "
        "stored in the import session. `rejected` rows are skipped during commit.",
        "",
    ])
    return "\n".join(lines)
