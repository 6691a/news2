# 주식 분석 LLM 시스템 설계 문서

> **버전**: v0.9 · **작성일**: 2026-07-09 · **갱신**: 2026-07-31 (기업행사·SKHY ADR·국채·원자재 선물 설계 추가)
> **주의**: 이 문서는 첫 설계 초안 기반이다. 코드와 다르면 코드가 소스 오브 트루스 — 구현하며 계속 갱신한다.
> **목적**: 확정된 추적 종목 9개(한국 2 + 미국 7, §1.4)에 대한 뉴스·시세 기반 LLM 분석/시그널 생성 시스템의 전체 설계
> **성격**: 개인 분석 도구 및 AI/LLM 엔지니어링 포트폴리오 프로젝트 (자동매매 아님)

---

## 1. 개요

### 1.1 시스템 정의

뉴스, 공시, 시세, 매크로 지표(지수·선물·환율)를 수집하고, RAG와 LLM을 결합해
관심 종목에 대한 **영향 분석과 시그널**을 생성하는 시스템.

### 1.2 핵심 설계 원칙

| 원칙 | 내용 |
|---|---|
| LLM = 해석·판단 엔진 | LLM에게 가격 예측을 직접 시키지 않는다. 뉴스/이벤트의 의미 해석, 종목 영향 판단, 근거 생성을 담당 |
| 하이브리드 시그널 | LLM 정성 분석 + 기술적 지표(pandas 계산) + 룰 기반 로직을 결합 |
| 평가 우선 | 시그널 → 실제 수익률 백테스트 파이프라인을 초기부터 구축. 모든 개선은 이 지표로 검증 |
| API 우선, 파인튜닝은 후순위 | 초기에는 Claude/Gemini API 사용. 운영 로그가 쌓인 뒤 오픈소스 LLM 파인튜닝 |
| 범위 한정 | 전 종목이 아닌 확정된 9개 종목(§1.4)만 대상. 인프라를 경량으로 유지 |

### 1.3 명시적 비목표 (Non-goals)

- 자동매매 실행 (자본시장법상 라이선스 이슈, 프로젝트 범위 외)
- 투자 자문 서비스화 (출력물에 "검증되지 않은 분석" 고지 포함)
- 전 종목 커버리지

### 1.4 추적 대상 종목 (확정)

| 시장 | 티커 | 종목명 | 유형 | 비고 |
|---|---|---|---|---|
| KRX | 005930 | 삼성전자 | 개별주 | KIS API 수집 |
| KRX | 000660 | SK하이닉스 | 개별주 | NVDA HBM 공급 관계 → 관계 레이어 핵심 노드 |
| NASDAQ | AAPL | 애플 | 개별주 | |
| NASDAQ | GOOGL | 알파벳(구글) | 개별주 | GOOGL(Class A) 기준, GOOG는 별칭 등록 |
| NASDAQ | MSFT | 마이크로소프트 | 개별주 | |
| NASDAQ | META | 메타 | 개별주 | |
| NASDAQ | NVDA | 엔비디아 | 개별주 | |
| NASDAQ | QQQ | Invesco QQQ | ETF | 나스닥100 추종 — 시그널 대상 겸 시장 벤치마크 |
| NYSE Arca | SPY | SPDR S&P 500 | ETF | S&P500 추종 — 시그널 대상 겸 시장 벤치마크 |

**종목 구성 관련 설계 메모**:

- **ETF 이중 역할**: QQQ/SPY는 개별 시그널 대상이면서 §8 백테스트의 **시장 기준선**
  역할을 겸한다 (개별주 시그널의 초과수익 여부를 이 벤치마크 대비로 평가).
- **높은 상관 구조**: 미국 5개 개별주는 모두 QQQ/SPY의 상위 구성 종목이므로,
  빅테크 공통 이벤트(금리·AI 규제 등)는 매크로 시그널로 묶어 처리하고
  종목별 시그널은 개별 고유 이벤트에 집중한다.
- **뉴스 필터 기준**: ① 9개 종목 직접 언급, ② 관계 레이어 1~2홉 이내 엔티티
  (TSMC, 반도체 업황, AI 인프라 등) 언급, ③ 매크로(연준·환율·지수 급변) —
  이 세 범주 외 뉴스는 ①차 필터에서 제외.
- **엔티티 별칭 등록 필수**: 예) 삼성전자 = {005930, Samsung Electronics, 삼전},
  알파벳 = {GOOGL, GOOG, Google, 구글, Alphabet}.

### 1.5 매크로 지표 (시장 컨텍스트)

개별 시그널 대상이 아닌, 분석 컨텍스트와 관계 레이어의 매크로 노드로 사용하는 지표.
**T1 = 항상 LLM 컨텍스트에 요약 주입 / T2 = 급변·이벤트 시에만 참조 /
T3 = 수집·저장만 하고 분석 미투입 (히스토리 축적 목적, 백테스트 검증 후 승격).**

| 분류 | 지표 | 수집 소스 | 티어 | 비고 |
|---|---|---|---|---|
| 지수 | S&P500, NASDAQ, KOSPI, VIX | yfinance / KIS API | T1 | |
| 지수 | **필라델피아 반도체지수 (SOX)** | yfinance `^SOX` | T1 | 삼성전자·하이닉스·NVDA 직결 — 반도체 섹터 체온계 |
| 지수 (중국) | **상하이종합, 항셍, 항셍테크** | yfinance `000001.SS`, `^HSI`, HSTECH | T2 | 중국 경기·기술주 심리 |
| 지수 (일본) | **Nikkei225** | yfinance `^N225` | T2 | 한국장과 시간대 중첩 — 아시아 위험선호 지표. 엔화 강세 + 닛케이 급락 = 리스크 오프 신호 |
| 지수 (대만) | **TAIEX (대만가권)** | yfinance `^TWII` | T2 | 반도체 공급망 심리 |
| 지수 | **러셀2000 (소형주)** | yfinance `^RUT` | T2 | QQQ 대비 상대 강도 → 메가캡→소형주 순환매·시장 폭(breadth) 감지, 금리 민감 지표 |
| 개별 참조 | **TSMC ADR (TSM)** | yfinance `TSM` | T2 | 시그널 대상 아님 — NVDA·AAPL·반도체 공급망 핵심 참조 가격 |
| 개별 참조 | **SK하이닉스 ADR (SKHY)** | KIS 해외주식 / yfinance | T1 | `000660` 전용 야간 선행값 — 1 ADR=보통주 0.1주, USD/KRW를 적용한 원화 환산가격·괴리율 사용 |
| 선물 | S&P500·NASDAQ 지수 선물 | yfinance | T1 | 프리마켓 방향성 |
| 선물 | **KOSPI200 선물 (가격 + 베이시스)** | KIS API | T1 | 외국인 포지션(§수급)과 결합 해석 |
| 환율 | USD/KRW | yfinance (`KRW=X`) | T1 | 수출주 실적·외인 수급 |
| 환율 | USD/JPY (엔/달러) | yfinance (`JPY=X`) | T1 | 엔캐리 트레이드 — 급격한 엔화 강세 = 유동성 축소 신호 |
| 환율 | JPY/KRW (엔/원) | yfinance (`JPYKRW=X`) | T2 | 수출 경합 맥락 |
| 환율 | **USD/CNY·CNH (위안)** | yfinance (`CNY=X`, `CNH=X`) | T2 | 역외 CNH가 시장 스트레스를 더 빠르게 반영 — 급변 시 T1 승격. 위안 절하 = 리스크 오프 |
| 환율 | **달러인덱스 (DXY)** | yfinance (`DX-Y.NYB`) | T1 | 글로벌 달러 유동성 종합 |
| 채권 (미) | **국채 2Y / 10Y / 30Y 금리 + 10Y-2Y 스프레드** | FRED API (`DGS2`, `DGS10`, `DGS30`) + yfinance `^TNX` | T1 | 빅테크 밸류에이션 직결, 장단기 역전 = 침체 신호 |
| 선물 | **미 10년물 국채선물 ZN (가격)** | yfinance 상당(Yahoo chart) `ZN=F` | T2 | 아시아 세션 미 금리 방향성 신호 — 수익률 환산(CTD) 안 함, 확정 정산가 미수집 |
| 채권 (한) | **국고채 3Y / 10Y + 한은 기준금리** | 한국은행 ECOS OpenAPI | T1 | 국내 금리 환경 |
| 선물 | **한국 3년 국채선물 (최근월물)** | KIS 국내선물옵션 API | T2 | 현물금리 휴장 중 한은 정책 기대·야간 금리 방향 반영 — 만기 롤 구간 분리 |
| 채권 (일) | **일본 국채 10Y 금리 + BOJ 금리 결정·총재 발언** | 크롤링(투자정보 사이트) + econ_calendar 이벤트 | T2 | 엔캐리 해석 보강 — JGB 금리 급등·BOJ 긴축 = 엔캐리 청산 리스크 |
| 반도체 | **TSMC 월매출** | TSMC IR 발표 (매월 10일경) 크롤링 | T1 | 글로벌 반도체 수요의 월 단위 최선행 지표 — NVDA·AAPL·국내 반도체 공통 |
| 반도체 | **DRAM / NAND 현물가 (+ HBM 수요 뉴스)** | 초기: 뉴스 기반 이벤트 추출 + 주간 크롤링 (TrendForce 등 유료 API는 추후 검토) | T1 | 삼성전자·SK하이닉스 실적의 가장 직접적인 선행 지표 |
| 원자재 선물 | **금(GC)·은(SI)·구리(HG)·WTI 원유(CL) 최근월물** | KIS 해외선물 REST·웹소켓 | T2 | 주 5일 약 23시간 거래 — 금은 위험회피·실질금리, 은·구리는 경기·산업수요, 유가는 인플레 신호. 월물 롤 구간 분리 |
| 경기지표 (미) | **CPI, 고용(NFP), ISM PMI, FOMC 금리 결정** | FRED API + 경제 캘린더 | T1 | 발표 이벤트 자체가 시장 단위 시그널 트리거 |
| 경기지표 (중) | **제조업 PMI (국가통계국·차이신), 산업생산** | 발표치 수집 (FRED `CHNPMI` 대용 / 캘린더 크롤링) | T2 | 중국 경기 → 한국 수출·반도체 수요 경로 |
| 경기지표 (한) | **수출입 통계 — 특히 반도체 수출액** | 관세청 수출입 통계 (10일 단위 발표) | T1 | 삼성전자·하이닉스 실적의 최선행 지표 |
| 수급 | 한국 시장·종목별 외국인/기관 순매수 | KIS API 투자자별 매매동향 | T1 | 삼성전자·하이닉스 단기 수급의 핵심 변수 |
| 수급 | KOSPI200 선물 외국인 포지션 | KIS API 선물옵션 매매동향 | T1 | 선물 수급 → 현물 방향성 선행 지표 |
| 수급 | **프로그램 매매 순매수 (시장·종목별)** | KIS API 프로그램매매 동향 | T3 | 외국인 순매수의 성격 구분 (차익 물량 vs 실질 매수) — Day 1부터 축적 |
| 수급 | **공매도 거래대금·잔고 (삼전·하이닉스)** | KRX 공매도통합포털 + KIS API | T3 | **잔고는 T+2 공시 — `published_at` 필수 기록** (look-ahead bias 방지) |
| 수급 | **대차잔고** | 금융투자협회 FreeSIS 크롤링 (일 1회) | T3 | 공매도 대기 물량 추정 |
| 수급 | **신용융자 잔고** | 금융투자협회 FreeSIS 크롤링 (일 1회) | T3 | 개인 레버리지 과열도 |

