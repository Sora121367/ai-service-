from fastapi import APIRouter, Depends, FastAPI

from app.api.auth import require_service_token


def include_protected(router: APIRouter, target: FastAPI) -> None:
    """Mount a feature router. Every endpoint except /health requires the service token."""
    target.include_router(router, dependencies=[Depends(require_service_token)])
