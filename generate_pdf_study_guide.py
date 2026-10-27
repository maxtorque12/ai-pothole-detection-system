"""Generates an exhaustive, publication-grade PDF study guide for the AI Pothole Detection System.

Utilizes ReportLab to construct a professional, multi-page document complete with
cover page, styled headings, code snippets, mathematical derivations, bug root-cause
analyses, and comprehensive viva Q&A.
"""

from __future__ import annotations

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and draw total page counts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        # Suppress headers and footers on the cover page
        if self._pageNumber > 1:
            # Header
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#0f172a"))
            self.drawString(54, 750, "AI POTHOLE DETECTION & MUNICIPAL GEOSPATIAL SYSTEM")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748b"))
            self.drawRightString(612 - 54, 750, "Viva Defense Technical Manual")

            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(54, 742, 612 - 54, 742)

            # Footer
            self.line(54, 45, 612 - 54, 45)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748b"))
            self.drawString(54, 32, "Confidential - Final Year Engineering Capstone Defense")
            page_text = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(612 - 54, 32, page_text)

        self.restoreState()


def clean_xml(text: str) -> str:
    """Escapes XML entities for safe ReportLab paragraph rendering."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_pdf(filename: str = "AI_Pothole_Detection_Complete_Study_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    c_navy = colors.HexColor("#0f172a")
    c_blue = colors.HexColor("#0284c7")
    c_sky = colors.HexColor("#0ea5e9")
    c_dark = colors.HexColor("#1e293b")
    c_gray = colors.HexColor("#475569")
    c_code_bg = colors.HexColor("#f8fafc")
    c_code_border = colors.HexColor("#e2e8f0")

    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=30,
        textColor=c_navy,
        alignment=0,
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=c_blue,
        alignment=0,
    )

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=20,
        textColor=c_navy,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=c_blue,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=c_dark,
        spaceAfter=6,
    )

    bullet_style = ParagraphStyle(
        "BulletDark",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=3,
    )

    code_style = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#0f172a"),
    )

    callout_style = ParagraphStyle(
        "CalloutText",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0369a1"),
    )

    story = []

    def code_box(code_str: str):
        cleaned = clean_xml(code_str.strip())
        lines = cleaned.split("\n")
        para_content = "<br/>".join([f"&nbsp;&nbsp;{line}" if line.startswith("  ") else line for line in lines])
        p = Paragraph(para_content, code_style)
        t = Table([[p]], colWidths=[504])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), c_code_bg),
                    ("BOX", (0, 0), (-1, -1), 0.75, c_code_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return t

    def callout_box(text: str, bg_color="#f0f9ff", border_color="#bae6fd"):
        p = Paragraph(text, callout_style)
        t = Table([[p]], colWidths=[504])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_color)),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(border_color)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return t

    # ==========================================
    # COVER PAGE
    # ==========================================
    story.append(Spacer(1, 20))
    story.append(
        HRFlowable(
            width="100%",
            thickness=4,
            color=c_blue,
            spaceAfter=20,
            spaceBefore=0,
        )
    )
    story.append(Paragraph("AI-POWERED POTHOLE DETECTION &amp; MUNICIPAL GEOSPATIAL SYSTEM", title_style))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Complete Viva Defense, Architectural Blueprint, Mathematical Formulations &amp; Code Implementation Manual",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 15))

    meta_table_data = [
        [
            Paragraph("<b>Academic Level:</b> Final Year Engineering Capstone", body_style),
            Paragraph("<b>Target GPU:</b> NVIDIA RTX 4060 (3072 Cores)", body_style),
        ],
        [
            Paragraph("<b>Vision Model:</b> YOLOv8 Anchor-Free Single-Stage", body_style),
            Paragraph("<b>Inference Latency:</b> 1.1 ms / frame (60+ FPS)", body_style),
        ],
        [
            Paragraph("<b>Spatial Clustering:</b> 5-Meter Haversine Spherical", body_style),
            Paragraph("<b>Tracking Engine:</b> ByteTrack Kalman State Space", body_style),
        ],
        [
            Paragraph("<b>Backend Architecture:</b> Flask Multi-Threaded WSGI", body_style),
            Paragraph("<b>Database:</b> Dual-Engine MongoDB / In-Memory RAM", body_style),
        ],
        [
            Paragraph("<b>GIS Dashboard:</b> Leaflet.js + OpenStreetMap", body_style),
            Paragraph("<b>Dataset Scale:</b> 4,396 Train / 683 Val (IVCNZ Merged)", body_style),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[250, 254])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 20))

    elevator_pitch = (
        "<b>The 60-Second Viva Elevator Pitch:</b><br/>"
        "&quot;Traditional road maintenance relies on reactionary citizen complaints or hazardous manual surveys. "
        "We built an end-to-end, edge-to-cloud cyber-physical system mounted on standard patrol vehicles. "
        "A fine-tuned YOLOv8 model inspects road video in <b>1.1 ms</b> on an RTX 4060 GPU. Detections are tracked across "
        "frames via <b>ByteTrack</b> and spatially clustered within <b>5 meters via Haversine geometry</b> to prevent duplicate records. "
        "Detections are automatically categorized into severity tiers (Sky-Blue Low, Orange Medium, Red High) and dispatched "
        "to a municipal <b>Leaflet.js GIS dashboard</b> with high-resolution zoomed crops for instantaneous contractor work-order execution.&quot;"
    )
    story.append(callout_box(elevator_pitch, bg_color="#f0fdf4", border_color="#86efac"))
    story.append(PageBreak())

    # ==========================================
    # SECTION 1: ARCHITECTURAL DATA FLOW
    # ==========================================
    story.append(Paragraph("1. End-to-End Architectural Pipeline", h1_style))
    story.append(
        Paragraph(
            "The system operates across three tightly integrated tiers: Edge Perception, Telemetry Deduplication, and Municipal Command.",
            body_style,
        )
    )

    pipeline_steps = [
        ["Tier", "Execution Stage", "Technology", "Operational Logic"],
        ["Edge", "1. Video Capture", "OpenCV DirectShow", "Grabs unbuffered 1080p frames at 30 FPS with zero lag."],
        ["Edge", "2. Neural Inference", "YOLOv8 + CUDA", "Detects non-rigid pothole bounds in 1.1 ms on RTX 4060 GPU."],
        ["Edge", "3. Temporal Tracking", "ByteTrack", "Assigns persistent IDs (e.g. ID #1) across consecutive frames."],
        ["Edge", "4. Severity Triage", "Relative Ratio", "Calculates bbox_ratio = (w*h)/(W*H) (Low <2%, Med 2-6%, High >6%)."],
        ["Edge", "5. Context Crop", "OpenCV Bicubic", "Cuts 25% padded road border; upscales to >=320px for human review."],
        ["Network", "6. Async Dispatch", "ThreadPoolExecutor", "Dispatches non-blocking HTTP POST payload; keeps edge at 60 FPS."],
        ["Backend", "7. Spatial Cluster", "Haversine 5m", "Merges detections within 5m radius into existing cluster."],
        ["Backend", "8. Dual Failover", "MongoDB / RAM", "Saves to MongoDB; auto-falls back to RAM dictionary if offline."],
        ["Frontend", "9. GIS Visualizer", "Leaflet.js + OSM", "Plots color-coded pins, displays zoom modal, updates lifecycle."],
    ]
    p_table = Table(pipeline_steps, colWidths=[55, 95, 110, 244])
    p_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), c_navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8.5),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(p_table)
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 2: THE 9 CORE TECHNOLOGIES & CODE
    # ==========================================
    story.append(Paragraph("2. Comprehensive Technology Deep Dive & Implementations", h1_style))
    story.append(
        Paragraph(
            "Below is the complete breakdown of every technology utilized, including technical justifications and easy-to-understand implementation code snippets.",
            body_style,
        )
    )

    # 1. YOLOv8
    story.append(Paragraph("2.1 YOLOv8 (Edge Object Detection)", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> A state-of-the-art single-stage anchor-free convolutional object detection network developed by Ultralytics.<br/>"
            "<b>Why we chose it:</b> Unlike Faster R-CNN (which takes 100 ms) or SSD/YOLOv5 (which use rigid anchor boxes), YOLOv8 predicts bounding boxes "
            "directly from feature centers without preset aspect ratios, running in just <b>1.1 ms on our RTX 4060 GPU</b>.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    yolo_code = """from ultralytics import YOLO
