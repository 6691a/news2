FROM python:3.13-slim

# uv 바이너리만 가져온다.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 의존성만 먼저 설치해 소스 변경 시에도 레이어 캐시를 재활용한다.
# build-system이 없는 프로젝트라 자기 자신은 설치하지 않고(PYTHONPATH로 실행) 의존성만 넣는다.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 애플리케이션 소스만 복사한다(.env·노트북은 이미지에 넣지 않는다).
COPY app ./app

# python -m app.kis → app/kis/__main__.py 실행.
CMD ["python", "-m", "app.kis"]
