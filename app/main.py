from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.containers import container


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="News2", lifespan=lifespan)
app.container = container