**매크로 지표 설계 메모**:

- 일반 지표 수집 주기는 15분~1시간이며, 원자재 선물은 거래 세션 중 WebSocket으로 수집한다
  (채권 금리·경기지표는 일 1회 / 발표 시점).
- 저장은 §4.2 시계열 테이블을 공용 사용 (`instruments`에 `type='macro'`로 등록).
- LLM 분석(§7) 시 ②컨텍스트 수집 단계에서 **T1 지표의 최근 스냅샷**
  (금리 수준·변화, 환율 추세, VIX, SOX, 수급)을 요약 주입. T2는 임계치 초과
  변동(예: 위안 1% 이상 절하) 시에만 컨텍스트에 포함.
- **경제 이벤트 캘린더**: FOMC, 미국 CPI/고용, 한은 금통위, 중국 PMI, 한국 수출입
  발표 일정을 별도 테이블(`econ_calendar`)로 관리. 발표 직전에는 시그널을 보수적으로
  조정하고, 발표 직후에는 시장 단위(QQQ/SPY/KOSPI) 분석을 트리거.
- **지표 비대화 방지 원칙**: 모든 지표는 ②컨텍스트 요약 또는 룰 로직에서 실제로
  사용될 때만 유지. 3개월간 어떤 시그널에도 기여하지 않은 지표는 수집 중단 검토.
- **의도적 제외 — 다우존스(DJIA)**: S&P500과 정보 중복이 크고 가격가중 방식의
  구조적 한계로 분석 기준 가치가 낮아 수집하지 않음. 러셀2000은 반대로
  메가캡 집중 포트폴리오의 순환매 리스크 감지용으로 채택 (위 표 참조).
- **Phase 2 백로그 (당장 미수집)**: VKOSPI(수집 난이도 — 평가 대시보드 구축 후 필요 시),
  CSI300(상하이·항셍과 중복), **China A50 선물(SGX 거래로 본토장 폐장 시간에도 중국 심리
  반영 — Phase 2 장중 실시간 대응 도입 시 재검토)**, TOPIX(Nikkei와 중복 — 일본 개별
  섹터 분석 시 재검토), PBOC 고시환율(뉴스 이벤트로 감지, 수치는 USD/CNY·CNH로 대체).
  → 백테스트에서 기존 지표의 설명력 한계가 확인될 때 순차 도입.
- **온디맨드 조회 지표**: USD/TWD 등 "평상시 불필요, 이벤트 시에만 유의미"한 지표는
  정기 수집 대신 **LangGraph ②컨텍스트 수집 노드가 조건 충족 시(예: TAIEX·TSM 급락,
  대만 지정학 뉴스) yfinance를 즉석 조회**하는 방식으로 처리. 저장 파이프라인 없이
  참조 가능하며, 백로그 지표 전반에 재사용 가능한 범용 패턴.
- **T3(수집 전용) 도입 근거**: 프로그램 매매·공매도·대차잔고·신용융자는 분석 투입은
  나중이지만 **과거분 소급 수집이 번거로워** Day 1부터 축적. 수집 비용이 낮고
  (KIS API 엔드포인트 추가 + FreeSIS 일 1회 크롤링), 백테스트 검증 후 T2/T1 승격.
  공시 지연 데이터(공매도 잔고 T+2 등)는 백테스트 시 `published_at` 기준으로만 사용.
- **T2 우선 도입 원칙**: 신규 지표는 T2로 시작하고, 백테스트 기여도가 검증된
  것만 T1으로 승격한다.
- **매크로 이벤트 시그널**: FOMC, 급격한 금리/환율 변동은 종목별이 아닌
  시장 단위(QQQ/SPY) 시그널로 1회 처리 — §1.4 중복 분석 방지 원칙과 동일.
- **국채선물 해석**: 선물 가격과 금리는 반대로 움직이므로 금리 압력 신호는 선물 수익률의
  부호를 반대로 사용한다. 최근월물 코드·만기·거래량·미결제약정을 함께 저장하고,
  만기 교체 전후의 원가격을 그대로 이어 붙이지 않는다.
- **원자재 선물 해석**: COMEX `GC`·`SI`·`HG`와 NYMEX `CL`의 거래량 기준 최근월물을 사용한다. 표준 계약은
  24/7이 아니라 일일 정기 중단이 있는 주 5일 약 23시간 거래이므로 휴장 중 무수신을
  장애로 보지 않는다. 원가격은 월물별로 보존하고 롤 전후 수익률만 연결한다.
- **의도적 제외 — 금리 옵션 체인**: 미국 10년물 옵션은 행사가·만기 전체를 수집하지 않는다.
  방향 신호보다 기대 변동성 정보가 필요해질 때 CME 10년물 CVOL 같은 단일 집계 지표를
  T3로 검토한다. KRX에는 한국 3년 국채선물에 대응하는 국채 옵션 상품이 없어 수집 대상이 아니다.

---

## 2. 전체 아키텍처

```mermaid
flowchart TD
    A["<b>1. 데이터 수집 (Ingestion)</b><br/>뉴스 · 시세 · 지수/선물/환율 · 공시<br/>Celery Beat / APScheduler 스케줄링"]
    B["<b>2. 저장 · 전처리 (Storage)</b><br/>PostgreSQL (시계열 + 원문 + pgvector)<br/>중복 제거 · NER 종목 매핑 · 필터링"]
    C["<b>3. 검색 (RAG)</b><br/>벡터 + 키워드(BM25) 하이브리드<br/>시간 가중치 + 메타데이터 필터<br/>경량 관계 레이어 (멀티홉 영향 전파)"]
    D["<b>4. LLM 분석 (LangGraph)</b><br/>저비용 필터 → 컨텍스트 수집 → 상위 모델 분석<br/>Structured Output (JSON) · Langfuse 추적"]
    E["<b>5. 시그널 · 평가 (Output & Eval)</b><br/>데일리 리포트 · 실시간 알림 · 백테스트"]

    A --> B --> C --> D --> E
```

