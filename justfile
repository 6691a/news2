set shell := ["powershell", "-NoLogo", "-NoProfile", "-Command"]

default:
    @just --list

dev service="":
    docker compose -f compose.local.yaml up -d {{service}}

migrate:
    uv run alembic upgrade head

makemigrations message:
    uv run alembic revision --autogenerate -m "{{message}}"
