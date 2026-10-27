from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


def test_invalid_status_is_rejected_before_database_access() -> None:
    def database_must_not_be_accessed():
        yield object()

    app.dependency_overrides[get_db] = database_must_not_be_accessed
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/assets/00000000-0000-0000-0000-000000000001/operational-status",
            json={
                "status": "banana",
                "source": "user",
                "actor": "admin",
                "reason": "invalid status test",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.close()

    assert response.status_code == 422
