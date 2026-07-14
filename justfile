# 사용 가능한 명령을 표시한다.
default:
    @just --list

migrate:
    uv run alembic upgrade head

makemigrations message:
    uv run alembic revision --autogenerate -m "{{message}}"
