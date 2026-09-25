import azure.functions as func

from app.main import create_app


def test_docs_page_is_served(client):
    assert client.get("/api/docs").status_code == 200


def test_openapi_is_served_under_api(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]


def test_every_documented_path_lives_under_api():
    assert all(path.startswith("/api/") for path in create_app().openapi()["paths"])


def test_paths_outside_api_are_404(client):
    assert client.get("/").status_code == 404
    assert client.get("/health").status_code == 404


def test_function_app_wraps_fastapi_anonymously():
    import function_app

    assert isinstance(function_app.app, func.AsgiFunctionApp)
    assert function_app.app.auth_level == func.AuthLevel.ANONYMOUS