**기술 스택**: FastAPI · LangGraph · PostgreSQL(+pgvector) · Celery · structlog · Langfuse
· Claude/Gemini API (Phase 3에서 오픈소스 LLM + LoRA 추가 검토)

---

## 3. 데이터 수집 레이어

### 3.0 수집 원칙 — 이중 그레인 (모든 지표에 적용)

새 시세·지표를 붙일 때는 **두 그레인을 모두 확보할 수 있는지 먼저 확인하고, 가능하면
둘 다 수집한다.** 한쪽만 있으면 시스템의 절반이 성립하지 않는다.

| 그레인 | 목적 | 성질 | 예 |
|---|---|---|---|
| **장중 1분봉·잠정치** | 당일 흐름 판단, 장중 대응 | 갱신 중인 값. 사후 정정될 수 있다 | `us_treasury_bars`, 투자자 수급 `is_provisional=true` |
| **장 마감 확정값** | 과거 분석·백테스트(§8.2)·예측 | 소스 오브 트루스. 수정주가·정산가 반영 | `ohlcv` `timeframe='1d'`, `us_treasury_yield_daily`, 수급 확정치 |

- **확정값이 없으면 백테스트가 성립하지 않는다.** §8.2의 1/3/5일 수익률은 확정 일봉에서만
  계산할 수 있고, 실시간 tick으로 대신할 수 없다 — 프로세스가 죽은 구간이 영구 결손이 되고,
  수정주가가 반영되지 않으며, 과거 백필 경로가 없기 때문이다.
- **장중 값이 없으면 당일 대응을 할 수 없다.** 확정값은 그날 장이 끝난 뒤에야 나온다.
- 두 그레인은 **서로 덮어쓰지 않고 각각 저장**한다. 장중 잠정치를 확정치로 갱신해 버리면
  "외국인이 몇 시부터 순매수로 돌았는가" 같은 장중 흐름을 사후에 재구성할 수 없다.
- **확정값 소스가 없는 지표는 "없다"는 사실을 남긴다.** 조사하고 없는 것과 빠뜨린 것이
  구분되어야 한다. 현재 해당하는 것: **ZN 국채선물**(무료 공식 정산가 없음 — 방향성 신호 전용).
- 확정값에는 **과거 백필 경로**를 함께 만든다(아래 백필 기준 참조).
  1분봉은 소스 보관 기간이 짧아(Yahoo 30일) 백필이 불가능하므로, 가동 시작 시점부터가 곧
  데이터의 시작이다.

#### 백필 기준 (모든 확정값 지표 공통)

**기준 시작일은 `2025-01-01`이다** (`app/core/collection.py`의 `BACKFILL_START`).
새 지표를 붙일 때도 이 상수를 가져다 쓴다 — 지표마다 다른 날짜를 쓰면 백테스트 구간을
맞추는 일이 지표 수만큼 늘어난다.

- **소스가 그 날짜부터 주지 못하면 실패로 보지 않고, 소스가 주는 가장 이른 데이터부터 담는다.**
  상장이 2025년 이후이거나(예: 신규 ETF), 소스 보관 기간이 짧은 경우가 여기 해당한다.
  빈 구간을 메우려고 다른 소스를 끌어오지 않는다 — 소스가 섞이면 조정 기준이 달라져
  같은 계열 안에서 가격이 튄다.
- **실제로 어디부터 담겼는지는 수집 로그의 `first_ts`로 확인한다.** "요청은 2025-01인데
  데이터는 2025-06부터"인 상태가 로그만 보고 드러나야 한다. 백테스트 구간을 잡을 때는
  이 값이 종목별로 다를 수 있다는 전제로 시작한다.
- 종료일은 지정하지 않으면 **거래소 현지 오늘**이다. 국내와 미국은 같은 순간에도 날짜가
  다를 수 있어 시장마다 따로 계산한다.

확정값을 담는 모든 패키지가 `backfill` 인자를 같은 뜻으로 받는다
(`app/core/collection.py`의 `BACKFILL_KEYWORD`).

```
uv run python -m app.ohlcv korea backfill          # 국내 확정 일봉
uv run python -m app.ohlcv overseas backfill       # 해외 확정 일봉
uv run python -m app.macro.us.treasury backfill    # 미국채 10Y 확정 수익률(FRED)
uv run python -m app.kis.korea.investor backfill   # 국내 투자자 수급 확정치

uv run python -m app.ohlcv overseas 2025-06-01     # 시작일만 지정 — 오늘까지
```

| 패키지 | 호출 방식 | 소요 |
|---|---|---|
| `app.ohlcv` (국내) | 종목마다 100일 단위로 분할 호출 | 종목당 약 8회 |
| `app.ohlcv` (해외) | 종목마다 1회 (yfinance가 기간을 통째로 준다) | 종목당 1회 |
| `app.macro.us.treasury` | **1회** — FRED가 기간 조회를 지원한다 | 즉시 |
| `app.kis.korea.investor` | **거래일마다 TR 5건** — 종목 확정 TR이 날짜를 하나씩만 받는다 | 약 400일 × 0.5초 ≈ 5분 |

투자자 수급 백필만 호출 수가 많아 요청 사이에 간격을 둔다(`BACKFILL_PACING_SECONDS`).
KIS 초당 거래건수 제한에 걸리면 HTTP 200 + `rt_cd != "0"`으로 와서 그 날짜만 0행이 되므로,
백필 후에는 경고 로그에 빠진 날짜가 없는지 확인한다. 주말은 호출하지 않고 미리 거른다.

### 3.1 데이터 소스

| 데이터 | 한국 | 미국/글로벌 | 비용 |
|---|---|---|---|
| 시세 — 실시간 (체결/호가 tick) | KIS Developers OpenAPI 웹소켓 | KIS 해외주식 웹소켓 (미국 주간거래) | 무료 |
| 시세 — 일봉/과거 (OHLCV) | KIS OpenAPI | yfinance | 무료 |
| **기업행사** | **KIS 예탁원정보(배당·무상증자·자본감소·상장일정) + DART 공시** | **KIS 해외주식 기간별권리조회(배당·분할·합병 등) + SEC EDGAR** | 무료 |
| 지수·선물·환율 | KIS API (KOSPI, KOSDAQ) | yfinance (S&P500, NASDAQ, VIX, 선물, USD/KRW, **USD/JPY, JPY/KRW**) | 무료 |
| 채권 금리 | **한국은행 ECOS OpenAPI (국고채 3Y/10Y)** | **yfinance `^TNX` + FRED API (미국채 10Y/2Y)** | 무료 |
| **수급 동향** | **KIS API 투자자별 매매동향 (외국인/기관/개인 순매수 — 종목별·시장별), 보완: KRX 정보데이터시스템** | (해당 없음 — 한국 시장 특화) | 무료 |
| **선물 수급** | **KIS API 선물옵션 투자자별 매매동향 (KOSPI200 선물 외국인/기관 포지션)** | (해당 없음) | 무료 |
| **T3 수급 상세** | **KIS API 프로그램매매 + KRX 공매도통합포털 + 금투협 FreeSIS (대차/신용, 일 1회 크롤링)** | (해당 없음) | 무료 |
| **원자재 선물** | (해당 없음) | KIS 해외선물 REST·웹소켓 (COMEX `GC`·`SI`·`HG`, NYMEX `CL`) | API 무료 / CME 실시간 시세 신청 유료 |
| **글로벌 지수** | (해당 없음) | yfinance (SOX, DXY, 상하이·항셍) | 무료 |
| **경기지표** | 관세청 수출입 통계 (반도체 수출), 한국은행 ECOS | FRED API (CPI, 고용, PMI), 중국 PMI 발표치 | 무료 |
| **경제 캘린더** | FOMC·금통위·주요 지표 발표 일정 — 수동 등록 + 크롤링 보완 | 동일 | 무료 |
| 뉴스 | 네이버 뉴스 검색 API, 언론사 RSS | Finnhub / NewsAPI, 주요 매체 RSS | 무료 티어 |
| 공시 | DART OpenAPI | SEC EDGAR | 무료 |
| 보완 수집 | BeautifulSoup / Playwright 크롤러 (API 부재 소스) | 동일 | - |

기업행사는 Yahoo 대신 아래 KIS REST API를 1차 소스로 사용한다.

| 시장 | KIS 조회 | API 경로 | TR ID |
|---|---|---|---|
| 국내 | 배당일정 | `/uapi/domestic-stock/v1/ksdinfo/dividend` | `HHKDB669102C0` |
| 국내 | 무상증자 | `/uapi/domestic-stock/v1/ksdinfo/bonus-issue` | `HHKDB669101C0` |
| 국내 | 자본감소 | `/uapi/domestic-stock/v1/ksdinfo/cap-dcrs` | `HHKDB669106C0` |
| 국내 | 상장일정 | `/uapi/domestic-stock/v1/ksdinfo/list-info` | `HHKDB669107C0` |
| 해외 | 기간별 권리(배당·합병·분할·역분할 등) | `/uapi/overseas-price/v1/quotations/period-rights` | `CTRGT011R` |

