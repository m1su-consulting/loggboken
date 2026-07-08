from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import artifacts, environments, health, installations
from app.config import settings
from app.db import connect_pool, disconnect_pool
from app.errors import register_exception_handlers
from app.middleware import MaxBodySizeMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_pool()
    yield
    await disconnect_pool()


app = FastAPI(title="Environment Inventory", lifespan=lifespan)
register_exception_handlers(app)
app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_request_body_bytes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(installations.router, prefix="/api/v1")
app.include_router(environments.router, prefix="/api/v1")
app.include_router(artifacts.router, prefix="/api/v1")
