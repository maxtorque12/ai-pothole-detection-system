"""System Health Check & Automated Verification Suite.

Validates:
  1. PyTorch CUDA GPU availability (RTX 4060) and trained weights loading.
  2. Severity classification logic (<2% Low, 2-6% Medium, >6% High).
  3. Haversine geospatial clustering formula (5m radius threshold).
  4. Backend REST API lifecycle (POST defect, GET filters, PATCH status).
  5. Static web dashboard assets and mock data integrity.
"""

from __future__ import annotations

import sys
import unittest
import numpy as np
import torch
from ultralytics import YOLO

from backend_service.app import create_app
from backend_service.clustering import haversine_distance, find_nearby_cluster
from edge_detection.detector import classify_severity, encode_image_base64
from edge_detection.alert import AlertManager
from edge_detection.gps_tracker import GPSTracker


class TestPotholeSystem(unittest.TestCase):
    def test_01_cuda_and_model_loading(self):
        """Verifies GPU acceleration and trained YOLO weights."""
        self.assertTrue(torch.cuda.is_available(), "CUDA GPU is not detected.")
        gpu_name = torch.cuda.get_device_name(0)
        print(f"\n  [✓] GPU Active: {gpu_name}")

        model = YOLO("weights/pothole_best.pt")
        self.assertEqual(model.names[0], "pothole", "Model class 0 must be 'pothole'.")
        print(f"  [✓] Loaded model weights: weights/pothole_best.pt ({model.names})")

    def test_02_severity_classification(self):
        """Validates bounding box to frame area severity tier boundaries."""
        # Low: < 2% (e.g. 1% -> ratio 0.01)
        sev_low, ratio_low = classify_severity(100, 10000)
        self.assertEqual(sev_low, "Low")
        self.assertAlmostEqual(ratio_low, 0.01)

        # Medium: 2% to 6% (e.g. 4% -> ratio 0.04)
        sev_med, ratio_med = classify_severity(400, 10000)
        self.assertEqual(sev_med, "Medium")
        self.assertAlmostEqual(ratio_med, 0.04)

        # High: > 6% (e.g. 8% -> ratio 0.08)
        sev_high, ratio_high = classify_severity(800, 10000)
        self.assertEqual(sev_high, "High")
        self.assertAlmostEqual(ratio_high, 0.08)
        print(f"  [✓] Severity Tiers Verified: Low (<2%), Medium (2-6%), High (>6%)")

    def test_03_haversine_clustering(self):
        """Validates Haversine 5m duplicate detection clustering."""
        # 3.3 meters apart (should cluster)
        d_close = haversine_distance(28.61390, 77.20900, 28.61393, 77.20900)
        self.assertLess(d_close, 5.0)

        # 678 meters apart (should not cluster)
        d_far = haversine_distance(28.61390, 77.20900, 28.62000, 77.20900)
        self.assertGreater(d_far, 5.0)

        match = find_nearby_cluster(28.61393, 77.20900, [{"latitude": 28.61390, "longitude": 77.20900, "cluster_id": "c1"}], radius_meters=5.0)
        self.assertIsNotNone(match)
        self.assertEqual(match[0]["cluster_id"], "c1")
        print(f"  [✓] Haversine 5m Spatial Clustering Verified ({d_close:.2f}m clustered, {d_far:.2f}m separate)")

    def test_04_backend_api_lifecycle(self):
        """Tests Flask POST /api/v1/potholes, GET with filters, and PATCH status."""
        app = create_app()
        client = app.test_client()

        # Dummy 10x10 test image
        dummy_img = np.zeros((10, 10, 3), dtype=np.uint8)
        b64 = encode_image_base64(dummy_img)

        # 1. POST
        res_post = client.post("/api/v1/potholes", json={
            "timestamp": "2026-10-22T10:00:00Z",
            "track_id": 42,
            "latitude": 28.6139,
            "longitude": 77.2090,
            "severity": "High",
            "confidence": 0.94,
            "image": b64,
            "crop_image": b64,
        })
        self.assertEqual(res_post.status_code, 201)
        data = res_post.get_json()["data"]
        doc_id = data["id"]
        self.assertEqual(data["severity"], "High")
        self.assertEqual(data["status"], "reported")
        self.assertEqual(data["track_id"], 42)
        self.assertTrue(data["image_url"].startswith("/uploads/pothole_"))
        self.assertTrue(data["crop_url"].startswith("/uploads/crop_"))

        # 2. GET
        res_get = client.get("/api/v1/potholes?severity=High")
        self.assertEqual(res_get.status_code, 200)
        items = res_get.get_json()["data"]
        self.assertTrue(any(x["id"] == doc_id for x in items))

        # 3. PATCH
        res_patch = client.patch(f"/api/v1/potholes/{doc_id}", json={"status": "in-progress"})
        self.assertEqual(res_patch.status_code, 200)
        self.assertEqual(res_patch.get_json()["data"]["status"], "in-progress")

        # 4. DELETE (Flush data & snapshots)
        res_del = client.delete("/api/v1/potholes")
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.get_json()["status"], "success")
        res_after = client.get("/api/v1/potholes")
        self.assertEqual(len(res_after.get_json()["data"]), 0)

        # 5. Mobile Phone GPS Telemetry Sync
        res_gps = client.post("/api/v1/telemetry/gps", json={"latitude": 28.6186, "longitude": 77.3013, "accuracy": 5.0})
        self.assertEqual(res_gps.status_code, 200)
        res_gps_get = client.get("/api/v1/telemetry/gps")
        self.assertEqual(res_gps_get.status_code, 200)
        self.assertEqual(res_gps_get.get_json()["data"]["latitude"], 28.6186)
        print(f"  [✓] REST API Lifecycle Verified (POST -> GET -> PATCH -> DELETE -> GPS Sync)")

    def test_05_web_dashboard_integration(self):
        """Verifies municipal dashboard static files and mock data."""
        app = create_app()
        client = app.test_client()

        r_dash = client.get("/")
        self.assertEqual(r_dash.status_code, 200)
        self.assertIn(b"AI Municipal Pothole Detection", r_dash.data)

        r_mock = client.get("/mock_data.json")
        self.assertEqual(r_mock.status_code, 200)
        print(f"  [✓] Web Dashboard & Leaflet Map Assets Verified")


if __name__ == "__main__":
    print("====================================================================")
    print(" AI POTHOLE DETECTION SYSTEM - AUTOMATED VERIFICATION SUITE")
    print("====================================================================")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPotholeSystem)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n>>> ALL SYSTEM TESTS PASSED SUCCESSFULLY! <<<")
        sys.exit(0)
    else:
        print("\n[!] Tests failed. Review output above.")
        sys.exit(1)
