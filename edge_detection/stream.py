"""Multi-threaded OpenCV video consumer with buffer clearing and fallback.

Smartphone IP webcam feeds streaming over RTSP or HTTP/MJPEG introduce
severe multi-second latency if OpenCV's internal decoding buffer fills up.
This module implements a worker thread that continuously drains the socket
buffer, discarding stale frames and making only the latest frame available
for inference. Includes automatic fallback to local webcam if the network
stream fails.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple, Union

import cv2
import numpy as np

from edge_detection.config import config

logger = logging.getLogger("edge_detection.stream")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] [%(levelname)s] [Stream] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class VideoStreamConsumer:
    """Threaded OpenCV video capture manager with aggressive buffer clearing.

    Attributes:
        source: Video stream URL (e.g. 'http://192.168.1.100:8080/video') or webcam index (0).
        use_webcam: Explicit flag instructing stream to bypass network and use webcam.
        webcam_fallback_index: Index of local webcam if network stream fails.
    """

    def __init__(
        self,
        source: Optional[Union[str, int]] = None,
        use_webcam: bool = False,
        webcam_fallback_index: int = 0,
    ) -> None:
        self.use_webcam = use_webcam or config.USE_WEBCAM
        self.webcam_fallback_index = webcam_fallback_index or config.WEBCAM_INDEX

        if self.use_webcam:
            self.source: Union[str, int] = self.webcam_fallback_index
        else:
            self.source = source if source is not None else config.PHONE_STREAM_URL

        self.cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._is_running = False
        self._is_fallback_active = self.use_webcam
        self._frames_read = 0
        self._frames_dropped = 0
        self._fps: float = 0.0
        self._last_fps_calc_time = time.time()
        self._fps_counter = 0

    def _open_capture(self, target_source: Union[str, int]) -> Optional[cv2.VideoCapture]:
        """Attempts to open a cv2.VideoCapture instance with optimized buffer flags."""
        logger.info("Connecting to video source: %s", target_source)
        try:
            # On Windows, DirectShow backend (cv2.CAP_DSHOW) offers lower latency for local webcams
            if isinstance(target_source, int):
                cap = cv2.VideoCapture(target_source, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(str(target_source))

            if not cap.isOpened():
                # Try fallback backend if DSHOW failed
                cap = cv2.VideoCapture(target_source)

            if cap.isOpened():
                # Force minimum internal buffer size in OpenCV to prevent lag
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap
        except Exception as exc:
            logger.warning("Error opening video capture %s: %s", target_source, exc)

        return None

    def _initialize_stream(self) -> bool:
        """Connects to the primary stream, or falls back to local webcam on failure."""
        if not self.use_webcam:
            for attempt in range(1, config.MAX_CONNECT_RETRIES + 1):
                logger.info(
                    "Attempt %d/%d: Opening phone stream at %s...",
                    attempt,
                    config.MAX_CONNECT_RETRIES,
                    self.source,
                )
                self.cap = self._open_capture(self.source)
                if self.cap and self.cap.isOpened():
                    ret, test_frame = self.cap.read()
                    if ret and test_frame is not None:
                        logger.info("Successfully established stream with phone camera.")
                        self._is_fallback_active = False
                        return True
                    self.cap.release()
                    self.cap = None

                time.sleep(config.RECONNECT_DELAY_SECONDS)

            logger.warning(
                "Failed to connect to phone stream '%s'. Initiating automated fallback to webcam (index %d).",
                self.source,
                self.webcam_fallback_index,
            )

        # Fallback to local webcam
        self.cap = self._open_capture(self.webcam_fallback_index)
        if self.cap and self.cap.isOpened():
            ret, test_frame = self.cap.read()
            if ret and test_frame is not None:
                logger.info(
                    "Webcam fallback established on camera index %d.",
                    self.webcam_fallback_index,
                )
                self._is_fallback_active = True
                return True

        logger.error("All video sources failed to initialize.")
        return False

    def _worker(self) -> None:
        """Continuous background thread draining frames to keep buffer latency ~0 ms."""
        while not self._stop_event.is_set():
            if self.cap is None or not self.cap.isOpened():
                # Try reconnecting
                time.sleep(1.0)
                if not self._stop_event.is_set():
                    self._initialize_stream()
                continue

            # grab() is much faster than read(); it grabs next frame without decoding
            grabbed = self.cap.grab()
            if not grabbed:
                logger.warning("Stream frame grab failed. Retrying...")
                time.sleep(0.05)
                continue

            # Decode the grabbed frame
            ret, frame = self.cap.retrieve()
            if not ret or frame is None:
                continue

            # Thread-safe swap of the latest frame
            with self._frame_lock:
                if self._latest_frame is not None:
                    self._frames_dropped += 1
                self._latest_frame = frame
                self._frames_read += 1

            # Update FPS tracking
            self._fps_counter += 1
            now = time.time()
            elapsed = now - self._last_fps_calc_time
            if elapsed >= 1.0:
                self._fps = self._fps_counter / elapsed
                self._fps_counter = 0
                self._last_fps_calc_time = now

    def start(self) -> VideoStreamConsumer:
        """Starts the background frame consumer thread."""
        if self._is_running:
            return self

        success = self._initialize_stream()
        if not success:
            logger.warning("Starting consumer without active stream; will continue reconnecting.")

        self._stop_event.clear()
        self._is_running = True
        self._thread = threading.Thread(
            target=self._worker, name="VideoStreamWorker", daemon=True
        )
        self._thread.start()
        return self

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Returns the freshest unread frame from the buffer, skipping stale frames.

        Returns:
            (True, frame_ndarray) if a frame is available, or (False, None) otherwise.
        """
        with self._frame_lock:
            if self._latest_frame is not None:
                frame = self._latest_frame.copy()
                # Clear buffer so same frame isn't reprocessed if consumer is faster than camera
                self._latest_frame = None
                return True, frame
            return False, None

    def read_latest_persist(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Returns the most recent frame without clearing the buffer."""
        with self._frame_lock:
            if self._latest_frame is not None:
                return True, self._latest_frame.copy()
            return False, None

    def get_fps(self) -> float:
        """Returns the measured input stream frames-per-second."""
        return round(self._fps, 1)

    def is_fallback(self) -> bool:
        """Indicates whether the stream is running on the local webcam fallback."""
        return self._is_fallback_active

    def stop(self) -> None:
        """Stops the worker thread and releases video capture hardware."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._is_running = False

        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        logger.info("Video stream consumer shut down cleanly.")

    def __enter__(self) -> VideoStreamConsumer:
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
