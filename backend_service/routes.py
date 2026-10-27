"""REST API route handlers for pothole registration, query filtering, and status updates.

Implements:
  - POST /api/v1/potholes: Validates payload, saves base64 snapshot to uploads/,
    clusters within 5m using Haversine, and persists to MongoDB.
  - GET /api/v1/potholes: Retrieves defects with query filters for severity and status.
  - PATCH /api/v1/potholes/<id>: Updates municipal repair status.
  - GET /uploads/<filename>: Serves persisted defect snapshots.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request, send_from_directory, Response
import threading
import time
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from backend_service.clustering import find_nearby_cluster
from backend_service.config import config

logger = logging.getLogger("backend_service.routes")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [Routes] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


class DatabaseManager:
    """Manages MongoDB connectivity with automated in-memory fallback for local dev."""

    def __init__(self) -> None:
        self._client: Optional[MongoClient] = None
        self._collection: Optional[Collection] = None
        self._is_in_memory: bool = False
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self._initialize_connection()

    def _initialize_connection(self) -> None:
        """Tries connecting to MongoDB, falling back to memory store if unavailable."""
        try:
            client: MongoClient = MongoClient(
                config.MONGO_URI,
                serverSelectionTimeoutMS=config.MONGO_TIMEOUT_MS,
            )
            # Ping database to verify live connection
            client.admin.command("ping")
            self._client = client
            db = self._client[config.MONGO_DB_NAME]
            self._collection = db[config.MONGO_COLLECTION_NAME]
            # Create 2dsphere index for geospatial queries if not present
            try:
                self._collection.create_index([("location", "2dsphere")])
            except Exception:
                pass
            self._is_in_memory = False
            logger.info("Connected to MongoDB successfully at '%s'", config.MONGO_URI)
        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as exc:
            logger.warning(
                "MongoDB connection failed (%s). Operating in robust IN-MEMORY mode.",
                exc.__class__.__name__,
            )
            self._is_in_memory = True

    @property
    def is_in_memory(self) -> bool:
        return self._is_in_memory

    def insert_pothole(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Inserts a pothole document, assigning a string ID."""
        doc_id = str(uuid.uuid4())
        record["id"] = doc_id
        record["created_at"] = record.get("created_at") or datetime.now(timezone.utc).isoformat()

        if self._is_in_memory or self._collection is None:
            self._memory_store[doc_id] = record.copy()
            return record.copy()

        try:
            mongo_doc = record.copy()
            mongo_doc["_id"] = doc_id
            self._collection.insert_one(mongo_doc)
            return record.copy()
        except Exception as exc:
            logger.error("MongoDB insert failed: %s. Falling back to memory.", exc)
            self._memory_store[doc_id] = record.copy()
            return record.copy()

    def find_all(
        self,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Queries defects with optional severity and status filters."""
        if self._is_in_memory or self._collection is None:
            results = list(self._memory_store.values())
            if severity:
                results = [
                    r for r in results if r.get("severity", "").lower() == severity.lower()
                ]
            if status:
                results = [
                    r for r in results if r.get("status", "").lower() == status.lower()
                ]
            results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return results[:limit]

        try:
            query: Dict[str, Any] = {}
            if severity:
                query["severity"] = {"$regex": f"^{severity}$", "$options": "i"}
            if status:
                query["status"] = status.lower()

            cursor = self._collection.find(query).sort("timestamp", -1).limit(limit)
            documents: List[Dict[str, Any]] = []
            for doc in cursor:
                # Normalize _id to string id
                doc["id"] = str(doc.get("_id", doc.get("id", "")))
                doc.pop("_id", None)
                documents.append(doc)
            return documents
        except Exception as exc:
            logger.error("MongoDB query failed: %s. Reading from memory store.", exc)
            results = list(self._memory_store.values())
            return results[:limit]

    def update_status(self, defect_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        """Updates repair status for a pothole by ID."""
        if self._is_in_memory or self._collection is None:
            if defect_id in self._memory_store:
                self._memory_store[defect_id]["status"] = new_status
                self._memory_store[defect_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                return self._memory_store[defect_id].copy()
            return None

        try:
            # Try finding by string ID first, then ObjectId
            query: Dict[str, Any] = {"_id": defect_id}
            update = {
                "$set": {
                    "status": new_status,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            }
            res = self._collection.find_one_and_update(
                query, update, return_document=True
            )
            if not res:
                try:
                    obj_id = ObjectId(defect_id)
                    res = self._collection.find_one_and_update(
                        {"_id": obj_id}, update, return_document=True
                    )
                except InvalidId:
                    pass

            if res:
                res["id"] = str(res.get("_id", res.get("id", "")))
                res.pop("_id", None)
                return res
        except Exception as exc:
            logger.error("MongoDB update failed: %s", exc)

        # Check memory store fallback
        if defect_id in self._memory_store:
            self._memory_store[defect_id]["status"] = new_status
            self._memory_store[defect_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            return self._memory_store[defect_id].copy()

        return None

    def clear_all(self) -> int:
        """Flushes all stored defect records from MongoDB and in-memory cache."""
        count = len(self._memory_store)
        self._memory_store.clear()
        if self._collection is not None:
            try:
                res = self._collection.delete_many({})
                count = max(count, res.deleted_count)
            except Exception as e:
                logger.error("Failed clearing MongoDB collection: %s", e)
        return count


# Global database manager instance
db_manager = DatabaseManager()


def save_base64_snapshot(b64_data: str, prefix: str = "pothole") -> str:
    """Decodes base64 image data and writes a JPEG file to UPLOAD_FOLDER.

    Returns:
        The relative URL path to access the uploaded image (e.g. '/uploads/pothole_xyz.jpg').
    """
    if not b64_data:
        return ""

    # Strip data URL header if present (e.g. 'data:image/jpeg;base64,')
    if "," in b64_data:
        header, b64_data = b64_data.split(",", 1)

    try:
        raw_bytes = base64.b64decode(b64_data)
        filename = f"{prefix}_{uuid.uuid4().hex[:12]}.jpg"
        target_path = config.UPLOAD_FOLDER / filename
        with open(target_path, "wb") as f:
            f.write(raw_bytes)
        return f"/uploads/{filename}"
    except Exception as exc:
        logger.error("Failed saving snapshot image: %s", exc)
        return ""


# ------------------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------------------


@api_bp.route("/potholes", methods=["POST"])
def report_pothole():
    """POST /api/v1/potholes

    Validates incoming detection payload, clusters within 5m radius, saves snapshot
    to uploads/, and records defect in MongoDB.
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({"error": "Payload must be a JSON object."}), 400

    # 1. Payload validation
    lat = data.get("latitude")
    lon = data.get("longitude")
    severity = data.get("severity")
    confidence = data.get("confidence")

    if lat is None or lon is None:
        return jsonify({"error": "Missing required fields: 'latitude' and 'longitude'."}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        return jsonify({"error": "Coordinates 'latitude' and 'longitude' must be valid numbers."}), 400

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return jsonify({"error": "Coordinates out of bounds (-90<=lat<=90, -180<=lon<=180)."}), 400

    if not severity or str(severity).lower() not in config.ALLOWED_SEVERITIES:
        return (
            jsonify(
                {
                    "error": f"Invalid severity '{severity}'. Allowed: {sorted(list(config.ALLOWED_SEVERITIES))}"
                }
            ),
            400,
        )

    # Normalize severity format to Title Case ("Low", "Medium", "High")
    normalized_severity = str(severity).strip().capitalize()

    try:
        confidence = float(confidence) if confidence is not None else 0.5
        confidence = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        confidence = 0.5

    timestamp = data.get("timestamp") or datetime.now(timezone.utc).isoformat()
    track_id = data.get("track_id")
    raw_image_data = data.get("image", "")
    raw_crop_data = data.get("crop_image", "")

    # 2. Snapshot persistence (saves both full scene and high-res cropped defect)
    image_url = save_base64_snapshot(raw_image_data, prefix="pothole")
    if not image_url and data.get("image_url"):
        image_url = data.get("image_url")
    crop_url = save_base64_snapshot(raw_crop_data, prefix="crop") if raw_crop_data else ""
    if not crop_url and data.get("crop_url"):
        crop_url = data.get("crop_url")

    # 3. Spatial Clustering (Haversine 5m radius deduplication)
    existing_potholes = db_manager.find_all(limit=200)
    nearby_match = find_nearby_cluster(
        latitude=lat,
        longitude=lon,
        candidate_records=existing_potholes,
        radius_meters=config.CLUSTER_RADIUS_METERS,
    )

    if nearby_match is not None:
        closest_pothole, distance_m = nearby_match
        cluster_id = closest_pothole.get("cluster_id") or closest_pothole.get("id")
        logger.info(
            "Detection clustered with existing pothole %s (Distance: %.2fm)",
            cluster_id,
            distance_m,
        )
    else:
        cluster_id = f"cluster_{uuid.uuid4().hex[:8]}"

    # 4. Construct persistence document
    record: Dict[str, Any] = {
        "timestamp": timestamp,
        "track_id": track_id,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "location": {
            "type": "Point",
            "coordinates": [round(lon, 6), round(lat, 6)],
        },
        "severity": normalized_severity,
        "confidence": round(confidence, 4),
        "bbox_ratio": data.get("bbox_ratio"),
        "street": data.get("street"),
        "status": "reported",
        "image_url": image_url,
        "crop_url": crop_url,
        "cluster_id": cluster_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # 5. Insert into Database
    saved_record = db_manager.insert_pothole(record)

    return jsonify(
        {
            "message": "Pothole defect recorded successfully.",
            "data": saved_record,
        }
    ), 201


@api_bp.route("/potholes", methods=["GET"])
def get_potholes():
    """GET /api/v1/potholes

    Query parameters:
        - severity: filter by 'Low', 'Medium', 'High'
        - status: filter by 'reported', 'in-progress', 'repaired'
        - limit: maximum number of records to return (default: 100)
    """
    severity = request.args.get("severity")
    status = request.args.get("status")
    limit_str = request.args.get("limit", "100")

    try:
        limit = int(limit_str)
        limit = max(1, min(limit, 500))
    except ValueError:
        limit = 100

    records = db_manager.find_all(severity=severity, status=status, limit=limit)
    return jsonify(
        {
            "count": len(records),
            "filters": {"severity": severity, "status": status},
            "data": records,
        }
    ), 200


@api_bp.route("/potholes/<defect_id>", methods=["PATCH"])
def update_pothole_status(defect_id: str):
    """PATCH /api/v1/potholes/<id>

    Updates repair status of a specified pothole.
    Allowed statuses: 'reported', 'in-progress', 'repaired'.
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    new_status = data.get("status")

    if not new_status or str(new_status).lower() not in config.ALLOWED_STATUSES:
        return (
            jsonify(
                {
                    "error": (
                        f"Invalid status '{new_status}'. "
                        f"Allowed: {sorted(list(config.ALLOWED_STATUSES))}"
                    )
                }
            ),
            400,
        )

    normalized_status = str(new_status).strip().lower()
    updated_record = db_manager.update_status(defect_id, normalized_status)

    if updated_record is None:
        return (
            jsonify({"error": f"Pothole with ID '{defect_id}' not found."}),
            404,
        )

    logger.info("Updated defect %s status -> %s", defect_id, normalized_status)
    return (
        jsonify(
            {
                "message": "Pothole status updated successfully.",
                "data": updated_record,
            }
        ),
        200,
    )


@api_bp.route("/potholes", methods=["DELETE"])
def flush_potholes():
    """DELETE /api/v1/potholes

    Flushes all recorded defects from the database and removes stored snapshot images.
    """
    count = db_manager.clear_all()

    # Clear uploads folder (preserve .gitkeep)
    deleted_files = 0
    try:
        if config.UPLOAD_FOLDER.exists():
            for file in config.UPLOAD_FOLDER.iterdir():
                if file.is_file() and file.name != ".gitkeep":
                    try:
                        file.unlink()
                        deleted_files += 1
                    except Exception:
                        pass
    except Exception as exc:
        logger.error("Failed cleaning uploads folder: %s", exc)

    logger.info("Flushed %d defect records and %d snapshot images.", count, deleted_files)
    return (
        jsonify(
            {
                "status": "success",
                "message": f"Successfully flushed {count} defect records and {deleted_files} snapshot images.",
                "deleted_records": count,
                "deleted_images": deleted_files,
            }
        ),
        200,
    )


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint indicating API and DB status."""
    return jsonify(
        {
            "status": "healthy",
            "service": "backend_service",
            "db_mode": "in-memory" if db_manager.is_in_memory else "mongodb",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ), 200


# Live GPS telemetry buffer
_latest_live_gps: Optional[Dict[str, Any]] = None
_latest_gps_lock = threading.Lock()


@api_bp.route("/telemetry/gps", methods=["POST"])
def ingest_live_gps():
    """POST /api/v1/telemetry/gps

    Ingests live satellite GPS coordinates broadcast by a mobile phone browser or sensor client.
    """
    global _latest_live_gps
    if not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 400

    data = request.get_json()
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return jsonify({"error": "Missing latitude or longitude."}), 400

    with _latest_gps_lock:
        _latest_live_gps = {
            "latitude": float(lat),
            "longitude": float(lon),
            "accuracy": data.get("accuracy"),
            "timestamp": data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "received_at": time.time(),
        }

    return jsonify({"status": "ok", "data": _latest_live_gps}), 200


@api_bp.route("/telemetry/gps", methods=["GET"])
def get_live_gps():
    """GET /api/v1/telemetry/gps

    Returns the latest live GPS coordinates broadcast from connected mobile devices.
    """
    with _latest_gps_lock:
        if _latest_live_gps and (time.time() - _latest_live_gps.get("received_at", 0) < 60):
            return jsonify({"status": "live", "data": _latest_live_gps}), 200

    return jsonify({"status": "offline", "data": None}), 200


# Live video stream buffer
_live_frame_bytes: Optional[bytes] = None
_live_frame_lock = threading.Lock()
_live_frame_event = threading.Event()


def _get_placeholder_frame() -> bytes:
    """Generates an initial placeholder frame before camera starts transmitting."""
    import cv2
    import numpy as np
    placeholder = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.putText(
        placeholder,
        "CONNECTING TO CAMERA...",
        (40, 150),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 200, 255),
        2,
        cv2.LINE_AA,
    )
    _, buffer = cv2.imencode(".jpg", placeholder, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    return buffer.tobytes()


@api_bp.route("/live_frame", methods=["POST"])
def ingest_live_frame():
    """Ingests latest JPEG frame from edge detector."""
    global _live_frame_bytes
    raw_data = request.data
    if raw_data:
        with _live_frame_lock:
            _live_frame_bytes = raw_data
        _live_frame_event.set()
    return jsonify({"status": "ok"}), 200


@api_bp.route("/live_stream", methods=["GET"])
def stream_live_video():
    """Streams MJPEG feed to browsers and smartphones."""
    def generate():
        placeholder = _get_placeholder_frame()
        while True:
            # Wait up to 150ms for new camera frame
            signaled = _live_frame_event.wait(timeout=0.15)
            _live_frame_event.clear()
            with _live_frame_lock:
                frame = _live_frame_bytes

            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            else:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + placeholder + b"\r\n"
                )
                time.sleep(0.2)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
