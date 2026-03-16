from pydantic import BaseModel


# ── Webhook (Android → Server) ──
class WebhookPayload(BaseModel):
    id: int = 0
    type: str  # "SMS" or "NOTIFICATION"
    source: str
    sourceName: str
    title: str = ""
    content: str
    timestamp: int


# ── Accounts ──
class AccountCreate(BaseModel):
    code: str
    name: str
    type: str  # asset, liability, equity, income, expense
    parent_id: int | None = None
    is_group: int = 0


class AccountUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    type: str | None = None
    parent_id: int | None = None
    is_group: int | None = None
    is_active: int | None = None
    sort_order: int | None = None


class AccountOut(BaseModel):
    id: int
    code: str
    name: str
    type: str
    parent_id: int | None
    is_group: int = 0
    is_active: int
    sort_order: int = 0
    balance: int = 0
    depth: int = 0
    children_count: int = 0

    model_config = {"from_attributes": True}


# ── Journal Lines ──
class JournalLineIn(BaseModel):
    account_id: int
    debit: int = 0
    credit: int = 0


class JournalLineOut(BaseModel):
    id: int
    account_id: int
    account_name: str = ""
    account_code: str = ""
    debit: int
    credit: int

    model_config = {"from_attributes": True}


# ── Journal Entries ──
class EntryCreate(BaseModel):
    entry_date: str  # YYYY-MM-DD
    description: str
    memo: str = ""
    lines: list[JournalLineIn]


class EntryUpdate(BaseModel):
    entry_date: str | None = None
    description: str | None = None
    memo: str | None = None
    lines: list[JournalLineIn] | None = None


class EntryOut(BaseModel):
    id: int
    entry_date: str
    description: str
    memo: str
    raw_message_id: int | None
    source: str = "web"
    created_by: str = ""
    is_confirmed: int
    created_at: str
    lines: list[JournalLineOut] = []
    raw_content: str | None = None

    model_config = {"from_attributes": True}


# ── Raw Messages ──
class MessageOut(BaseModel):
    id: int
    source_type: str
    source: str
    source_name: str
    title: str
    content: str
    timestamp: int
    status: str
    ai_result: str | None
    created_at: str

    model_config = {"from_attributes": True}


# ── Dashboard ──
class AccountBalance(BaseModel):
    id: int
    code: str
    name: str
    type: str
    is_group: int = 0
    balance: int


class DashboardOut(BaseModel):
    total_asset: int = 0
    total_liability: int = 0
    total_income: int = 0
    total_expense: int = 0
    net_worth: int = 0
    accounts: list[AccountBalance] = []
    pending_count: int = 0


class MonthlyRow(BaseModel):
    month: str  # YYYY-MM
    income: int = 0
    expense: int = 0


# ── Category Rules ──
class RuleOut(BaseModel):
    id: int
    merchant_pattern: str
    debit_account_id: int | None
    credit_account_id: int | None
    debit_account_name: str | None = None
    credit_account_name: str | None = None
    hit_count: int

    model_config = {"from_attributes": True}


class RuleUpdate(BaseModel):
    merchant_pattern: str | None = None
    debit_account_id: int | None = None
    credit_account_id: int | None = None