import cv2

# Load fine-tuned weights on CUDA device 0 (NVIDIA RTX 4060)
model = YOLO("weights/pothole_best.pt")

# Perform inference on an image or video frame
frame = cv2.imread("road_sample.jpg")
results = model.predict(source=frame, device="0", conf=0.25, verbose=False)

for r in results:
    boxes = r.boxes.xyxy.cpu().numpy()  # [x1, y1, x2, y2]
    scores = r.boxes.conf.cpu().numpy() # Confidence (e.g. 0.92)
    for box, score in zip(boxes, scores):
        x1, y1, x2, y2 = map(int, box)
        print(f"Pothole detected at ({x1}, {y1}) to ({x2}, {y2}) with conf {score:.2f}")"""
    story.append(code_box(yolo_code))
    story.append(Spacer(1, 8))

    # 2. ByteTrack
    story.append(Paragraph("2.2 ByteTrack (Multi-Object Video Tracking)", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> An advanced association algorithm using Kalman Filters and Hungarian matching on IoU distances.<br/>"
            "<b>Why we chose it:</b> Eliminates duplicate detections. When a car passes a pothole over 30 consecutive frames, ByteTrack associates "
            "both high and low confidence boxes, maintaining a persistent ID (`ID #1`) so the edge detector reports it <b>exactly once</b>.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    bytetrack_code = """reported_ids = set() # Memory set for deduplication

