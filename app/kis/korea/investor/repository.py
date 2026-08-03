"""투자자 수급 응답을 ORM 행으로 변환하고 저장한다."""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.instruments.models import Instrument, Market
from app.core._time import KST
from app.kis.korea.investor.models import InvestorFlow
from app.kis.korea.investor.schemas import (
    INVESTOR_FLOW_FIELD_PARTS,
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowResult,
    InvestorType,
    MarketFinalFlowBody,
    MarketIntradayFlowBody,
    MarketInvestorFlowDetails,
    MarketInvestorFlowValues,
    StockFinalFlowBody,
    StockIntradayFlowDetails,
    StockIntradayFlowBody,
)


logger = get_logger(__name__)

# 재시도를 같은 눈금에 묶기 위한 슬롯 크기. 시장 수집이 30분 간격이고, 종목
# 수집 시각(09:31·10:01·11:21·13:21·14:31)도 서로 다른 30분 슬롯에 떨어진다.
SNAPSHOT_SLOT_MINUTES = 30


def snapshot_slot_start(moment: datetime) -> datetime:
    """수집 시각을 고정 슬롯의 시작 시각으로 내린다.

    snapshot_ts가 UNIQUE 키에 있으므로 매 호출마다 새 시각을 쓰면 재시도가 곧
    중복 저장이 된다. 같은 슬롯의 재시도가 같은 값을 쓰도록 눈금을 맞춘다.

    Args:
        moment: 내림할 timezone-aware 시각.

    Returns:
        SNAPSHOT_SLOT_MINUTES 단위로 내린 시각.
    """

    return moment.replace(
        minute=moment.minute // SNAPSHOT_SLOT_MINUTES * SNAPSHOT_SLOT_MINUTES,
        second=0,
        microsecond=0,
    )


def to_flow_rows(
    result: InvestorFlowResult,
    options: InvestorFlowProbeOptions,
    instrument_id: int,
    snapshot_ts: datetime,
) -> list[InvestorFlow]:
    """응답 1건을 투자자 유형별 InvestorFlow 행 목록으로 펼친다.

    Args:
        result: 서비스가 수집한 단일 KIS 응답 결과.
        options: 수집 실행 옵션. phase로 is_provisional을, trade_date로 기준일을 정한다.
        instrument_id: result.target에 대응하는 instruments.id.
        snapshot_ts: 응답을 수신한 timezone-aware UTC 시각.

    Returns:
        저장 가능한 InvestorFlow 행 목록. 오류 응답이거나 파싱하지 못한 본문이면 빈 목록.
    """

    trade_date = options.trade_date or snapshot_ts.astimezone(KST).date()
    is_provisional = options.phase is InvestorFlowPhase.INTRADAY

    match result.body:
        case StockIntradayFlowBody() as body:
            return [
                _to_row(
                    result=result,
                    instrument_id=instrument_id,
                    trade_date=trade_date,
                    is_provisional=is_provisional,
                    snapshot_ts=snapshot_ts,
                    investor_type=investor_type,
                    net_buy_volume=net_buy_volume,
                    net_buy_value=None,
                    time_bucket=row.bsop_hour_gb,
                    # 합계는 외국인+기관의 파생값이라 별도 행으로 만들지 않는다.
                    details=StockIntradayFlowDetails(sum_fake_ntby_qty=row.sum_fake_ntby_qty),
                )
                for row in body.output2
                for investor_type, net_buy_volume in (
                    (InvestorType.FOREIGN, row.frgn_fake_ntby_qty),
                    (InvestorType.INSTITUTION, row.orgn_fake_ntby_qty),
                )
            ]
        case MarketIntradayFlowBody() as body:
            return [
                _to_market_row(
                    result=result,
                    instrument_id=instrument_id,
                    trade_date=trade_date,
                    is_provisional=is_provisional,
                    snapshot_ts=snapshot_ts,
                    investor_type=investor_type,
                    values=values,
                )
                for row in body.output
                for investor_type in InvestorType
                for values in (row.values_for(investor_type),)
                if values.reports_investor
            ]
        case StockFinalFlowBody() as body:
            return [
                _to_market_row(
                    result=result,
                    instrument_id=instrument_id,
                    trade_date=trade_date,
                    is_provisional=is_provisional,
                    snapshot_ts=snapshot_ts,
                    investor_type=investor_type,
                    values=row.values_for(investor_type),
                )
                for row in body.output2
                if row.stck_bsop_date == trade_date.strftime("%Y%m%d")
                for investor_type in InvestorType
            ]
        case MarketFinalFlowBody() as body:
            return [
                _to_row(
                    result=result,
                    instrument_id=instrument_id,
                    trade_date=trade_date,
                    is_provisional=is_provisional,
                    snapshot_ts=snapshot_ts,
                    investor_type=investor_type,
                    net_buy_volume=getattr(row, f"{prefix}_ntby_{volume_suffix}"),
                    net_buy_value=getattr(row, f"{prefix}_ntby_tr_pbmn"),
                    time_bucket="",
                    # 시장 장마감 TR은 매수·매도 총량 없이 순매수만 제공한다.
                    details=None,
                )
                for row in body.output
                if row.stck_bsop_date == trade_date.strftime("%Y%m%d")
                for investor_type in InvestorType
                for prefix, volume_suffix in (INVESTOR_FLOW_FIELD_PARTS[investor_type],)
            ]
        case _:
            # TR 4종에는 모두 전용 DTO가 있으므로, 여기 오는 것은 rt_cd != "0"
            # 오류 봉투이거나 JSON이 아닌 본문(InvestorFlowTextBody)이다.
            return []


