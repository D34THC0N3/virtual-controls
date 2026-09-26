"""Live camera smoke test - skipped unless -m live is passed.

Gates the camera thread against real hardware (A3). See plan L647-690.
"""

import time

import pytest

from vctrl.capture.camera import Camera
from vctrl.config.schemas import CameraConfig

pytestmark = pytest.mark.live


def test_live_camera_smoke() -> None:
    cam = Camera(CameraConfig())
    assert cam.open()
    assert cam.start()
    try:
        time.sleep(2.0)
        ok, frame, ts = cam.latest()
        assert ok
        assert frame is not None
        assert frame.shape == (480, 640, 3)
        assert ts > 0.0

        # fps: ts is a monotonic clock; measure over the recorded window
        assert ts > 0.0
        frames_seen = 1
        prev = ts
        t_end = time.time() + 2.0
        while time.time() < t_end:
            ok2, f2, t2 = cam.latest()
            if ok2 and t2 > prev:
                frames_seen += 1
                prev = t2
        assert frames_seen / 2.0 >= 25, f"fps too low: {frames_seen / 2.0}"
    finally:
        cam.stop()
    assert cam.state in {"running", "closed"}
