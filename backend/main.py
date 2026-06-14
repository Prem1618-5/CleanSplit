from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime
from typing import Optional, List
import json
import os

import models
import auth as auth_utils
from database import engine, get_db
from services.balance import compute_group_balances, compute_member_breakdown, calculate_splits
from services.importer import parse_csv, generate_report, render_import_report_markdown

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="CleanSplit Expenses", version="1.0.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════

@app.post("/api/auth/register", status_code=201)
def register(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(400, "Email already registered")
    user = models.User(
        name=name,
        email=email,
        password_hash=auth_utils.hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth_utils.create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


@app.post("/api/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not auth_utils.verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = auth_utils.create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


@app.get("/api/auth/me")
def me(current_user: models.User = Depends(auth_utils.get_current_user)):
    return _user_out(current_user)


def _user_out(u: models.User):
    return {"id": u.id, "name": u.name, "email": u.email}


# ══════════════════════════════════════════════════════════════
# GROUPS
# ══════════════════════════════════════════════════════════════

@app.get("/api/groups")
def list_groups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    memberships = db.query(models.GroupMember).filter(
        models.GroupMember.user_id == current_user.id
    ).all()
    group_ids = {m.group_id for m in memberships}
    groups = db.query(models.Group).filter(models.Group.id.in_(group_ids)).all()
    return [_group_out(g, db) for g in groups]


@app.post("/api/groups", status_code=201)
def create_group(
    name: str = Form(...),
    usd_inr_rate: float = Form(85.0),
    joined_at: str = Form("2026-02-01"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    group = models.Group(name=name, created_by=current_user.id, usd_inr_rate=usd_inr_rate)
    db.add(group)
    db.flush()
    member = models.GroupMember(
        group_id=group.id,
        user_id=current_user.id,
        joined_at=date.fromisoformat(joined_at),
    )
    db.add(member)
    db.commit()
    db.refresh(group)
    return _group_out(group, db)


@app.get("/api/groups/{group_id}")
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    group = _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    return _group_out(group, db)


@app.patch("/api/groups/{group_id}")
def update_group(
    group_id: int,
    name: Optional[str] = Form(None),
    usd_inr_rate: Optional[float] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    group = _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    if name:
        group.name = name
    if usd_inr_rate is not None:
        group.usd_inr_rate = usd_inr_rate
    db.commit()
    return _group_out(group, db)


def _group_out(g: models.Group, db: Session):
    members = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == g.id
    ).all()
    return {
        "id": g.id,
        "name": g.name,
        "usd_inr_rate": g.usd_inr_rate,
        "created_at": g.created_at.isoformat(),
        "members": [_member_out(m) for m in members],
    }


# ══════════════════════════════════════════════════════════════
# MEMBERS
# ══════════════════════════════════════════════════════════════

@app.post("/api/groups/{group_id}/members", status_code=201)
def add_member(
    group_id: int,
    user_email: str = Form(...),
    joined_at: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    user = db.query(models.User).filter(models.User.email == user_email).first()
    if not user:
        raise HTTPException(404, "User not found")
    existing = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == user.id,
    ).first()
    if existing:
        raise HTTPException(400, "Already a member")
    member = models.GroupMember(
        group_id=group_id,
        user_id=user.id,
        joined_at=date.fromisoformat(joined_at),
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return _member_out(member)


@app.patch("/api/groups/{group_id}/members/{user_id}")
def update_member(
    group_id: int,
    user_id: int,
    left_at: Optional[str] = Form(None),
    joined_at: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_member(group_id, current_user.id, db)
    member = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(404, "Member not found")
    if left_at is not None:
        member.left_at = date.fromisoformat(left_at) if left_at else None
    if joined_at is not None:
        member.joined_at = date.fromisoformat(joined_at)
    db.commit()
    return _member_out(member)


def _member_out(m: models.GroupMember):
    return {
        "id": m.id,
        "user_id": m.user_id,
        "name": m.user.name,
        "email": m.user.email,
        "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        "left_at": m.left_at.isoformat() if m.left_at else None,
        "active": m.left_at is None or m.left_at >= date.today(),
    }


# ══════════════════════════════════════════════════════════════
# EXPENSES
# ══════════════════════════════════════════════════════════════

@app.get("/api/groups/{group_id}/expenses")
def list_expenses(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    expenses = (
        db.query(models.Expense)
        .filter(
            models.Expense.group_id == group_id,
            models.Expense.is_deleted == False,
        )
        .order_by(models.Expense.expense_date.desc())
        .all()
    )
    return [_expense_out(e) for e in expenses]


@app.post("/api/groups/{group_id}/expenses", status_code=201)
def create_expense(
    group_id: int,
    description: str = Form(...),
    amount: float = Form(...),
    currency: str = Form("INR"),
    paid_by_user_id: int = Form(...),
    split_type: str = Form(...),
    expense_date: str = Form(...),
    split_members: str = Form(...),       # JSON: {"user_id": value}
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    group = _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)

    exp_date = date.fromisoformat(expense_date)
    try:
        split_details = json.loads(split_members)  # {str(user_id): float}
        split_details_int = {int(k): v for k, v in split_details.items()}
    except (TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(400, "split_members must be a JSON object keyed by user id")

    _require_member_on_date(group_id, paid_by_user_id, exp_date, db)
    for uid in split_details_int:
        _require_member_on_date(group_id, uid, exp_date, db)

    try:
        splits_calc = calculate_splits(
            amount=amount,
            currency=currency,
            split_type=split_type,
            split_details=split_details_int,
            usd_inr_rate=group.usd_inr_rate,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    exp = models.Expense(
        group_id=group_id,
        description=description,
        amount=amount,
        currency=currency.upper(),
        paid_by_user_id=paid_by_user_id,
        split_type=split_type,
        expense_date=exp_date,
        notes=notes,
        usd_inr_rate_used=group.usd_inr_rate,
    )
    db.add(exp)
    db.flush()

    for uid, vals in splits_calc.items():
        split = models.ExpenseSplit(
            expense_id=exp.id,
            user_id=uid,
            amount_inr=vals["amount_inr"],
            original_amount=vals.get("original_amount"),
            share_count=vals.get("share_count"),
            percentage=vals.get("percentage"),
        )
        db.add(split)

    db.commit()
    db.refresh(exp)
    return _expense_out(exp)


@app.get("/api/expenses/{expense_id}")
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    exp = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not exp:
        raise HTTPException(404, "Expense not found")
    _require_member(exp.group_id, current_user.id, db)
    return _expense_out(exp)


@app.delete("/api/expenses/{expense_id}")
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    exp = db.query(models.Expense).filter(models.Expense.id == expense_id).first()
    if not exp:
        raise HTTPException(404, "Expense not found")
    _require_member(exp.group_id, current_user.id, db)
    exp.is_deleted = True
    db.commit()
    return {"ok": True}


def _expense_out(e: models.Expense):
    return {
        "id": e.id,
        "group_id": e.group_id,
        "description": e.description,
        "amount": e.amount,
        "currency": e.currency,
        "paid_by_user_id": e.paid_by_user_id,
        "paid_by_name": e.paid_by.name if e.paid_by else None,
        "split_type": e.split_type,
        "expense_date": e.expense_date.isoformat() if e.expense_date else None,
        "notes": e.notes,
        "usd_inr_rate_used": e.usd_inr_rate_used,
        "splits": [
            {
                "user_id": s.user_id,
                "name": s.user.name,
                "amount_inr": s.amount_inr,
                "original_amount": s.original_amount,
                "share_count": s.share_count,
                "percentage": s.percentage,
            }
            for s in e.splits
        ],
        "import_session_id": e.import_session_id,
    }


# ══════════════════════════════════════════════════════════════
# BALANCES
# ══════════════════════════════════════════════════════════════

@app.get("/api/groups/{group_id}/balances")
def group_balances(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    return compute_group_balances(group_id, db)


@app.get("/api/groups/{group_id}/balances/{user_id}")
def member_balance_breakdown(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    return compute_member_breakdown(group_id, user_id, db)


# ══════════════════════════════════════════════════════════════
# SETTLEMENTS
# ══════════════════════════════════════════════════════════════

@app.get("/api/groups/{group_id}/settlements")
def list_settlements(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    settlements = (
        db.query(models.Settlement)
        .filter(models.Settlement.group_id == group_id)
        .order_by(models.Settlement.settlement_date.desc())
        .all()
    )
    return [_settlement_out(s) for s in settlements]


@app.post("/api/groups/{group_id}/settlements", status_code=201)
def create_settlement(
    group_id: int,
    payer_id: int = Form(...),
    receiver_id: int = Form(...),
    amount: float = Form(...),
    currency: str = Form("INR"),
    settlement_date: str = Form(...),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)
    if payer_id == receiver_id:
        raise HTTPException(400, "Payer and receiver must be different")
    stl_date = date.fromisoformat(settlement_date)
    _require_member_on_date(group_id, payer_id, stl_date, db)
    _require_member_on_date(group_id, receiver_id, stl_date, db)
    s = models.Settlement(
        group_id=group_id,
        payer_id=payer_id,
        receiver_id=receiver_id,
        amount=amount,
        currency=currency.upper(),
        settlement_date=stl_date,
        notes=notes,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _settlement_out(s)


def _settlement_out(s: models.Settlement):
    return {
        "id": s.id,
        "group_id": s.group_id,
        "payer_id": s.payer_id,
        "payer_name": s.payer.name,
        "receiver_id": s.receiver_id,
        "receiver_name": s.receiver.name,
        "amount": s.amount,
        "currency": s.currency,
        "settlement_date": s.settlement_date.isoformat(),
        "notes": s.notes,
    }


# ══════════════════════════════════════════════════════════════
# CSV IMPORT
# ══════════════════════════════════════════════════════════════

@app.post("/api/import/upload", status_code=201)
def upload_csv(
    group_id: int = Form(...),
    usd_inr_rate: float = Form(85.0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    _require_group(group_id, db)
    _require_member(group_id, current_user.id, db)

    file_bytes = file.file.read()
    staging_rows = parse_csv(file_bytes, usd_inr_rate=usd_inr_rate)

    session = models.ImportSession(
        group_id=group_id,
        filename=file.filename,
        status="pending",
        usd_inr_rate=usd_inr_rate,
        created_by=current_user.id,
    )
    db.add(session)
    db.flush()

    for sr in staging_rows:
        row = models.ImportRow(
            session_id=session.id,
            row_number=sr["row_number"],
            raw_data=sr["raw_data"],
            parsed_data=sr["parsed_data"],
            status=sr["status"],
            anomalies=sr["anomalies"],
        )
        db.add(row)

    db.commit()
    db.refresh(session)
    rows = db.query(models.ImportRow).filter(
        models.ImportRow.session_id == session.id
    ).all()
    report = generate_report([{"status": r.status, "anomalies": r.anomalies} for r in rows])

    return {"session_id": session.id, "report": report, "rows": [_row_out(r) for r in rows]}


@app.get("/api/import/{session_id}/rows")
def get_import_rows(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    session = _require_import_session(session_id, db)
    _require_member(session.group_id, current_user.id, db)
    rows = (
        db.query(models.ImportRow)
        .filter(models.ImportRow.session_id == session_id)
        .order_by(models.ImportRow.row_number)
        .all()
    )
    report = generate_report([{"status": r.status, "anomalies": r.anomalies} for r in rows])
    return {"session_id": session_id, "status": session.status, "report": report, "rows": [_row_out(r) for r in rows]}


@app.get("/api/import/{session_id}/report.md")
def download_import_report(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    session = _require_import_session(session_id, db)
    _require_member(session.group_id, current_user.id, db)
    rows = (
        db.query(models.ImportRow)
        .filter(models.ImportRow.session_id == session_id)
        .order_by(models.ImportRow.row_number)
        .all()
    )
    report = render_import_report_markdown(
        [
            {
                "row_number": row.row_number,
                "raw_data": row.raw_data,
                "parsed_data": row.parsed_data,
                "status": row.status,
                "anomalies": row.anomalies,
            }
            for row in rows
        ],
        filename=session.filename or "expenses_export.csv",
        session_status=session.status,
        usd_inr_rate=session.usd_inr_rate,
    )
    return Response(
        content=report,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="import-report-{session_id}.md"'},
    )


@app.patch("/api/import/{session_id}/rows/{row_id}")
def update_import_row(
    session_id: int,
    row_id: int,
    new_status: str = Form(...),       # approved | rejected
    parsed_override: Optional[str] = Form(None),  # JSON string
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    session = _require_import_session(session_id, db)
    _require_member(session.group_id, current_user.id, db)
    if session.status != "pending":
        raise HTTPException(400, "Session already committed or cancelled")
    row = db.query(models.ImportRow).filter(
        models.ImportRow.id == row_id,
        models.ImportRow.session_id == session_id,
    ).first()
    if not row:
        raise HTTPException(404, "Row not found")
    if new_status not in {"approved", "rejected"}:
        raise HTTPException(400, "new_status must be approved or rejected")
    row.status = new_status
    if parsed_override:
        try:
            json.loads(parsed_override)
        except json.JSONDecodeError:
            raise HTTPException(400, "parsed_override must be valid JSON")
        row.parsed_data = parsed_override
    db.commit()
    return _row_out(row)


@app.post("/api/import/{session_id}/commit")
def commit_import(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    session = _require_import_session(session_id, db)
    _require_member(session.group_id, current_user.id, db)
    if session.status != "pending":
        raise HTTPException(400, "Already committed or cancelled")

    rows = db.query(models.ImportRow).filter(
        models.ImportRow.session_id == session_id
    ).all()

    # Block if any rows still need review
    pending_review = [r for r in rows if r.status == "needs_review"]
    if pending_review:
        raise HTTPException(
            400,
            f"{len(pending_review)} row(s) still need review. Approve or reject before committing.",
        )

    # Build user name→id map from group members
    members = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == session.group_id
    ).all()
    name_to_id = {m.user.name: m.user_id for m in members}

    imported = 0
    settlements_created = 0
    skipped = 0

    for row in rows:
        if row.status in ("rejected",):
            skipped += 1
            continue
        if row.status not in ("approved", "auto_fixed", "clean"):
            skipped += 1
            continue

        try:
            parsed = json.loads(row.parsed_data or "{}")
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not parsed:
            skipped += 1
            continue

        expense_date_str = parsed.get("date")
        if not expense_date_str:
            skipped += 1
            continue

        expense_date = date.fromisoformat(expense_date_str)
        amount = parsed.get("amount")
        if amount is None:
            skipped += 1
            continue

        paid_by_name = parsed.get("paid_by")
        paid_by_id = name_to_id.get(paid_by_name) if paid_by_name else None

        # Handle settlement rows
        if parsed.get("is_settlement"):
            # Only import as settlement if payer is known
            # For "Rohan paid Aisha back" style: payer=Rohan, receiver=Aisha
            desc_lower = parsed.get("description", "").lower()
            # Attempt heuristic: "X paid Y back"
            import re
            m = re.match(r"(\w+)\s+paid\s+(\w+)", desc_lower)
            receiver_id = None
            if m:
                receiver_name = m.group(2).strip().capitalize()
                receiver_id = name_to_id.get(receiver_name)
            elif len(parsed.get("split_names", [])) == 1:
                receiver_id = name_to_id.get(parsed["split_names"][0])

            if receiver_id and paid_by_id and paid_by_id != receiver_id:
                s = models.Settlement(
                    group_id=session.group_id,
                    payer_id=paid_by_id,
                    receiver_id=receiver_id,
                    amount=abs(amount),
                    currency=parsed.get("currency", "INR"),
                    settlement_date=expense_date,
                    notes=parsed.get("notes"),
                )
                db.add(s)
                settlements_created += 1
                continue
            skipped += 1
            continue

        if not paid_by_id:
            skipped += 1
            continue

        # Compute splits
        split_names = parsed.get("split_names", [])
        split_details_raw = parsed.get("split_details", {})
        split_type = parsed.get("split_type", "equal")
        currency = parsed.get("currency", "INR")

        # Build user_id keyed split_details
        if split_type == "equal":
            uid_details = {name_to_id[n]: 1 for n in split_names if n in name_to_id}
        else:
            uid_details = {}
            for name, val in split_details_raw.items():
                uid = name_to_id.get(name)
                if uid:
                    uid_details[uid] = val

        if not uid_details and split_names:
            # fallback to equal among named members present in group
            uid_details = {name_to_id[n]: 1 for n in split_names if n in name_to_id}
            split_type = "equal"

        if not uid_details:
            skipped += 1
            continue

        valid_uid_details = {}
        try:
            _require_member_on_date(session.group_id, paid_by_id, expense_date, db)
            for uid, val in uid_details.items():
                _require_member_on_date(session.group_id, uid, expense_date, db)
                valid_uid_details[uid] = val
        except HTTPException:
            skipped += 1
            continue

        # Negative amount = refund; flip to positive, reversal handled by balance calc sign
        is_refund = amount < 0
        abs_amount = abs(amount)

        try:
            splits_calc = calculate_splits(
                amount=abs_amount,
                currency=currency,
                split_type=split_type if split_type else "equal",
                split_details=valid_uid_details,
                usd_inr_rate=session.usd_inr_rate,
            )
        except ValueError:
            skipped += 1
            continue

        exp = models.Expense(
            group_id=session.group_id,
            description=parsed.get("description", "Imported expense"),
            amount=-abs_amount if is_refund else abs_amount,
            currency=currency,
            paid_by_user_id=paid_by_id,
            split_type=split_type or "equal",
            expense_date=expense_date,
            notes=parsed.get("notes"),
            import_session_id=session_id,
            usd_inr_rate_used=session.usd_inr_rate,
        )
        db.add(exp)
        db.flush()

        for uid, vals in splits_calc.items():
            split_inr = -vals["amount_inr"] if is_refund else vals["amount_inr"]
            sp = models.ExpenseSplit(
                expense_id=exp.id,
                user_id=uid,
                amount_inr=split_inr,
                original_amount=(-vals.get("original_amount", 0) if is_refund
                                 else vals.get("original_amount")),
                share_count=vals.get("share_count"),
                percentage=vals.get("percentage"),
            )
            db.add(sp)

        row.expense_id = exp.id
        imported += 1

    session.status = "committed"
    db.commit()

    return {
        "ok": True,
        "imported": imported,
        "settlements_created": settlements_created,
        "skipped": skipped,
    }


@app.delete("/api/import/{session_id}")
def cancel_import(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth_utils.get_current_user),
):
    session = _require_import_session(session_id, db)
    _require_member(session.group_id, current_user.id, db)
    session.status = "cancelled"
    db.commit()
    return {"ok": True}


def _row_out(r: models.ImportRow):
    return {
        "id": r.id,
        "row_number": r.row_number,
        "raw_data": json.loads(r.raw_data or "{}"),
        "parsed_data": json.loads(r.parsed_data or "{}"),
        "status": r.status,
        "anomalies": json.loads(r.anomalies or "[]"),
        "expense_id": r.expense_id,
    }


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _require_group(group_id: int, db: Session) -> models.Group:
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(404, "Group not found")
    return group


def _require_member(group_id: int, user_id: int, db: Session):
    m = db.query(models.GroupMember).filter(
        models.GroupMember.group_id == group_id,
        models.GroupMember.user_id == user_id,
    ).first()
    if not m:
        raise HTTPException(403, "Not a member of this group")
    return m


def _require_member_on_date(group_id: int, user_id: int, on_date: date, db: Session):
    m = _require_member(group_id, user_id, db)
    if m.joined_at and on_date < m.joined_at:
        raise HTTPException(400, f"{m.user.name} joined after this date")
    if m.left_at and on_date > m.left_at:
        raise HTTPException(400, f"{m.user.name} left before this date")
    return m


def _require_import_session(session_id: int, db: Session) -> models.ImportSession:
    session = db.query(models.ImportSession).filter(
        models.ImportSession.id == session_id
    ).first()
    if not session:
        raise HTTPException(404, "Import session not found")
    return session


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