def _to_market_row(
    *,
    result: InvestorFlowResult,
    instrument_id: int,
    trade_date: date,
    is_provisional: bool,
    snapshot_ts: datetime,
    investor_type: InvestorType,
    values: MarketInvestorFlowValues,
) -> InvestorFlow:
    """시장 TR 행에서 한 투자자 유형의 순매수를 뽑아 ORM 행으로 만든다."""

    return _to_row(
        result=result,
        instrument_id=instrument_id,
        trade_date=trade_date,
        is_provisional=is_provisional,
        snapshot_ts=snapshot_ts,
        investor_type=investor_type,
        net_buy_volume=values.net_buy_volume,
        # *_ntby_tr_pbmn은 백만원 단위다. 환산하지 않고 원본 그대로 저장하고,
        # 억원이 필요한 쪽에서 100으로 나눈다. 여기서 곱해두면 되돌릴 수 없다.
        net_buy_value=values.net_buy_value,
        time_bucket="",
        details=values.details,
    )


def _to_row(
    *,
    result: InvestorFlowResult,
    instrument_id: int,
    trade_date: date,
    is_provisional: bool,
    snapshot_ts: datetime,
    investor_type: InvestorType,
    net_buy_volume: int | None,
    net_buy_value: int | None,
    time_bucket: str,
    details: StockIntradayFlowDetails | MarketInvestorFlowDetails | None,
) -> InvestorFlow:
    """모든 TR이 공유하는 InvestorFlow 행을 만든다."""

    return InvestorFlow(
        instrument_id=instrument_id,
        trade_date=trade_date,
        venue=result.venue,
        investor_type=investor_type,
        net_buy_volume=net_buy_volume,
        net_buy_value=net_buy_value,
        time_bucket=time_bucket,
        is_provisional=is_provisional,
        snapshot_ts=snapshot_ts,
        details=details.model_dump(mode="json") if details is not None else {},
    )