# Run YOLO with persistent ByteTrack enabled
results = model.track(source=frame, persist=True, tracker="bytetrack.yaml")

for r in results:
    if r.boxes.id is not None:
        track_ids = r.boxes.id.int().cpu().tolist()
        for box, track_id in zip(r.boxes.xyxy.cpu().numpy(), track_ids):
            if track_id not in reported_ids:
                reported_ids.add(track_id)
                print(f"NEW POTHOLE (ID #{track_id}) -> Dispatching alert to backend!")
            else:
                print(f"Tracked Pothole (ID #{track_id}) already reported. Suppressing duplicate.")"""
    story.append(code_box(bytetrack_code))
    story.append(Spacer(1, 8))

    # 3. OpenCV
    story.append(Paragraph("2.3 OpenCV (`cv2`) Image Processing & Padded Crops", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> The industry-standard open-source computer vision library.<br/>"
            "<b>Why we chose it:</b> Grabs unbuffered DirectShow camera frames (`CAP_DSHOW`), calculates 25% road-context padding, upscales "
            "defects via bicubic interpolation (`INTER_CUBIC`), and encodes snapshots into Base64 strings for JSON transmission.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    opencv_code = """import cv2, base64

# Open camera index 1 with DirectShow to eliminate buffer latency
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
ret, frame = cap.read()
H, W, _ = frame.shape

# Extract 25% padded defect crop for engineering inspection
x1, y1, x2, y2 = 100, 150, 300, 350
pw, ph = int(0.25 * (x2 - x1)), int(0.25 * (y2 - y1))
crop = frame[max(0, y1-ph):min(H, y2+ph), max(0, x1-pw):min(W, x2+pw)]

# Bicubic upscale if smaller than 320px
if crop.shape[0] < 320:
    crop = cv2.resize(crop, (320, 320), interpolation=cv2.INTER_CUBIC)

# Encode to Base64 for REST API payload
_, buf = cv2.imencode(".jpg", crop)
b64_str = base64.b64encode(buf).decode("utf-8")"""
    story.append(code_box(opencv_code))
    story.append(Spacer(1, 8))

    # 4. Haversine
    story.append(Paragraph("2.4 Haversine Distance Formula (Spatial Clustering)", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> A spherical trigonometry formula calculating the shortest great-circle distance over the Earth's curved surface.<br/>"
            "<b>Why we chose it:</b> Flat Euclidean distance $(\Delta x^2 + \Delta y^2)$ causes massive errors because degrees of longitude shrink toward the poles. "
            "Haversine gives sub-meter accuracy anywhere on Earth, clustering all detections within <b>5 meters</b> into a single database entry.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    haversine_code = """import math

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000.0  # Earth's mean radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    
    a = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

