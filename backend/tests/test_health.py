import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import UserRole
from fake_mongodb import FakeDatabase


class HealthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()

        async def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.s3_check = patch("app.main.s3_is_available", new_callable=AsyncMock, return_value=True)
        self.s3_check.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.s3_check.stop()

    def authorize_admin(self):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=UserRole.ADMIN)

    def test_liveness_does_not_ping_database(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(self.db.command_calls, 0)

    def test_readiness_reports_database_available(self):
        response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "database": "reachable"})

    def test_readiness_returns_503_when_database_fails(self):
        self.db.command_error = ConnectionError("database unavailable")

        response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], {
            "status": "not_ready",
            "database": "unavailable",
        })

    def test_readiness_times_out_when_database_hangs(self):
        async def hang_on_command(command):
            await asyncio.sleep(1)

        self.db.command = hang_on_command
        with patch("app.main.HEALTH_CHECK_TIMEOUT_SECONDS", 0.01):
            response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["database"], "unavailable")

    def test_health_detail_requires_admin_role(self):
        response = self.client.get("/health/detail")

        self.assertEqual(response.status_code, 401)

    def test_health_detail_rejects_non_admin(self):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=UserRole.TECHNICIAN)

        response = self.client.get("/health/detail", headers={"Authorization": "Bearer test"})

        self.assertEqual(response.status_code, 403)

    def test_admin_health_detail_reports_dependencies_separately(self):
        self.authorize_admin()

        response = self.client.get("/health/detail")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "database": {"status": "ok"},
            "s3": {"status": "ok"},
        })

    def test_admin_health_detail_keeps_database_and_s3_status_separate(self):
        self.authorize_admin()
        self.db.command_error = ConnectionError("database unavailable")
        self.s3_check.stop()
        self.s3_check = patch("app.main.s3_is_available", new_callable=AsyncMock, return_value=False)
        self.s3_check.start()

        response = self.client.get("/health/detail")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "database": {"status": "unavailable"},
            "s3": {"status": "unavailable"},
        })


if __name__ == "__main__":
    unittest.main()
