"""공용 enum_column 헬퍼와 Enum 컬럼 DDL 동결 회귀 테스트."""

from enum import StrEnum

from sqlalchemy import CheckConstraint

from app.core.models import enum_column
from app.instruments.models import Instrument, Market
from app.kis.korea.investor.models import InvestorFlow
from app.macro.us_treasury.models import UsTreasuryBar, UsTreasuryYieldDaily


class SampleEnum(StrEnum):
    FIRST_MEMBER = "first"
    SECOND_MEMBER = "second"


FROZEN_DDL = [
    (
        Instrument,
        "market",
        "instrument_market",
        9,
        ["KRX", "NASDAQ", "NYSE_ARCA"],
    ),
    (
        InvestorFlow,
        "venue",
        "investor_flow_venue",
        11,
        ["KRX", "NXT", "UNSPECIFIED"],
    ),
    (
        InvestorFlow,
        "investor_type",
        "investor_flow_investor_type",
        18,
        [
            "foreign",
            "retail",
            "institution",
            "securities",
            "trust",
            "private_equity",
            "bank",
            "insurance",
            "merchant_bank",
            "pension_fund",
            "other_organization",
            "other_corporation",
        ],
    ),
    (
        UsTreasuryBar,
        "series",
        "us_treasury_series",
        5,
        ["US10Y", "ZN"],
    ),
    (
        UsTreasuryYieldDaily,
        "series",
        "us_treasury_series",
        5,
        ["US10Y", "ZN"],
    ),
]


def test_enum_column_applies_project_flags() -> None:
    column_type = enum_column(SampleEnum, name="sample")

    assert column_type.name == "sample"
    assert column_type.native_enum is False
    assert column_type.create_constraint is True
    assert column_type.validate_strings is True


def test_enum_column_persists_member_values() -> None:
    column_type = enum_column(SampleEnum, name="sample")

    assert list(column_type.enums) == ["first", "second"]
    assert column_type.length == 6


def test_enum_column_returns_new_instance_per_call() -> None:
    first = enum_column(SampleEnum, name="sample")
    second = enum_column(SampleEnum, name="sample")

    assert first is not second


def test_market_member_names_equal_values() -> None:
    for member in Market:
        assert member.name == member.value


def test_enum_columns_keep_frozen_ddl() -> None:
    for model, column_name, enum_name, length, values in FROZEN_DDL:
        table = model.__table__
        column_type = table.c[column_name].type

        assert column_type.name == enum_name
        assert column_type.native_enum is False
        assert column_type.create_constraint is True
        assert column_type.validate_strings is True
        assert column_type.length == length
        assert list(column_type.enums) == values

        checks = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name == enum_name
        ]
        assert len(checks) == 1