# 5-Meter Backend Deduplication Logic
dist = haversine_distance(28.61860, 77.30130, 28.61863, 77.30132)
if dist <= 5.0:
    print(f"Distance {dist:.2f}m <= 5m: Clustering into existing pothole record!")
else:
    print(f"Distance {dist:.2f}m > 5m: Creating brand new road defect entry.")"""
    story.append(code_box(haversine_code))
    story.append(Spacer(1, 8))

    # 5. ThreadPoolExecutor
    story.append(Paragraph("2.5 Python Concurrency (`ThreadPoolExecutor`)", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> A high-level thread management interface from Python's standard library `concurrent.futures`.<br/>"
            "<b>Why we chose it:</b> HTTP network requests take 50–200 ms. If executed on the main thread, the camera feed would freeze. "
            "`ThreadPoolExecutor` runs HTTP POST requests on background worker threads, allowing the video loop to process at 60+ FPS.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    thread_code = """from concurrent.futures import ThreadPoolExecutor
import requests

executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="HTTPDispatch")

def send_alert(payload):
    try:
        requests.post("http://127.0.0.1:5000/api/v1/potholes", json=payload, timeout=2.0)
    except Exception as e:
        print(f"Background network error: {e}")

# In main video loop: non-blocking dispatch
payload = {"latitude": 28.6186, "longitude": 77.3013, "severity": "High"}
executor.submit(send_alert, payload)  # Returns immediately; zero video stutter!"""
    story.append(code_box(thread_code))
    story.append(Spacer(1, 8))

    # 6. Flask
    story.append(Paragraph("2.6 Python Flask RESTful Microservice", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> A lightweight, modular Python WSGI web framework implementing an Application Factory and Blueprints.<br/>"
            "<b>Why we chose it:</b> Zero bloat, instant JSON serialization, thread-safe request routing, and native support for multipart MJPEG video streaming.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    flask_code = """from flask import Flask, Blueprint, request, jsonify

app = Flask(__name__)
api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

@api_bp.route("/potholes", methods=["POST"])
def create_pothole():
    data = request.get_json()
    if not data or "latitude" not in data or "longitude" not in data:
        return jsonify({"error": "Missing coordinates"}), 400
    
    # Store defect and return 201 Created
    record = {"id": "pot_01", "lat": data["latitude"], "lon": data["longitude"], "status": "reported"}
    return jsonify({"status": "success", "data": record}), 201

app.register_blueprint(api_bp)"""
    story.append(code_box(flask_code))
    story.append(Spacer(1, 8))

    # 7. MongoDB Failover
    story.append(Paragraph("2.7 MongoDB & In-Memory Failover Architecture", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> Document-oriented NoSQL database with 2dsphere geospatial indexing, wrapped with an automatic in-memory RAM cache.<br/>"
            "<b>Why we chose it:</b> Stores complex GeoJSON coordinates. If MongoDB daemon is not running during a viva presentation, the backend catches "
            "the connection timeout and seamlessly stores records in RAM dictionary cache with <b>zero crashes</b>.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    mongo_code = """from pymongo import MongoClient

class DatabaseManager:
    def __init__(self):
        self.memory_store = {}
        try:
            self.client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
            self.client.admin.command("ping")
            self.collection = self.client["pothole_db"]["defects"]
            self.is_mongo = True
        except Exception:
            print("MongoDB offline! Activating robust in-memory RAM dictionary failover.")
            self.is_mongo = False

    def insert(self, record_id, data):
        if self.is_mongo:
            self.collection.insert_one(data)
        else:
            self.memory_store[record_id] = data  # 100% stable demo fallback!"""
    story.append(code_box(mongo_code))
    story.append(Spacer(1, 8))

    # 8. Leaflet.js
    story.append(Paragraph("2.8 Leaflet.js & OpenStreetMap (GIS Dashboard)", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> An open-source, mobile-friendly JavaScript mapping library loading standard OpenStreetMap slippy tiles.<br/>"
            "<b>Why we chose it:</b> Unlike Google Maps API, Leaflet is under 40 KB, requires zero API keys, zero credit card billing, "
            "and runs completely offline inside private municipal intranets.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    leaflet_code = """// Initialize Leaflet map centered on East Delhi [28.6186, 77.3013]
const map = L.map("map").setView([28.6186, 77.3013], 14);

// Load 100% free OpenStreetMap tile layer
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

// Add color-coded severity marker (Crimson Red for High Severity)
const marker = L.circleMarker([28.6186, 77.3013], {
  radius: 12,
  fillColor: "#ef4444",
  color: "#7f1d1d",
  weight: 2,
  fillOpacity: 0.9
}).addTo(map);
marker.bindPopup("<b>HIGH SEVERITY CRATER</b><br/>Status: Reported");"""
    story.append(code_box(leaflet_code))
    story.append(Spacer(1, 8))

    # 9. HTML5 Geolocation
    story.append(Paragraph("2.9 HTML5 Geolocation API (`navigator.geolocation`)", h2_style))
    story.append(
        Paragraph(
            "<b>What it is:</b> Native W3C browser interface accessing physical device GNSS/GPS hardware chips.<br/>"
            "<b>Why we chose it:</b> Enables mobile phones to broadcast satellite coordinates directly to the edge detector without installing third-party apps.<br/>"
            "<b>Basic Implementation Code:</b>",
            body_style,
        )
    )
    geo_code = """// Watch live device GPS coordinates with high satellite accuracy
navigator.geolocation.watchPosition(
  (pos) => {
    const coords = {
      latitude: pos.coords.latitude,
      longitude: pos.coords.longitude,
      accuracy: pos.coords.accuracy,
      timestamp: new Date().toISOString()
    };
    // Transmit to edge detector via backend telemetry route
    fetch("/api/v1/telemetry/gps", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(coords)
    });
  },
  (err) => console.warn("GPS error:", err.message),
  { enableHighAccuracy: true, maximumAge: 1000 }
);"""
    story.append(code_box(geo_code))
    story.append(PageBreak())

    # ==========================================
    # SECTION 3: MATHEMATICAL FORMULATIONS
    # ==========================================
    story.append(Paragraph("3. Mathematical Formulations & Derivations", h1_style))
    story.append(
        Paragraph(
            "<b>3.1 Relative Bounding Box Ratio:</b><br/>"
            "To achieve resolution-independent severity scoring across 720p, 1080p, and 4K cameras, severity is computed relative to the full image frame area:<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>bbox_ratio = (w_box &times; h_box) / (W_frame &times; H_frame)</b><br/>"
            "&nbsp;&nbsp;&bull; <b>Low Severity:</b> bbox_ratio &lt; 0.02 (Under 2% of frame). Sky-Blue (#0EA5E9).<br/>"
            "&nbsp;&nbsp;&bull; <b>Medium Severity:</b> 0.02 &le; bbox_ratio &le; 0.06 (2% to 6% of frame). Safety Orange (#F97316).<br/>"
            "&nbsp;&nbsp;&bull; <b>High Severity:</b> bbox_ratio &gt; 0.06 (Over 6% of frame). Crimson Red (#EF4444).",
            body_style,
        )
    )
    story.append(Spacer(1, 4))

    story.append(
        Paragraph(
            "<b>3.2 Haversine Spherical Trigonometry:</b><br/>"
            "Given two coordinates on an oblate spheroid (&phi;1, &lambda;1) and (&phi;2, &lambda;2) with mean Earth radius R = 6,371,000 meters:<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>&Delta;&phi; = &phi;2 - &phi;1, &nbsp;&nbsp; &Delta;&lambda; = &lambda;2 - &lambda;1</b><br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>a = sin&sup2;(&Delta;&phi; / 2) + cos(&phi;1) &times; cos(&phi;2) &times; sin&sup2;(&Delta;&lambda; / 2)</b><br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>c = 2 &times; atan2(&radic;a, &radic;(1 - a))</b><br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>d = R &times; c</b><br/>"
            "If distance d &le; 5.0 meters, the detection is merged into the existing cluster.",
            body_style,
        )
    )
    story.append(Spacer(1, 4))

    story.append(
        Paragraph(
            "<b>3.3 Complete IoU Loss (CIoU) Formulation:</b><br/>"
            "Standard IoU only accounts for overlapping area. Complete IoU penalizes center point distance and aspect ratio variance:<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;<b>L_CIoU = 1 - IoU + (&rho;&sup2;(b, b_gt) / c&sup2;) + &alpha;&nu;</b><br/>"
            "Where &rho;(b, b_gt) is the Euclidean distance between predicted and ground truth centroids, c is the diagonal of the smallest enclosing box, and &nu; measures aspect ratio consistency: &nu; = (4/&pi;&sup2;) &times; (arctan(w_gt/h_gt) - arctan(w/h))&sup2;.",
            body_style,
        )
    )
    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 4: ROOT CAUSE ANALYSES (RCAS)
    # ==========================================
    story.append(Paragraph("4. Engineering Challenges & Root Cause Analyses (RCAs)", h1_style))
    story.append(
        Paragraph(
            "During development and live testing, five major engineering roadblocks were diagnosed and permanently rectified:",
            body_style,
        )
    )

    rca_data = [
        ["#", "Failure Mode Observed", "Root Cause Analysis (RCA)", "Engineering Rectification"],
        [
            "1",
            "Duplicate Frame Flooding",
            "A single pothole viewed across 30 consecutive video frames caused 30 duplicate database writes.",
            "Integrated ByteTrack persistent tracking IDs on edge and 5m Haversine spatial clustering on backend.",
        ],
        [
            "2",
            "Missed Wet / Rain Potholes",
            "Water puddles created specular sky reflections, destroying aggregate convolutional edge gradients.",
            "Retrained with 1,243 wet road images from IVCNZ (Chitale et al.) using perspective & HSV jitter.",
        ],
        [
            "3",
            "Low-Severity Marker Blending",
            "Yellow markers blended completely into OpenStreetMap's light highway rendering canvas.",
            "Upgraded low-severity markers to high-contrast Vivid Sky-Blue (#0EA5E9) with a 12px radius.",
        ],
        [
            "4",
            "Unclear Inspection Photos",
            "Full 1080p frame thumbnails were too small for human inspectors to distinguish shadows from cracks.",
            "Extracted 25% road-context padded crops with bicubic upscaling and an interactive 400% zoom viewer.",
        ],
        [
            "5",
            "Mobile GPS 'Secure Origin' Error",
            "Mobile Chrome strictly blocks HTML5 Geolocation API on non-HTTPS local IP addresses.",
            "Added an interactive 'Set Location' map-pinning tool, enabling 1-tap demo simulation anywhere on Earth.",
        ],
        [
            "6",
            "Cloudflare Tunnel Error 1033",
            "An <img> tag loaded /api/v1/live_stream on page load; Cloudflare proxy timed out on infinite MJPEG stream.",
            "Implemented lazy-loading: live video stream connects only when the PiP modal is actively toggled open.",
        ],
    ]
    rca_table = Table(rca_data, colWidths=[20, 110, 160, 214])
    rca_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), c_navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 7.5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(rca_table)
    story.append(PageBreak())

    # ==========================================
    # SECTION 5: TOP 15 VIVA QUESTIONS
    # ==========================================
    story.append(Paragraph("5. Top 15 Viva Defense Questions & Answers", h1_style))
    story.append(
        Paragraph(
            "Below are the most critical technical questions evaluators ask, paired with concise, high-scoring responses:",
            body_style,
        )
    )

    qa_list = [
        (
            "Q1: What is the primary novelty of your system?",
            "Most academic projects stop at offline model accuracy on static images. Our novelty is an operational, real-time cyber-physical pipeline featuring 1.1 ms edge inference, ByteTrack multi-frame deduplication, Haversine 5m spatial clustering, dual zoomed inspection crops, and a municipal work-order state lifecycle dashboard.",
        ),
        (
            "Q2: Why YOLOv8 over Faster R-CNN or SSD?",
            "Faster R-CNN is a two-stage detector that proposes regions first, running at only 10–15 FPS (too slow for a vehicle traveling at 50 km/h). SSD uses rigid anchor boxes that struggle with non-rigid, irregular potholes. YOLOv8 is an anchor-free single-stage detector predicting box bounds directly, running in 1.1 ms on our RTX 4060 GPU.",
        ),
        (
            "Q3: Why use Haversine instead of Euclidean distance?",
            "Euclidean distance assumes a flat 2D plane. Earth is an oblate spheroid where longitudinal distance shrinks as latitude increases. Haversine computes great-circle spherical distance, providing sub-meter accuracy without map projection distortion.",
        ),
        (
            "Q4: How do you prevent counting the same pothole multiple times?",
            "We employ a two-tier deduplication pipeline: 1) At the edge, ByteTrack Kalman filtering tracks persistent IDs across video frames, and an in-memory set ensures each defect is POSTed only once; 2) At the backend, Haversine 5-meter clustering merges subsequent vehicle passes into the same record.",
        ),
        (
            "Q5: How do you differentiate between dark shadows and real potholes?",
            "Shadows have sharp geometric contours with smooth asphalt aggregate texture and zero depth transition. Potholes have jagged, eroded borders with internal gravel spalling and depth shadow transitions. Our training dataset includes negative background samples of shadows, and ByteTrack suppresses single-frame flickers.",
        ),
        (
            "Q6: What happens if MongoDB crashes or is offline?",
            "Our backend includes an automated DatabaseManager failover engine. If MongoDB is unreachable, it catches the ServerSelectionTimeoutError and diverts all writes to an internal thread-safe Python dictionary in RAM. The REST API continues responding with 200 OK and zero downtime.",
        ),
        (
            "Q7: Why did you choose Leaflet.js over Google Maps API?",
            "Google Maps requires proprietary API keys, mandatory credit card billing, incurs per-thousand load charges, and requires constant cloud connectivity. Leaflet.js is open-source (<40 KB), integrates with free OpenStreetMap tiles, and can run completely offline inside a secure municipal intranet.",
        ),
        (
            "Q8: What is your model inference latency?",
            "Average GPU forward pass takes just 1.1 milliseconds on our NVIDIA RTX 4060 Laptop GPU. Total edge loop latency (including preprocessing and ByteTrack) is only 7.5 ms, easily supporting 60+ FPS real-time vehicular throughput.",
        ),
        (
            "Q9: How do municipal contractors interact with your dashboard?",
            "Supervisors filter potholes by severity, inspect high-res zoomed photos, and transition work orders from 'Reported' to 'In Progress' to 'Repaired'. Repaired defects turn emerald green, updating city maintenance metrics in real time. They can also export CSV work-order logs.",
        ),
        (
            "Q10: Why is asynchronous HTTP dispatching necessary?",
            "Network requests take 50–200 ms. If executed synchronously on the main thread, the camera ingestion loop would freeze, dropping frames. We offload dispatching to a ThreadPoolExecutor with 3 workers so video inference runs uninterrupted.",
        ),
        (
            "Q11: How did you handle wet and water-logged road conditions?",
            "Water reflects sky glare, blinding naive models. We augmented our dataset with 1,243 wet and perspective-angled pothole images from the IVCNZ benchmark dataset (Chitale et al.) and trained with severe HSV color jitter and perspective shear.",
        ),
        (
            "Q12: Why is the Live Stream implemented using MJPEG?",
            "H.264 and WebRTC require complex media servers, SDP negotiation, and transcoding overhead. MJPEG streams sequential JPEG frames over a multipart HTTP boundary, supported natively by every browser <img> tag with zero client-side JavaScript.",
        ),
        (
            "Q13: Why is 25% road-context padding added to crops?",
            "Tightly cropped bounding boxes show only black asphalt interior, making it impossible to judge scale or surrounding road conditions. Adding 25% padding reveals lane markings, cracks, and aggregate wear for municipal engineers.",
        ),
        (
            "Q14: What is the purpose of the interactive 'Set Location' tool?",
            "Satellite GPS signals are often blocked or drift by 50–100 meters inside concrete college buildings and seminar halls. The 'Set Location' tool allows evaluators to click any university or city location directly on the map for realistic demonstration.",
        ),
        (
            "Q15: What is the future scope of this project?",
            "Phase 1 (Edge AI Vision) and Phase 2 (Municipal GIS Dashboard) are complete. Phase 3 includes: 1) Stereo-camera 3D depth estimation to measure asphalt repair volume; 2) Vehicle OBD-II accelerometer fusion to correlate visual cracks with vertical suspension shock; 3) Native mobile app for repair crews.",
        ),
    ]

    for q, a in qa_list:
        p_q = Paragraph(f"<b>{clean_xml(q)}</b>", ParagraphStyle("QA_Q", parent=body_style, fontName="Helvetica-Bold", textColor=c_navy, spaceBefore=4, spaceAfter=2))
        p_a = Paragraph(f"<b>Answer:</b> {clean_xml(a)}", ParagraphStyle("QA_A", parent=body_style, textColor=c_dark, spaceAfter=6))
        story.append(p_q)
        story.append(p_a)

    story.append(Spacer(1, 10))

    # ==========================================
    # SECTION 6: LIVE DEMO REHEARSAL PLAYBOOK
    # ==========================================
    story.append(Paragraph("6. Live Viva Defense Demonstration Playbook", h1_style))
    story.append(
        Paragraph(
            "Follow this exact sequential choreography during your evaluation:",
            body_style,
        )
    )

    demo_steps = [
        "<b>Step 1: Start Backend Server:</b> In Terminal 1, execute <code>py -m backend_service.app</code>. Open <code>http://localhost:5000/</code> in Chrome. Point out the green 'LIVE' connection status badge.",
        "<b>Step 2: Load Seed Demo Potholes:</b> Click the <b>Blue Star Button</b> in the sidebar. Five realistic defects across Connaught Place, Barakhamba, and Minto Road populate the map instantly.",
        "<b>Step 3: Show Dynamic Filters:</b> Click 'High (>6%)', 'Medium (2-6%)', and 'Low (<2%)' filter pills to show instant marker filtering.",
        "<b>Step 4: Demonstrate Work-Order Lifecycle:</b> Click any pothole card and change status from 'Reported' to 'In Progress' to 'Repaired'. Point out that the badge turns emerald green and the metric counter updates in real time.",
        "<b>Step 5: Demonstrate 400% Zoom Viewer:</b> Click an image to open the dual-image inspection modal. Use the '+' button and mouse click to zoom in up to 400% on the granular asphalt surface.",
        "<b>Step 6: Reset Board:</b> Click the <b>Red Trash Button</b> to flush records and clear the map.",
        "<b>Step 7: Live AI Camera Detection:</b> In Terminal 2, execute <code>py -m edge_detection.detector --model weights/pothole_best.pt --device 0 --use-webcam --camera-index 1</code>. Hold up a pothole image to your webcam, show the ByteTrack ID, and watch the pin appear on the map in real time!",
    ]
    for step in demo_steps:
        story.append(Paragraph(f"&bull;&nbsp;&nbsp;{step}", bullet_style))

    story.append(Spacer(1, 15))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=c_blue,
            spaceAfter=10,
            spaceBefore=10,
        )
    )
    story.append(
        Paragraph(
            "<font size='8' color='#64748b'>AI Pothole Detection &amp; Municipal Geospatial System &bull; Final Year Engineering Defense &bull; Generated October 2026</font>",
            ParagraphStyle("FooterNote", parent=styles["Normal"], alignment=1),
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] Generated complete PDF study guide: {filename}")


if __name__ == "__main__":
    build_pdf()