국내 API의 `CTS`, 해외 API의 `CTX_AREA_NK50`·`CTX_AREA_FK50`와 응답 헤더
`tr_cont`를 사용해 마지막 페이지까지 수집한다. KIS 일정에 없는 최초 발표 시각과
정정·취소 이력만 DART/EDGAR 공시에서 보완한다.

원자재 선물은 KIS가 배포하는 해외선물 종목정보에서 거래량이 가장 많은 `GC`·`SI`·
`HG`·`CL` 월물코드를 선택한다. Yahoo 연속선물 심볼은 사용하지 않는다.

| 용도 | KIS API | 경로·TR ID | 핵심 값 |
|---|---|---|---|
| 실시간 체결 | WebSocket | `HDFFF020` | `tr_key=월물코드`; `last_price`, `vol`, `mrkt_open_*`, `mrkt_close_*`, `active_flag` |
| 현재가·정산가 | REST | `/uapi/overseas-futureoption/v1/quotations/inquire-price` · `HHDFC55010000` | `SRS_CD`; `last_price`, `sttl_price`, `expr_date`, `vol` |
| 확정 일봉 | REST | `/uapi/overseas-futureoption/v1/quotations/daily-ccnl` · `HHDFC55020100` | `SRS_CD`, `EXCH_CD`, 조회일, `QRY_TP`, `QRY_CNT`, `INDEX_KEY`; OHLCV |

WebSocket은 `approval_key`로 인증하며 CME 실시간 시세 신청이 없으면 구독이 거절된다.
REST는 접근토큰과 표준 `appkey`·`appsecret`·`tr_id` 헤더를 사용하고, 연속조회 시
응답의 `tr_cont`와 `INDEX_KEY`를 이어 보낸다.

### 3.2 수집 주기

| 데이터 | 주기 | 비고 |
|---|---|---|
| 시세 — tick | 장중 웹소켓 실시간 (KIS 체결/호가) | 미시구조 신호용. 확정 시세를 대신하지 않는다 |
| 시세 — 확정 일봉 | 국내 KST 18:00 / 해외 KST 07:00, 각 1회 | 국내 KIS `FHKST03010100`(수정주가), 해외 yfinance `interval=1d`. 최근 7일을 겹쳐 조회해 휴장·재시도 구멍을 메운다 |
| 시세 — 장중 1분봉 | (P1 예정) 국내 KIS `FHKST03010200`, 해외 yfinance `interval=1m` | 백필 불가 — 가동 시점부터 축적 |
| 기업행사 | 일 1회 + 최근 30일 겹쳐 조회 | KIS 구조화 일정이 1차 소스. DART/EDGAR는 발표·정정·취소 원문 확인. `published_at` 이전에는 백테스트에 노출하지 않는다 |
| 뉴스 | 5~15분 | 실시간 대응의 실질 병목 지점 |
| 공시 | 30분~1시간 | |
| 지수/선물/환율 | 15분 | USD/JPY, JPY/KRW 포함 |
| 원자재 선물 | COMEX·NYMEX 거래 세션 중 WebSocket 상시 + 마감 후 확정 일봉 1회 | `GC`·`SI`·`HG`·`CL`. 장 개폐 시각은 수신값 `mrkt_open_*`·`mrkt_close_*` 기준. 만기·휴일·정기 중단은 무수신 경고 대상에서 제외 |
| 채권 금리 | 장중 15분 폴링(`^TNX`·`ZN=F` 1분봉) + 미 영업일 1회 확정(FRED `DGS10`) | 금리 레벨의 소스 오브 트루스는 FRED 확정치. ZN 선물은 아시아 세션 방향성 신호 전용 |
| 수급 동향 (현물/선물) | 장중 잠정치 30분~1시간, 마감 후 확정치 1회 | 장중 데이터는 **잠정치**(provisional) 플래그로 구분 저장. 덮어쓰지 않고 `snapshot_ts`별로 이력 축적 |

### 3.3 스케줄링

- **Celery Beat** (또는 APScheduler)로 주기 작업 관리
- Kafka 등 스트리밍 인프라는 현재 규모(소수 종목)에서 불필요 — 의도적으로 배제
- 수집 실패 시 재시도 + 로깅 (수집 지연 자체를 메트릭으로 기록)
- KIS WebSocket 네트워크 단절은 백오프 후 재연결하지만, 필수 구독 거절 또는
  5초 내 구독 확인 실패는 해당 시장 수집 프로세스를 종료해 감시 프로세스가
  재시작하게 한다. `ALREADY IN SUBSCRIBE`는 멱등적 성공으로 처리한다.
- 국내·해외 실시간 DTO는 수신 직후 SQLAlchemy repository가 건별 트랜잭션으로 저장한다.
  DB 저장 실패는 해당 tick만 폐기하고 구조화 로그를 남긴 뒤 스트림 수신을 계속한다.
- KIS REST 접근토큰은 발급 제한(1분 1회)이 있으므로 Redis에 캐시해 모든 프로세스가
  공유한다. 만료는 `expires_in`에서 여유분 10분을 뺀 Redis TTL이 강제하며, 캐시가
  살아 있는 동안에는 `/oauth2/tokenP`를 호출하지 않는다.
- Yahoo 1분봉은 yfinance로 수집하며, yfinance가 내부에서 curl_cffi 브라우저 임퍼소네이션을 사용한다.
  쿠키만 실어도 TLS(JA3/JA4)·HTTP/2 지문이 브라우저와 달라 엣지 쿼터
  (`429 Edge: Too Many Requests`)에 걸리기 때문이다. 요청 헤더는 손으로 만들지 않고
  임퍼소네이션이 심는 기본값을 그대로 쓴다.
- Yahoo 세션 쿠키는 `finance.yahoo.com`에서 한 번 받아 Redis에 6시간 TTL로 캐시하고
  chart 호출마다 실어 보낸다. 쿠키 획득과 chart 호출은 같은 임퍼소네이션 세션을 탄다.
  401/403/429면 1회만 재획득해 재시도하고, 그래도 429면 재시도 없이 다음 15분 회차로 넘긴다.

### 3.4 국가별 패키지 경로

매크로 수집 패키지는 국가 코드를 디렉터리 네임스페이스로 사용한다.

```text
app/macro/
└── us/
    └── treasury/   # app.macro.us.treasury
```

`app/macro/us_treasury`처럼 국가와 기능을 밑줄로 합치지 않으며, 테스트도
`tests/macro/us/treasury`로 같은 구조를 따른다. DB 테이블명(`us_treasury_bars`)과
로그 이벤트명은 Python 패키지 경로가 아니므로 기존 `snake_case`를 유지한다.

### 3.5 로깅

- 애플리케이션 로깅 API는 **structlog**로 통일한다. 표준 `logging`은 Uvicorn,
  SQLAlchemy 등 외부 라이브러리 로그를 같은 출력 형식으로 전달하는 내부 계층으로만 사용한다.
- 로컬 기본값은 `LOG_FORMAT=console`, 운영 환경은 `LOG_FORMAT=json`을 사용한다.
  로그 시간은 UTC ISO 8601 형식이며 `LOG_LEVEL` 기본값은 `INFO`다.
- 이벤트 이름은 고정된 `snake_case`로 기록하고, 종목·시장·TR ID·재시도 횟수 등은
  메시지 문자열에 합치지 않고 구조화 필드로 전달한다.

**실패도 누락도 조용히 넘어가지 않는다.** 외부 API가 4xx·5xx면 `ERROR` 로그를 남기고
예외를 올린다(`app.core.http.raise_for_status`). 여기에 더해 **데이터가 조용히 줄어드는
자리**를 전부 로그로 드러낸다 — 수집 파이프라인에서 손실은 예외보다 필터 쪽에서 훨씬
자주, 훨씬 늦게 발견되기 때문이다.

| 사건 | 이벤트 | 수준 |
|---|---|---|
| 파서가 행을 버림 (자리 채움·결측) | `*_blank_rows_dropped`, `*_rows_without_price` | WARNING |
| 파싱 건수 대조 | `*_parsed` (`received`/`parsed`/`skipped_unsettled`) | INFO |
| 대상 하나가 0건 | `ohlcv_instrument_returned_no_bars` | WARNING |
| 소스가 빈 응답 (없는 심볼 포함) | `yahoo_daily_chart_empty` | WARNING |
| instruments 미등록 대상 | `ohlcv_instrument_not_registered` | WARNING |
| 저장 결과 | `*_saved` (`fetched`/`saved`) | INFO |

0건은 휴장 때문일 수도, 심볼을 잘못 등록해서일 수도 있고 **응답 모양이 같다**. 그래서
정상일 수 있어도 경고로 남긴다. yfinance는 없는 심볼에 예외 대신 빈 프레임을 주므로
특히 이 규칙이 필요하다.

