from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import threading
import urllib.error
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import re2
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.environ.get("CLONARCH_DATA_DIR", ROOT / "var")).resolve()
DB_PATH = DATA_DIR / "clonarch.sqlite3"
APP_HOST = os.environ.get("CLONARCH_HOST", "192.168.105.10")
APP_PORT = int(os.environ.get("CLONARCH_PORT", "8787"))
APP_ORIGIN = os.environ.get("CLONARCH_ORIGIN", f"http://{APP_HOST}:{APP_PORT}")
TIMEZONE = os.environ.get("CLONARCH_TIMEZONE", "America/New_York")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


try:
    ZoneInfo(TIMEZONE)
except ZoneInfoNotFoundError as exc:
    raise RuntimeError(f"Invalid CLONARCH_TIMEZONE: {TIMEZONE}") from exc

DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(DATA_DIR, 0o700)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False, "timeout": 20})
SessionLocal = sessionmaker(engine, expire_on_commit=False)
csrf_sessions: dict[str, str] = {}
plaid_sync_lock = threading.Lock()


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100))
    owner: Mapped[str] = mapped_column(String(100), default="Household")
    kind: Mapped[str] = mapped_column(String(20), default="credit_card")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(80), unique=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    purchase_date: Mapped[date] = mapped_column(Date)
    posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(500))
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="expense")
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    spend_type: Mapped[str] = mapped_column(String(20), default="regular")
    event: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="posted")
    rule_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    pattern: Mapped[str] = mapped_column(String(512))
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    spend_type: Mapped[str] = mapped_column(String(20), default="regular")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Allocation(Base):
    __tablename__ = "allocations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), unique=True)
    start_month: Mapped[str] = mapped_column(String(7))
    end_month_exclusive: Mapped[str] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    rows_json: Mapped[str] = mapped_column(Text)
    errors_json: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="previewed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlaidConnection(Base):
    __tablename__ = "plaid_connections"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id: Mapped[str] = mapped_column(String(128), unique=True)
    institution_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    institution_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    state: Mapped[str] = mapped_column(String(30), default="active")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlaidAccountLink(Base):
    __tablename__ = "plaid_account_links"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    connection_id: Mapped[str] = mapped_column(ForeignKey("plaid_connections.id"))
    external_account_id: Mapped[str] = mapped_column(String(128), unique=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    mask: Mapped[str | None] = mapped_column(String(8), nullable=True)
    subtype: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PlaidTransactionSource(Base):
    __tablename__ = "plaid_transaction_sources"
    external_transaction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))


class TransactionIn(BaseModel):
    account_id: str
    amount_minor: int
    purchase_date: date
    posted_date: date | None = None
    description: str = Field(min_length=1, max_length=500)
    merchant: str | None = Field(default=None, max_length=200)
    kind: Literal["expense", "refund", "income", "transfer"] = "expense"
    category_id: str | None = None
    spend_type: Literal["regular", "exceptional"] = "regular"
    event: str | None = Field(default=None, max_length=120)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Description cannot be blank")
        return value

    @model_validator(mode="after")
    def check_sign(self):
        if self.kind == "expense" and self.amount_minor > 0:
            raise ValueError("Expense amounts must be negative")
        if self.kind in {"refund", "income"} and self.amount_minor < 0:
            raise ValueError("Refund and income amounts must be positive")
        if self.event and self.spend_type != "exceptional":
            raise ValueError("Events are only valid for exceptional spending")
        return self


class TransactionPatch(BaseModel):
    category_id: str | None = None
    spend_type: Literal["regular", "exceptional"] | None = None
    kind: Literal["expense", "refund", "income", "transfer"] | None = None
    event: str | None = Field(default=None, max_length=120)


class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    pattern: str = Field(min_length=1, max_length=512)
    category_id: str | None = None
    spend_type: Literal["regular", "exceptional"] = "regular"
    priority: int = 100

    @field_validator("pattern")
    @classmethod
    def safe_pattern(cls, value: str) -> str:
        if len(value) > 512:
            raise ValueError("Regex too long")
        try:
            re2.compile(value)
        except Exception as exc:
            raise ValueError("Unsupported or invalid RE2 expression") from exc
        return value


class AllocationIn(BaseModel):
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month_exclusive: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    @model_validator(mode="after")
    def validate_range(self):
        start = month_index(self.start_month)
        end = month_index(self.end_month_exclusive)
        if end <= start or end - start > 60:
            raise ValueError("Allocation period must be between 1 and 60 months")
        return self


def month_index(month: str) -> int:
    year, m = map(int, month.split("-"))
    return year * 12 + m - 1


