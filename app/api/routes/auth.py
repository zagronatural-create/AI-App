from fastapi import APIRouter, Depends

from app.core.auth import AuthUser, get_current_user
from app.core.config import settings

router = APIRouter()


@router.get('/whoami')
def whoami(current_user: AuthUser = Depends(get_current_user)) -> dict:
    return {
        'auth_enabled': settings.auth_enabled,
        'user': current_user.model_dump(),
    }
