from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()

OPS_HTML = Path(__file__).resolve().parents[2] / "web" / "ops_dashboard.html"


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/ops", status_code=307)


@router.get("/ops")
def ops_dashboard() -> FileResponse:
    return FileResponse(OPS_HTML)
