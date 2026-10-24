def test_openapi_exposes_health_operation(client):
    spec = client.get("/openapi.json").json()

    assert spec["info"]["title"] == "InsightHub AI Service (internal)"
    assert spec["paths"]["/health"]["get"]["operationId"] == "health"
