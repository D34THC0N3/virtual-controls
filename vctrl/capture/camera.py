from __future__ import annotations

import logging
import threading
import time

import cv2
import numpy as np

from vctrl.config.schemas import CameraConfig

log = logging.getLogger(__name__)

BACKENDS = {"auto": None, "dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}


class Camera:
    """Single-slot camera: a reader thread keeps only the latest frame.

    state: open -> running -> (stalled -> reopening x3) -> lost
    """

    def __init__(self, cfg: CameraConfig) -> None:
        self.cfg = cfg
        self._cap: cv2.VideoCapture | None = None
        self._lock = threading.Lock()
        self._slot: tuple[bool, np.ndarray | None, int] = (False, None, 0)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_frame_mono = 0.0
        self._reopen_attempts = 0
        self.state = "closed"

    def open(self) -> bool:
        backend = BACKENDS[self.cfg.backend]
        self._cap = (
            cv2.VideoCapture(self.cfg.device, backend)
            if backend
            else cv2.VideoCapture(self.cfg.device)
        )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        ok = bool(self._cap.isOpened())
        self.state = "open" if ok else "lost"
        return ok

    def start(self) -> bool:
        if self._thread is not None:
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()
        return True

    def latest(self) -> tuple[bool, np.ndarray | None, int]:
        with self._lock:
            ok, frame, ts = self._slot
            return ok, None if frame is None else frame.copy(), ts

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.state = "closed"

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._cap is None or not self._cap.isOpened():
                if not self._try_reopen():
                    continue
            ok, frame = self._cap.read() if self._cap else (False, None)
            if ok and frame is not None:
                if self.cfg.mirror:
                    frame = cv2.flip(frame, 1)
                ts = time.monotonic_ns() // 1_000_000
                with self._lock:
                    self._slot = (True, frame, ts)
                self._last_frame_mono = time.monotonic()
                self._reopen_attempts = 0
                self.state = "running"
            else:
                self._handle_stall()
            time.sleep(0.001)

    def _handle_stall(self) -> None:
        stalled = time.monotonic() - self._last_frame_mono
        if self._last_frame_mono and stalled < 1.5:
            return
        self._reopen_attempts += 1
        log.warning(
            "camera stalled %.1fs (attempt %d/3)", stalled, self._reopen_attempts
        )
        if self._reopen_attempts > 3:
            self.state = "lost"
            self._stop.set()
            return
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        time.sleep(0.2)

    def _try_reopen(self) -> bool:
        if self._reopen_attempts > 3:
            self.state = "lost"
            self._stop.set()
            return False
        self._reopen_attempts += 1
        log.warning("reopening camera (attempt %d/3)", self._reopen_attempts)
        time.sleep(0.2)
        return self.open()