---

## 4. 저장 · 전처리 레이어

### 4.1 저장소 구성 (PostgreSQL 단일화)

| 테이블 그룹 | 내용 | 비고 |
|---|---|---|
| 시계열 | 종목별 실시간 tick(체결/호가), OHLCV, 지수, 환율, 선물 | 규모 증가 시 TimescaleDB 확장 검토 |
| 원문 | 뉴스/공시 원문 + 메타데이터 | |
| 기업행사 | 배당·분할·증자/감자·합병·종목 변경 일정 | 가격 조정 검증과 이벤트 컨텍스트 |
| 벡터 | 청크 + 임베딩 (pgvector) | |
| 관계 | 엔티티·관계 테이블 (§6 참조) | |
| 시그널/평가 | LLM 분석 결과, 시그널, 백테스트 기록 | |

### 4.2 핵심 스키마 (초안)

```sql
-- 종목/시세
-- 종목 마스터. 거래되는 종목과 지수가 함께 들어간다(지수는 수급 집계 단위이자 가격 대상).
CREATE TABLE instruments (
  id            BIGSERIAL PRIMARY KEY,
  ticker        TEXT NOT NULL,        -- '005930', 'AAPL', 'KOSPI'
  market        TEXT NOT NULL,        -- 'KRX' | 'NASDAQ' | 'NYSE_ARCA'
  name          TEXT NOT NULL,
  kind          TEXT NOT NULL,        -- 'EQUITY' | 'ETF' | 'INDEX' | 'FUTURE'
  source_symbol TEXT,                 -- 소스에서 쓰는 심볼. 티커와 다를 때만 (KOSPI → '^KS11')
  is_watched    BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (ticker, market)
);
-- kind가 필요한 이유: market만으로는 가격 소스를 고를 수 없다. KOSPI는 시장이 KRX지만
-- 종목 시세 TR(FHKST03010100)로 받을 수 없고, 거래되는 ETF는 개별주와 같은 TR을 쓴다.
--   KRX + (EQUITY|ETF) → KIS 종목 시세 TR
--   그 밖(해외 전부, INDEX 전부) → yfinance, source_symbol 우선

-- 봉 데이터 (확정 일봉 + 장중 분봉)
-- 설계 노트:
--  · 일봉과 분봉은 컬럼이 같고 그레인만 달라 timeframe으로 한 테이블을 공유한다
--  · 일봉의 ts는 거래소 현지 00:00에 대응하는 UTC 시각 — 현지 거래일로 되돌릴 때는
--    거래소 시간대로 변환한다. 분봉과 시간 키를 하나로 유지하기 위한 선택
--  · 진행 중인 봉은 저장하지 않는다. 정규장 마감(KRX 15:30, 미국 16:00 ET)에
--    여유 10분을 더한 시각이 지나야 그 거래일을 확정으로 본다
--  · 조정 기준이 시장별로 다르다 — 국내는 KIS 수정주가(분할·증자만),
--    해외는 Yahoo auto_adjust(배당까지). 국내·해외 수익률 비교 시 주의
--  · 실시간 tick 테이블은 미시구조 신호용이고, 백테스트가 쓰는 확정 시세는 이 테이블이다
CREATE TABLE ohlcv (
  id            BIGSERIAL PRIMARY KEY,
  instrument_id BIGINT NOT NULL REFERENCES instruments(id) ON DELETE RESTRICT,
  timeframe     TEXT NOT NULL,          -- '1m'(장중) | '1d'(확정 일봉)
  ts            TIMESTAMPTZ NOT NULL,   -- 봉 시작 UTC 시각
  open          NUMERIC(28, 8) NOT NULL,
  high          NUMERIC(28, 8) NOT NULL,
  low           NUMERIC(28, 8) NOT NULL,
  close         NUMERIC(28, 8) NOT NULL,
  volume        BIGINT NOT NULL,
  snapshot_ts   TIMESTAMPTZ NOT NULL,   -- 응답 수신 UTC 시각. 수정주가 소급 반영 시 갱신
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (instrument_id, timeframe, ts)
);
-- 같은 거래일 재수집이 정상 동작이라(정기 수집은 최근 구간을 겹쳐 조회, 백필은 기간이
-- 겹칠 수 있음) 종가가 달라졌을 때만 ON CONFLICT DO UPDATE로 갱신한다.
-- UNIQUE 제약이 만드는 btree 인덱스가 (종목, 봉간격, 기간) 조회 인덱스를 겸한다.

-- 기업행사. 행사 유형별 테이블을 나누지 않고 공통 날짜·금액·교환비율을 한 곳에 둔다.
-- KIS가 주는 구조화 일정을 1차 소스로 쓰고 DART/EDGAR 공시는 발표·정정·취소 확인에 쓴다.
CREATE TABLE corporate_actions (
  id                BIGSERIAL PRIMARY KEY,
  instrument_id     BIGINT NOT NULL REFERENCES instruments(id) ON DELETE RESTRICT,
  action_type       TEXT NOT NULL,        -- 'cash_dividend' | 'stock_dividend' |
                                          -- 'split' | 'reverse_split' | 'rights_issue' |
                                          -- 'bonus_issue' | 'capital_reduction' |
                                          -- 'merger' | 'spinoff' | 'symbol_change' | 'delisting'
  status            TEXT NOT NULL,        -- 'announced' | 'confirmed' | 'cancelled'
  announced_at      TIMESTAMPTZ,          -- 회사가 최초 발표한 시각. 소스에 없으면 NULL
  published_at      TIMESTAMPTZ NOT NULL, -- 시스템이 알 수 있게 된 시각. 백테스트 노출 기준
  ex_date           DATE,                 -- 배당락·권리락일
  record_date       DATE,                 -- 권리 기준일
  payable_date      DATE,                 -- 현금·주식 지급일
  effective_date    DATE,                 -- 분할·합병·티커 변경 효력일
  cash_amount       NUMERIC(28, 8),       -- 주당 현금액
  currency          TEXT,                 -- 'KRW' | 'USD' 등. cash_amount가 있으면 필수
  old_shares        NUMERIC(28, 8),       -- 기존 주식 수(예: 1→2 분할이면 1)
  new_shares        NUMERIC(28, 8),       -- 행사 후 주식 수(예: 1→2 분할이면 2)
  source            TEXT NOT NULL,        -- 'kis_ksd' | 'kis_overseas_rights' | 'dart' | 'edgar'
  source_event_id   TEXT NOT NULL,        -- 원본 ID. 없으면 종목·유형·기준일의 안정 해시
  snapshot_ts       TIMESTAMPTZ NOT NULL, -- 응답 수신 UTC 시각
  details           JSONB NOT NULL,       -- KIS 권리유형·확정여부, 공시 접수번호 등 원본
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, source_event_id),
  CHECK (status IN ('announced', 'confirmed', 'cancelled')),
  CHECK (cash_amount IS NULL OR currency IS NOT NULL),
  CHECK ((old_shares IS NULL) = (new_shares IS NULL)),
  CHECK (old_shares IS NULL OR (old_shares > 0 AND new_shares > 0))
);
CREATE INDEX ON corporate_actions (instrument_id, published_at);
CREATE INDEX ON corporate_actions (instrument_id, effective_date);
-- 수정주가는 가격 비교용이고 corporate_actions는 "무슨 일이 언제 알려졌는가"의 원장이다.
-- 같은 정보를 ohlcv에 합치지 않는다. LLM·백테스트는 published_at 이후에만 행사를 보고,
-- 가격 조정 검증은 ex_date/effective_date와 old_shares:new_shares를 사용한다.

-- 실시간 tick (KIS 웹소켓 체결/호가 원시 데이터)
-- 설계 노트:
--  · 호가 10단계는 JSONB 단일 컬럼 — 소비 패턴이 항상 스냅샷 전체 복원이라 정규화 이득 없음
--  · v1은 종목코드 직저장, instruments 정착 후 FK 전환
--  · 모든 datetime은 timezone-aware UTC. KST/현지 시각 원본은 details JSONB에 보존
--  · 모든 ORM 모델은 EntityModel의 id/created_at/updated_at 공통 컬럼을 상속
CREATE TABLE korea_trades (
  id                        BIGSERIAL PRIMARY KEY,
  stock_code                TEXT NOT NULL,
  event_ts                  TIMESTAMPTZ NOT NULL, -- UTC 체결 시각
  price                     NUMERIC(28, 8) NOT NULL,
  volume                    BIGINT NOT NULL,
  cumulative_volume         BIGINT NOT NULL,
  cumulative_amount         NUMERIC(28, 8) NOT NULL,
  trade_strength            NUMERIC(20, 8),
  best_bid_price            NUMERIC(28, 8) NOT NULL,
  best_ask_price            NUMERIC(28, 8) NOT NULL,
  trade_classification_code TEXT NOT NULL,
  details                   JSONB NOT NULL,
  received_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON korea_trades (stock_code, event_ts);

CREATE TABLE korea_orderbooks (
  id                 BIGSERIAL PRIMARY KEY,
  stock_code         TEXT NOT NULL,
  event_ts           TIMESTAMPTZ NOT NULL, -- UTC 호가 시각
  best_bid_price     NUMERIC(28, 8) NOT NULL,
  best_ask_price     NUMERIC(28, 8) NOT NULL,
  total_bid_quantity BIGINT NOT NULL,
  total_ask_quantity BIGINT NOT NULL,
  levels             JSONB NOT NULL,
  details            JSONB NOT NULL,
  received_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON korea_orderbooks (stock_code, event_ts);

CREATE TABLE overseas_trades (
  id                  BIGSERIAL PRIMARY KEY,
  realtime_symbol     TEXT NOT NULL,
  symbol              TEXT NOT NULL,
  market              TEXT NOT NULL,
  event_ts            TIMESTAMPTZ NOT NULL, -- UTC 체결 시각
  local_business_date DATE NOT NULL,        -- 거래소 영업일이며 timestamp가 아님
  decimal_places      SMALLINT NOT NULL,
  price               NUMERIC(28, 8) NOT NULL,
  volume              BIGINT NOT NULL,
  cumulative_volume   BIGINT NOT NULL,
  cumulative_amount   NUMERIC(28, 8) NOT NULL,
  best_bid_price      NUMERIC(28, 8) NOT NULL,
  best_ask_price      NUMERIC(28, 8) NOT NULL,
  best_bid_quantity   BIGINT NOT NULL,
  best_ask_quantity   BIGINT NOT NULL,
  trade_strength      NUMERIC(20, 8),
  market_type         TEXT NOT NULL,
  details             JSONB NOT NULL,
  received_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON overseas_trades (symbol, event_ts);

CREATE TABLE overseas_orderbooks (
  id                 BIGSERIAL PRIMARY KEY,
  realtime_symbol    TEXT NOT NULL,
  symbol             TEXT NOT NULL,
  market             TEXT NOT NULL,
  event_ts           TIMESTAMPTZ NOT NULL, -- UTC 호가 시각
  decimal_places     SMALLINT NOT NULL,
  best_bid_price     NUMERIC(28, 8) NOT NULL,
  best_ask_price     NUMERIC(28, 8) NOT NULL,
  best_bid_quantity  BIGINT NOT NULL,
  best_ask_quantity  BIGINT NOT NULL,
  total_bid_quantity BIGINT NOT NULL,
  total_ask_quantity BIGINT NOT NULL,
  levels             JSONB NOT NULL,
  details            JSONB NOT NULL,
  received_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON overseas_orderbooks (symbol, event_ts);

-- 수급 동향 (한국 시장: 현물 종목별 + 선물 시장 단위)
CREATE TABLE investor_flows (
  id             BIGSERIAL PRIMARY KEY,
  instrument_id  INT NOT NULL REFERENCES instruments(id),  -- 종목별 수급. 시장/선물 단위는
                                                  -- 'KOSPI', 'KOSPI200_FUT' 등 macro instrument로 등록
  trade_date     DATE NOT NULL,        -- 한국 날짜. 장중 응답에는 날짜가 없어 snapshot_ts의 KST 날짜 사용
  venue          TEXT NOT NULL,        -- 'KRX' | 'NXT' | 'UNSPECIFIED'
                                       -- 마감 종목 TR은 KRX/NXT를 따로 호출한다
  investor_type  TEXT NOT NULL,        -- 'foreign', 'institution', 'retail',
                                       -- 'securities', 'trust', 'pension_fund', ...
                                       -- 'institution'은 하위 유형의 합계 — 이중 계산 주의
  net_buy_value  BIGINT,               -- 순매수 금액. **백만원 단위(*_ntby_tr_pbmn) 원본 그대로 저장**
                                       -- 억원 환산은 조회하는 쪽에서 /100. 저장 시 곱하지 않는다.
                                       -- 종목 장중 TR에는 금액이 없어 NULL
  net_buy_volume BIGINT,               -- 순매수 수량 (계약수/주식수)
  time_bucket    TEXT NOT NULL DEFAULT '',  -- 종목 장중 TR의 집계 시간대(bsop_hour_gb '1'~'4')
                                            -- 시간대 구분이 없으면 ''(NULL 금지: UNIQUE 무력화)
  is_provisional BOOLEAN NOT NULL,     -- 장중 가집계(잠정치) 여부. 수집 단계에서 항상 채운다
  snapshot_ts    TIMESTAMPTZ NOT NULL, -- 응답 수신 UTC 시각. 30분 슬롯으로 내려 재시도를 같은 눈금에 묶는다
  details        JSONB NOT NULL,       -- 매도/매수 원본 등 순매수 외 필드
  UNIQUE (instrument_id, trade_date, investor_type,
          venue, time_bucket, is_provisional, snapshot_ts)
);
CREATE INDEX ON investor_flows (instrument_id, trade_date);
-- 장중 잠정치를 확정치로 "덮어쓰지" 않고, snapshot_ts를 키에 포함해 이력을 그대로 축적한다
-- (외국인이 몇 시부터 순매수로 돌았는지 같은 장중 흐름 분석을 위해).

-- 미국 국채 10년물 (수익률 ^TNX + 국채선물 ZN=F 장중 1분봉, FRED DGS10 일별 확정치)
-- 설계 노트:
--  · v1은 계열 코드 직저장, instruments 정착 후 FK 전환 (tick 테이블들과 같은 방침)
--  · 수익률은 % 원본, 선물은 가격 포인트 원본 그대로 저장 — bp·CTD 환산은 조회하는 쪽의 몫
--  · details JSONB 없음 — Yahoo는 Unix epoch(UTC), FRED는 ISO 날짜만 주므로 보존할
--    현지 시각 원본이 없고, 남길 값이 전부 스칼라라 typed 컬럼으로 승격했다
--  · 장중 테이블은 두 계열 공용. 소스·파싱·그레인·저장 로직이 같고 단위만 다르다
CREATE TABLE us_treasury_bars (
  id          BIGSERIAL PRIMARY KEY,
  series      TEXT NOT NULL,             -- 'US10Y'(수익률 %) | 'ZN'(선물 가격 포인트)
  event_ts    TIMESTAMPTZ NOT NULL,      -- 봉 시작 UTC 시각. 진행 중인 봉은 저장하지 않는다
  open        NUMERIC(16, 8),            -- 소스가 null이면 NULL
  high        NUMERIC(16, 8),
  low         NUMERIC(16, 8),
  close       NUMERIC(16, 8) NOT NULL,   -- 1/64·1/128 분수 가격까지 손실 없이 담는 scale
  snapshot_ts TIMESTAMPTZ NOT NULL,      -- 응답 수신 UTC 시각(추적용, 키 아님)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (series, event_ts)              -- 폐장·휴장 폴링의 재수집은 ON CONFLICT DO NOTHING으로 흘린다
);

CREATE TABLE us_treasury_yield_daily (
  id               BIGSERIAL PRIMARY KEY,
  series           TEXT NOT NULL,        -- 확정치는 'US10Y'만 존재 (ZN은 무료 공식 정산가 없음)
  observation_date DATE NOT NULL,        -- ET 영업일. dispatch 시점에 고정해 넘긴다
  yield_pct        NUMERIC(8, 4) NOT NULL,  -- 연준 H.15 CMT 수익률(%)
  snapshot_ts      TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (series, observation_date)
);

-- T3 수집 전용 일별 지표 (프로그램 매매, 공매도, 대차/신용 잔고 등)
CREATE TABLE daily_metrics (
  instrument_id INT REFERENCES instruments(id),  -- 시장 단위는 macro instrument 사용
  trade_date    DATE NOT NULL,                   -- 데이터 기준일
  metric        TEXT NOT NULL,                   -- 'program_net_buy', 'short_sale_value',
                                                 -- 'short_balance', 'loan_balance',
                                                 -- 'margin_loan_balance'
  value         NUMERIC,
  published_at  TIMESTAMPTZ NOT NULL,            -- 공시/입수 시점 — T+1·T+2 지연 데이터의
                                                 -- look-ahead bias 방지 (백테스트는 이 기준)
  PRIMARY KEY (instrument_id, trade_date, metric)
);

-- 경제 이벤트 캘린더 (FOMC, CPI, 금통위, 중국 PMI, 한국 수출입 등)
CREATE TABLE econ_calendar (
  id           SERIAL PRIMARY KEY,
  event_name   TEXT NOT NULL,          -- 'FOMC', 'US_CPI', 'BOK_RATE', 'BOJ_RATE',
                                       -- 'CN_PMI', 'KR_EXPORT', 'TSMC_REV'
  country      TEXT NOT NULL,          -- 'US', 'KR', 'CN'
  scheduled_at TIMESTAMPTZ NOT NULL,
  importance   SMALLINT,               -- 1~3 (발표 전 시그널 보수화 판단용)
  actual       TEXT,                   -- 발표치 (발표 후 기록)
  consensus    TEXT                    -- 시장 예상치
);

-- 뉴스/공시 원문
CREATE TABLE news (
  id           BIGSERIAL PRIMARY KEY,
  source       TEXT NOT NULL,         -- 'naver', 'finnhub', 'dart', 'edgar'
  url          TEXT UNIQUE,
  title        TEXT,
  body         TEXT,
  published_at TIMESTAMPTZ,
  lang         TEXT,                  -- 'ko', 'en'
  dedup_hash   TEXT,                  -- 중복 제거용
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- RAG 청크 (pgvector)
CREATE TABLE news_chunks (
  id           BIGSERIAL PRIMARY KEY,
  news_id      BIGINT REFERENCES news(id),
  chunk_index  INT,
  content      TEXT,
  embedding    VECTOR(1024),          -- 임베딩 모델 차원에 맞춤
  published_at TIMESTAMPTZ,           -- 시간 필터용 비정규화
  tsv          TSVECTOR               -- 키워드(BM25 대용) 검색용
);
CREATE INDEX ON news_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON news_chunks USING gin (tsv);
```

