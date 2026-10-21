"""Background GPS telemetry tracker with automatic mock fallback.

Polls the Android/iOS IP Webcam application's `/sensors.json` telemetry endpoint
on a background thread. If the device is unreachable, times out, or lacks a
GPS fix, it smoothly falls back to mock coordinates [28.6139, 77.2090]
(Connaught Place / Central Delhi) without impeding the detection loop.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

import requests

from edge_detection.config import config

logger = logging.getLogger("edge_detection.gps_tracker")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [GPS] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class GPSTracker:
    """Threaded GPS polling client for IP Webcam telemetry."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        poll_interval: Optional[float] = None,
        mock_coords: Optional[Tuple[float, float]] = None,
    ) -> None:
        self.endpoint_url = endpoint_url or config.PHONE_GPS_URL
        self.poll_interval = poll_interval or config.GPS_POLL_INTERVAL
        self.mock_coords = mock_coords or config.MOCK_COORDINATES

        self._current_latitude: float = self.mock_coords[0]
        self._current_longitude: float = self.mock_coords[1]
        self._is_mock_active: bool = True
        self._last_success_timestamp: float = 0.0

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._session = requests.Session()

    def _parse_gps_payload(self, data: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        """Extracts latitude and longitude from various IP Webcam JSON formats."""
        try:
            # IP Webcam standard format: {"gps": {"data": [[timestamp, [lat, lon, alt, ...]]]}}
            if "gps" in data and isinstance(data["gps"], dict):
                gps_entries = data["gps"].get("data", [])
                if gps_entries and isinstance(gps_entries, list):
                    latest_entry = gps_entries[-1]
                    if len(latest_entry) >= 2 and isinstance(latest_entry[1], list):
                        coords = latest_entry[1]
                        lat, lon = float(coords[0]), float(coords[1])
                        # Basic geographic sanity check
                        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and (lat != 0.0 or lon != 0.0):
                            return lat, lon

            # Flat location format: {"location": {"latitude": ..., "longitude": ...}}
            if "location" in data and isinstance(data["location"], dict):
                loc = data["location"]
                if "latitude" in loc and "longitude" in loc:
                    lat, lon = float(loc["latitude"]), float(loc["longitude"])
                    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                        return lat, lon

            # Direct top-level keys
            if "latitude" in data and "longitude" in data:
                lat, lon = float(data["latitude"]), float(data["longitude"])
                if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                    return lat, lon

        except (ValueError, TypeError, IndexError) as exc:
            logger.debug("Failed parsing GPS JSON: %s", exc)

        return None

    def _poll_once(self) -> None:
        """Executes a single HTTP GET request to the phone's sensors endpoint."""
        try:
            resp = self._session.get(
                self.endpoint_url,
                timeout=config.GPS_REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                coords = self._parse_gps_payload(resp.json())
                if coords:
                    lat, lon = coords
                    with self._lock:
                        self._current_latitude = lat
                        self._current_longitude = lon
                        self._is_mock_active = False
                        self._last_success_timestamp = time.time()
                    return

            # Phone responded but returned no valid GPS fix
            with self._lock:
                self._current_latitude, self._current_longitude = self.mock_coords
                self._is_mock_active = True

        except requests.RequestException:
            # Unreachable or timed out -> fallback to mock coordinates
            with self._lock:
                self._current_latitude, self._current_longitude = self.mock_coords
                self._is_mock_active = True

    def _worker(self) -> None:
        """Background thread executing periodic telemetry polls."""
        logger.info(
            "Starting GPS worker polling '%s' every %.1fs (Mock fallback: %s)",
            self.endpoint_url,
            self.poll_interval,
            self.mock_coords,
        )
        while not self._stop_event.is_set():
            self._poll_once()
            self._stop_event.wait(self.poll_interval)

    def start(self) -> GPSTracker:
        """Starts the background telemetry thread."""
        if self._thread and self._thread.is_alive():
            return self

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker, name="GPSTrackerWorker", daemon=True
        )
        self._thread.start()
        return self

    def get_coordinates(self) -> Tuple[float, float]:
        """Thread-safe getter returning current (latitude, longitude)."""
        with self._lock:
            return self._current_latitude, self._current_longitude

    def is_using_mock(self) -> bool:
        """Returns True if telemetry is currently operating on mock fallback."""
        with self._lock:
            return self._is_mock_active

    def get_telemetry_status(self) -> Dict[str, Any]:
        """Provides a complete status dictionary for debugging or UI overlay."""
        with self._lock:
            return {
                "latitude": self._current_latitude,
                "longitude": self._current_longitude,
                "is_mock": self._is_mock_active,
                "last_success": self._last_success_timestamp,
            }

    def stop(self) -> None:
        """Signals the background polling thread to terminate."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._session.close()
        logger.info("GPS tracker stopped.")

    def __enter__(self) -> GPSTracker:
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
