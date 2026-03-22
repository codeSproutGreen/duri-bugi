"""Seed realistic mock data matching production account structure."""
import json
from datetime import datetime, timedelta
from app.database import engine, SessionLocal, Base
from app.models import (
    Account, RawMessage, JournalEntry, JournalLine, CategoryRule,
    StockPerson, StockAccount, StockHolding, RealEstate,
)

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# ── Clean all data ──
db.query(JournalLine).delete()
db.query(JournalEntry).delete()
db.query(RawMessage).delete()
db.query(CategoryRule).delete()
db.query(StockHolding).delete()
db.query(StockAccount).delete()
db.query(StockPerson).delete()
db.query(RealEstate).delete()
db.query(Account).delete()
db.commit()

# ── Create accounts matching production structure ──
# Groups only on asset/liability (양/꾸). Income/expense/equity are flat.
# Format: (code, name, type, is_group, parent_code or None, sort_order)
ACCOUNTS = [
    # ── 자산 (그룹: 양/꾸) ──
    ("1005", "양",              "asset", 1, None, 0),
    ("1001", "신한은행",        "asset", 0, "1005", 0),
    ("1007", "케이뱅크",        "asset", 0, "1005", 1),
    ("1010", "온통대전(충전액)", "asset", 0, "1005", 2),
    ("1100", "투자자산",        "asset", 0, "1005", 3),
    ("1012", "온통대전(캐시백)", "asset", 0, "1005", 4),
    ("1105", "온누리카드(충전액)", "asset", 0, "1005", 11),

    ("1006", "꾸",              "asset", 1, None, 1),
    ("1002", "KB국민은행",      "asset", 0, "1006", 1),
    ("1003", "산업은행",        "asset", 0, "1006", 0),
    ("1009", "새마을금고",      "asset", 0, "1006", 2),
    ("1011", "온통대전(충전액)", "asset", 0, "1006", 3),
    ("1013", "온통대전(캐시백)", "asset", 0, "1006", 4),
    ("1101", "투자자산",        "asset", 0, "1006", 7),
    ("1102", "삼성증권_예수금", "asset", 0, "1006", 8),
    ("1103", "토스증권_예수금", "asset", 0, "1006", 9),
    ("1104", "KB증권_예수금",   "asset", 0, "1006", 10),
    ("1106", "온누리카드(충전액)", "asset", 0, "1006", 12),

    # ── 부채 (그룹: 양/꾸) ──
    ("2004", "양",                     "liability", 1, None, 0),
    ("2003", "신한카드(#페이)",        "liability", 0, "2004", 0),
    ("2001", "KB국민카드(헬로모바일)", "liability", 0, "2004", 1),
    ("2007", "롯데카드(loca365)",      "liability", 0, "2004", 2),
    ("2013", "삼성카드",               "liability", 0, "2004", 5),
    ("2014", "미지급세금",             "liability", 0, "2004", 6),

    ("2005", "꾸",                     "liability", 1, None, 1),
    ("2002", "하나카드",               "liability", 0, "2005", 0),
    ("2006", "현대카드(네이버현대)",   "liability", 0, "2005", 1),
    ("2010", "KB국민카드(헬로모바일)", "liability", 0, "2005", 2),
    ("2011", "우리카드(교통카드)",     "liability", 0, "2005", 3),
    ("2012", "삼성카드",               "liability", 0, "2005", 4),
    ("2015", "미지급세금",             "liability", 0, "2005", 7),

    # ── 자본 ──
    ("3001", "기초자본",    "equity", 0, None, 0),

    # ── 수입 (flat, no groups) ──
    ("4001", "급여",                "income", 0, None, 0),
    ("4100", "투자손익",            "income", 0, None, 1),
    ("4006", "상여",                "income", 0, None, 2),
    ("4007", "연구수당",            "income", 0, None, 3),
    ("4005", "용돈",                "income", 0, None, 4),
    ("4002", "이자수입",            "income", 0, None, 5),
    ("4003", "기타수입",            "income", 0, None, 6),
    ("4102", "출장비,실비정산(양)", "income", 0, None, 8),

    # ── 비용 (flat, no groups) ──
    ("5001", "식료품/장보기",  "expense", 0, None, 0),
    ("5011", "카페/음료",      "expense", 0, None, 1),
    ("5016", "외식비",         "expense", 0, None, 2),
    ("5002", "교통비",         "expense", 0, None, 3),
    ("5003", "통신비",         "expense", 0, None, 4),
    ("5004", "의복",           "expense", 0, None, 5),
    ("5015", "화장품/미용",    "expense", 0, None, 6),
    ("5005", "의료비",         "expense", 0, None, 7),
    ("5014", "교육비",         "expense", 0, None, 8),
    ("5012", "보험료",         "expense", 0, None, 9),
    ("5017", "취미/여가",      "expense", 0, None, 10),
    ("5018", "주거비",         "expense", 0, None, 11),
    ("5013", "세금/이자",      "expense", 0, None, 12),
    ("5006", "기타비용",       "expense", 0, None, 13),
    ("5019", "경조사",         "expense", 0, None, 14),
    ("5007", "투자수수료",     "expense", 0, None, 15),
    ("5020", "전기차 충전",    "expense", 0, None, 16),
]

