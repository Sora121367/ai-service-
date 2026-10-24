from fastapi import FastAPI

app = FastAPI(
    title="InsightHub AI Service (internal)",
    version="0.1.0",
    description="Internal API called only by Spring Boot. See contracts/ai-service.yaml.",
)


@app.get("/health", operation_id="health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Feature routers are mounted with app.api.routing.include_protected(router, app).