def month_name(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def plaid_configuration() -> tuple[dict[str, str], Fernet] | None:
    config_path = ROOT / ".secrets" / "plaid.json"
    key_path = ROOT / ".secrets" / "plaid-fernet.key"
    if not config_path.is_file() or not key_path.is_file():
        return None
    if config_path.stat().st_mode & 0o077 or key_path.stat().st_mode & 0o077:
        raise RuntimeError("Plaid credential files must be private (mode 0600)")
    config = json.loads(config_path.read_text())
    if config.get("environment") != "production" or not config.get("client_id") or not config.get("secret"):
        raise RuntimeError("Plaid configuration must contain Trial Production credentials")
    return config, Fernet(key_path.read_bytes().strip())


def plaid_api(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    configured = plaid_configuration()
    if not configured:
        raise HTTPException(409, "Plaid credentials are not configured on this VM")
    config, _ = configured
    # Plaid Trial uses Production. API host is fixed; the frontend cannot select an endpoint.
    body = {"client_id": config["client_id"], "secret": config["secret"], **payload}
    request = urllib.request.Request(
        f"https://production.plaid.com/{endpoint.lstrip('/')}",
        data=json.dumps(body, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", "Plaid-Version": "2020-09-14"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(502, "Plaid response exceeded the configured size limit")
        return json.loads(raw, parse_float=Decimal)
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read(65536))
            code = str(error.get("error_code", "PLAID_ERROR"))[:80]
        except Exception:
            code = "PLAID_ERROR"
        raise HTTPException(502, f"Plaid request failed ({code}); check connection status") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise HTTPException(503, "Plaid could not be reached; retry later") from None


def allocate(amount_minor: int, months: int) -> list[int]:

    quotient, remainder = divmod(abs(amount_minor), months)
    sign = -1 if amount_minor < 0 else 1
    return [sign * (quotient + (i < remainder)) for i in range(months)]


def db_session():
    with SessionLocal() as session:
        yield session


def envelope(data: Any, request: Request, revision: int | None = None):
    result = {"data": data, "meta": {"request_id": request.state.request_id}}
    if revision is not None:
        result["meta"]["ledger_revision"] = revision
    return result


def tx_dict(tx: Transaction, db: Session) -> dict[str, Any]:
    category = db.get(Category, tx.category_id) if tx.category_id else None
    account = db.get(Account, tx.account_id)
    allocation = db.scalar(select(Allocation).where(Allocation.transaction_id == tx.id))
    return {
        "id": tx.id, "account_id": tx.account_id, "account_name": account.name if account else "Unknown",
        "amount_minor": tx.amount_minor, "currency": "USD", "purchase_date": tx.purchase_date.isoformat(),
        "posted_date": tx.posted_date.isoformat() if tx.posted_date else None,
        "date_provenance": ("posted_income" if tx.kind == "income" and tx.posted_date else
                            "posted_fallback" if tx.posted_date and tx.purchase_date == tx.posted_date else "purchase_date"),
        "description": tx.description, "merchant": tx.merchant, "kind": tx.kind,
        "category_id": tx.category_id, "category": category.name if category else "Uncategorized",
        "spend_type": tx.spend_type, "event": tx.event, "source": tx.source, "status": tx.status,
        "rule_locked": tx.rule_locked,
        "allocation": ({"start_month": allocation.start_month, "end_month_exclusive": allocation.end_month_exclusive}
                       if allocation else None),
    }


def apply_rules(tx: Transaction, db: Session) -> None:
    if tx.rule_locked:
        return
    rules = db.scalars(select(Rule).where(Rule.enabled.is_(True)).order_by(Rule.priority, Rule.id)).all()
    text = (tx.merchant or tx.description).casefold()[:4096]
    for rule in rules:
        try:
            match = re2.search(rule.pattern, text)
        except Exception:
            match = None
        if match:
            tx.category_id = rule.category_id
            tx.spend_type = rule.spend_type
            return


def validate_tx(payload: TransactionIn, db: Session):
    if not db.get(Account, payload.account_id):
        raise HTTPException(422, "Unknown account")
    if payload.category_id and not db.get(Category, payload.category_id):
        raise HTTPException(422, "Unknown category")


def seed(db: Session):
    if not db.scalar(select(Account.id).limit(1)):
        for name, owner, kind in [
            ("Chase Card 1", "Household", "credit_card"), ("Chase Card 2", "Household", "credit_card"),
            ("Amex Card 1", "Household", "credit_card"), ("Amex Card 2", "Household", "credit_card"),
            ("Chase Checking", "Owner", "checking"),
        ]:
            db.add(Account(name=name, owner=owner, kind=kind))
    if not db.scalar(select(Category.id).limit(1)):
        for name in ["Groceries", "Dining", "Housing", "Utilities", "Transport", "Health", "Shopping",
                     "Subscriptions", "Insurance", "Travel", "Home maintenance", "Other"]:
            db.add(Category(name=name))
    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql("PRAGMA busy_timeout=20000")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield
    engine.dispose()


app = FastAPI(title="Clonarch", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[f"{APP_HOST}:{APP_PORT}", APP_HOST, "localhost", "127.0.0.1"])


@app.middleware("http")
async def browser_safety(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        session_id = request.cookies.get("clonarch_session")
        token = request.headers.get("x-csrf-token")
        if origin != APP_ORIGIN or not session_id or csrf_sessions.get(session_id) != token:
            return JSONResponse({"error": {"code": "CSRF_REJECTED", "message": "Refresh Clonarch and retry"}}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://cdn.plaid.com; style-src 'self' 'unsafe-inline'; connect-src 'self' https://*.plaid.com; frame-src https://*.plaid.com; img-src 'self' data: https://*.plaid.com; frame-ancestors 'none'; base-uri 'self'"
    return response


@app.get("/api/v1/context")
def context(request: Request):
    session_id = request.cookies.get("clonarch_session") or secrets.token_urlsafe(32)
    csrf = csrf_sessions.setdefault(session_id, secrets.token_urlsafe(32))
    response = JSONResponse(envelope({"name": "Clonarch", "currency": "USD", "timezone": TIMEZONE,
                                      "date_basis": "purchase date; posted fallback shown",
                                      "features": {"plaid": plaid_configuration() is not None, "jex": False, "imports": True}}, request))
    response.set_cookie("clonarch_session", session_id, httponly=True, samesite="strict", secure=False, max_age=28800, path="/")
    response.headers["X-CSRF-Token"] = csrf
    return response


@app.get("/api/v1/plaid/status")
def plaid_status(request: Request, db: Session = Depends(db_session)):
    configured = plaid_configuration() is not None
    rows = db.scalars(select(PlaidConnection).order_by(PlaidConnection.created_at)).all()
    return envelope({"configured": configured, "environment": "production" if configured else None,
                     "history_days_requested": 365, "connections": [{
                         "id": c.id, "institution_name": c.institution_name or "Financial institution",
                         "state": c.state, "update_status": c.update_status,
                         "last_success_at": c.last_success_at.isoformat() if c.last_success_at else None,
                         "accounts": [{"name": (db.get(Account, link.account_id).name if db.get(Account, link.account_id) else "Account"),
                                       "mask": link.mask, "subtype": link.subtype}
                                      for link in db.scalars(select(PlaidAccountLink).where(PlaidAccountLink.connection_id == c.id)).all()]
                     } for c in rows]}, request)


@app.post("/api/v1/plaid/link-token")
def plaid_link_token(request: Request):
    response = plaid_api("link/token/create", {
        "client_name": "Clonarch", "user": {"client_user_id": "clonarch-household-v1"},
        "products": ["transactions"], "country_codes": ["US"], "language": "en",
        "transactions": {"days_requested": 365}
    })
    return envelope({"link_token": response["link_token"], "expiration": response.get("expiration"),
                     "history_days_requested": 365}, request)


@app.post("/api/v1/plaid/exchange")
def plaid_exchange(payload: dict, request: Request, db: Session = Depends(db_session)):
    public_token = payload.get("public_token")
    metadata = payload.get("metadata") or {}
    if not isinstance(public_token, str) or not public_token or len(public_token) > 4096:
        raise HTTPException(422, "Invalid Plaid Link token")
    configured = plaid_configuration()
    if not configured:
        raise HTTPException(409, "Plaid credentials are not configured")
    _, fernet = configured
    exchanged = plaid_api("item/public_token/exchange", {"public_token": public_token})
    item_id = exchanged.get("item_id")
    access_token = exchanged.get("access_token")
    if not isinstance(item_id, str) or not isinstance(access_token, str):
        raise HTTPException(502, "Plaid returned an invalid connection response")
    connection = db.scalar(select(PlaidConnection).where(PlaidConnection.item_id == item_id))
    if connection:
        raise HTTPException(409, "This Plaid connection is already saved; use the existing connection")
    connection = PlaidConnection(item_id=item_id, institution_id=str(metadata.get("institution", {}).get("institution_id") or "")[:100] or None,
                                 institution_name=str(metadata.get("institution", {}).get("name") or "")[:160] or None,
                                 access_token_encrypted=fernet.encrypt(access_token.encode()).decode(), state="active")
    db.add(connection)
    db.commit()
    accounts_response = plaid_api("accounts/get", {"access_token": access_token})
    saved_accounts = []
    institution = connection.institution_name or "Plaid"
    for provider_account in accounts_response.get("accounts", []):
        external_id = provider_account.get("account_id")
        if not isinstance(external_id, str):
            continue
        existing = db.scalar(select(PlaidAccountLink).where(PlaidAccountLink.external_account_id == external_id))
        if existing:
            saved_accounts.append(existing.account_id)
            continue
        account_type = provider_account.get("type")
        subtype = str(provider_account.get("subtype") or "")[:50]
        is_card = account_type == "credit"
        kind = "credit_card" if is_card else ("checking" if account_type == "depository" and subtype == "checking" else "other")
        mask = str(provider_account.get("mask") or "")[-4:] or None
        display = str(provider_account.get("name") or provider_account.get("official_name") or "Account")[:70]
        label = f"{institution} · {display}" + (f" ····{mask}" if mask else "")
        account = Account(name=label[:100], owner="Household" if is_card else "Owner", kind=kind)
        db.add(account)
        db.flush()
        link = PlaidAccountLink(connection_id=connection.id, external_account_id=external_id,
                                account_id=account.id, mask=mask, subtype=subtype or None)
        db.add(link)
        saved_accounts.append(account.id)
    db.commit()
    return envelope({"connection_id": connection.id, "institution_name": institution,
                     "accounts": [{"id": account_id, "name": db.get(Account, account_id).name,
                                   "kind": db.get(Account, account_id).kind} for account_id in saved_accounts]}, request)


def sync_plaid_connection(connection: PlaidConnection, db: Session) -> dict[str, Any]:
    configured = plaid_configuration()
    if not configured:
        raise HTTPException(409, "Plaid credentials are not configured")
    _, fernet = configured
    try:
        access_token = fernet.decrypt(connection.access_token_encrypted.encode()).decode()
    except (InvalidToken, ValueError):
        raise HTTPException(500, "Could not decrypt Plaid connection token; check the local key file") from None
    starting_cursor = connection.cursor
    cursor = starting_cursor
    added: list[dict[str, Any]] = []
    modified: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    update_status = None
    for _ in range(1000):
        body: dict[str, Any] = {"access_token": access_token, "count": 500}
        if cursor:
            body["cursor"] = cursor
        page = plaid_api("transactions/sync", body)
        added.extend(page.get("added", []))
        modified.extend(page.get("modified", []))
        removed.extend(page.get("removed", []))
        cursor = page.get("next_cursor", cursor)
        update_status = page.get("transactions_update_status", update_status)
        if not page.get("has_more"):
            break
    else:
        raise HTTPException(502, "Plaid history exceeded the safe pagination limit; no updates were applied")

    links = {link.external_account_id: link for link in db.scalars(
        select(PlaidAccountLink).where(PlaidAccountLink.connection_id == connection.id)).all()}
    replaced_pending: set[str] = set()
    added_count = modified_count = removed_count = skipped = 0
    for row, is_added in [(r, True) for r in added] + [(r, False) for r in modified]:
        external_account_id = row.get("account_id")
        account_link = links.get(external_account_id)
        external_id = row.get("transaction_id")
        if not account_link or not isinstance(external_id, str):
            skipped += 1
            continue
        source = db.get(PlaidTransactionSource, external_id)
        pending_id = row.get("pending_transaction_id")
        if source is None and isinstance(pending_id, str) and pending_id:
            source = db.get(PlaidTransactionSource, pending_id)
            if source:
                replaced_pending.add(pending_id)
        if source:
            tx = db.get(Transaction, source.transaction_id)
        else:
            tx = Transaction(account_id=account_link.account_id, amount_minor=0, purchase_date=date.today(),
                             description="", source="plaid", status="pending")
            db.add(tx)
            db.flush()
        try:
            pla_amount = Decimal(str(row.get("amount")))
            cents = pla_amount * 100
            if cents != cents.to_integral_value():
                raise ValueError("non-cent amount")
            amount_minor = -int(cents)
            raw_date = row.get("date")
            purchase = date.fromisoformat(str(row.get("authorized_date") or raw_date))
            posted = date.fromisoformat(str(raw_date)) if not row.get("pending") and raw_date else None
        except (ValueError, InvalidOperation, TypeError):
            skipped += 1
            continue
        description = str(row.get("name") or row.get("original_description") or "Plaid transaction")[:500]
        merchant = str(row.get("merchant_name") or "")[:200] or None
        is_card = (db.get(Account, account_link.account_id).kind == "credit_card")
        classification_text = f"{description} {merchant or ''}".casefold()
        payment_hint = bool(re.search(r"\b(payment|autopay|payment thank you|credit card|cardmember|online payment|transfer)\b", classification_text))
        payroll_hint = bool(re.search(r"\b(payroll|paycheck|salary|direct deposit|employer)\b", classification_text))
        if payment_hint:
            kind = "transfer"
        elif is_card:
            kind = "expense" if amount_minor < 0 else "refund"
        else:
            kind = "income" if amount_minor > 0 and payroll_hint else ("transfer" if amount_minor > 0 else "expense")
        tx.account_id = account_link.account_id
        tx.amount_minor = amount_minor
        tx.purchase_date = purchase
        tx.posted_date = posted
        tx.description = description
        tx.merchant = merchant
        tx.kind = kind
        tx.status = "pending" if row.get("pending") else "posted"
        tx.source = "plaid"
        if not tx.rule_locked:
            apply_rules(tx, db)
        if db.get(PlaidTransactionSource, external_id) is None:
            db.add(PlaidTransactionSource(external_transaction_id=external_id,
                                          account_id=account_link.account_id, transaction_id=tx.id))
        if is_added:
            added_count += 1
        else:
            modified_count += 1
    for row in removed:
        external_id = row.get("transaction_id")
        if not isinstance(external_id, str) or external_id in replaced_pending:
            continue
        source = db.get(PlaidTransactionSource, external_id)
        if source:
            tx = db.get(Transaction, source.transaction_id)
            if tx and tx.status != "removed":
                tx.status = "removed"
                removed_count += 1
    connection.cursor = cursor
    connection.update_status = update_status
    connection.last_success_at = utcnow()
    connection.last_error_code = None
    connection.state = "active"
    db.commit()
    return {"added": added_count, "modified": modified_count, "removed": removed_count,
            "skipped": skipped, "update_status": update_status, "has_cursor": bool(cursor)}


@app.get("/api/v1/plaid/connections")
def plaid_connections(request: Request, db: Session = Depends(db_session)):
    return plaid_status(request, db)


@app.post("/api/v1/plaid/{connection_id}/sync")
def plaid_sync(connection_id: str, request: Request, db: Session = Depends(db_session)):
    connection = db.get(PlaidConnection, connection_id)
    if not connection:
        raise HTTPException(404, "Plaid connection not found")
    if not plaid_sync_lock.acquire(blocking=False):
        raise HTTPException(409, "A Plaid sync is already running; retry shortly")
    try:
        try:
            result = sync_plaid_connection(connection, db)
        except HTTPException as exc:
            connection.last_error_code = str(exc.detail)[:100]
            connection.state = "error" if exc.status_code >= 500 else connection.state
            db.commit()
            raise
        return envelope(result, request)
    finally:
        plaid_sync_lock.release()


@app.get("/api/v1/health/ready")
def health(db: Session = Depends(db_session)):
    db.execute(select(Account.id).limit(1))
    return {"status": "ready", "app": "Clonarch"}


@app.get("/api/v1/accounts")
def accounts(request: Request, db: Session = Depends(db_session)):
    rows = db.scalars(select(Account).order_by(Account.kind, Account.name)).all()
    return envelope([{"id": a.id, "name": a.name, "owner": a.owner, "kind": a.kind} for a in rows], request)


@app.post("/api/v1/accounts", status_code=201)
def create_account(payload: dict, request: Request, db: Session = Depends(db_session)):
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 100:
        raise HTTPException(422, "Account name required (max 100 characters)")
    kind = payload.get("kind", "credit_card")
    if kind not in {"credit_card", "checking", "cash", "other"}:
        raise HTTPException(422, "Invalid account kind")
    account = Account(name=name, owner=str(payload.get("owner", "Household"))[:100], kind=kind)
    db.add(account)
    db.commit()
    return envelope({"id": account.id, "name": account.name, "owner": account.owner, "kind": account.kind}, request)


@app.get("/api/v1/categories")
def categories(request: Request, db: Session = Depends(db_session)):
    rows = db.scalars(select(Category).where(Category.archived.is_(False)).order_by(Category.name)).all()
    return envelope([{"id": c.id, "name": c.name} for c in rows], request)


@app.get("/api/v1/transactions")
def transactions(request: Request, month: str | None = None, spend_type: str | None = None,
                category_id: str | None = None, limit: int = 100, db: Session = Depends(db_session)):
    limit = min(max(limit, 1), 250)
    stmt = select(Transaction).where(Transaction.status == "posted").order_by(Transaction.purchase_date.desc(), Transaction.id)
    if month:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise HTTPException(422, "month must be YYYY-MM")
        stmt = stmt.where(Transaction.purchase_date >= date.fromisoformat(month + "-01"))
        y, m = map(int, month.split("-"))
        end = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        stmt = stmt.where(Transaction.purchase_date < end)
    if spend_type:
        stmt = stmt.where(Transaction.spend_type == spend_type)
    if category_id == "uncategorized":
        stmt = stmt.where(Transaction.category_id.is_(None))
    elif category_id:
        stmt = stmt.where(Transaction.category_id == category_id)
    rows = db.scalars(stmt.limit(limit)).all()
    return envelope([tx_dict(tx, db) for tx in rows], request)


@app.post("/api/v1/transactions", status_code=201)
def add_transaction(payload: TransactionIn, request: Request, db: Session = Depends(db_session)):
    validate_tx(payload, db)
    tx = Transaction(**payload.model_dump(), source="manual", status="posted")
    apply_rules(tx, db)
    db.add(tx)
    db.commit()
    return envelope(tx_dict(tx, db), request)


@app.patch("/api/v1/transactions/{tx_id}")
def update_transaction(tx_id: str, payload: TransactionPatch, request: Request, db: Session = Depends(db_session)):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "Transaction not found")
    changes = payload.model_dump(exclude_unset=True)
    if "category_id" in changes and changes["category_id"] and not db.get(Category, changes["category_id"]):
        raise HTTPException(422, "Unknown category")
    next_kind = changes.get("kind", tx.kind)
    if next_kind == "expense" and tx.amount_minor > 0:
        raise HTTPException(422, "Expense amounts must be negative")
    if next_kind in {"income", "refund"} and tx.amount_minor < 0:
        raise HTTPException(422, "Income and refund amounts must be positive")
    if changes.get("event") and changes.get("spend_type", tx.spend_type) != "exceptional":
        raise HTTPException(422, "Events are only valid for exceptional spending")
    for key, value in changes.items():
        setattr(tx, key, value)
    tx.rule_locked = True
    db.commit()
    return envelope(tx_dict(tx, db), request)


@app.get("/api/v1/reports/monthly")
def monthly_report(request: Request, month: str, basis: Literal["actual", "normalized"] = "actual", db: Session = Depends(db_session)):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(422, "month must be YYYY-MM")
    rows = db.scalars(select(Transaction).where(Transaction.status == "posted")).all()
    idx = month_index(month)
    def report_month(tx: Transaction) -> str:
        basis_date = (tx.posted_date or tx.purchase_date) if tx.kind == "income" else tx.purchase_date
        return basis_date.strftime("%Y-%m")
    category_totals: dict[str, dict[str, int]] = {}
    totals = {"regular": 0, "exceptional": 0, "income": 0}
    actual_by_type = {"regular": 0, "exceptional": 0}
    for tx in rows:
        txmonth = report_month(tx)
        if txmonth == month:
            if tx.kind in ("expense", "refund"):
                contribution = -tx.amount_minor
                actual_by_type[tx.spend_type] += contribution
                actual_bucket = category_totals.setdefault(tx.category_id or "uncategorized", {"actual": 0, "normalized": 0})
                actual_bucket["actual"] += contribution
                actual_bucket["normalized"] += contribution
                if tx.spend_type in totals:
                    totals[tx.spend_type] += contribution
            elif tx.kind == "income":
                totals["income"] += tx.amount_minor
        allocation = db.scalar(select(Allocation).where(Allocation.transaction_id == tx.id))
        if allocation and tx.kind in ("expense", "refund"):
            start, stop = month_index(allocation.start_month), month_index(allocation.end_month_exclusive)
            if start <= idx < stop:
                shares = allocate(-tx.amount_minor, stop - start)
                contribution = shares[idx - start]
                totals[tx.spend_type] += contribution
                bucket = category_totals.setdefault(tx.category_id or "uncategorized", {"actual": 0, "normalized": 0})
                bucket["normalized"] += contribution
                if txmonth == month:
                    bucket["normalized"] -= -tx.amount_minor
    normalized = {"regular": 0, "exceptional": 0}
    for tx in rows:
        if tx.kind not in ("expense", "refund"):
            continue
        txmonth = report_month(tx)
        allocation = db.scalar(select(Allocation).where(Allocation.transaction_id == tx.id))
        amount = -tx.amount_minor
        if txmonth == month:
            normalized[tx.spend_type] += amount
        if allocation:
            start, stop = month_index(allocation.start_month), month_index(allocation.end_month_exclusive)
            if start <= idx < stop:
                normalized[tx.spend_type] += allocate(amount, stop-start)[idx-start]
                if txmonth == month:
                    normalized[tx.spend_type] -= amount
    report = {
        "month": month, "currency": "USD", "timezone": TIMEZONE,
        "actual": {"regular_minor": actual_by_type["regular"], "exceptional_minor": actual_by_type["exceptional"],
                   "total_expense_minor": sum(actual_by_type.values()), "income_minor": totals["income"],
                   "recorded_surplus_minor": totals["income"] - sum(actual_by_type.values())},
        "normalized": {"regular_minor": normalized["regular"], "exceptional_minor": normalized["exceptional"],
                       "total_expense_minor": sum(normalized.values())},
        "basis": basis,
        "by_category": [{"category_id": key, "actual_minor": value["actual"], "normalized_minor": value["normalized"]}
                        for key, value in category_totals.items()],
        "transactions": len(rows),
    }
    return envelope(report, request)


@app.get("/api/v1/rules")
def get_rules(request: Request, db: Session = Depends(db_session)):
    rows = db.scalars(select(Rule).order_by(Rule.priority, Rule.id)).all()
    return envelope([{"id": r.id, "name": r.name, "pattern": r.pattern, "category_id": r.category_id,
                      "spend_type": r.spend_type, "priority": r.priority, "enabled": r.enabled} for r in rows], request)


@app.post("/api/v1/rules", status_code=201)
def create_rule(payload: RuleIn, request: Request, db: Session = Depends(db_session)):
    if payload.category_id and not db.get(Category, payload.category_id):
        raise HTTPException(422, "Unknown category")
    rule = Rule(**payload.model_dump())
    db.add(rule)
    db.commit()
    return envelope({"id": rule.id, **payload.model_dump()}, request)


@app.post("/api/v1/rules/apply")
def run_rules(request: Request, db: Session = Depends(db_session)):
    changed = 0
    rows = db.scalars(select(Transaction).where(Transaction.status == "posted")).all()
    for tx in rows:
        before = (tx.category_id, tx.spend_type)
        tx.rule_locked = False
        apply_rules(tx, db)
        changed += before != (tx.category_id, tx.spend_type)
    db.commit()
    return envelope({"changed": changed}, request)


@app.put("/api/v1/transactions/{tx_id}/allocation")
def put_allocation(tx_id: str, payload: AllocationIn, request: Request, db: Session = Depends(db_session)):
    tx = db.get(Transaction, tx_id)
    if not tx or tx.status != "posted" or tx.kind not in {"expense", "refund"}:
        raise HTTPException(422, "Only posted expenses and refunds can be allocated")
    allocation = db.scalar(select(Allocation).where(Allocation.transaction_id == tx_id))
    if allocation is None:
        allocation = Allocation(transaction_id=tx_id, start_month=payload.start_month,
                                end_month_exclusive=payload.end_month_exclusive)
        db.add(allocation)
    else:
        allocation.start_month = payload.start_month
        allocation.end_month_exclusive = payload.end_month_exclusive
    db.commit()
    return envelope({"transaction_id": tx_id, "start_month": allocation.start_month,
                     "end_month_exclusive": allocation.end_month_exclusive,
                     "monthly_minor": allocate(-tx.amount_minor, month_index(allocation.end_month_exclusive)-month_index(allocation.start_month))}, request)


@app.delete("/api/v1/transactions/{tx_id}/allocation")
def delete_allocation(tx_id: str, request: Request, db: Session = Depends(db_session)):
    allocation = db.scalar(select(Allocation).where(Allocation.transaction_id == tx_id))
    if allocation:
        db.delete(allocation)
        db.commit()
    return {"status": "deleted"}


@app.post("/api/v1/imports/csv", status_code=201)
async def import_csv(request: Request, file: UploadFile = File(...), account_id: str = "", db: Session = Depends(db_session)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(422, "Choose an account before importing")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "CSV exceeds 10 MiB")
    digest = hashlib.sha256(raw).hexdigest()
    duplicate = db.scalar(select(ImportBatch).where(ImportBatch.file_hash == digest, ImportBatch.account_id == account_id))
    if duplicate:
        raise HTTPException(409, "This exact file was already previewed or imported for this account")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except Exception as exc:
        raise HTTPException(422, "Could not parse UTF-8 CSV") from exc
    if not reader.fieldnames or len(rows) > 50000:
        raise HTTPException(422, "CSV needs headers and at most 50,000 rows")
    headers = {h.strip().casefold(): h for h in reader.fieldnames if h}
    date_col = next((headers[x] for x in ("purchase_date", "authorized_date", "date", "transaction date") if x in headers), None)
    amount_col = next((headers[x] for x in ("amount", "amount_minor") if x in headers), None)
    desc_col = next((headers[x] for x in ("description", "merchant", "name") if x in headers), None)
    if not date_col or not amount_col or not desc_col:
        raise HTTPException(422, "CSV needs date, amount and description columns; expected purchase_date/date, amount and description")
    candidates, errors = [], []
    for line, row in enumerate(rows, start=2):
        try:
            txdate = date.fromisoformat((row.get(date_col) or "").strip()[:10])
            amount_text = (row.get(amount_col) or "").replace("$", "").replace(",", "").strip()
            value = Decimal(amount_text)
            if amount_col.strip().casefold() == "amount_minor":
                if value != value.to_integral_value(): raise ValueError("amount_minor must be an integer")
                amount_minor = int(value)
            else:
                cents = value * 100
                if cents != cents.to_integral_value(): raise ValueError("amount must have no more than two decimal places")
                amount_minor = int(cents)
            description = (row.get(desc_col) or "").strip()[:500]
            if not description: raise ValueError("blank description")
            if amount_minor == 0: raise ValueError("zero amount")
            description_key = description.casefold()
            card_payment = bool(re.search(r"\b(credit card payment|card payment|payment thank you|autopay|payment to (chase|amex))\b", description_key))
            payroll = bool(re.search(r"\b(payroll|paycheck|salary|direct deposit|employer)\b", description_key))
            if account.kind == "credit_card":
                kind = "transfer" if amount_minor > 0 and card_payment else ("expense" if amount_minor < 0 else "refund")
                posted_date = None
            else:
                kind = "transfer" if card_payment else ("income" if amount_minor > 0 and payroll else
                                                          "expense" if amount_minor < 0 else "transfer")
                posted_date = txdate if kind == "income" else None
            candidates.append({"row": line, "purchase_date": txdate.isoformat(), "amount_minor": amount_minor,
                               "description": description, "kind": kind})
        except (ValueError, InvalidOperation, TypeError) as exc:
            errors.append({"row": line, "error": str(exc)[:100]})
    batch = ImportBatch(file_hash=digest, account_id=account_id, rows_json=json.dumps(candidates),
                        errors_json=json.dumps(errors), state="previewed")
    db.add(batch)
    db.commit()
    return envelope({"import_id": batch.id, "state": batch.state, "account_name": account.name,
                     "candidate_count": len(candidates), "error_count": len(errors),
                     "errors": errors[:100], "sample": candidates[:25],
                     "sign_convention": "negative=outflow; positive=card refund or checking income",
                     "warning": "Review the preview. Overlapping statement files may duplicate transactions."}, request)


@app.post("/api/v1/imports/{batch_id}/commit")
def commit_import(batch_id: str, request: Request, db: Session = Depends(db_session)):
    batch = db.get(ImportBatch, batch_id)
    if not batch: raise HTTPException(404, "Import preview not found")
    if batch.state == "committed": raise HTTPException(409, "Import was already committed")
    candidates = json.loads(batch.rows_json)
    errors = json.loads(batch.errors_json)
    if errors: raise HTTPException(422, "Fix or remove invalid CSV rows before importing; no rows committed")
    created = 0
    for item in candidates:
        txdate = date.fromisoformat(item["purchase_date"])
        tx = Transaction(account_id=batch.account_id, amount_minor=item["amount_minor"], purchase_date=txdate,
                         posted_date=txdate if item["kind"] == "income" else None,
                         description=item["description"], merchant=item["description"], kind=item["kind"],
                         spend_type="regular", source="csv", status="posted")
        apply_rules(tx, db)
        db.add(tx)
        created += 1
    batch.state = "committed"
    db.commit()
    return envelope({"import_id": batch.id, "state": batch.state, "created": created,
                     "warning": "Overlapping statement periods are not automatically deduplicated."}, request)


@app.get("/{path:path}")
def frontend(path: str):
    index = ROOT / "frontend" / "dist" / "index.html"
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    if not index.exists():
        return JSONResponse({"status": "building", "message": "Clonarch frontend has not been built yet"}, status_code=503)
    asset = (index.parent / path).resolve()
    if path and asset.is_relative_to(index.parent) and asset.is_file():
        return FileResponse(asset)
    return FileResponse(index)