### 4.3 전처리 파이프라인

1. **중복 제거**: 동일 사건의 다중 보도 → 제목/본문 해시 + 유사도 기반 dedup
2. **종목 매핑 (NER)**: "삼성전자" / "005930" / "Samsung Electronics" → 동일 엔티티 정규화
3. **관련성 필터**: 관심 종목·산업과 무관한 뉴스 제외 (규칙 + 저비용 LLM)
4. **청킹 + 임베딩**: 뉴스 단위 또는 문단 단위 청킹 → 임베딩 → pgvector 적재

---

## 5. RAG 검색 레이어

### 5.1 하이브리드 검색

- **벡터 검색** (pgvector, cosine) + **키워드 검색** (tsvector) 결과를 RRF 등으로 결합
- **시간 가중치 (recency decay)**: 금융 뉴스는 시의성이 핵심 — 오래된 문서 점수 감쇠
- **메타데이터 필터**: `종목 코드 + 기간(예: 최근 3일) + 소스 유형`을 벡터 검색 전에 필터

> 순수 유사도 검색만 사용하면 수개월 전 유사 뉴스가 상위에 노출되는 문제 발생.
> "필터 먼저, 유사도는 그 다음"이 기본 원칙.

### 5.2 검색 용도 구분

| 용도 | 방식 |
|---|---|
| 과거 유사 사례 검색 | 벡터 + 키워드 하이브리드 |
| 간접 영향 경로 탐색 | 관계 레이어 (§6) — 벡터 검색과 상호 보완 |