# First pass: create all accounts (without parent_id)
acct_objs = {}
for code, name, acct_type, is_group, _, sort_order in ACCOUNTS:
    a = Account(code=code, name=name, type=acct_type, is_group=is_group, sort_order=sort_order)
    db.add(a)
    db.flush()
    acct_objs[code] = a

# Second pass: set parent_id
for code, _, _, _, parent_code, _ in ACCOUNTS:
    if parent_code:
        acct_objs[code].parent_id = acct_objs[parent_code].id
db.commit()

A = acct_objs
now = datetime.now()

# ── 기초자산 세팅 (자본) ──
equity_acct = A["3001"]
init_balances = [
    # 양
    ("2025-10-31", "기초자산 - 신한은행", "1001", 3_500_000),
    ("2025-10-31", "기초자산 - 케이뱅크", "1007", 500_000),
    ("2025-10-31", "기초자산 - 온통대전(충전액)", "1010", 500_000),
    # 꾸
    ("2025-10-31", "기초자산 - KB국민은행", "1002", 20_000_000),
    ("2025-10-31", "기초자산 - 산업은행", "1003", 700_000),
    ("2025-10-31", "기초자산 - 새마을금고", "1009", 50_000),
    ("2025-10-31", "기초자산 - 온통대전(충전액)", "1011", 400_000),
    ("2025-10-31", "기초자산 - 온통대전(캐시백)", "1013", 150_000),
    ("2025-10-31", "기초자산 - 삼성증권_예수금", "1102", 600_000),
    ("2025-10-31", "기초자산 - 토스증권_예수금", "1103", 1_000_000),
]
for date_str, desc, code, amount in init_balances:
    entry = JournalEntry(
        entry_date=date_str, description=desc, memo="기초 잔액",
        is_confirmed=1,
        created_at=datetime.fromisoformat(date_str + "T00:00:00").isoformat(),
        updated_at=datetime.fromisoformat(date_str + "T00:00:00").isoformat(),
    )
    db.add(entry)
    db.flush()
    acct = A[code]
    if acct.type == "asset":
        db.add(JournalLine(entry_id=entry.id, account_id=acct.id, debit=amount, credit=0))
        db.add(JournalLine(entry_id=entry.id, account_id=equity_acct.id, debit=0, credit=amount))
    else:  # liability
        db.add(JournalLine(entry_id=entry.id, account_id=acct.id, debit=0, credit=amount))
        db.add(JournalLine(entry_id=entry.id, account_id=equity_acct.id, debit=amount, credit=0))
db.commit()

