"""기존 데이터 유지, 다양한 상태/형태의 mock 메시지만 추가."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import json
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import RawMessage

db = SessionLocal()
now = datetime.now()

def ts(hours_ago):
    return int((now - timedelta(hours=hours_ago)).timestamp() * 1000)

def ai(txn_type, amount, merchant, debit, credit, confidence=0.95, memo="일시불", date=None):
    return json.dumps({
        "transaction_type": txn_type,
        "amount": amount,
        "merchant": merchant,
        "card_or_account": "",
        "date": date or now.strftime("%Y-%m-%d"),
        "memo": memo,
        "suggested_debit_code": debit,
        "suggested_credit_code": credit,
        "confidence": confidence,
    }, ensure_ascii=False)

messages = [
    # ── pending (AI 파싱 완료, 검토 대기) ──
    RawMessage(
        source_type="SMS", source="15880000", source_name="신한카드",
        device_name="양", title="",
        content="[신한카드] 승인 김*영 12,000원 스타벅스강남 04/03 09:15 일시불 (누적 238,500원)",
        timestamp=ts(1), status="pending",
        ai_result=ai("card_payment", 12000, "스타벅스", "5011", "2003", 0.97, "일시불"),
    ),
    RawMessage(
        source_type="SMS", source="15881688", source_name="KB국민카드",
        device_name="꾸", title="",
        content="KB국민카드 승인 홍*동 48,500원 이마트왕십리 04/03 11:32 일시불",
        timestamp=ts(2), status="pending",
        ai_result=ai("card_payment", 48500, "이마트", "5001", "2001", 0.92, "일시불"),
    ),
    RawMessage(
        source_type="NOTIFICATION", source="com.kakaobank.channel", source_name="카카오뱅크",
        device_name="꾸", title="입금 알림",
        content="카카오뱅크\n입금 500,000원\n잔액 1,234,567원\n04/03 14:00",
        timestamp=ts(3), status="pending",
        ai_result=ai("deposit", 500000, "", "1002", "4001", 0.78, "급여일부"),
    ),
    RawMessage(
        source_type="SMS", source="15771000", source_name="하나카드",
        device_name="꾸", title="",
        content="하나카드 승인 홍*동 22,000원 배달의민족 04/02 19:45 일시불",
        timestamp=ts(14), status="pending",
        ai_result=ai("card_payment", 22000, "배달의민족", "5016", "2002", 0.95, "일시불"),
    ),
    RawMessage(
        source_type="SMS", source="15886000", source_name="현대카드",
        device_name="꾸", title="",
        content="[현대카드] 홍*동님 35,000원 쿠팡 04/02 22:10 승인 (잔여한도 2,450,000원)",
        timestamp=ts(16), status="pending",
        ai_result=ai("card_payment", 35000, "쿠팡", "5004", "2006", 0.89, "일시불"),
    ),

    # ── parsed (분개 생성됨, 승인 대기) ──
    RawMessage(
        source_type="SMS", source="15881688", source_name="KB국민카드",
        device_name="양", title="",
        content="KB국민카드 승인 김*영 6,500원 메가커피역삼 04/01 08:50 일시불",
        timestamp=ts(28), status="parsed",
        ai_result=ai("card_payment", 6500, "메가커피", "5011", "2001", 0.96, "일시불"),
    ),
    RawMessage(
        source_type="NOTIFICATION", source="com.shinhan.sbanking", source_name="신한은행",
        device_name="양", title="출금",
        content="신한은행 출금 50,000원\n교통카드 충전\n잔액 1,820,300원",
        timestamp=ts(30), status="parsed",
        ai_result=ai("withdrawal", 50000, "교통카드충전", "5002", "1001", 0.88, "교통카드"),
    ),

    # ── approved (승인 완료) ──
    RawMessage(
        source_type="SMS", source="15559999", source_name="롯데카드",
        device_name="양", title="",
        content="[롯데카드] loca365 김*영 17,000원 넷플릭스 03/31 00:01 일시불",
        timestamp=ts(48), status="approved",
        ai_result=ai("card_payment", 17000, "넷플릭스", "5017", "2007", 0.99, "일시불"),
    ),
    RawMessage(
        source_type="SMS", source="15881688", source_name="KB국민카드",
        device_name="꾸", title="",
        content="KB국민카드 승인 홍*동 8,000원 GS25역삼점 03/30 13:20 일시불",
        timestamp=ts(60), status="approved",
        ai_result=ai("card_payment", 8000, "GS25", "5001", "2010", 0.94, "일시불"),
    ),

    # ── cancelled / 승인취소 ──
    RawMessage(
        source_type="SMS", source="15881688", source_name="KB국민카드",
        device_name="양", title="",
        content="KB국민카드 승인취소 김*영 32,000원 교보문고강남 03/28 15:04",
        timestamp=ts(72), status="pending",
        ai_result=ai("cancellation", 32000, "교보문고", "2001", "5014", 0.93, "승인취소"),
    ),

    # ── 낮은 신뢰도 ──
    RawMessage(
        source_type="NOTIFICATION", source="com.nhn.android.nmap", source_name="네이버지도",
        device_name="꾸", title="결제 완료",
        content="네이버페이 결제 완료\n금액: 14,900원\n가맹점: 알 수 없음",
        timestamp=ts(36), status="pending",
        ai_result=ai("card_payment", 14900, "", "5006", "2006", 0.41, ""),
    ),

    # ── rejected ──
    RawMessage(
        source_type="SMS", source="02-1234-5678", source_name="스팸",
        device_name="양", title="",
        content="[이벤트] 지금 바로 100만원 당첨! 클릭하세요 http://spam.example.com",
        timestamp=ts(96), status="rejected",
        ai_result=ai("unknown", 0, "", "5006", "5006", 0.02, ""),
    ),

    # ── failed ──
    RawMessage(
        source_type="NOTIFICATION", source="com.samsung.android.messaging", source_name="문자",
        device_name="꾸", title="",
        content="귀하의 소포가 도착했습니다. 수령 확인: [배송조회]",
        timestamp=ts(50), status="failed",
        ai_result=None,
    ),
    RawMessage(
        source_type="SMS", source="15441234", source_name="온통대전",
        device_name="양", title="",
        content="온통대전 체크카드 승인 3,000원 팔복집 04/02 18:30 잔액 47,000원",
        timestamp=ts(18), status="failed",
        ai_result=json.dumps({"error": "account mapping failed"}),
    ),

    # ── duplicate ──
    RawMessage(
        source_type="SMS", source="15881688", source_name="KB국민카드",
        device_name="꾸", title="",
        content="KB국민카드 승인 홍*동 22,000원 배달의민족 04/02 19:45 일시불",
        timestamp=ts(14) + 1000, status="duplicate",
        ai_result=ai("card_payment", 22000, "배달의민족", "5016", "2002", 0.95, "일시불"),
    ),
]

db.add_all(messages)
db.commit()
db.close()

print(f"메시지 {len(messages)}건 추가 완료")