---

## 6. 경량 관계 레이어 (GraphRAG 절충안)

### 6.1 배경 및 결정

- **목적**: 멀티홉 영향 전파 — 예: "TSMC 감산 → TSMC는 애플 공급사 → 애플(관심 종목) 간접 영향"
- **결정**: 풀 그래프 DB(Neo4j) 대신 **PostgreSQL 관계형 테이블 + 재귀 CTE**로 시작
- **근거**: 관심 종목이 소수 고정 → 핵심 관계(공급망·경쟁·산업)는 수십~백 개 수준의
  준정적(semi-static) 데이터. 수동/반자동 구축으로 충분하며, LLM 트리플 추출 파이프라인과
  그래프 DB 운영 비용을 현 단계에서 정당화하기 어려움
- **효과**: GraphRAG가 주는 가치의 약 80%를 10% 비용으로 확보

### 6.2 스키마

```sql
CREATE TABLE entities (
  id      SERIAL PRIMARY KEY,
  name    TEXT NOT NULL,
  ticker  TEXT,                        -- 종목이면 매핑
  type    TEXT NOT NULL,               -- 'company', 'person', 'sector', 'commodity'
  aliases TEXT[]                       -- NER 정규화용 별칭
);

CREATE TABLE relations (
  source_id  INT REFERENCES entities(id),
  target_id  INT REFERENCES entities(id),
  rel_type   TEXT NOT NULL,            -- 'supplies_to', 'competes_with',
                                       -- 'belongs_to_sector', 'subsidiary_of', ...
  weight     REAL DEFAULT 1.0,         -- 영향 강도 추정
  valid_from DATE,
  note       TEXT,
  PRIMARY KEY (source_id, target_id, rel_type)
);

CREATE TABLE news_entity_mentions (
  news_id    BIGINT REFERENCES news(id),
  entity_id  INT REFERENCES entities(id),
  sentiment  TEXT,                     -- 'positive', 'negative', 'neutral'
  confidence REAL,
  PRIMARY KEY (news_id, entity_id)
);
```

### 6.3 활용 흐름

1. 신규 뉴스 → NER로 엔티티 추출 → `news_entity_mentions` 기록
2. 재귀 CTE로 "언급된 엔티티 → 1~2홉 이내 관심 종목" 경로 탐색
3. 경로 존재 시, 경로 정보(관계 유형·강도)를 LLM 프롬프트 컨텍스트에 주입
   → 간접 영향 분석 수행

**초기 시드 관계 예시 (§1.4 확정 종목 기준)**:

```
SK하이닉스  --supplies_to(HBM)-->        엔비디아
SK하이닉스 ADR(SKHY)* --represents(1 ADR=0.1주)--> SK하이닉스
삼성전자    --supplies_to(메모리/파운드리)--> 엔비디아, 애플 등
삼성전자    --competes_with-->            SK하이닉스 (메모리), 애플 (스마트폰)
TSMC*      --supplies_to(파운드리)-->     엔비디아, 애플
빅테크 5종  --belongs_to_index-->         QQQ, SPY
전 종목    --belongs_to_sector-->         반도체 / 빅테크 / AI 인프라
연준 금리* --affects-->                   QQQ, SPY (매크로 노드)
미국채 10Y 금리* --affects(밸류에이션)-->  빅테크 5종, QQQ, SPY
USD/JPY (엔캐리)* --affects(유동성)-->    QQQ, SPY
USD/KRW*  --affects(수출/외인수급)-->     삼성전자, SK하이닉스
중국 PMI·경기* --affects(반도체 수요)-->   삼성전자, SK하이닉스
SOX 지수* --tracks(섹터 방향)-->          삼성전자, SK하이닉스, 엔비디아
한국 반도체 수출액* --leads(실적 선행)-->  삼성전자, SK하이닉스
DRAM/NAND 현물가* --leads(실적 선행)-->   삼성전자, SK하이닉스
TSMC 월매출* --leads(수요 선행)-->        엔비디아, 애플, 반도체 섹터
ASML·AMAT·LRCX·KLAC(장비)* --supplies_to(장비/투자 사이클)--> 삼성전자, SK하이닉스, TSMC
마이크론(MU)* --competes_with(메모리)-->   삼성전자, SK하이닉스
AVGO·AMD* --belongs_to_sector(AI 반도체)--> SOX, 엔비디아 (섹터 심리 경로)
BOJ 금리·JGB* --affects(엔캐리)-->         USD/JPY → QQQ, SPY

* 추적 종목은 아니지만 관계 그래프에는 엔티티로 등록 (간접 영향 경로용)
```

### 6.4 확장 경로 (학습 목적 포함)

| 단계 | 내용 | 시점 |
|---|---|---|
| 1단계 | 순수 벡터 RAG 완성 + 백테스트 베이스라인 확보 | Phase 1 |
| 2단계 | 경량 관계 레이어 (본 절) — GraphRAG 개념을 그래프 DB 없이 체득 | Phase 2 |
| 3단계 | 본격 GraphRAG 학습 프로젝트 | Phase 3 이후 |

**3단계 학습 포인트**:
- LLM 기반 트리플 추출: 뉴스 → (엔티티, 관계, 엔티티) structured output 파이프라인,
  추출 품질 평가 (GraphRAG 구축의 실질적 난이도 대부분)
- 그래프 저장·탐색: Neo4j + Cypher, 또는 PostgreSQL Apache AGE 확장 실험,
  Microsoft GraphRAG 라이브러리(커뮤니티 감지 기반 요약) 비교
- 하이브리드 라우팅: 쿼리별 벡터/그래프/결합 검색 선택 로직 (LangGraph 노드로 구현)

**핵심 원칙**: 1단계의 평가 지표가 있어야 "그래프 도입이 검색 품질을 실제로 올렸는가"를
측정 가능. 최종 결과물 = "벡터 RAG vs 벡터+그래프 하이브리드 동일 평가셋 비교".

---

## 7. LLM 분석 레이어 (LangGraph)

