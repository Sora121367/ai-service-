from fastapi import FastAPI

from app.api.errors import register_error_handlers

app = FastAPI(
    title="InsightHub AI Service (internal)",
    version="0.1.0",
    description="Internal API called only by Spring Boot. See contracts/ai-service.yaml.",
)

register_error_handlers(app)


@app.get("/health", operation_id="health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Feature routers are mounted with app.api.routing.include_protected(router, app).