# ── Mock transactions (confirmed) ──
# 양: 1001 신한, 1010 온통대전충전, 2003 신한카드, 2001 KB국민카드, 2007 롯데카드, 2013 삼성카드
# 꾸: 1002 KB국민, 1003 산업, 1011 온통대전충전, 2002 하나카드, 2006 현대카드, 2010 KB국민카드, 2012 삼성카드
confirmed_txns = [
    # 11월
    ("2025-11-03", "급여 입금",             [("1002", 4_200_000, 0), ("4001", 0, 4_200_000)]),
    ("2025-11-03", "연구수당",              [("1003", 300_000, 0), ("4007", 0, 300_000)]),
    ("2025-11-05", "SK텔레콤 통신비",       [("5003", 59_000, 0), ("1001", 0, 59_000)]),
    ("2025-11-07", "이마트 장보기",          [("5001", 112_500, 0), ("2001", 0, 112_500)]),
    ("2025-11-09", "스타벅스 라떼",          [("5011", 5_800, 0), ("2006", 0, 5_800)]),
    ("2025-11-11", "교통카드 충전",          [("5002", 50_000, 0), ("2011", 0, 50_000)]),
    ("2025-11-13", "다이소 생활용품",        [("5006", 8_500, 0), ("2007", 0, 8_500)]),
    ("2025-11-15", "배달의민족 피자",        [("5016", 28_000, 0), ("2002", 0, 28_000)]),
    ("2025-11-17", "KB국민은행 이자",        [("1002", 1_050, 0), ("4002", 0, 1_050)]),
    ("2025-11-19", "점심 백반",              [("5016", 8_500, 0), ("2003", 0, 8_500)]),
    ("2025-11-20", "보험료 자동이체",        [("5012", 41_825, 0), ("1001", 0, 41_825)]),
    ("2025-11-22", "병원 정기검진",          [("5005", 35_000, 0), ("2003", 0, 35_000)]),
    ("2025-11-24", "쿠팡 겨울 패딩",         [("5004", 67_200, 0), ("2006", 0, 67_200)]),
    ("2025-11-25", "온통대전 성심당",        [("5001", 12_000, 0), ("1010", 0, 12_000)]),
    ("2025-11-25", "캐시백 - 성심당",        [("1012", 950, 0), ("4003", 0, 950)]),
    ("2025-11-27", "넷플릭스 구독",          [("5017", 17_000, 0), ("2003", 0, 17_000)]),
    ("2025-11-28", "유튜브 프리미엄",        [("5017", 14_900, 0), ("2003", 0, 14_900)]),
    ("2025-11-29", "전기차 충전 (E-pit)",     [("5020", 8_500, 0), ("2012", 0, 8_500)]),
    ("2025-11-30", "GS25 편의점",            [("5001", 5_600, 0), ("2012", 0, 5_600)]),
    # 12월
    ("2025-12-01", "급여 입금",             [("1002", 4_200_000, 0), ("4001", 0, 4_200_000)]),
    ("2025-12-01", "연구수당",              [("1003", 300_000, 0), ("4007", 0, 300_000)]),
    ("2025-12-03", "SK텔레콤 통신비",       [("5003", 59_000, 0), ("1001", 0, 59_000)]),
    ("2025-12-03", "관리비",                [("5018", 185_000, 0), ("1002", 0, 185_000)]),
    ("2025-12-05", "홈플러스 장보기",        [("5001", 105_000, 0), ("2001", 0, 105_000)]),
    ("2025-12-07", "스타벅스 아메리카노",    [("5011", 4_500, 0), ("2006", 0, 4_500)]),
    ("2025-12-08", "교통카드 충전",          [("5002", 50_000, 0), ("2011", 0, 50_000)]),
    ("2025-12-10", "크리스마스 선물 (옷)",   [("5004", 150_000, 0), ("2006", 0, 150_000)]),
    ("2025-12-12", "점심 국밥",              [("5016", 9_500, 0), ("2003", 0, 9_500)]),
    ("2025-12-14", "배달의민족 중식",        [("5016", 19_000, 0), ("2002", 0, 19_000)]),
    ("2025-12-15", "상여 입금",             [("1002", 2_000_000, 0), ("4006", 0, 2_000_000)]),
    ("2025-12-17", "KB국민은행 이자",        [("1002", 1_200, 0), ("4002", 0, 1_200)]),
    ("2025-12-18", "산업은행 이자",          [("1003", 850, 0), ("4002", 0, 850)]),
    ("2025-12-19", "약국 감기약",            [("5005", 8_500, 0), ("2003", 0, 8_500)]),
    ("2025-12-20", "보험료 자동이체",        [("5012", 41_825, 0), ("1001", 0, 41_825)]),
    ("2025-12-21", "전기차 충전 (차지비)",    [("5020", 12_300, 0), ("2006", 0, 12_300)]),
    ("2025-12-22", "CU 편의점",             [("5001", 4_200, 0), ("2010", 0, 4_200)]),
    ("2025-12-23", "온통대전 팔복집",        [("5016", 8_000, 0), ("1010", 0, 8_000)]),
    ("2025-12-23", "캐시백 - 팔복집",        [("1012", 635, 0), ("4003", 0, 635)]),
    ("2025-12-25", "결혼식 축의금",          [("5019", 100_000, 0), ("1001", 0, 100_000)]),
    ("2025-12-27", "넷플릭스 구독",          [("5017", 17_000, 0), ("2003", 0, 17_000)]),
    ("2025-12-28", "올리브영 화장품",        [("5015", 32_000, 0), ("2001", 0, 32_000)]),
    ("2025-12-30", "신한→KB 이체",          [("1002", 500_000, 0), ("1001", 0, 500_000)]),
    # 1월
    ("2026-01-02", "급여 입금",             [("1002", 4_200_000, 0), ("4001", 0, 4_200_000)]),
    ("2026-01-02", "연구수당",              [("1003", 300_000, 0), ("4007", 0, 300_000)]),
    ("2026-01-05", "SK텔레콤 통신비",       [("5003", 59_000, 0), ("1001", 0, 59_000)]),
    ("2026-01-05", "관리비",                [("5018", 195_000, 0), ("1002", 0, 195_000)]),
    ("2026-01-07", "홈플러스 장보기",       [("5001", 95_300, 0), ("2001", 0, 95_300)]),
    ("2026-01-10", "스타벅스 카페",         [("5011", 12_000, 0), ("2006", 0, 12_000)]),
    ("2026-01-12", "교통카드 충전",         [("5002", 50_000, 0), ("2011", 0, 50_000)]),
    ("2026-01-14", "학원비",               [("5014", 150_000, 0), ("1002", 0, 150_000)]),
    ("2026-01-15", "쿠팡 겨울옷",           [("5004", 89_000, 0), ("2006", 0, 89_000)]),
    ("2026-01-18", "KB국민은행 이자",       [("1002", 1_100, 0), ("4002", 0, 1_100)]),
    ("2026-01-20", "점심 순대국",           [("5016", 9_000, 0), ("2003", 0, 9_000)]),
    ("2026-01-22", "신한→KB 이체",          [("1002", 300_000, 0), ("1001", 0, 300_000)]),
    ("2026-01-25", "넷플릭스 구독",         [("5017", 17_000, 0), ("2003", 0, 17_000)]),
    ("2026-01-26", "전기차 충전 (E-pit)",    [("5020", 9_200, 0), ("2012", 0, 9_200)]),
    ("2026-01-28", "편의점 간식",           [("5001", 3_400, 0), ("2012", 0, 3_400)]),
    # 2월
    ("2026-02-01", "급여 입금",             [("1002", 4_200_000, 0), ("4001", 0, 4_200_000)]),
    ("2026-02-03", "이마트 장보기",         [("5001", 87_600, 0), ("2001", 0, 87_600)]),
    ("2026-02-04", "관리비",               [("5018", 210_000, 0), ("1002", 0, 210_000)]),
    ("2026-02-05", "SK텔레콤 통신비",       [("5003", 59_000, 0), ("1001", 0, 59_000)]),
    ("2026-02-08", "스타벅스 라떼",         [("5011", 5_800, 0), ("2006", 0, 5_800)]),
    ("2026-02-10", "교보문고 책 구매",      [("5014", 32_000, 0), ("2012", 0, 32_000)]),
    ("2026-02-12", "교통카드 충전",         [("5002", 50_000, 0), ("2011", 0, 50_000)]),
    ("2026-02-15", "배달의민족 치킨",       [("5016", 25_000, 0), ("2002", 0, 25_000)]),
    ("2026-02-18", "병원 진료비",           [("5005", 45_000, 0), ("2003", 0, 45_000)]),
    ("2026-02-20", "산업은행 이자",         [("1003", 980, 0), ("4002", 0, 980)]),
    ("2026-02-22", "올리브영 스킨케어",     [("5015", 15_000, 0), ("2007", 0, 15_000)]),
    ("2026-02-25", "온통대전 팔복집",       [("5016", 7_500, 0), ("1010", 0, 7_500)]),
    ("2026-02-25", "캐시백 - 팔복집",       [("1012", 595, 0), ("4003", 0, 595)]),
    ("2026-02-26", "출장비 정산",           [("1007", 102_400, 0), ("4102", 0, 102_400)]),
    ("2026-02-28", "유튜브 프리미엄",       [("5017", 14_900, 0), ("2003", 0, 14_900)]),
    ("2026-02-23", "전기차 충전 (차지비)",    [("5020", 10_800, 0), ("2006", 0, 10_800)]),
    ("2026-02-28", "보험료 자동이체",       [("5012", 41_825, 0), ("1001", 0, 41_825)]),
    # 3월
    ("2026-03-01", "급여 입금",             [("1002", 4_200_000, 0), ("4001", 0, 4_200_000)]),
    ("2026-03-02", "스타벅스 아메리카노",   [("5011", 6_500, 0), ("2001", 0, 6_500)]),
    ("2026-03-03", "교통카드 충전",         [("5002", 50_000, 0), ("2011", 0, 50_000)]),
    ("2026-03-03", "관리비",               [("5018", 190_000, 0), ("1002", 0, 190_000)]),
    ("2026-03-04", "SK텔레콤 통신비",       [("5003", 59_000, 0), ("1001", 0, 59_000)]),
    ("2026-03-05", "쿠팡 봄 자켓",          [("5004", 35_800, 0), ("2006", 0, 35_800)]),
    ("2026-03-06", "점심 김밥천국",         [("5016", 8_000, 0), ("2003", 0, 8_000)]),
    ("2026-03-07", "KB국민은행 이자",       [("1002", 1_250, 0), ("4002", 0, 1_250)]),
    ("2026-03-08", "GS25 편의점",           [("5001", 4_200, 0), ("2012", 0, 4_200)]),
    ("2026-03-09", "올리브영 화장품",       [("5015", 28_900, 0), ("2001", 0, 28_900)]),
    ("2026-03-10", "배달의민족 저녁",       [("5016", 22_000, 0), ("2002", 0, 22_000)]),
    ("2026-03-11", "약국 감기약",           [("5005", 12_500, 0), ("2003", 0, 12_500)]),
    ("2026-03-12", "KB국민→산업 이체",      [("1003", 500_000, 0), ("1002", 0, 500_000)]),
    ("2026-03-12", "넷플릭스 구독",         [("5017", 17_000, 0), ("2003", 0, 17_000)]),
    ("2026-03-14", "기타수입 - 중고장터",   [("1002", 55_000, 0), ("4003", 0, 55_000)]),
    ("2026-03-15", "장례식 조의금",         [("5019", 50_000, 0), ("1001", 0, 50_000)]),
    ("2026-03-16", "온통대전 팔복집",       [("5016", 3_000, 0), ("1010", 0, 3_000)]),
    ("2026-03-16", "캐시백 - 팔복집",       [("1012", 238, 0), ("4003", 0, 238)]),
    ("2026-03-18", "학원비",               [("5014", 150_000, 0), ("1002", 0, 150_000)]),
    ("2026-03-19", "전기차 충전 (E-pit)",    [("5020", 7_600, 0), ("2012", 0, 7_600)]),
    ("2026-03-20", "미용실",               [("5015", 20_000, 0), ("2003", 0, 20_000)]),
]

