from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audit, auth, automation, ccp, compliance, dashboard, kpi, recall, risk, trace, ui
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.security import AuthRequiredMiddleware, InMemoryRateLimiterMiddleware, RequestContextMiddleware

app = FastAPI(
    title="Supply Intelligence and Compliance Automation API",
    version="0.1.0",
    description=(
        "AI-assisted traceability, compliance intelligence, risk detection, and "
        "audit automation. Not a legal certification system."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(AuthRequiredMiddleware)
app.add_middleware(InMemoryRateLimiterMiddleware)
register_exception_handlers(app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(trace.router, prefix="/api/v1/trace", tags=["traceability"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(compliance.router, prefix="/api/v1/compliance", tags=["compliance"])
app.include_router(ccp.router, prefix="/api/v1/ccp", tags=["ccp"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(automation.router, prefix="/api/v1/automation", tags=["automation"])
app.include_router(recall.router, prefix="/api/v1/recall", tags=["recall"])
app.include_router(risk.router, prefix="/api/v1/ai", tags=["risk"])
app.include_router(kpi.router, prefix="/api/v1/kpi", tags=["kpi"])
app.include_router(ui.router, tags=["ui"])
