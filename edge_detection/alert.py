"""Non-blocking audible and console alerting for High-severity potholes.

When a High-severity road hazard (> 6% of the frame) is detected, this module
dispatches an immediate visual terminal alert and triggers an asynchronous
audible beep. On Windows 11, winsound.Beep is executed inside a detached daemon
worker so that the real-time video stream and YOLO GPU inference pipeline
experience zero frame-rate degradation.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Any, Dict, Optional

from edge_detection.config import config

logger = logging.getLogger("edge_detection.alert")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [Alert] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class AlertManager:
    """Manages audio-visual notifications with cooldown protection and concurrency safety."""

    def __init__(self, cooldown_seconds: Optional[float] = None) -> None:
        self.cooldown_seconds = (
            cooldown_seconds
            if cooldown_seconds is not None
            else config.ALERT_COOLDOWN_SECONDS
        )
        self._last_alert_time: float = 0.0
        self._lock = threading.Lock()
        self._is_windows = sys.platform.startswith("win")

    def _play_beep_sync(self, frequency: int = 1500, duration_ms: int = 350) -> None:
        """Executes the system beep synchronously inside the worker thread."""
        try:
            if self._is_windows:
                import winsound

                # Double alert pulse for high urgency
                winsound.Beep(frequency, duration_ms)
                time.sleep(0.05)
                winsound.Beep(int(frequency * 1.25), int(duration_ms * 0.8))
            else:
                # ASCII bell fallback for non-Windows environments
                sys.stdout.write("\a")
                sys.stdout.flush()
        except Exception as exc:
            logger.debug("Audible alert playback failed: %s", exc)

    def trigger(
        self,
        severity: str,
        confidence: float,
        latitude: float,
        longitude: float,
        bbox_ratio: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Triggers non-blocking alert if severity is High and cooldown elapsed.

        Args:
            severity: Defect tier ('High', 'Medium', 'Low').
            confidence: Model confidence score (0.0 to 1.0).
            latitude: Current latitude.
            longitude: Current longitude.
            bbox_ratio: Bounding box area divided by frame area.
            metadata: Optional additional detection context.

        Returns:
            True if high severity alert was dispatched, False otherwise.
        """
        if severity.lower() != "high":
            return False

        now = time.time()
        with self._lock:
            if now - self._last_alert_time < self.cooldown_seconds:
                # Cooldown active; skip audio to prevent audio buffer saturation
                return False
            self._last_alert_time = now

        # 1. High-visibility console alert banner
        red = "\033[91m"
        bold = "\033[1m"
        yellow = "\033[93m"
        reset = "\033[0m"

        banner = (
            f"\n{red}{bold}===================================================================={reset}\n"
            f"{red}{bold} [!] CRITICAL ROAD HAZARD DETECTED: HIGH SEVERITY POTHOLE [!] {reset}\n"
            f"{red}{bold}===================================================================={reset}\n"
            f"  {yellow}Severity:{reset}      {bold}HIGH{reset} (Frame Area Ratio: {bbox_ratio * 100:.2f}%)\n"
            f"  {yellow}Confidence:{reset}    {confidence * 100:.1f}%\n"
            f"  {yellow}Coordinates:{reset}   Lat: {latitude:.6f}, Lon: {longitude:.6f}\n"
            f"  {yellow}Timestamp:{reset}     {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}\n"
            f"{red}{bold}===================================================================={reset}\n"
        )
        sys.stdout.write(banner)
        sys.stdout.flush()

        # 2. Asynchronous audible beep dispatched to a background daemon thread
        beep_thread = threading.Thread(
            target=self._play_beep_sync,
            name="AudioAlertThread",
            daemon=True,
        )
        beep_thread.start()
        return True


# Global shared alert manager instance
alert_manager = AlertManager()


def trigger_alert(
    severity: str,
    confidence: float,
    latitude: float,
    longitude: float,
    bbox_ratio: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """Convenience helper function invoking the shared alert manager."""
    return alert_manager.trigger(
        severity=severity,
        confidence=confidence,
        latitude=latitude,
        longitude=longitude,
        bbox_ratio=bbox_ratio,
        metadata=metadata,
    )