### 7.1 워크플로 (뉴스 이벤트 기준)

```mermaid
flowchart TD
    N["신규 뉴스 수신"]
    F1["<b>① 관련성 필터</b><br/>저비용 모델 (Haiku / Gemini Flash)<br/>관심 종목·산업과 관련 있는가?"]
    X["종료<br/>(~90% 필터링)"]
    F2["<b>② 컨텍스트 수집</b><br/>RAG: 과거 유사 뉴스/사례<br/>관계 레이어: 간접 영향 경로<br/>시세: 최근 가격·기술적 지표 (pandas)<br/>수급: 외국인/기관 순매수·선물 포지션 (한국 종목)<br/>기업행사: 배당락·분할·증자/감자 일정<br/>온디맨드: 이벤트 조건 시 보조 지표 즉석 조회 (USD/TWD 등)"]
    F3["<b>③ 영향 분석</b><br/>상위 모델 (Sonnet / Gemini Pro)<br/>Structured Output(JSON):<br/>direction · magnitude · affected_tickers<br/>rationale · risks · confidence"]
    F4["<b>④ 시그널 생성</b><br/>LLM 정성 분석 + 기술적 지표 + 룰 결합"]
    F5["<b>⑤ 저장 · 알림</b><br/>signals 테이블 기록 → 리포트/알림 발송"]

    N --> F1
    F1 -- "무관" --> X
    F1 -- "관련 있음" --> F2
    F2 --> F3 --> F4 --> F5
```

### 7.2 비용 최적화

- **2단계 모델 라우팅**: 저비용 모델 1차 필터 → 통과분만 상위 모델 분석
  (뉴스의 약 90%가 1차에서 걸러져 API 비용 대폭 절감)
- **프롬프트 캐싱** 활용 (시스템 프롬프트·고정 컨텍스트)
- 배치 분석 가능 작업(데일리 리포트)은 배치 API 검토

### 7.3 관측성 (Observability)

- **Langfuse** 연동: 노드별 비용·레이턴시·입출력 추적, 프롬프트 버전 관리
- 시그널 품질 지표(§8)와 연결해 프롬프트 개선 루프 구성

### 7.4 오픈소스 LLM 파인튜닝 (후순위, Phase 3)

- 초기에는 학습 데이터 부재 → API 운영 중 축적되는
  **"뉴스 → 분석 → 실제 주가 반응" 로그가 곧 파인튜닝 데이터셋**
- 데이터가 쌓이면 Qwen 계열 등 오픈 모델에 LoRA 적용, API 대비 성능/비용 비교

---

## 8. 시그널 · 평가 레이어

### 8.1 시그널 스키마 (초안)

```sql
CREATE TABLE signals (
  id            BIGSERIAL PRIMARY KEY,
  instrument_id INT REFERENCES instruments(id),
  news_id       BIGINT REFERENCES news(id),   -- 트리거 이벤트 (nullable)
  direction     TEXT,                          -- 'bullish', 'bearish', 'neutral'
  magnitude     SMALLINT,                      -- 1~5
  confidence    REAL,
  rationale     TEXT,
  model         TEXT,                          -- 사용 모델/프롬프트 버전
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE signal_outcomes (
  signal_id   BIGINT REFERENCES signals(id),
  horizon     TEXT,          -- '1d', '3d', '5d'
  return_pct  REAL,          -- 실제 수익률
  hit         BOOLEAN,       -- 방향 적중 여부
  evaluated_at TIMESTAMPTZ,
  PRIMARY KEY (signal_id, horizon)
);
```

### 8.2 백테스트 파이프라인

- 시그널 생성 시점 이후 N일(1/3/5일) 실제 수익률과 비교 → `signal_outcomes` 기록
- **핵심 지표**: 방향 적중률(hit rate), 강도별 적중률, 신뢰도 캘리브레이션,
  기준선(랜덤/모멘텀 룰) 대비 성능
- 이 지표가 프롬프트 개선·GraphRAG 도입·파인튜닝 효과 검증의 유일한 기준

### 8.3 출력물

| 출력 | 내용 | Phase |
|---|---|---|
| 데일리 리포트 | 장 마감 후 종목별 뉴스 요약 + 영향 분석 + 시그널 | 1 |
| 실시간 알림 | 장중 이벤트 감지 시 텔레그램/디스코드 알림 | 2 |
| 평가 대시보드 | 시그널 적중률·비용·레이턴시 추이 | 2~3 |

---

## 9. 로드맵

### Phase 1 — 배치 파이프라인 (4~6주)

- [x] 관심 종목 확정 — 총 9개 (§1.4): 삼성전자, SK하이닉스, AAPL, GOOGL, MSFT, META, NVDA, QQQ, SPY
- [ ] `instruments` 테이블 등록 + 엔티티 별칭(aliases) 입력
- [x] KIS 인증 + 웹소켓 실시간 시세 수신 (국내/해외 체결·호가 DTO 파싱까지)
- [x] KIS 실시간 tick 저장 (국내·해외 체결/호가 테이블, §4.2)
- [x] 확정 일봉 수집·저장 (`ohlcv`, 국내 KIS + 해외 yfinance, 백필 CLI 포함)
- [x] 확정값 백필 경로 (`<패키지> backfill` — 일봉 · 미국채 · 투자자 수급, 기준 2025-01-01)
- [ ] 백필 실행 (백테스트 베이스라인 확보)
- [ ] 장중 1분봉 수집 (국내 KIS `FHKST03010200`, 해외 yfinance) — §3.0 이중 그레인의 나머지 절반
- [ ] 원자재 선물 수집 (KIS 해외선물 `GC`·`SI`·`HG`·`CL` 최근월물, WebSocket 체결 + 확정 일봉)
- [ ] 기업행사 수집·저장 (`corporate_actions`, 국내 KIS 예탁원정보 + 해외 KIS 기간별권리조회, DART/EDGAR 원문 보완)
- [ ] 데이터 수집: 뉴스(네이버/RSS/Finnhub) + 공시(DART/EDGAR)
- [ ] DB 스키마 구축 (§4.2, §6.2, §8.1)
- [ ] 전처리: dedup, NER 종목 매핑, 청킹·임베딩
- [ ] 벡터 RAG (하이브리드 + 시간 가중치)
- [ ] LangGraph 배치 분석: 장 마감 후 1일 1회 데일리 리포트
- [ ] Langfuse 연동
- [ ] 백테스트 파이프라인 v1 (베이스라인 확보)

### Phase 2 — 실시간 대응 (이후 4주~)

- [ ] 장중 뉴스 이벤트 감지 → 즉시 분석 → 알림
- [ ] 경량 관계 레이어 구축 (관심 종목 공급망·경쟁 관계 수동/반자동 입력)
- [ ] 간접 영향 분석 노드 추가, 백테스트로 가치 검증
- [ ] 평가 대시보드

> 실시간 대응의 병목은 LLM 추론(수 초)이 아니라 **뉴스 수집 지연**임을 전제로
> 수집 주기·소스 다양화에 우선 투자

### Phase 3 — 고도화 (학습 목표 포함)

- [ ] 축적 로그 기반 평가 데이터셋 구축
- [ ] 오픈소스 LLM(Qwen 등) LoRA 파인튜닝 → API 대비 비교
- [ ] 본격 GraphRAG 실험 (§6.4 3단계): 트리플 자동 추출, Neo4j/AGE,
      벡터 vs 하이브리드 동일 평가셋 비교

---

## 10. 리스크 및 유의사항

| 항목 | 내용 |
|---|---|
| 법적 범위 | 자동매매 연동은 자본시장법상 라이선스 이슈 → 개인 분석 도구 범위 유지 |
| 신뢰성 고지 | LLM 분석은 검증되지 않은 참고 정보임을 시스템 출력에 명시 |
| API 비용 | 2단계 라우팅·캐싱으로 통제, Langfuse로 상시 모니터링 |
| 데이터 품질 | 뉴스 중복·오보·SEO성 저품질 소스 → dedup + 소스 화이트리스트 |
| 평가 없는 개선 금지 | 모든 변경(프롬프트, RAG, 그래프)은 백테스트 지표로 전후 비교 |

---

## 11. 포트폴리오 관점 요약

이 프로젝트가 보여주는 역량:

- **에이전틱 엔지니어링**: LangGraph 멀티 스텝 워크플로, 모델 라우팅, structured output
- **RAG 설계**: 하이브리드 검색, 시간 가중치, 메타데이터 필터링, 도메인 특화 청킹
- **GraphRAG 판단력**: "왜 그래프 DB 대신 관계형 경량 구현을 택했고, 어느 규모부터
  전환하는가"라는 트레이드오프 서사
- **평가 파이프라인**: 백테스트 기반 정량 평가 — LLM 시스템의 실효성 검증 능력
- **운영 관점**: Langfuse 관측성, 비용 최적화, 데이터 품질 관리
