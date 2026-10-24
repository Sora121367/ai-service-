from fastapi import APIRouter, Depends, FastAPI

from app.auth import require_service_token

app = FastAPI(
    title="InsightHub AI Service (internal)",
    version="0.1.0",
    description="Internal API called only by Spring Boot. See contracts/ai-service.yaml.",
)


@app.get("/health", operation_id="health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def include_protected(router: APIRouter, target: FastAPI = app) -> None:
    """Mount a feature router. Every endpoint except /health requires the service token."""
    target.include_router(router, dependencies=[Depends(require_service_token)])
