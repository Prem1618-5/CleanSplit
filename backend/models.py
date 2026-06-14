from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    memberships = relationship("GroupMember", back_populates="user")


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    usd_inr_rate = Column(Float, default=85.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("GroupMember", back_populates="group")
    expenses = relationship("Expense", back_populates="group")
    settlements = relationship("Settlement", back_populates="group")


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id"),)
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(Date, nullable=False)
    left_at = Column(Date, nullable=True)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="memberships")


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    paid_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    split_type = Column(String, nullable=False)   # equal | unequal | percentage | share
    expense_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False)
    import_session_id = Column(Integer, ForeignKey("import_sessions.id"), nullable=True)
    usd_inr_rate_used = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="expenses")
    paid_by = relationship("User", foreign_keys=[paid_by_user_id])
    splits = relationship("ExpenseSplit", back_populates="expense", cascade="all, delete-orphan")


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount_inr = Column(Float, nullable=False)      # always in INR
    original_amount = Column(Float, nullable=True)  # in expense currency
    share_count = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)

    expense = relationship("Expense", back_populates="splits")
    user = relationship("User")


class Settlement(Base):
    __tablename__ = "settlements"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    payer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    settlement_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="settlements")
    payer = relationship("User", foreign_keys=[payer_id])
    receiver = relationship("User", foreign_keys=[receiver_id])


class ImportSession(Base):
    __tablename__ = "import_sessions"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    filename = Column(String, nullable=True)
    status = Column(String, default="pending")   # pending | committed | cancelled
    usd_inr_rate = Column(Float, default=85.0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    rows = relationship("ImportRow", back_populates="session", cascade="all, delete-orphan")


class ImportRow(Base):
    __tablename__ = "import_rows"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("import_sessions.id"), nullable=False)
    row_number = Column(Integer, nullable=False)
    raw_data = Column(Text, nullable=False)    # JSON of original CSV row
    parsed_data = Column(Text, nullable=True)  # JSON of cleaned row after resolution
    status = Column(String, default="pending") # pending | approved | rejected | auto_fixed
    anomalies = Column(Text, nullable=True)    # JSON array of anomaly objects
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True)

    session = relationship("ImportSession", back_populates="rows")
