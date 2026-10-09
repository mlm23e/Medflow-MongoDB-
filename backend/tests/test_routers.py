from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import EquipStatus, OrderPriority, OrderStatus, UserRole


class FakeResult:
    def __init__(self, items=None, rows=None, scalar=None):
        self.items = items or []
        self.rows = rows or []
        self.scalar = scalar

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.items if self.items else self.rows

    def scalar_one_or_none(self):
        return self.scalar


class FakeSession:
    def __init__(self):
        self.execute = AsyncMock(return_value=FakeResult())
        self.get = AsyncMock(return_value=None)
        self.add = Mock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.delete = AsyncMock()


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.current_user = SimpleNamespace(role=UserRole.TECHNICIAN)

        async def override_db():
            yield self.session

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()

    def test_login_rejects_unknown_user(self):
        response = self.client.post(
            "/auth/token",
            data={"username": "unknown", "password": "not-a-password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect username or password")

    def test_equipment_list_returns_database_rows(self):
        equipment = SimpleNamespace(
            id=4,
            serial_number="MED-004",
            model="Monitor X",
            status=EquipStatus.AVAILABLE,
            charge_level=Decimal("18.50"),
            facility_id=2,
        )
        self.session.execute.return_value = FakeResult(items=[equipment])

        response = self.client.get("/equipment?max_charge=20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["serial_number"], "MED-004")
        self.assertEqual(response.json()[0]["charge_level"], "18.50")

    def test_equipment_filter_rejects_out_of_range_charge(self):
        response = self.client.get("/equipment?max_charge=101")

        self.assertEqual(response.status_code, 422)
        self.session.execute.assert_not_awaited()

    def test_equipment_create_returns_404_for_missing_hospital(self):
        self.current_user.role = UserRole.ADMIN

        response = self.client.post(
            "/equipment",
            json={
                "serial_number": "MED-NEW",
                "model": "Monitor X",
                "charge_level": 80,
                "facility_id": 99,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Facility '99' not found")
        self.session.add.assert_not_called()

    def test_hospital_maintenance_flags_serializes_aggregate(self):
        self.session.execute.return_value = FakeResult(
            rows=[
                {
                    "id": 7,
                    "name": "North Clinic",
                    "equipment_total": 4,
                    "maintenance_total": 2,
                    "maintenance_rate": Decimal("50.0"),
                }
            ]
        )

        response = self.client.get("/hospitals/maintenance-flags")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["name"], "North Clinic")
        self.assertEqual(response.json()[0]["maintenance_rate"], "50.0")

    def test_report_create_returns_404_for_missing_work_order(self):
        response = self.client.post(
            "/reports",
            json={"work_order_id": 404, "file_url": "s3://bucket/report.txt", "notes": "test"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "WorkOrder '404' not found")

    def test_user_list_requires_admin_role(self):
        response = self.client.get("/users")

        self.assertEqual(response.status_code, 403)
        self.session.execute.assert_not_awaited()

    def test_active_calls_returns_technician_summary(self):
        self.session.execute.return_value = FakeResult(
            rows=[
                {
                    "technician_id": 12,
                    "first_name": "Ari",
                    "last_name": "Lee",
                    "active_call_count": 3,
                }
            ]
        )

        response = self.client.get("/users/active-calls/12")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [
            {
                "technician_id": 12,
                "first_name": "Ari",
                "last_name": "Lee",
                "active_call_count": 3,
            }
        ])

    def test_reliability_returns_completion_and_failure_rates(self):
        self.session.execute.return_value = FakeResult(
            rows=[
                {
                    "model": "Monitor X",
                    "total_calls": 4,
                    "completed_calls": 2,
                    "failed_calls": 1,
                }
            ]
        )

        response = self.client.get("/work_orders/reliability")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["total_calls"], 4)
        self.assertAlmostEqual(float(response.json()[0]["completion_rate"]), 66.6667, places=3)
        self.assertAlmostEqual(float(response.json()[0]["failure_rate"]), 33.3333, places=3)

    def test_discrepancy_route_serializes_cross_hospital_assignment(self):
        self.session.execute.return_value = FakeResult(
            rows=[
                {
                    "work_order_id": 8,
                    "title": "Inspect pump",
                    "equipment_id": 3,
                    "equipment_facility_id": 2,
                    "technician_id": 9,
                    "technician_facility_id": 5,
                }
            ]
        )

        response = self.client.get("/work_orders/discrepancies?priority=Critical")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["equipment_facility_id"], 2)
        self.assertEqual(response.json()[0]["technician_facility_id"], 5)

    def test_completing_work_order_sets_completion_timestamp(self):
        work_order = SimpleNamespace(
            id=6,
            title="Replace battery",
            priority=OrderPriority.CRITICAL,
            status=OrderStatus.IN_PROGRESS,
            equipment_id=3,
            technician_id=9,
            created_at=datetime(2026, 1, 1),
            completed_at=None,
        )
        self.session.get.return_value = work_order

        response = self.client.patch(
            "/work_orders/6/status",
            json={"status": "Completed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "Completed")
        self.assertIsNotNone(work_order.completed_at)


if __name__ == "__main__":
    unittest.main()