class KISInvestorFlowRepository:
    """투자자 수급 응답 묶음을 한 트랜잭션으로 저장한다."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """비동기 세션 팩토리를 주입받는다.

        Args:
            session_factory: 작업 단위마다 세션을 만드는 SQLAlchemy 팩토리.
        """

        self._session_factory = session_factory

    async def save(
        self,
        results: tuple[InvestorFlowResult, ...],
        options: InvestorFlowProbeOptions,
        snapshot_ts: datetime,
    ) -> int:
        """한 번의 수집 결과 전체를 같은 트랜잭션으로 저장한다.

        같은 snapshot_ts에 이미 저장된 (instrument, venue)는 건너뛴다. Celery 재시도가
        같은 슬롯을 다시 수집해도 중복이 쌓이지 않게 하기 위한 것이다.
        instruments에 등록되지 않은 대상도 건너뛰고 경고 로그만 남긴다.

        Args:
            results: 서비스가 수집한 응답 결과 묶음.
            options: 수집에 사용한 수집 실행 옵션.
            snapshot_ts: snapshot_slot_start로 내린 timezone-aware UTC 시각.

        Returns:
            저장한 InvestorFlow 행 수. 전부 건너뛰었으면 0.
        """

        # 확정치는 하루에 하나뿐이라 snapshot_ts와 무관하게 이미 있으면 건너뛴다.
        # 백필은 수백 날짜를 한 snapshot_ts로 도는데, 여기에 snapshot_ts 조건을 걸면
        # 재실행할 때마다 같은 거래일이 통째로 다시 쌓인다.
        # 장중 잠정치는 반대로 슬롯별 이력이 분석 대상이라 snapshot_ts로 좁힌다.
        trade_date = options.trade_date or snapshot_ts.astimezone(KST).date()
        is_provisional = options.phase is InvestorFlowPhase.INTRADAY
        saved_statement = (
            select(InvestorFlow.instrument_id, InvestorFlow.venue)
            .where(
                InvestorFlow.trade_date == trade_date,
                InvestorFlow.is_provisional.is_(is_provisional),
            )
            .distinct()
        )
        if is_provisional:
            saved_statement = saved_statement.where(InvestorFlow.snapshot_ts == snapshot_ts)
        instrument_statement = select(Instrument.ticker, Instrument.id).where(
            Instrument.market == Market.KRX,
            Instrument.ticker.in_({result.target for result in results}),
        )
        rows: list[InvestorFlow] = []

        async with self._session_factory.begin() as session:
            # 종목 task와 시장 task는 스케줄이 달라 같은 거래일에 겹칠 수 있다.
            # 거래일 단위로만 막으면 먼저 저장한 쪽이 나중 쪽을 통째로 삼키므로
            # (instrument, venue) 단위로 좁힌다. 마감 종목 TR은 KRX와 NXT를 따로
            # 호출하므로, instrument만 보면 KRX만 저장된 부분 성공 상태에서
            # 재실행해도 NXT를 영영 복구하지 못한다.
            # ponytail: beat 1개 + worker concurrency 1 전제라 검사와 삽입 사이에
            # 경쟁이 없다. 동시 실행을 붙이면 pg insert(...).on_conflict_do_nothing(
            # constraint="uq_investor_flows_snapshot")으로 바꿀 것.
            already_saved = set((await session.execute(saved_statement)).all())
            instrument_ids = dict((await session.execute(instrument_statement)).all())
            for result in results:
                instrument_id = instrument_ids.get(result.target)
                if instrument_id is None:
                    logger.warning(
                        "investor_flow_instrument_missing",
                        target=result.target,
                        tr_id=result.tr_id.value,
                    )
                    continue

                if (instrument_id, result.venue) in already_saved:
                    logger.info(
                        "investor_flow_slot_already_saved",
                        target=result.target,
                        venue=result.venue.value,
                        snapshot_ts=snapshot_ts.isoformat(),
                    )
                    continue

                result_rows = to_flow_rows(result, options, instrument_id, snapshot_ts)
                if not result_rows:
                    # 오류 응답이거나, 성공 응답인데 해당 영업일 행이 없는 경우다.
                    # (마감 TR은 여러 날치를 돌려주므로 trade_date로 걸러낸다.)
                    # 조용히 사라지면 무인 배치에서 며칠씩 누락을 못 알아챈다.
                    logger.warning(
                        "investor_flow_response_unusable",
                        target=result.target,
                        tr_id=result.tr_id.value,
                        http_status=result.http_status,
                    )
                rows.extend(result_rows)

            session.add_all(rows)

        return len(rows)
