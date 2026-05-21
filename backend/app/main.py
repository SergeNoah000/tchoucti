"""FastAPI entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.middleware import TenantMiddleware
from app.api.v1 import api_router

# Import models so SQLAlchemy registers them at startup
import app.models  # noqa: F401



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantMiddleware)

# Routes
app.include_router(api_router, prefix="/api")


@app.get("/api/health")

async def health():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENVIRONMENT}


@app.get("/api/whoami-tenant")
async def whoami_tenant(request: Request):
    """Debug helper — returns the resolved tenant context."""
    ctx = request.state.tenant
    return {
        "is_platform_admin": ctx.is_platform_admin,
        "groupement_slug": ctx.groupement_slug,
        "raw_host": ctx.raw_host,
    }
