"""Alembic의 비동기 migration 환경을 구성한다."""

import asyncio
from importlib import import_module
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.containers import container
from app.core.database import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    container.settings().database_url.replace("%", "%%"),
)

import_module("app.instruments.models")
import_module("app.kis.korea.models")
import_module("app.kis.korea.investor.models")
import_module("app.kis.overseas.models")
import_module("app.macro.us_treasury.models")
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """DB에 연결하지 않고 migration SQL을 생성한다."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """동기 connection 문맥에서 migration을 실행한다.

    Args:
        connection: 비동기 connection에서 변환한 SQLAlchemy 동기 connection.
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """일회성 비동기 엔진으로 online migration을 실행한다."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"timezone": "UTC"}},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """비동기 엔진을 사용해 migration을 실행한다."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
