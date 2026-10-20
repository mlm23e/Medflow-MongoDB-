from datetime import datetime
from types import SimpleNamespace
import unittest

from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models import EquipStatus, OrderPriority, OrderStatus, UserRole
from fake_mongodb import FakeDatabase


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.current_user = SimpleNamespace(role=UserRole.TECHNICIAN)

        async def override_db():
            yield self.db

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
        self.db.equipment.documents.append({
            "id": 4,
            "serial_number": "MED-004",
            "model": "Monitor X",
            "status": EquipStatus.AVAILABLE.value,
            "charge_level": 18.5,
            "facility_id": 2,
        })

        response = self.client.get("/equipment?max_charge=20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["serial_number"], "MED-004")
        self.assertEqual(response.json()[0]["charge_level"], "18.5")

    def test_equipment_filter_rejects_out_of_range_charge(self):
        response = self.client.get("/equipment?max_charge=101")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.db.equipment.find_calls, 0)

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
        self.assertEqual(self.db.equipment.documents, [])

    def test_hospital_maintenance_flags_serializes_aggregate(self):
        self.db.hospitals.documents.append({"id": 7, "name": "North Clinic"})
        self.db.equipment.documents.extend([
            {"id": 1, "facility_id": 7, "status": "Maintenance"},
            {"id": 2, "facility_id": 7, "status": "Maintenance"},
            {"id": 3, "facility_id": 7, "status": "Available"},
            {"id": 4, "facility_id": 7, "status": "Available"},
        ])

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
        self.assertEqual(self.db.users.find_calls, 0)

    def test_active_calls_returns_technician_summary(self):
        self.db.users.documents.append({
            "id": 12,
            "first_name": "Ari",
            "last_name": "Lee",
            "role": UserRole.TECHNICIAN.value,
            "facility_id": 2,
        })
        self.db.hospitals.documents.append({"id": 2})
        self.db.work_orders.documents.extend([
            {"id": 1, "technician_id": 12, "status": OrderStatus.PENDING.value},
            {"id": 2, "technician_id": 12, "status": OrderStatus.IN_PROGRESS.value},
            {"id": 3, "technician_id": 12, "status": OrderStatus.COMPLETED.value},
        ])

        response = self.client.get("/users/active-calls/12")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{
            "technician_id": 12,
            "first_name": "Ari",
            "last_name": "Lee",
            "active_call_count": 2,
        }])

    def test_reliability_returns_completion_and_failure_rates(self):
        self.db.equipment.documents.append({"id": 3, "model": "Monitor X"})
        self.db.work_orders.documents.extend([
            {"id": 1, "equipment_id": 3, "status": OrderStatus.COMPLETED.value},
            {"id": 2, "equipment_id": 3, "status": OrderStatus.COMPLETED.value},
            {"id": 3, "equipment_id": 3, "status": OrderStatus.FAILED.value},
            {"id": 4, "equipment_id": 3, "status": OrderStatus.PENDING.value},
        ])

        response = self.client.get("/work_orders/reliability")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["total_calls"], 4)
        self.assertAlmostEqual(float(response.json()[0]["completion_rate"]), 66.6667, places=3)
        self.assertAlmostEqual(float(response.json()[0]["failure_rate"]), 33.3333, places=3)

    def test_discrepancy_route_serializes_cross_hospital_assignment(self):
        self.db.equipment.documents.append({"id": 3, "facility_id": 2})
        self.db.users.documents.extend([
            {"id": 9, "facility_id": 5},
            {"id": 10, "facility_id": None},
        ])
        self.db.work_orders.documents.append({
            "id": 8,
            "title": "Inspect pump",
            "equipment_id": 3,
            "technician_id": 9,
            "priority": OrderPriority.CRITICAL.value,
        })
        self.db.work_orders.documents.append({
            "id": 9,
            "title": "Unassigned technician",
            "equipment_id": 3,
            "technician_id": 10,
            "priority": OrderPriority.CRITICAL.value,
        })

        response = self.client.get("/work_orders/discrepancies?priority=Critical")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["equipment_facility_id"], 2)
        self.assertEqual(response.json()[0]["technician_facility_id"], 5)

    def test_completing_work_order_sets_completion_timestamp(self):
        self.db.work_orders.documents.append({
            "id": 6,
            "title": "Replace battery",
            "priority": OrderPriority.CRITICAL.value,
            "status": OrderStatus.IN_PROGRESS.value,
            "equipment_id": 3,
            "technician_id": 9,
            "created_at": datetime(2026, 1, 1),
            "completed_at": None,
        })

        response = self.client.patch(
            "/work_orders/6/status",
            json={"status": "Completed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "Completed")
        self.assertIsNotNone(response.json()["completed_at"])


if __name__ == "__main__":
    unittest.main()
