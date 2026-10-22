"""Edge Detection Pipeline for Real-Time Pothole Identification & Telemetry Dispatch.

Ingests low-latency video via VideoStreamConsumer, tracks live GPS coordinates via
GPSTracker, executes YOLOv8n inference on NVIDIA RTX 4060 GPU (device=0), classifies
defect severity tier by bounding box area ratio, triggers audible/visual alerts
for High-severity hazards, and asynchronously dispatches JSON payloads with base64
snapshots to the backend municipal service.
"""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import requests
import torch
from ultralytics import YOLO

from edge_detection.alert import trigger_alert
from edge_detection.config import config
from edge_detection.gps_tracker import GPSTracker
from edge_detection.stream import VideoStreamConsumer

logger = logging.getLogger("edge_detection.detector")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [Detector] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def classify_severity(bbox_area: float, frame_area: float) -> Tuple[str, float]:
    """Computes defect severity tier based on relative bounding box area.

    Classification Boundaries (Bounding Box Area / Frame Area):
        - Low:    < 2% of frame
        - Medium: 2% – 6% of frame
        - High:   > 6% of frame

    Args:
        bbox_area: Bounding box area in pixels (width * height).
        frame_area: Total frame area in pixels (frame_width * frame_height).

    Returns:
        Tuple of (severity_tier, area_ratio).
    """
    if frame_area <= 0:
        return "Low", 0.0

    ratio = bbox_area / frame_area

    if ratio > config.MEDIUM_SEVERITY_MAX_RATIO:
        return "High", ratio
    elif ratio >= config.LOW_SEVERITY_MAX_RATIO:
        return "Medium", ratio
    else:
        return "Low", ratio


def encode_image_base64(frame: np.ndarray, quality: int = 80) -> str:
    """Encodes an OpenCV BGR image into a base64 JPEG data URL string."""
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode(".jpg", frame, encode_params)
    if not success:
        raise ValueError("Failed to encode frame to JPEG format.")
    b64_str = base64.b64encode(buffer.tobytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"


def enhance_road_contrast(frame_bgr: np.ndarray, clip_limit: float = 2.5) -> np.ndarray:
    """Applies LAB CLAHE to cut through water glare and sharpen subtle defect rim gradients."""
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)