MEMO_MAP = {
    "크리스마스 선물 (옷)": "아내 선물 - 코트",
    "결혼식 축의금": "대학 동기 김철수",
    "장례식 조의금": "부장님 부친상",
    "출장비 정산": "대전 출장 2/25-26 교통+숙박",
    "교보문고 책 구매": "파이썬 알고리즘 인터뷰",
    "병원 정기검진": "연말 건강검진",
    "병원 진료비": "감기 진료",
    "기타수입 - 중고장터": "당근마켓 모니터 판매",
    "온통대전 성심당": "명란바게트 2, 튀소 1",
}
for date_str, desc, lines_data in confirmed_txns:
    entry = JournalEntry(
        entry_date=date_str, description=desc, memo=MEMO_MAP.get(desc, ""), is_confirmed=1,
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
        "content": "KB국민카드 승인 홍*동 32,000원 교보문고 03/21 10:23 일시불",
        "date": "2026-03-21", "desc": "교보문고 책 구매",
        "debit_code": "5014", "credit_code": "2001", "amount": 32_000,
    },
    {
        "source": "15771000", "source_name": "하나카드",
        "content": "하나카드 승인 홍*동 15,500원 맥도날드강남 03/21 12:45 일시불",
        "date": "2026-03-21", "desc": "맥도날드 점심",
        "debit_code": "5016", "credit_code": "2002", "amount": 15_500,
    },
    {
        "source": "15881688", "source_name": "KB국민카드",
        "content": "KB국민카드 승인 홍*동 4,800원 CU편의점역삼 03/22 15:10 일시불",
        "date": "2026-03-22", "desc": "CU 편의점",
        "debit_code": "5001", "credit_code": "2010", "amount": 4_800,
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
    ("스타벅스", "5011", "2006", 5),
    ("배달의민족", "5016", "2002", 3),
    ("SK텔레콤", "5003", "1001", 3),
    ("쿠팡", "5004", "2006", 2),
    ("넷플릭스", "5017", "2003", 2),
    ("GS25", "5001", "2012", 1),
    ("CU", "5001", "2010", 1),
    ("올리브영", "5015", "2001", 2),
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

# ── Stock holdings ──
p1 = StockPerson(name="양")
p2 = StockPerson(name="꾸")
db.add_all([p1, p2])
db.flush()

a1 = StockAccount(person_id=p1.id, brokerage="키움증권", name="주식계좌", account_type="cash")
a1b = StockAccount(person_id=p1.id, brokerage="키움증권", name="연금저축", account_type="pension")
a2 = StockAccount(person_id=p2.id, brokerage="삼성증권", name="ISA", account_type="cash",
                   linked_account_id=A["1102"].id)
a2b = StockAccount(person_id=p2.id, brokerage="토스증권", name="주식계좌", account_type="cash",
                    linked_account_id=A["1103"].id)
a3 = StockAccount(person_id=p2.id, brokerage="KB증권", name="연금저축", account_type="pension",
                   linked_account_id=A["1104"].id)
db.add_all([a1, a1b, a2, a2b, a3])
db.flush()

stock_data = [
    (a1.id, "005930", "삼성전자", None, 50, 72_000, 56_800),
    (a1.id, "000660", "SK하이닉스", None, 10, 128_000, 185_500),
    (a1.id, "035720", "카카오", None, 30, 55_000, 38_600),
    (a1b.id, "360750", "TIGER S&P500", None, 200, 18_500, 21_300),
    (a1b.id, "379800", "KODEX 미국S&P500TR", None, 150, 15_200, 17_800),
    (a2.id, "005930", "삼성전자", None, 100, 68_500, 56_800),
    (a2.id, "373220", "LG에너지솔루션", None, 5, 420_000, 365_000),
    (a2b.id, "035420", "NAVER", None, 20, 210_000, 188_000),
    (a2b.id, "051910", "LG화학", None, 8, 550_000, 285_000),
    (a3.id, "360750", "TIGER S&P500", None, 300, 17_800, 21_300),
]
for acct_id, ticker, name, exchange, qty, avg, cur in stock_data:
    db.add(StockHolding(
        account_id=acct_id, ticker=ticker, name=name, exchange=exchange,
        quantity=qty, avg_price=avg, current_price=cur,
        price_updated_at=now.isoformat(),
    ))
db.commit()

# ── Real estate ──
db.add(RealEstate(name="서울 아파트", value=850_000_000, memo="강남구 34평"))
db.add(RealEstate(name="경기 오피스텔", value=220_000_000, memo="분당 투자용"))
db.commit()

db.close()

# Summary
n_groups = sum(1 for *_, g, _, _ in ACCOUNTS if g)
n_leaves = sum(1 for *_, g, _, _ in ACCOUNTS if not g)
print("Mock data seeded (production structure):")
print(f"  - {len(ACCOUNTS)} accounts ({n_groups} groups, {n_leaves} leaves)")
print(f"  - Groups: 양/꾸 on asset+liability only, flat income/expense")
print(f"  - {len(init_balances)} initial balance entries (2025-10-31)")
print(f"  - {len(confirmed_txns)} confirmed entries (Nov 2025 - Mar 2026)")
print(f"  - {len(pending_sms)} pending entries (review queue)")
print(f"  - 1 failed message")
print(f"  - {len(rules)} category rules")
print(f"  - 2 stock persons, 5 accounts, {len(stock_data)} holdings")
print(f"  - 2 real estate properties")
