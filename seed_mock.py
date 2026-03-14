"""Seed realistic mock data for UI preview."""
import json
from datetime import datetime, timedelta
from app.database import engine, SessionLocal, Base
from app.models import Account, RawMessage, JournalEntry, JournalLine, CategoryRule

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# -- Ensure accounts exist --
if db.query(Account).count() == 0:
    from app.main import SEED_ACCOUNTS
    for code, name, acct_type in SEED_ACCOUNTS:
        db.add(Account(code=code, name=name, type=acct_type))
    db.commit()

accts = {a.code: a for a in db.query(Account).all()}

# -- Add sub-accounts (level 2, 3) for grouping demo --
sub_accounts = [
    # 식비 하위
    ("5011", "🍚 집밥", "expense", "5010"),
    ("5012", "🍔 외식", "expense", "5010"),
    ("5013", "☕ 카페", "expense", "5010"),
    # 외식 하위 (level 3)
    ("50121", "🍜 점심", "expense", "5012"),
    ("50122", "🍺 회식", "expense", "5012"),
    # 쇼핑 하위
    ("5041", "🛒 생필품", "expense", "5040"),
    ("5042", "👕 의류", "expense", "5040"),
    # 자산 하위 — 은행 그룹
    ("1011", "💳 신한 입출금", "asset", "1010"),
    ("1012", "💰 신한 적금", "asset", "1010"),
]
for code, name, acct_type, parent_code in sub_accounts:
    parent = accts.get(parent_code)
    if parent:
        a = Account(code=code, name=name, type=acct_type, parent_id=parent.id)
        db.add(a)
        db.flush()
        accts[code] = a
db.commit()

# Refresh account map
accts = {a.code: a for a in db.query(Account).all()}
A = accts  # shorthand

now = datetime.now()

# ── Mock transactions (confirmed) ──
confirmed_txns = [
    # 3월 거래들
    ("2026-03-01", "급여 입금", [("4010", 0, 3_500_000), ("1010", 3_500_000, 0)]),
    ("2026-03-02", "스타벅스 아메리카노", [("5013", 6_500, 0), ("2010", 0, 6_500)]),
    ("2026-03-03", "지하철 교통카드 충전", [("5020", 50_000, 0), ("1020", 0, 50_000)]),
    ("2026-03-04", "SK텔레콤 통신비", [("5030", 59_000, 0), ("1010", 0, 59_000)]),
    ("2026-03-05", "쿠팡 주문 (생필품)", [("5041", 35_800, 0), ("2010", 0, 35_800)]),
    ("2026-03-06", "점심 김밥천국", [("50121", 8_000, 0), ("1040", 0, 8_000)]),
    ("2026-03-07", "카카오뱅크 이자", [("1020", 1_250, 0), ("4020", 0, 1_250)]),
    ("2026-03-08", "GS25 편의점", [("5010", 4_200, 0), ("2030", 0, 4_200)]),
    ("2026-03-09", "올리브영 화장품", [("5042", 28_900, 0), ("2010", 0, 28_900)]),
    ("2026-03-10", "배달의민족 저녁", [("5012", 22_000, 0), ("2020", 0, 22_000)]),
    ("2026-03-11", "약국 감기약", [("5050", 12_500, 0), ("1040", 0, 12_500)]),
    ("2026-03-12", "카카오뱅크→토스 이체", [("1030", 500_000, 0), ("1020", 0, 500_000)]),
    ("2026-03-12", "넷플릭스 구독", [("5060", 17_000, 0), ("2010", 0, 17_000)]),
    # 2월 거래들
    ("2026-02-01", "급여 입금", [("4010", 0, 3_500_000), ("1010", 3_500_000, 0)]),
    ("2026-02-03", "이마트 장보기", [("5010", 87_600, 0), ("2010", 0, 87_600)]),
    ("2026-02-05", "SK텔레콤 통신비", [("5030", 59_000, 0), ("1010", 0, 59_000)]),
    ("2026-02-08", "스타벅스 라떼", [("5010", 5_800, 0), ("2010", 0, 5_800)]),
    ("2026-02-10", "교보문고 책 구매", [("5060", 32_000, 0), ("2030", 0, 32_000)]),
    ("2026-02-12", "지하철 교통카드 충전", [("5020", 50_000, 0), ("1020", 0, 50_000)]),
    ("2026-02-15", "배달의민족 치킨", [("5010", 25_000, 0), ("2020", 0, 25_000)]),
    ("2026-02-18", "병원 진료비", [("5050", 45_000, 0), ("2010", 0, 45_000)]),
    ("2026-02-20", "카카오뱅크 이자", [("1020", 980, 0), ("4020", 0, 980)]),
    ("2026-02-22", "다이소 생활용품", [("5040", 15_000, 0), ("1040", 0, 15_000)]),
    ("2026-02-25", "점심 도시락", [("5010", 7_500, 0), ("1040", 0, 7_500)]),
    ("2026-02-28", "유튜브 프리미엄", [("5060", 14_900, 0), ("2010", 0, 14_900)]),
    # 1월 거래들
    ("2026-01-02", "급여 입금", [("4010", 0, 3_500_000), ("1010", 3_500_000, 0)]),
    ("2026-01-05", "SK텔레콤 통신비", [("5030", 59_000, 0), ("1010", 0, 59_000)]),
    ("2026-01-07", "홈플러스 장보기", [("5010", 95_300, 0), ("2010", 0, 95_300)]),
    ("2026-01-10", "스타벅스 카페", [("5010", 12_000, 0), ("2010", 0, 12_000)]),
    ("2026-01-12", "교통카드 충전", [("5020", 50_000, 0), ("1020", 0, 50_000)]),
    ("2026-01-15", "쿠팡 겨울옷", [("5040", 89_000, 0), ("2010", 0, 89_000)]),
    ("2026-01-18", "카카오뱅크 이자", [("1020", 1_100, 0), ("4020", 0, 1_100)]),
    ("2026-01-20", "점심 순대국", [("5010", 9_000, 0), ("1040", 0, 9_000)]),
    ("2026-01-25", "넷플릭스 구독", [("5060", 17_000, 0), ("2010", 0, 17_000)]),
    ("2026-01-28", "편의점 간식", [("5010", 3_400, 0), ("2030", 0, 3_400)]),
]