class PotholeDetectorEngine:
    """Orchestrates video ingestion, YOLOv8 GPU inference, alerting, and backend sync."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        use_webcam: bool = False,
        camera_index: int = 0,
        source: Optional[str] = None,
        backend_url: Optional[str] = None,
        display: bool = True,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        water_mode: bool = False,
        gps_url: Optional[str] = None,
        phone_ip: Optional[str] = None,
    ) -> None:
        self.model_path = model_path or config.MODEL_PATH
        self.target_device = device or config.EDGE_DEVICE
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else config.CONFIDENCE_THRESHOLD
        )
        self.use_webcam = use_webcam
        self.camera_index = camera_index
        self.source = source
        self.backend_url = backend_url or config.BACKEND_API_URL
        self.display = display
        self.water_mode = water_mode

        # Resolve compute device (NVIDIA GPU cuda:0 with graceful CPU fallback)
        self.resolved_device = self._resolve_device(self.target_device)

        logger.info(
            "Initializing YOLOv8 model '%s' on device '%s'...",
            self.model_path,
            self.resolved_device,
        )
        self.model = YOLO(self.model_path)

        # Video ingestion & Telemetry trackers
        self.stream_consumer = VideoStreamConsumer(
            source=self.source,
            use_webcam=self.use_webcam,
            webcam_fallback_index=self.camera_index,
        )
        mock_coords = (lat, lon) if (lat is not None and lon is not None) else None
        
        # Configure live phone GPS sensor URL if provided (or auto-infer from source)
        resolved_gps_url = None
        if gps_url:
            resolved_gps_url = gps_url
        elif phone_ip:
            clean_ip = phone_ip.replace("http://", "").replace("https://", "").strip("/")
            resolved_gps_url = f"http://{clean_ip}/sensors.json" if ":8080" in clean_ip else f"http://{clean_ip}:8080/sensors.json"
        elif self.source and "http://" in self.source and ":8080" in self.source:
            base_url = self.source.split(":8080")[0]
            resolved_gps_url = f"{base_url}:8080/sensors.json"

        self.gps_tracker = GPSTracker(
            endpoint_url=resolved_gps_url,
            mock_coords=mock_coords,
        )

        # Thread pool for non-blocking asynchronous POST requests to backend
        self._dispatch_executor = ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="BackendDispatch"
        )
        self._http_session = requests.Session()

        # Persistent multi-object tracking and deduplication set
        self.reported_track_ids: set[int] = set()
        self._last_dispatch_time: float = 0.0
        self._last_stream_time: float = 0.0
        self._total_detections_count: int = 0
        self._total_dispatches_sent: int = 0

    def _stream_frame_async(self, frame_bgr: np.ndarray) -> None:
        """Sends lightweight compressed JPEG frame to backend live stream."""
        try:
            success, buffer = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
            if success:
                live_url = self.backend_url.replace("/potholes", "/live_frame")
                self._http_session.post(
                    live_url,
                    data=buffer.tobytes(),
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=0.5,
                )
        except Exception:
            pass

    def _resolve_device(self, requested_device: str) -> str:
        """Validates requested device and falls back to CPU if CUDA is not available."""
        if requested_device in ("0", "cuda", "cuda:0"):
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                logger.info(
                    "CUDA Hardware acceleration active: %s (Device %s)",
                    device_name,
                    requested_device,
                )
                return requested_device
            else:
                logger.warning(
                    "CUDA device '%s' requested, but torch.cuda.is_available() is False. "
                    "Falling back to CPU execution.",
                    requested_device,
                )
                return "cpu"
        return requested_device

    def _send_payload_async(self, payload: Dict[str, Any]) -> None:
        """Worker function running in ThreadPoolExecutor to POST detection to backend."""
        try:
            resp = self._http_session.post(
                self.backend_url,
                json=payload,
                timeout=config.HTTP_POST_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                self._total_dispatches_sent += 1
                logger.info(
                    "Pothole dispatched successfully -> Server response HTTP %d (Total Sent: %d)",
                    resp.status_code,
                    self._total_dispatches_sent,
                )
            else:
                logger.warning(
                    "Backend rejected payload with HTTP %d: %s",
                    resp.status_code,
                    resp.text[:120],
                )
        except requests.RequestException as exc:
            logger.warning(
                "Backend API unreachable at '%s' (%s). Payload buffered/dropped.",
                self.backend_url,
                exc.__class__.__name__,
            )

    def _annotate_and_evaluate(
        self,
        frame: np.ndarray,
    ) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
        """Runs YOLO inference, measures severity, and draws HUD overlay."""
        frame_h, frame_w = frame.shape[:2]
        frame_area = frame_w * frame_h

        # Apply adaptive CLAHE contrast enhancement when water/glare mode is enabled
        infer_source = enhance_road_contrast(frame) if self.water_mode else frame

        # Execute YOLO multi-object tracking (ByteTrack)
        results = self.model.track(
            source=infer_source,
            persist=True,
            tracker="bytetrack.yaml",
            device=self.resolved_device,
            conf=self.confidence_threshold,
            verbose=False,
        )

        detections: List[Dict[str, Any]] = []
        annotated_frame = frame.copy()

        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            for box in boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                cls_id = int(box.cls[0].cpu().numpy())
                class_name = self.model.names.get(cls_id, f"class_{cls_id}")
                track_id = int(box.id[0].cpu().numpy()) if (hasattr(box, "id") and box.id is not None) else None

                x1, y1, x2, y2 = map(int, xyxy)
                bw = max(0, x2 - x1)
                bh = max(0, y2 - y1)
                bbox_area = float(bw * bh)

                severity, ratio = classify_severity(bbox_area, frame_area)

                detection_info = {
                    "track_id": track_id,
                    "bbox": (x1, y1, x2, y2),
                    "confidence": round(conf, 4),
                    "class_name": class_name,
                    "severity": severity,
                    "bbox_ratio": round(ratio, 4),
                }
                detections.append(detection_info)

                # UI Color assignment (BGR): Red for High, Orange for Medium, Yellow for Low
                if severity == "High":
                    box_color = (0, 0, 255)       # Red (BGR)
                    badge_color = (0, 0, 200)
                elif severity == "Medium":
                    box_color = (0, 140, 255)     # Orange (BGR)
                    badge_color = (0, 120, 230)
                else:
                    box_color = (0, 220, 255)     # Yellow (BGR)
                    badge_color = (0, 180, 220)

                # Draw bounding box
                thickness = 3 if severity == "High" else 2
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), box_color, thickness)

                # Draw label badge with persistent Track ID
                if track_id is not None:
                    label_text = f"ID #{track_id} {severity.upper()} ({ratio*100:.1f}%) | {conf:.2f}"
                else:
                    label_text = f"{severity.upper()} ({ratio*100:.1f}%) | {conf:.2f}"
                (txt_w, txt_h), baseline = cv2.getTextSize(
                    label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2
                )
                label_top = max(0, y1 - txt_h - 10)
                cv2.rectangle(
                    annotated_frame,
                    (x1, label_top),
                    (x1 + txt_w + 10, label_top + txt_h + baseline + 6),
                    badge_color,
                    -1,
                )
                cv2.putText(
                    annotated_frame,
                    label_text,
                    (x1 + 5, label_top + txt_h + 3),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

        return annotated_frame, detections

    def _render_hud(
        self,
        frame: np.ndarray,
        fps: float,
        lat: float,
        lon: float,
        is_mock_gps: bool,
    ) -> None:
        """Overlays real-time system telemetry and operational status on screen."""
        h, w = frame.shape[:2]

        # Top telemetry bar
        bar_height = 42
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, bar_height), (20, 20, 25), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

        # Telemetry string
        gps_tag = "MOCK GPS" if is_mock_gps else "LIVE GPS"
        gps_color = (0, 165, 255) if is_mock_gps else (0, 255, 0)
        source_tag = "WEBCAM" if self.stream_consumer.is_fallback() else "PHONE STREAM"

        mode_str = " | WET-MODE: ON" if self.water_mode else ""
        hud_left = (
            f"FPS: {fps:.1f} | SRC: {source_tag} | DEV: {self.resolved_device.upper()} | "
            f"POTHOLES: {self._total_detections_count}{mode_str}"
        )
        cv2.putText(
            frame,
            hud_left,
            (12, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )

        gps_str = f"[{gps_tag}] {lat:.5f}, {lon:.5f}"
        (txt_w, _), _ = cv2.getTextSize(gps_str, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
        cv2.putText(
            frame,
            gps_str,
            (w - txt_w - 15, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            gps_color,
            1,
            cv2.LINE_AA,
        )

    def run(self) -> None:
        """Starts the capture, inference, alerting, and dispatch loop."""
        logger.info("Starting Edge Detection Engine...")
        self.stream_consumer.start()
        self.gps_tracker.start()

        window_name = "AI Pothole Detection System - Edge Telemetry"
        if self.display:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 1024, 576)

        fps_calc_time = time.time()
        fps_frame_counter = 0
        current_fps = 0.0

        try:
            while True:
                ret, frame = self.stream_consumer.read()
                if not ret or frame is None:
                    # Brief sleep to avoid CPU busy spin if buffer is temporarily starved
                    time.sleep(0.01)
                    continue

                fps_frame_counter += 1
                now = time.time()
                if now - fps_calc_time >= 1.0:
                    current_fps = fps_frame_counter / (now - fps_calc_time)
                    fps_frame_counter = 0
                    fps_calc_time = now

                # 1. Telemetry Coordinates
                lat, lon = self.gps_tracker.get_coordinates()
                is_mock_gps = self.gps_tracker.is_using_mock()

                # 2. YOLO GPU Inference & Severity Tiering
                annotated_frame, detections = self._annotate_and_evaluate(frame)

                # 3. Multi-Pothole Tracking, Deduplication & Alerting
                if detections:
                    h_f, w_f = frame.shape[:2]

                    for det in detections:
                        track_id = det.get("track_id")
                        severity = det["severity"]
                        confidence = det["confidence"]
                        bbox_ratio = det["bbox_ratio"]
                        x1, y1, x2, y2 = det["bbox"]

                        # Deduplication: check if this specific pothole was already recorded
                        if track_id is not None:
                            if track_id in self.reported_track_ids:
                                # Already recorded this tracked pothole! Prevent duplicate database entries.
                                continue
                            self.reported_track_ids.add(track_id)
                            # Keep track ID set bounded to avoid memory growth
                            if len(self.reported_track_ids) > 2000:
                                self.reported_track_ids.pop()
                        else:
                            # Fallback time cooldown if tracking ID temporarily lost
                            if now - self._last_dispatch_time < config.DISPATCH_COOLDOWN_SECONDS:
                                continue
                            self._last_dispatch_time = now

                        self._total_detections_count += 1
                        logger.info(
                            "New Unique Pothole Tracked [ID: %s, Severity: %s, Conf: %.2f]",
                            track_id if track_id is not None else "N/A",
                            severity,
                            confidence,
                        )

                        # Acquire coordinates (advances simulated road position in mock mode)
                        disp_lat, disp_lon = self.gps_tracker.get_coordinates(advance_step=True)

                        # Trigger non-blocking audio-visual alert if High severity
                        if severity == "High":
                            trigger_alert(
                                severity=severity,
                                confidence=confidence,
                                latitude=disp_lat,
                                longitude=disp_lon,
                                bbox_ratio=bbox_ratio,
                            )

                        # Encode full context snapshot with HUD & bounding boxes
                        try:
                            b64_image = encode_image_base64(annotated_frame)
                        except Exception as e:
                            logger.error("Failed encoding snapshot: %s", e)
                            b64_image = ""

                        # Extract high-resolution crop of the specific pothole with context margin
                        try:
                            # 25% contextual road padding around defect
                            pad_x = int(bw * 0.25)
                            pad_y = int(bh * 0.25)
                            cx1 = max(0, x1 - pad_x)
                            cy1 = max(0, y1 - pad_y)
                            cx2 = min(w_f, x2 + pad_x)
                            cy2 = min(h_f, y2 + pad_y)
                            crop_patch = frame[cy1:cy2, cx1:cx2]

                            # Upscale small defects to at least 320px for clear inspection
                            if crop_patch.size > 0:
                                ch, cw = crop_patch.shape[:2]
                                if cw < 320 or ch < 320:
                                    scale = max(320.0 / cw, 320.0 / ch)
                                    nw = int(cw * scale)
                                    nh = int(ch * scale)
                                    crop_patch = cv2.resize(
                                        crop_patch, (nw, nh), interpolation=cv2.INTER_CUBIC
                                    )
                                b64_crop = encode_image_base64(crop_patch)
                            else:
                                b64_crop = ""
                        except Exception:
                            b64_crop = ""

                        payload = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "track_id": track_id,
                            "latitude": disp_lat,
                            "longitude": disp_lon,
                            "severity": severity,
                            "confidence": confidence,
                            "bbox_ratio": bbox_ratio,
                            "image": b64_image,
                            "crop_image": b64_crop,
                        }

                        # Dispatch asynchronously without stalling video pipeline
                        self._dispatch_executor.submit(self._send_payload_async, payload)

                # 4. HUD Telemetry Overlay
                self._render_hud(annotated_frame, current_fps, lat, lon, is_mock_gps)

                # 5. Non-blocking Live Video Stream Dispatch (~12 FPS)
                if now - self._last_stream_time >= 0.08:
                    self._last_stream_time = now
                    self._dispatch_executor.submit(self._stream_frame_async, annotated_frame)

                # 6. Display Window
                if self.display:
                    cv2.imshow(window_name, annotated_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), ord("Q"), 27):  # 'q' or ESC
                        logger.info("Termination key pressed. Exiting...")
                        break
                else:
                    # Gentle sleep to throttle CPU when running headless
                    time.sleep(0.005)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Shutting down...")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Cleans up hardware connections, threads, and UI windows."""
        logger.info("Releasing edge detection resources...")
        self.stream_consumer.stop()
        self.gps_tracker.stop()
        self._dispatch_executor.shutdown(wait=False)
        self._http_session.close()
        if self.display:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
        logger.info("Edge Detection Engine shutdown complete.")


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments for edge detection execution."""
    parser = argparse.ArgumentParser(
        description="Edge Detection Pipeline for AI Pothole Detection System."
    )
    parser.add_argument(
        "--use-webcam",
        action="store_true",
        help="Bypass network phone stream and use local PC webcam directly.",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=config.WEBCAM_INDEX,
        help="Webcam device index (0 for built-in webcam, 1 for external USB webcam).",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Custom video source URL or video file path.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=config.EDGE_DEVICE,
        help="Inference device: '0' for CUDA GPU or 'cpu' (default: 0).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=config.MODEL_PATH,
        help="Path to YOLO weights (default: yolov8n.pt).",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=config.CONFIDENCE_THRESHOLD,
        help="Model confidence threshold (default: 0.35).",
    )
    parser.add_argument(
        "--backend-url",
        type=str,
        default=config.BACKEND_API_URL,
        help="Backend REST API endpoint for defect ingest.",
    )
    parser.add_argument(
        "--lat",
        type=float,
        default=None,
        help="Custom latitude for GPS telemetry (e.g. 28.6327).",
    )
    parser.add_argument(
        "--lon",
        type=float,
        default=None,
        help="Custom longitude for GPS telemetry (e.g. 77.2198).",
    )
    parser.add_argument(
        "--water-mode",
        action="store_true",
        help="Enable adaptive CLAHE contrast enhancement for wet/water-filled roads and specular reflections.",
    )
    parser.add_argument(
        "--phone-ip",
        type=str,
        default=None,
        help="IP address of phone running IP Webcam for GPS sensors (e.g. 192.168.1.15).",
    )
    parser.add_argument(
        "--gps-url",
        type=str,
        default=None,
        help="Custom GPS telemetry endpoint URL (e.g. http://192.168.1.15:8080/sensors.json).",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Run headless without rendering OpenCV GUI window.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for command-line execution."""
    args = parse_args()
    engine = PotholeDetectorEngine(
        model_path=args.model,
        device=args.device,
        confidence_threshold=args.conf,
        use_webcam=args.use_webcam,
        camera_index=args.camera_index,
        source=args.source,
        backend_url=args.backend_url,
        display=not args.no_display,
        lat=args.lat,
        lon=args.lon,
        water_mode=args.water_mode,
        gps_url=args.gps_url,
        phone_ip=args.phone_ip,
    )
    engine.run()


if __name__ == "__main__":
    main()
