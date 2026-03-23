# 두리부기 (duri-bugi)

Android 알림/SMS를 자동으로 복식부기 가계부에 기록하는 셀프호스팅 웹 앱.

카드 승인, 은행 입출금 알림을 AI(Google Gemini)가 파싱하여 차변/대변 분개를 자동 생성합니다.

## 구조

```mermaid
graph LR
    A["📱 Android\nduri-bugi-app"] -->|webhook| B["🖥️ Self-hosted 서버\nduri-bugi\n(FastAPI + SQLite)"]
    B -->|HTTP| C["🤖 Gemini API\nAI 파싱 · 차변/대변"]
    C -->|응답| B
    B -->|브라우저| D["🌐 웹 UI\n가계부 조회 · 검토/승인"]
```

> **필수 요건**: Self-hosted 서버 + Gemini API 키

## 주요 기능

- **웹훅 수신** — Android 앱에서 카드/은행 알림을 실시간 수신
- **AI 자동 파싱** — Gemini 2.5 Flash로 금액, 가맹점, 계정 자동 매칭
- **복식부기** — 차변/대변 분개장 기반 가계부
- **멀티 디바이스** — `deviceName`으로 기기별 계정 분리 (예: 꾸_하나카드, 양_신한카드)
- **검토 워크플로우** — AI 파싱 결과를 승인/수정/거부
- **계정 관리** — 드래그&드롭 정렬, 인라인 편집, 그룹/하위 계정 지원
- **대시보드** — 자산/부채/수입/지출 요약, 월별 추이 차트
- **멀티유저 PIN 인증** — 사용자별 PIN 로그인, 감사 로그
- **카테고리 규칙** — 반복 가맹점 자동 분류 학습

## 기술 스택

- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Alpine.js + SortableJS (SPA, 빌드 없음)
- **AI**: Google Gemini 2.5 Flash
- **배포**: Docker

## 빠른 시작

### Docker (권장)

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일 편집 — GEMINI_API_KEY, APP_PINS 등 설정

# 2. 빌드 & 실행
docker compose up -d --build

# 3. 접속
# http://localhost:8000
```

### 로컬 개발

```bash
# Python 3.12+
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `GEMINI_API_KEY` | Y | Google Gemini API 키 |
| `APP_PINS` | N | 멀티유저 PIN (`123456:이름,789012:이름`) |
| `SESSION_SECRET` | N | 쿠키 서명 시크릿 (기본값 있음) |
| `WEBHOOK_SECRET` | N | 웹훅 HMAC 검증 시크릿 |
| `SESSION_DAYS` | N | 세션 유효기간 일수 (기본: `7`) |
| `DATABASE_URL` | N | DB 경로 (기본: `sqlite:///ledger.db`) |

## 웹훅 포맷

Android 앱에서 아래 JSON을 `POST /api/webhook`으로 전송:

```json
{
  "type": "NOTIFICATION",
  "source": "com.shinhancard",
  "sourceName": "신한카드",
  "deviceName": "꾸폰",
  "title": "",
  "content": "신한카드 승인 15,200원 스타벅스 일시불 03/16 14:23",
  "timestamp": 1710568800000
}
```

## 프로젝트 구조

```
app/
├── main.py              # FastAPI 앱, 마이그레이션, 시드 데이터
├── config.py            # 환경변수 설정
├── database.py          # SQLAlchemy 엔진/세션
├── models.py            # ORM 모델 (Account, JournalEntry, AuditLog 등)
├── schemas.py           # Pydantic 스키마
├── routers/
│   ├── webhook.py       # 웹훅 수신 & 백그라운드 처리
│   ├── transactions.py  # 거래 CRUD
│   ├── accounts.py      # 계정 관리
│   ├── dashboard.py     # 대시보드 & 리포트
│   ├── rules.py         # 카테고리 규칙
│   └── auth.py          # PIN 인증
├── services/
│   ├── ai_parser.py     # Gemini AI 메시지 파싱
│   ├── ledger.py        # 분개 생성 로직
│   └── audit.py         # 감사 로그
└── static/              # 프론트엔드 (HTML/JS/CSS)
```

## 라이선스

MIT