for date_str, desc, lines_data in confirmed_txns:
    entry = JournalEntry(
        entry_date=date_str, description=desc, memo="", is_confirmed=1,
        created_at=datetime.fromisoformat(date_str + "T12:00:00").isoformat(),
        updated_at=datetime.fromisoformat(date_str + "T12:00:00").isoformat(),
    )
    db.add(entry)
    db.flush()
    for code, debit, credit in lines_data:
        db.add(JournalLine(entry_id=entry.id, account_id=A[code].id, debit=debit, credit=credit))

db.commit()

# ── Mock raw messages + pending entries (검토 대기) ──
pending_sms = [
    {
        "source": "15881688", "source_name": "KB국민카드",
        "content": "KB국민카드 승인 홍*동 32,000원 교보문고 03/13 10:23 일시불",
        "date": "2026-03-13", "desc": "교보문고 책 구매",
        "debit_code": "5060", "credit_code": "2010", "amount": 32_000,
    },
    {
        "source": "15771000", "source_name": "하나카드",
        "content": "하나카드 승인 홍*동 15,500원 맥도날드강남 03/13 12:45 일시불",
        "date": "2026-03-13", "desc": "맥도날드 점심",
        "debit_code": "5010", "credit_code": "2020", "amount": 15_500,
    },
    {
        "source": "15881688", "source_name": "KB국민카드",
        "content": "KB국민카드 승인 홍*동 4,800원 CU편의점역삼 03/13 15:10 일시불",
        "date": "2026-03-13", "desc": "CU 편의점",
        "debit_code": "5010", "credit_code": "2010", "amount": 4_800,
    },
]

for i, sms in enumerate(pending_sms):
    ts = int(datetime.fromisoformat(sms["date"] + "T12:00:00").timestamp() * 1000)
    msg = RawMessage(
        source_type="SMS", source=sms["source"], source_name=sms["source_name"],
        title="", content=sms["content"], timestamp=ts,
        status="parsed",
        ai_result=json.dumps({
            "transaction_type": "expense", "amount": sms["amount"],
            "merchant": sms["desc"].split()[0], "confidence": 0.95,
        }, ensure_ascii=False),
    )
    db.add(msg)
    db.flush()

    entry = JournalEntry(
        entry_date=sms["date"], description=sms["desc"], memo="",
        raw_message_id=msg.id, is_confirmed=0,
        created_at=now.isoformat(), updated_at=now.isoformat(),
    )
    db.add(entry)
    db.flush()
    db.add(JournalLine(entry_id=entry.id, account_id=A[sms["debit_code"]].id, debit=sms["amount"], credit=0))
    db.add(JournalLine(entry_id=entry.id, account_id=A[sms["credit_code"]].id, debit=0, credit=sms["amount"]))

db.commit()

# ── Failed message (AI 파싱 실패) ──
msg_fail = RawMessage(
    source_type="NOTIFICATION", source="com.nhn.android.search",
    source_name="네이버", title="네이버페이 결제",
    content="네이버페이 결제완료 7,900원 배민스토어",
    timestamp=int((now - timedelta(hours=2)).timestamp() * 1000),
    status="failed",
    ai_result=json.dumps({"error": "AI parse returned None"}),
)
db.add(msg_fail)
db.commit()

# ── Category rules ──
rules = [
    ("스타벅스", "5010", "2010", 5),
    ("배달의민족", "5010", "2020", 3),
    ("SK텔레콤", "5030", "1010", 3),
    ("쿠팡", "5040", "2010", 2),
    ("넷플릭스", "5060", "2010", 2),
    ("GS25", "5010", "2030", 1),
    ("CU", "5010", "2010", 1),
]
for pattern, debit_code, credit_code, hits in rules:
    db.add(CategoryRule(
        merchant_pattern=pattern,
        debit_account_id=A[debit_code].id,
        credit_account_id=A[credit_code].id,
        hit_count=hits,
        updated_at=now.isoformat(),
    ))
db.commit()

db.close()

# Summary
print("Mock data seeded:")
print(f"  - {len(confirmed_txns)} confirmed entries (Jan-Mar)")
print(f"  - {len(pending_sms)} pending entries (review queue)")
print(f"  - 1 failed message")
print(f"  - {len(rules)} category rules")
