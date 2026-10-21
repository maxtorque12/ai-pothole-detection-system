# AI-Based Real-Time Pothole Detection and Mapping System

An end-to-end, edge-to-cloud municipal road inspection platform built for high-throughput detection of road hazards, automated severity categorization, real-time alerting, Haversine geospatial clustering, and interactive municipal work-order remediation.

---

## Architecture Overview

The system is decoupled into three independent, modular sub-systems designed for parallel development across a 4-person engineering team:

```
ai-pothole-detection-system/
├── edge_detection/        # Module 1: Computer Vision & Edge Telemetry (Person 1 & 2)
│   ├── config.py          # Config loader for phone stream, GPS, and inference parameters
│   ├── stream.py          # Multi-threaded OpenCV frame consumer with buffer clearing & webcam fallback
│   ├── gps_tracker.py     # Background IP Webcam telemetry poller with mock fallback [28.6139, 77.2090]
│   ├── alert.py           # Non-blocking audio (winsound.Beep daemon) & visual console alerts
│   └── detector.py        # Main edge runner: YOLOv8n GPU inference, severity tiering, async HTTP dispatch
│
├── backend_service/       # Module 2: REST API & Geospatial Clustering (Person 3)
│   ├── app.py             # Flask application configured with CORS & static asset serving
│   ├── config.py          # Backend database settings & upload directory management
│   ├── clustering.py      # Haversine great-circle formula for 5m spatial clustering
│   ├── routes.py          # Ingest, query filters (severity, status), and repair status PATCH
│   └── uploads/           # Persisted defect snapshot images (.gitkeep protected)
│
├── web_dashboard/         # Module 3: Municipal Work-Order Dashboard (Person 4)
│   ├── index.html         # Responsive layout with full-screen OSM & collapsible work-order sidebar
│   ├── map.js             # Leaflet.js map with color-coded severity markers & live API/mock fallback
│   ├── filters.js         # Client-side severity & status filters, metrics counters, & status changer
│   └── mock_data.json     # 5 sample pothole entries around Connaught Place for offline verification
│
├── .env.example           # Environment template
├── requirements.txt       # Unified Python dependencies
└── README.md              # Project documentation
```

---

## Defect Severity Classification

Defect severity is calculated automatically on the edge device as the ratio of bounding box area to total frame area:

$$\text{Severity Ratio} = \frac{\text{BBox Width} \times \text{BBox Height}}{\text{Frame Width} \times \text{Frame Height}}$$

- **Low Severity**: $< 2\%$ of frame area (surface cracks and shallow depressions)
- **Medium Severity**: $2\% - 6\%$ of frame area (moderate potholes requiring standard maintenance)
- **High Severity**: $> 6\%$ of frame area (critical road craters triggering immediate non-blocking audio-visual alerts)

---

## Hardware & Environment Setup

- **Operating System**: Windows 11
- **Python**: 3.10+ (tested on Python 3.14)
- **GPU Acceleration**: NVIDIA RTX 4060 Laptop GPU (CUDA device `0` with automatic CPU fallback)
- **Smartphone Telemetry**: Smartphone running the *IP Webcam* app on Android/iOS, streaming video via `/video` and sensor coordinates via `/sensors.json`.

### 1. Installation

```powershell
# Clone the repository
git clone https://github.com/your-org/ai-pothole-detection-system.git
cd ai-pothole-detection-system

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
copy .env.example .env
```

---

## Running the Services

### 1. Backend Service (Port 5000)

```powershell
python -m backend_service.app
```
*Features:*
- Connects to local MongoDB or operates in an in-memory mode if MongoDB is offline.
- Serves REST endpoints at `/api/v1/potholes`.
- Also serves the web dashboard directly at `http://localhost:5000/`.

### 2. Edge Detection Pipeline

#### Option A: Local PC Webcam & Mock GPS (Offline Testing)
```powershell
python -m edge_detection.detector --use-webcam
```

#### Option B: Smartphone IP Webcam & Live Telemetry (Full Setup)
Ensure your phone and PC are on the same Wi-Fi network. Launch the *IP Webcam* app, start streaming, and run:
```powershell
python -m edge_detection.detector --source http://192.168.1.100:8080/video
```

#### CLI Flags:
- `--use-webcam`: Forces local webcam capture.
- `--source <url_or_file>`: Overrides camera stream or video file.
- `--device 0`: Targets NVIDIA RTX 4060 GPU (`0` or `cpu`).
- `--model yolov8n.pt`: Path to custom pothole weights.
- `--conf 0.35`: Confidence detection threshold.
- `--no-display`: Runs headless without rendering OpenCV window.

### 3. Municipal Web Dashboard

You can access the dashboard in either of two ways:
1. **Via Backend Server**: Open `http://localhost:5000/` or `http://localhost:5000/dashboard` in any browser.
2. **Standalone**: Open [web_dashboard/index.html](file:///c:/Users/arush/ai-pothole-detection-system/web_dashboard/index.html) directly in any modern browser. If the backend API is unreachable, it automatically falls back to `mock_data.json`.

---

## API Documentation

### `POST /api/v1/potholes`
Ingests a new pothole detection snapshot and clusters against existing defects within 5 meters.
```json
{
  "timestamp": "2026-10-21T20:53:39.000Z",
  "latitude": 28.613900,
  "longitude": 77.209000,
  "severity": "High",
  "confidence": 0.94,
  "bbox_ratio": 0.0825,
  "image": "data:image/jpeg;base64,..."
}
```

### `GET /api/v1/potholes`
Retrieves defect list with optional query parameters:
- `?severity=High`
- `?status=reported` (`reported`, `in-progress`, `repaired`)
- `?limit=50`

### `PATCH /api/v1/potholes/<id>`
Updates municipal repair workflow state:
```json
{
  "status": "in-progress"
}
```

---

## Team Role Distribution

- **Person 1 (Edge Vision & Inference)**: [`edge_detection/detector.py`](file:///c:/Users/arush/ai-pothole-detection-system/edge_detection/detector.py), model fine-tuning with custom pothole weights.
- **Person 2 (Edge Streaming & Telemetry)**: [`edge_detection/stream.py`](file:///c:/Users/arush/ai-pothole-detection-system/edge_detection/stream.py), [`edge_detection/gps_tracker.py`](file:///c:/Users/arush/ai-pothole-detection-system/edge_detection/gps_tracker.py), [`edge_detection/alert.py`](file:///c:/Users/arush/ai-pothole-detection-system/edge_detection/alert.py).
- **Person 3 (Backend & Spatial Clustering)**: [`backend_service/routes.py`](file:///c:/Users/arush/ai-pothole-detection-system/backend_service/routes.py), [`backend_service/clustering.py`](file:///c:/Users/arush/ai-pothole-detection-system/backend_service/clustering.py), MongoDB scaling.
- **Person 4 (Municipal GIS Dashboard)**: [`web_dashboard/map.js`](file:///c:/Users/arush/ai-pothole-detection-system/web_dashboard/map.js), [`web_dashboard/filters.js`](file:///c:/Users/arush/ai-pothole-detection-system/web_dashboard/filters.js), UI/UX enhancements.
