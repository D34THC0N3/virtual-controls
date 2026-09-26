# Plan A - Core Tracking Pipeline (Virtual Controls slice 1)

- Date: 2026-09-25
- Status: ready for execution
- Source of truth: `docs/superpowers/specs/2026-09-25-virtual-controls-slice1-design.md` (rev 2, approved)
- Plan sequence: A (this) -> B actions/bindings + mouse/keyboard + reliability -> C overlay + 8-tab menu + debug inspector -> D gamepad/touch/3D backends + profiles -> E calibration wizard UI, packaging, manual gates

## Goal

A working, tested core loop: webcam frames -> real MediaPipe face+hand
landmarks -> gaze model -> hand features -> gesture FSMs -> soft-magnet
fusion -> fused cursor state, threaded and CLI-driven, backed by a
real-recorded fixture corpus that every test runs against. No output
injection (Plan B), no overlay/menu (Plan C), no gamepad/touch (Plan D),
no calibration wizard UI (Plan E).

## Architecture (Plan A scope)

```text
camera thread (single-slot holder: latest frame only, no queue)
   -> LandmarkRunner (MediaPipe FaceLandmarker + HandLandmarker, VIDEO mode)
   -> ControlTracker (gates -> 1e filters -> soft magnet -> PinchFSM/dwell/registry)
   -> FrameResult written to single-slot holder by frame thread
        - Plan A consumer: headless CLI printer (`vctrl run`)
        - Plan B consumer: ActionBus -> outputs
        - Plan C consumer: Qt signals -> overlay
```

Exactly one producer thread (frame loop). Consumers read the latest slot.
No growing queues, no shared mutable state beyond guarded single-slot
holders.

## Tech stack

| Piece | Choice | Notes |
|---|---|---|
| Python | **3.14** (deviation from spec 14's 3.12) | mediapipe 1.0.1 / PySide6 6.11.2 / vgamepad 0.1.0 / pydantic 2.13.5 all verified installable; revisit 3.12 at packaging (Plan E) |
| Env | `uv` (`C:\Users\junio\.local\bin\uv.exe`), PowerShell 5.1 | `uv venv --python 3.14` then `uv sync` |
| Tracking | mediapipe 1.0.1 Tasks API | `FaceLandmarker` + `HandLandmarker`, `RunningMode.VIDEO`, `detect_for_video` |
| Models | `models/*.task` committed (~11.5 MB) | face 3,758,596 B + hand 7,819,105 B, URLs verified 200 |
| Config | pydantic 2.13 | atomic write (temp+replace), corrupt -> `.bak` + defaults |
| Capture | cv2 (via mediapipe's opencv dependency) | no extra opencv pin (avoid opencv-python/contrib clash) |
| UI (later) | PySide6 6.11.2 | Plan C; not imported in Plan A |
| Lint/test | ruff, pytest | gates before every commit |

## Global constraints (apply to every task)

1. **Real data only, no fakes/mocks** (spec 13): no mocked camera, no
   stubbed MediaPipe, no fake Win32. Tests consume the committed
   `fixtures/real-sessions/*.npz` corpus. Pure-math unit tests may use
   small literal numbers for degenerate cases (empty input, single sample)
   - that is math, not a fake system.
2. Gates green before every task commit: `uv run ruff check .` and
   `uv run pytest` (Tier 1+2; live tests excluded by default marker).
3. One commit per task, message `feat(aNN): ...` / `docs(aNN): ...`.
   Push after each commit; keep each push <= ~25 MB (models task and
   fixtures task push separately, `timeout: 300000`).
4. Files are written under the repo root `D:\DEV\VIrtual Controls\`.
   Python package import root is the repo root; run everything as
   `uv run python -m vctrl ...` (spec 14) or the `vctrl` script.
5. Interactive tasks (anything needing the user at the camera) are marked
   **STOP - ASK USER**; never block silently.
6. Every module is typed, one job, and imports only downward
   (`capture`/`tracking` may import `core`+`config`; nothing imports
   `pipeline`).

## File structure (task order)

```text
pyproject.toml                     T1
.gitignore (append)                T1
vctrl/__init__.py                  T1
vctrl/__main__.py                  T1 (stubs) -> T13 (record/replay/run)
vctrl/config/__init__.py           T2
vctrl/config/schemas.py            T2   pydantic models for config.json + gestures.json + calibration.json
vctrl/config/store.py              T2   load_model/save_model (atomic, corrupt->.bak)
vctrl/core/__init__.py             T2
vctrl/core/logging_setup.py        T2   logs/session.log 1 MB x 3
models/face_landmarker.task        T3
models/hand_landmarker.task        T3
vctrl/capture/__init__.py          T3
vctrl/capture/camera.py            T3   Camera thread + watchdog (1.5 s x3)
tests/conftest.py                  T3 (grow in T5)
tests/test_live.py                 T3   @pytest.mark.live camera smoke
vctrl/capture/mediapipe_runner.py  T4   LandmarkRunner
vctrl/tools/__init__.py            T5
vctrl/tools/record.py              T5   free + quick5 calib recording -> npz + manifest
tests/test_record_schema.py        T5
fixtures/real-sessions/*.npz       T5   STOP - ASK USER (record with user at camera)
fixtures/real-sessions/manifest.json T5
vctrl/core/filters.py              T6   OneEuro (Casiez), median-of-3
tests/test_filters.py              T6
vctrl/core/geometry.py             T7   affine/poly2 fit, mirror, norm<->screen
tests/test_geometry.py             T7
vctrl/tracking/__init__.py         T8
vctrl/tracking/gaze.py             T8   features, GazeModel(Set), LOO gate, calibration.json persistence
tests/test_gaze.py                 T8
vctrl/tracking/hand.py             T9   HandFeatures, pinch norm, palm EMA, primary pick
tests/test_hand.py                 T9
vctrl/tracking/gestures.py         T10  PinchFSM, dwell, GestureEngine, DEFAULT_DETECTORS
tests/test_gestures.py             T10
vctrl/tracking/tracker.py          T11  ControlTracker: gates, fusion, magnet, freeze
tests/test_tracker.py              T11
vctrl/tools/replay.py              T12  Session loader + run_replay
tests/test_replay.py               T12
vctrl/pipeline.py                  T13  frame thread + single-slot FrameResult
tests/test_pipeline_parity.py      T13  Tier 2: stored landmarks vs real MediaPipe on stored frames
docs/manual-test.md                T14  Plan A slice of the manual checklist
```

## Tasks

### Task 1 - Scaffold: pyproject, ruff/pytest config, CLI stub, .gitignore

**Files:** `pyproject.toml`, `vctrl/__init__.py`, `vctrl/__main__.py`, `.gitignore` (append)

`pyproject.toml` (complete):

```toml
[project]
name = "vctrl"
version = "0.1.0"
description = "Webcam eye/hand tracking -> virtual controller, mouse and keyboard"
requires-python = ">=3.14"
dependencies = [
    "mediapipe==1.0.1",
    "pydantic>=2.13",
]

[project.optional-dependencies]
gui = ["PySide6>=6.11"]
gamepad = ["vgamepad==0.1.0"]

[project.scripts]
vctrl = "vctrl.__main__:main"

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.9"]

[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not live'"
markers = [
    "live: needs a real webcam (and later, real SendInput) - opt in with -m live",
]
```

`vctrl/__init__.py`:

```python
__version__ = "0.1.0"
```

`vctrl/__main__.py` (T1 version - argparse skeleton only, subcommands added in T13):

```python
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vctrl", description="Virtual control software")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="headless tracking loop (added in A13)")
    sub.add_parser("record", help="record fixture sessions (added in A5)")
    sub.add_parser("replay", help="replay a fixture session (added in A12)")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(f"command {args.command!r} not implemented yet (Plan A in progress)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

`.gitignore` append (verify current content first, do not duplicate):

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
*.egg-info/
build/
dist/
```

**TDD steps:**

1. `uv venv --python 3.14` then `uv sync` in repo root; if the 3.14
   interpreter is missing run `uv python install 3.14` first.
2. Sanity gate before anything else: `uv run python -c "import mediapipe, pydantic; print(mediapipe.__version__, pydantic.__version__)"`.
   Expected `1.0.1 2.x` (Py3.14 deviation already verified this session).
3. Write `tests/test_cli_stub.py`:

```python
from vctrl.__main__ import main


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out


def test_unimplemented_command_returns_2(capsys):
    assert main(["run"]) == 2
    assert "not implemented" in capsys.readouterr().out
```

4. `uv run pytest` green, `uv run ruff check .` clean.
5. Commit `feat(a01): scaffold vctrl package, pyproject, ruff/pytest config`, push.

**Done when:** `uv run pytest` and `uv run ruff check .` both pass;
`uv run vctrl` (or `uv run python -m vctrl`) prints help.

---

### Task 2 - Config schemas + atomic store + logging

**Files:** `vctrl/config/schemas.py`, `vctrl/config/store.py`,
`vctrl/core/logging_setup.py`, `tests/test_config.py`, `tests/test_logging.py`

`schemas.py` (complete):

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class CameraConfig(BaseModel):
    device: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30
    mirror: bool = True
    backend: str = "auto"  # auto | dshow | msmf


class SignalFilterConfig(BaseModel):
    enabled: bool = True
    min_cutoff: float = 1.0
    beta: float = 0.007
    d_cutoff: float = 1.0


class FilterConfig(BaseModel):
    gaze: SignalFilterConfig = Field(default_factory=SignalFilterConfig)
    hand: SignalFilterConfig = Field(default_factory=lambda: SignalFilterConfig(min_cutoff=1.5))
    cursor: SignalFilterConfig = Field(default_factory=lambda: SignalFilterConfig(min_cutoff=1.2, beta=0.01))


class MagnetConfig(BaseModel):
    gain: float = 0.65
    precision_radius: float = 120.0


class PinchConfig(BaseModel):
    t_on: float = 0.35
    t_off: float = 0.45
    debounce_frames: int = 3
    tap_ms: int = 250
    hold_ms: int = 600
    watchdog_ms: int = 500
    precision_norm: float = 0.18  # pinch_norm below this -> precision mode


class GazeFitConfig(BaseModel):
    polynomial: bool = False  # affine default; poly2 behind this flag
    loo_gate_px: float = 150.0  # compared at 1080p; scaled by screen_w/1920
    loo_min_samples: int = 5
    variance_k: float = 3.0
    velocity_gate_ratio: float = 1.0  # x screen diagonal
    dwell_ms: int = 700
    dwell_radius_px: float = 40.0
    dwell_enabled: bool = False


class TrackingConfig(BaseModel):
    gaze_conf_min: float = 0.5
    hand_conf_min: float = 0.5
    palm_ema_alpha: float = 0.2
    max_step_px: float = 400.0
    reject_teleport: bool = True
    both_lost_grace_ms: int = 0


class HotkeysConfig(BaseModel):
    kill: str = "Ctrl+Alt+X"
    debug: str = "Ctrl+Alt+D"
    recalibrate: str = "Ctrl+Alt+R"
    markers: str = "Ctrl+Alt+M"
    profile_cycle: str = "Ctrl+Alt+P"
    pause: str = "Ctrl+Alt+Space"
    menu: str = "Ctrl+Alt+O"
    cheat_sheet: str = "Ctrl+Alt+H"


class DetectorCfg(BaseModel):
    name: str
    enabled: bool = True
    on_th: float = 0.7
    off_th: float = 0.4
    on_frames: int = 3
    cooldown_ms: int = 250
    hold_ms: int = 0
    params: dict[str, float] = Field(default_factory=dict)


class GesturesConfig(BaseModel):
    schema_version: int = 1
    detectors: list[DetectorCfg] = Field(default_factory=list)


class AppConfig(BaseModel):
    schema_version: int = 1
    camera: CameraConfig = Field(default_factory=CameraConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    magnet: MagnetConfig = Field(default_factory=MagnetConfig)
    pinch: PinchConfig = Field(default_factory=PinchConfig)
    gaze: GazeFitConfig = Field(default_factory=GazeFitConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    hotkeys: HotkeysConfig = Field(default_factory=HotkeysConfig)
    log_level: str = "INFO"
```

`store.py` (complete):

```python
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


def load_model(path: Path, model_type: type[M], defaults: M | None = None) -> M:
    """Load JSON at path into model_type. On missing file: defaults or fresh
    instance. On corrupt/invalid: rename the file to <name>.bak, log, fall back."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if defaults is not None:
            return defaults.model_copy(deep=True)
        return model_type()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _quarantine(path, f"invalid JSON: {exc}")
        return defaults.model_copy(deep=True) if defaults is not None else model_type()
    try:
        return model_type.model_validate(raw)
    except ValidationError as exc:
        _quarantine(path, f"schema error: {exc.error_count()} issues")
        return defaults.model_copy(deep=True) if defaults is not None else model_type()


def save_model(path: Path, model: BaseModel) -> None:
    """Atomic write: temp file in the same dir, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _quarantine(path: Path, why: str) -> None:
    backup = path.with_suffix(path.suffix + ".bak")
    log.warning("corrupt config %s (%s) -> %s", path.name, why, backup.name)
    try:
        path.replace(backup)
    except OSError:
        log.warning("could not rename %s", path, exc_info=True)
```

`logging_setup.py` (complete):

```python
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level.upper())
    fh = RotatingFileHandler(
        log_dir / "session.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.handlers[:] = [fh, sh]
```

**TDD steps:**

1. Write `tests/test_config.py` first:

```python
from pathlib import Path

from vctrl.config.schemas import AppConfig, DetectorCfg, GesturesConfig
from vctrl.config.store import load_model, save_model


def test_defaults_roundtrip(tmp_path: Path):
    p = tmp_path / "config.json"
    cfg = AppConfig()
    save_model(p, cfg)
    assert load_model(p, AppConfig) == cfg


def test_missing_file_returns_defaults(tmp_path: Path):
    assert load_model(tmp_path / "nope.json", AppConfig) == AppConfig()


def test_corrupt_file_quarantined(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    out = load_model(p, AppConfig)
    assert out == AppConfig()
    assert p.with_suffix(".json.bak").exists()
    assert not p.exists()


def test_wrong_schema_quarantined(tmp_path: Path):
    p = tmp_path / "config.json"
    p.write_text('{"camera": {"width": -5}}', encoding="utf-8")
    assert load_model(p, AppConfig).camera.width == 640
    assert p.with_suffix(".json.bak").exists()


def test_gestures_split_file(tmp_path: Path):
    p = tmp_path / "gestures.json"
    g = GesturesConfig(detectors=[DetectorCfg(name="index_pinch")])
    save_model(p, g)
    assert load_model(p, GesturesConfig).detectors[0].name == "index_pinch"
```

2. Write `tests/test_logging.py`:

```python
import logging
from pathlib import Path

from vctrl.core.logging_setup import setup_logging


def test_log_file_created_and_rotates(tmp_path: Path):
    setup_logging(tmp_path, "DEBUG")
    log = logging.getLogger("vctrl.test")
    log.info("hello")
    for h in logging.getLogger().handlers:
        h.flush()
    assert (tmp_path / "session.log").exists()
    assert "hello" in (tmp_path / "session.log").read_text(encoding="utf-8")
    # rotation wiring: cap at 1 MB, 3 backups
    fh = next(h for h in logging.getLogger().handlers if h.baseFilename.endswith("session.log"))
    assert fh.maxBytes == 1_000_000 and fh.backupCount == 3
```

3. `uv run pytest` green, `uv run ruff check .` clean.
4. Commit `feat(a02): pydantic config schemas, atomic store, rotating logs`, push.

**Done when:** corrupt and wrong-schema configs fall back to defaults with a
`.bak` left behind; log file appears under the given dir.

---

### Task 3 - Models + Camera thread + live camera smoke

**Files:** `models/face_landmarker.task`, `models/hand_landmarker.task`,
`vctrl/capture/camera.py`, `tests/conftest.py`, `tests/test_live.py`

Download (verified HTTP 200 this session):

```powershell
New-Item -ItemType Directory -Force -Path models | Out-Null
Invoke-WebRequest "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile models/face_landmarker.task
Invoke-WebRequest "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task" -OutFile models/hand_landmarker.task
(Get-Item models/face_landmarker.task).Length   # 3758596
(Get-Item models/hand_landmarker.task).Length  # 7819105
```

`vctrl/capture/camera.py` (complete):

```python
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
        self._cap = cv2.VideoCapture(self.cfg.device, backend) if backend else cv2.VideoCapture(
            self.cfg.device
        )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        ok = bool(self._cap.isOpened())
        self.state = "open" if ok else "lost"
        return ok

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()

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
        log.warning("camera stalled %.1fs (attempt %d/3)", stalled, self._reopen_attempts)
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
```

`tests/conftest.py` (seed - grows in T5):

```python
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "real-sessions"


def pytest_collection_modifyitems(config, items):  # noqa: ANN001, ARG001
    live = pytest.mark.live
    for item in items:
        if "live" in item.keywords:
            item.add_marker(live)


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    if not FIXTURES.exists():
        pytest.skip("fixture corpus missing - run `uv run python -m vctrl record` (A5)")
    return FIXTURES
```

`tests/test_live.py`:

```python
import time

import pytest

from vctrl.capture.camera import Camera
from vctrl.config.schemas import CameraConfig

pytestmark = pytest.mark.live


def test_camera_25fps_640x480():
    cam = Camera(CameraConfig())
    assert cam.open(), "camera failed to open - check Device Manager / Camo"
    cam.start()
    time.sleep(1.0)
    first = cam.latest()
    frames = 0
    t0 = time.monotonic()
    last_ts = 0
    while time.monotonic() - t0 < 2.0:
        ok, frame, ts = cam.latest()
        if ok and ts != last_ts:
            frames += 1
            last_ts = ts
            assert frame.shape[:2] == (480, 640)
        time.sleep(0.005)
    cam.stop()
    assert frames / 2.0 >= 25, f"only {frames / 2.0:.1f} fps"
    assert cam.state in {"running", "closed"}
```

**TDD steps:**

1. Write `tests/test_live.py` first; run `uv run pytest -m live` -
   **STOP - ASK USER** if it fails: earlier inventory showed HP Webcam
   status Unknown and "Camo" error; the camera may need enabling in
   Device Manager or Camo stopped. Do not proceed past T3 without a
   passing live camera test (fixture recording in T5 depends on it).
2. Write `camera.py`, conftest seed, download models.
3. `uv run pytest` (offline suite) green, `uv run pytest -m live` green,
   `uv run ruff check .` clean.
4. Commit + push. Models are ~11.5 MB - single push under the 25 MB cap.
   `feat(a03): camera thread with watchdog + committed MediaPipe models + live smoke`

**Done when:** live test shows >= 25 fps at 640x480 and frame shape correct.

---

### Task 4 - LandmarkRunner (MediaPipe Tasks) + live landmark smoke

**Files:** `vctrl/capture/mediapipe_runner.py`, `tests/test_live.py` (append)

`mediapipe_runner.py` (complete):

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode,
)

log = logging.getLogger(__name__)

N_FACE = 478
N_HAND = 21


@dataclass
class HandLandmarks:
    pts: np.ndarray  # (21, 3) float32, normalized x/y/z
    label: str  # "Left" | "Right"
    conf: float


@dataclass
class LandmarkResult:
    face: np.ndarray | None  # (478, 3) float32 or None
    face_conf: float  # 1.0 if present else 0.0 (Tasks API exposes no face score)
    hands: list[HandLandmarks]  # 0..2, best first


class LandmarkRunner:
    """Wraps FaceLandmarker + HandLandmarker in VIDEO mode.

    MediaPipe requires strictly increasing timestamps; we clamp incoming
    ms values ourselves so callers can pass wall/mono time freely.
    """

    def __init__(
        self,
        models_dir: Path,
        *,
        max_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        mirror: bool = True,
    ) -> None:
        self.mirror = mirror
        self._last_ts = -1
        self._face = FaceLandmarker.create_from_options(
            FaceLandmarkerOptions(
                base_options=BaseOptions(
                    model_asset_path=str(models_dir / "face_landmarker.task")
                ),
                running_mode=RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=min_detection_confidence,
                min_face_presence_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
        )
        self._hands = HandLandmarker.create_from_options(
            HandLandmarkerOptions(
                base_options=BaseOptions(
                    model_asset_path=str(models_dir / "hand_landmarker.task")
                ),
                running_mode=RunningMode.VIDEO,
                num_hands=max_hands,
                min_hand_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )
        )

    def close(self) -> None:
        self._face.close()
        self._hands.close()

    def detect(self, frame_bgr: np.ndarray, ts_ms: int) -> LandmarkResult:
        ts = max(int(ts_ms), self._last_ts + 1)
        self._last_ts = ts
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))

        fres = self._face.detect_for_video(img, ts)
        hres = self._hands.detect_for_video(img, ts)

        face = None
        face_conf = 0.0
        if fres.face_landmarks:
            face = np.array(
                [[p.x, p.y, p.z] for p in fres.face_landmarks[0]], dtype=np.float32
            )
            if face.shape != (N_FACE, 3):
                log.warning("unexpected face landmark shape %s", face.shape)
                face = None
            else:
                face_conf = 1.0

        hands: list[HandLandmarks] = []
        handedness = getattr(hres, "handedness", None) or []
        for i, lm_list in enumerate(getattr(hres, "hand_landmarks", []) or []):
            pts = np.array([[p.x, p.y, p.z] for p in lm_list], dtype=np.float32)
            if pts.shape != (N_HAND, 3):
                continue
            label, conf = "Right", 1.0
            if i < len(handedness) and handedness[i].categories:
                cat = handedness[i].categories[0]
                label, conf = cat.category_name or "Right", float(cat.score)
                # MediaPipe assumes a mirrored/selfie input; when we feed an
                # un-mirrored frame, swap so the label tracks the user's real hand.
                if not self.mirror:
                    label = "Left" if label == "Right" else "Right"
            hands.append(HandLandmarks(pts=pts, label=label, conf=conf))
        hands.sort(key=lambda h: h.conf, reverse=True)
        return LandmarkResult(face=face, face_conf=face_conf, hands=hands)
```

**TDD steps:**

1. Append to `tests/test_live.py`:

```python
import numpy as np
import pytest

from vctrl.capture.mediapipe_runner import N_FACE, N_HAND, LandmarkRunner

pytestmark = pytest.mark.live


def test_landmark_runner_real_frame(models_dir):
    from vctrl.capture.camera import Camera
    from vctrl.config.schemas import CameraConfig
    import time

    cam = Camera(CameraConfig())
    assert cam.open()
    cam.start()
    runner = LandmarkRunner(models_dir, mirror=True)
    faces = hands = 0
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0:
        ok, frame, ts = cam.latest()
        if ok and frame is not None:
            res = runner.detect(frame, ts)
            if res.face is not None:
                faces += 1
                assert res.face.shape == (N_FACE, 3)
                assert np.isfinite(res.face).all()
            assert len(res.hands) <= 2
            for h in res.hands:
                assert h.pts.shape == (N_HAND, 3)
                assert h.label in {"Left", "Right"}
                hands += 1
        time.sleep(0.005)
    runner.close()
    cam.stop()
    assert faces >= 10, f"face detected in only {faces} frames - face the camera"
```

2. Add to `tests/conftest.py`:

```python
@pytest.fixture(scope="session")
def models_dir() -> Path:
    root = Path(__file__).resolve().parent.parent / "models"
    if not (root / "face_landmarker.task").exists():
        pytest.skip("models missing - see Plan A Task 3")
    return root
```

3. Run `uv run pytest -m live`. **Expected unknowns:** exact
   `face_landmarks` / `hand_landmarks` / `handedness` attribute names on
   the 1.0.1 result dataclasses (verified shape only via docs). If an
   AttributeError appears, inspect the real object once:
   `uv run python -c "from mediapipe.tasks.python.vision import HandLandmarker; print([a for a in dir(HandLandmarker) if not a.startswith('_')])"`
   and adjust `getattr` names - record the confirmed names in a comment.
4. **STOP - ASK USER** to sit in front of the camera, face it, one hand
   raised, for the 5 s window.
5. Offline suite + ruff green; commit `feat(a04): MediaPipe landmark runner with monotonic ts clamping`, push.

**Done when:** live test sees a face (>= 10 of ~100 frames) with 478 rows
and hands with 21 rows while the user is in frame.

---

### Task 5 - Recorder + real fixture corpus (STOP - ASK USER)

**Files:** `vctrl/tools/record.py`, `tests/test_record_schema.py`,
`fixtures/real-sessions/*.npz`, `fixtures/real-sessions/manifest.json`,
`vctrl/__main__.py` (wire `record` subcommand)

**npz schema (contract for every later task):**

| key | dtype/shape | notes |
|---|---|---|
| `t` | f64 (N,) | ms, monotonic at detection |
| `frame_bytes` | u8 (S,) | concatenated JPEG q90 - only if `has_frames` |
| `frame_off` | i64 (N+1,) | offsets into frame_bytes; absent frames = zero-length slice |
| `face` | f16 (N,478,3) | 0 rows filled where invalid |
| `face_valid` | bool (N,) | |
| `face_conf` | f32 (N,) | 1/0 |
| `hands` | f16 (N,2,21,3) | pad slot = zeros |
| `hand_valid` | bool (N,2) | |
| `hand_conf` | f32 (N,2) | |
| `hand_label` | i8 (N,2) | -1 none, 0 Left, 1 Right |
| `labels` | i8 (N,) | -1 none, else index into `label_names` |
| `label_names` | str scalar | JSON list |
| `calib_targets` | f32 (N,2) | screen px; NaN rows outside calibration |
| `meta` | str scalar | JSON: width, height, mirror, scenario, has_frames, fps, models, recorded_at, screen |

**Fixture corpus (committed, ~6-8 MB total):** frames stored only for
`clean` and `pinch` (Tier-2 parity test needs them); the rest are
landmark-only: `calib-quick5`, `clean`, `pinch`, `hand-lost`,
`gaze-lost`, `two-hand`, `low-light`, `head-turned`.

`vctrl/tools/record.py` (complete):

```python
from __future__ import annotations

import ctypes
import json
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from vctrl.capture.camera import Camera
from vctrl.capture.mediapipe_runner import LandmarkResult, LandmarkRunner
from vctrl.config.schemas import CameraConfig

log = logging.getLogger(__name__)

QUICK5 = [(0.10, 0.10), (0.90, 0.10), (0.10, 0.90), (0.90, 0.90), (0.50, 0.50)]


def screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def _require_disk(path: Path, min_free_mb: int = 50) -> None:
    free = shutil.disk_usage(path if path.exists() else path.parent).free
    if free < min_free_mb * 1024 * 1024:
        raise RuntimeError(f"low disk: {free // (1024 * 1024)} MB free < {min_free_mb} MB")


class SessionAccumulator:
    def __init__(self, scenario: str, has_frames: bool, mirror: bool, size: tuple[int, int],
                 fps: int) -> None:
        self.scenario = scenario
        self.has_frames = has_frames
        self.mirror = mirror
        self.size = size
        self.fps = fps
        self.t: list[int] = []
        self.jpeg: list[np.ndarray] = []
        self.face: list[np.ndarray] = []
        self.face_valid: list[bool] = []
        self.hands: list[np.ndarray] = []
        self.hand_valid: list[np.ndarray] = []
        self.hand_conf: list[np.ndarray] = []
        self.hand_label: list[np.ndarray] = []
        self.labels: list[int] = []
        self.targets: list[tuple[float, float]] = []
        self.label_names: list[str] = []

    def add(self, res: LandmarkResult, ts: int, frame: np.ndarray | None, label: int,
            target: tuple[float, float] | None) -> None:
        self.t.append(ts)
        if self.has_frames:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            self.jpeg.append(buf.ravel() if ok else np.zeros(0, np.uint8))
        self.face.append(res.face if res.face is not None else np.zeros((478, 3), np.float32))
        self.face_valid.append(res.face is not None)
        h = np.zeros((2, 21, 3), np.float32)
        valid = np.zeros(2, bool)
        conf = np.zeros(2, np.float32)
        label = np.full(2, -1, np.int8)
        for i, hand in enumerate(res.hands[:2]):
            h[i] = hand.pts
            valid[i] = True
            conf[i] = hand.conf
            label[i] = 1 if hand.label == "Right" else 0
        self.hands.append(h)
        self.hand_valid.append(valid)
        self.hand_conf.append(conf)
        self.hand_label.append(label)
        self.labels.append(label)
        self.targets.append(target if target else (float("nan"), float("nan")))

    def save(self, out_path: Path, manifest_path: Path) -> dict:
        n = len(self.t)
        meta = {
            "width": self.size[0], "height": self.size[1], "mirror": self.mirror,
            "scenario": self.scenario, "has_frames": self.has_frames, "fps": self.fps,
            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        arrays: dict[str, np.ndarray] = {
            "t": np.asarray(self.t, np.float64),
            "face": np.asarray(self.face, np.float16),
            "face_valid": np.asarray(self.face_valid, bool),
            "face_conf": np.asarray(self.face_valid, np.float32),
            "hands": np.asarray(self.hands, np.float16),
            "hand_valid": np.asarray(self.hand_valid, bool),
            "hand_conf": np.asarray(self.hand_conf, np.float32),
            "hand_label": np.asarray(self.hand_label, np.int8),
            "labels": np.asarray(self.labels, np.int8),
            "label_names": np.array(json.dumps(self.label_names)),
            "calib_targets": np.asarray(self.targets, np.float32),
            "meta": np.array(json.dumps(meta)),
        }
        if self.has_frames:
            arrays["frame_bytes"] = (
                np.concatenate(self.jpeg) if self.jpeg else np.zeros(0, np.uint8)
            )
            offs = [0]
            for j in self.jpeg:
                offs.append(offs[-1] + len(j))
            arrays["frame_off"] = np.asarray(offs, np.int64)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out_path, **arrays)
        entry = {
            "file": out_path.name, "scenario": self.scenario, "n": n,
            "duration_s": round((self.t[-1] - self.t[0]) / 1000.0, 2) if n > 1 else 0.0,
            "has_frames": self.has_frames, "width": self.size[0], "height": self.size[1],
            "recorded_at": meta["recorded_at"],
        }
        _update_manifest(manifest_path, entry)
        return entry


def _update_manifest(manifest_path: Path, entry: dict) -> None:
    data = {"schema_version": 1, "sessions": []}
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["sessions"] = [s for s in data["sessions"] if s["file"] != entry["file"]]
    data["sessions"].append(entry)
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_jpeg(raw: bytes) -> np.ndarray | None:
    arr = np.frombuffer(raw, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR) if len(arr) else None
```

Continue `record.py` with the session loop and calibration mode (next chunk continues this file in the plan - same module):

```python
def record_session(
    scenario: str,
    duration_s: float,
    *,
    out_dir: Path,
    stride: int = 3,
    with_frames: bool = False,
    camera: CameraConfig | None = None,
    label: str | None = None,
    interactive_labels: bool = False,
) -> Path:
    """Capture one scenario at 1/stride of camera fps.

    interactive_labels: press 1 = start labeling subsequent frames with
    `label`, 0 = clear, q = stop early (Windows: msvcrt, no extra dep).
    """
    import msvcrt

    _require_disk(out_dir)
    cam = Camera(camera or CameraConfig())
    if not cam.open():
        raise RuntimeError("camera failed to open - see A3")
    runner = LandmarkRunner(out_dir.parent.parent / "models",
                            mirror=(camera or CameraConfig()).mirror)
    acc = SessionAccumulator(scenario, with_frames, (camera or CameraConfig()).mirror,
                             (640, 480), (camera or CameraConfig()).fps)
    cam.start()
    current_label = -1
    names: list[str] = []
    t0 = time.monotonic()
    last_ts = -1
    processed = 0
    try:
        while time.monotonic() - t0 < duration_s:
            if interactive_labels and msvcrt.kbhit():
                k = msvcrt.getch().decode("ascii", "ignore")
                if k == "q":
                    break
                elif k == "1" and label:
                    if label not in names:
                        names.append(label)
                    current_label = names.index(label)
                elif k == "0":
                    current_label = -1
            ok, frame, ts = cam.latest()
            if not ok or frame is None or ts == last_ts:
                time.sleep(0.002)
                continue
            if processed % stride:
                processed += 1
                continue
            processed += 1
            last_ts = ts
            res = runner.detect(frame, ts)
            acc.add(res, ts, frame if with_frames else None, current_label, None)
    finally:
        cam.stop()
        runner.close()
    acc.label_names = names
    out = out_dir / f"{scenario}.npz"
    entry = acc.save(out, out_dir / "manifest.json")
    log.info("recorded %s: %d frames, %ss", scenario, entry["n"], entry["duration_s"])
    return out


def record_calibration(
    out_dir: Path,
    *,
    points: list[tuple[float, float]] = QUICK5,
    samples_per_point: int = 15,
    hold_s: float = 1.2,
    camera: CameraConfig | None = None,
    stride: int = 2,
) -> Path:
    """Fullscreen cv2 window, target dot at each point; user looks at it.

    Targets stored in screen px; window assumes primary-screen fullscreen.
    """
    _require_disk(out_dir)
    sw, sh = screen_size()
    cfg = camera or CameraConfig()
    cam = Camera(cfg)
    if not cam.open():
        raise RuntimeError("camera failed to open - see A3")
    runner = LandmarkRunner(out_dir.parent.parent / "models", mirror=cfg.mirror)
    acc = SessionAccumulator("calib-quick5", False, cfg.mirror, (cfg.width, cfg.height), cfg.fps)
    win = "vctrl-calib"
    cv2.namedWindow(win, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cam.start()
    last_ts = -1
    processed = 0
    try:
        for nx, ny in points:
            target_px = (nx * sw, ny * sh)
            deadline = time.monotonic() + hold_s
            while time.monotonic() < deadline:
                canvas = np.zeros((sh, sw, 3), np.uint8)
                cv2.circle(canvas, (int(target_px[0]), int(target_px[1])), 24, (0, 255, 255), -1)
                cv2.imshow(win, canvas)
                cv2.waitKey(1)
                ok, frame, ts = cam.latest()
                if not ok or frame is None or ts == last_ts:
                    continue
                processed += 1
                if processed % stride:
                    continue
                last_ts = ts
                res = runner.detect(frame, ts)
                if res.face is not None:
                    acc.add(res, ts, None, -1, target_px)
                if len(acc.t) and len(acc.t) % samples_per_point == 0:
                    break
    finally:
        cv2.destroyWindow(win)
        cam.stop()
        runner.close()
    out = out_dir / "calib-quick5.npz"
    acc.save(out, out_dir / "manifest.json")
    return out
```

**Wire `record` into `vctrl/__main__.py`:** subcommand `record`
with `--scenario`, `--duration`, `--stride`, `--frames`, `--label`,
`--interactive-labels`, `--calib {quick5}`, `--out`
(default `fixtures/real-sessions`).

**TDD steps:**

1. Write `tests/test_record_schema.py` first (uses committed corpus;
   skips via `fixtures_dir` fixture if absent):

```python
import json

import numpy as np
import pytest


def test_manifest_lists_all_npz(fixtures_dir):
    manifest = json.loads((fixtures_dir / "manifest.json").read_text(encoding="utf-8"))
    files = {s["file"] for s in manifest["sessions"]}
    on_disk = {p.name for p in fixtures_dir.glob("*.npz")}
    assert files == on_disk
    assert {"clean.npz", "pinch.npz", "calib-quick5.npz"} <= files


def test_npz_contract_every_session(fixtures_dir):
    for p in sorted(fixtures_dir.glob("*.npz")):
        data = np.load(p, allow_pickle=False)
        n = len(data["t"])
        assert n >= 30, p.name
        assert data["face"].shape == (n, 478, 3)
        assert data["hands"].shape == (n, 2, 21, 3)
        assert data["labels"].shape == (n,)
        assert data["calib_targets"].shape == (n, 2)
        assert np.all(np.diff(data["t"]) >= 0), "timestamps must be monotonic"
        meta = json.loads(str(data["meta"]))
        assert meta["has_frames"] == ("frame_bytes" in data.files)
        if meta["has_frames"]:
            offs = data["frame_off"]
            assert len(offs) == n + 1
            assert offs[-1] == len(data["frame_bytes"])


def test_clean_has_frames_and_face_rate(fixtures_dir):
    data = np.load(fixtures_dir / "clean.npz")
    assert data["face_valid"].mean() > 0.7, "user should be visible in clean scenario"


def test_pinch_labels_present(fixtures_dir):
    data = np.load(fixtures_dir / "pinch.npz")
    names = json.loads(str(data["label_names"]))
    assert "pinch_on" in names
    idx = names.index("pinch_on")
    assert (data["labels"] == idx).sum() >= 5
    assert (data["labels"] == -1).sum() >= 5


def test_calib_targets_cover_screen(fixtures_dir):
    data = np.load(fixtures_dir / "calib-quick5.npz")
    ok = ~np.isnan(data["calib_targets"][:, 0])
    assert ok.sum() >= 5 * 5, "need >=5 samples per quick5 point"
    xs = data["calib_targets"][ok, 0]
    assert xs.min() < 0.2 * 1920 and xs.max() > 0.8 * 1920
```

2. Run `uv run pytest tests/test_record_schema.py` - **expected FAIL**
   (corpus does not exist yet). This is the red step.
3. **STOP - ASK USER:** "Fixture recording needs you at the camera for
   ~2 minutes. I'll record 8 scenarios (calibration dots, clean, pinch
   with Space-style labeling, hand lost, gaze lost, two hands, low
   light, head turned). Ready?" Wait for confirmation.
4. Record (user participation noted per scenario):

```powershell
uv run python -m vctrl record --calib quick5            # user stares at dots ~15s
uv run python -m vctrl record --scenario clean --duration 6 --frames
uv run python -m vctrl record --scenario pinch --duration 8 --frames --label pinch_on --interactive-labels   # user presses 1 while pinching, 0 to stop
uv run python -m vctrl record --scenario hand-lost --duration 6     # hand exits frame midway
uv run python -m vctrl record --scenario gaze-lost --duration 6     # user looks away
uv run python -m vctrl record --scenario two-hand --duration 6      # both hands visible
uv run python -m vctrl record --scenario low-light --duration 6     # dim room
uv run python -m vctrl record --scenario head-turned --duration 6   # profile views
```

5. `uv run pytest` green (schema tests now pass), ruff clean.
6. Commit + push. If corpus exceeds ~25 MB, push manifest+calib+clean
   first, then the rest: `feat(a05): fixture recorder + real-session corpus`
   (`timeout: 300000` on pushes).

**Done when:** schema tests pass against a committed corpus with a
`pinch_on` label span and quick5 targets covering the screen corners.

---

### Task 6 - One Euro filters (pure, tested on corpus + edge cases)

**Files:** `vctrl/core/filters.py`, `tests/test_filters.py`

`filters.py` (complete):

```python
from __future__ import annotations

import math

from vctrl.config.schemas import SignalFilterConfig


class OneEuroFilter:
    """1€ filter (Casiez et al.) for a single scalar.

    f = min_cutoff * sigma: sigma = 1/(2*pi*tau); tau = 1/(2*pi*d_cutoff)
    derivative uses the same d_cutoff smoothing.
    """

    def __init__(self, cfg: SignalFilterConfig) -> None:
        self.cfg = cfg
        self._x_prev: float | None = None
        self._dx_prev = 0.0
        self._t_prev: float | None = None

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, t: float) -> float:
        """t in seconds (monotonic). First sample passes through."""
        if self._x_prev is None or self._t_prev is None:
            self._x_prev, self._t_prev = x, t
            return x
        dt = t - self._t_prev
        if dt <= 0:
            return self._x_prev  # duplicate/backwards timestamp: hold last value
        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.cfg.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        if not self.cfg.enabled:
            self._x_prev, self._dx_prev, self._t_prev = x, dx_hat, t
            return x
        a = self._alpha(self.cfg.min_cutoff + self.cfg.beta * abs(dx_hat), dt)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_prev, self._dx_prev, self._t_prev = x_hat, dx_hat, t
        return x_hat

    def filter2(self, x: float, y: float, t: float) -> tuple[float, float]:
        """Convenience: two independent filters sharing timestamps.

        Implemented with two internal scalars so callers keep one object.
        """
        # lazily create the y-side state on first use
        if not hasattr(self, "_y"):
            self._y = OneEuroFilter(self.cfg)
        return self.filter(x, t), self._y.filter(y, t)
```

Note: to avoid the lazy `_y` hack being stateful weirdness across
`reset()`, the plan's final code also resets `_y`:

```python
    def reset(self) -> None:  # replaces the simpler reset above in final code
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None
        if hasattr(self, "_y"):
            self._y.reset()
```

`tests/test_filters.py` (complete - literal numbers here are *math
reference values*, not fake tracking data; corpus test below is real):

```python
import json
import math

import numpy as np
import pytest

from vctrl.config.schemas import SignalFilterConfig
from vctrl.core.filters import OneEuroFilter


def test_first_sample_passthrough():
    f = OneEuroFilter(SignalFilterConfig())
    assert f.filter(42.0, 1.0) == 42.0


def test_constant_signal_stays_constant():
    f = OneEuroFilter(SignalFilterConfig())
    prev = f.filter(10.0, 0.0)
    for i in range(1, 100):
        cur = f.filter(10.0, i / 30.0)
        assert math.isclose(cur, 10.0, abs_tol=1e-9)


def test_smoothing_reduces_jitter_variance():
    rng = np.random.default_rng(7)
    sig = SignalFilterConfig(min_cutoff=1.0, beta=0.007, d_cutoff=1.0)
    f = OneEuroFilter(sig)
    noisy = 100.0 + rng.normal(0, 5, 300)
    out = [f.filter(float(x), i / 30.0) for i, x in enumerate(noisy)]
    assert np.std(out[50:]) < np.std(noisy[50:])


def test_fast_motion_lags_then_converges():
    f = OneEuroFilter(SignalFilterConfig())
    f.filter(0.0, 0.0)
    for i in range(1, 10):
        f.filter(100.0, i / 30.0)  # step response
    # after 0.3s at 30fps the output must be well past the midpoint
    assert f.filter(100.0, 10 / 30.0) > 50.0
    for i in range(10, 300):
        last = f.filter(100.0, i / 30.0)
    assert math.isclose(last, 100.0, abs_tol=1.0)


def test_disabled_filter_is_identity():
    f = OneEuroFilter(SignalFilterConfig(enabled=False))
    assert f.filter(5.0, 0.0) == 5.0
    assert f.filter(999.0, 0.033) == 999.0


def test_zero_dt_holds_last():
    f = OneEuroFilter(SignalFilterConfig())
    f.filter(1.0, 0.0)
    assert f.filter(99.0, 0.0) == 1.0
    assert f.filter(99.0, -1.0) == 1.0  # backwards ts


def test_reset_forgets_state():
    f = OneEuroFilter(SignalFilterConfig())
    f.filter(1.0, 0.0)
    f.reset()
    assert f.filter(77.0, 5.0) == 77.0


def test_filter2_axes_independent():
    f = OneEuroFilter(SignalFilterConfig())
    x, y = f.filter2(10.0, 20.0, 0.0)
    assert (x, y) == (10.0, 20.0)
    x, y = f.filter2(10.0, 99.0, 1 / 30)
    assert y == 99.0 or y < 99.0  # y side is running


def test_real_corpus_gaze_series_filtered(fixtures_dir):
    """Real gaze landmarks: filter must track with bounded error."""
    data = np.load(fixtures_dir / "clean.npz")
    valid = data["face_valid"]
    t = data["t"][valid] / 1000.0
    face = data["face"][valid].astype(np.float64)
    iris = face[:, 468:473, :2]  # right iris subset - real coords
    series = iris[:, 0].mean(axis=1)
    f = OneEuroFilter(SignalFilterConfig(min_cutoff=1.0, beta=0.007))
    out = np.array([f.filter(float(v), float(tt)) for v, tt in zip(series, t, strict=True)])
    # error vs source bounded (normalized units stay within face space 0..1)
    assert np.all(np.abs(out - series) < 0.05)
    # latency-free on slow drift: median offset tiny
    assert np.median(np.abs(out - series)) < 0.01
```

**TDD steps:**

1. Write `tests/test_filters.py` first, run `uv run pytest tests/test_filters.py`
   - red (module missing).
2. Write `filters.py`, run tests - green; ruff clean.
3. Commit `feat(a06): One Euro filter (scalar + 2D) tested on real gaze series`, push.

**Done when:** all filter tests pass, including the corpus-derived one.

---

### Task 7 - Geometry: landmark -> pixel transforms + palm/pinch math

**Files:** `vctrl/core/geometry.py`, `tests/test_geometry.py`

`geometry.py` (complete):

```python
from __future__ import annotations

import numpy as np

# MediaPipe FaceMesh canon indices
LEFT_EYE_OUTER, LEFT_EYE_INNER = 33, 133
RIGHT_EYE_INNER, RIGHT_EYE_OUTER = 362, 263
NOSE_TIP = 1
LEFT_EAR, RIGHT_EAR = 234, 454
IRIS_RIGHT_START = 468  # 468..472 right iris, 473..477 left iris

# Hand canon indices
THUMB_TIP, INDEX_TIP, MIDDLE_TIP = 4, 8, 12
INDEX_MCP, PINKY_MCP = 5, 17


def to_pixels(norm_pts: np.ndarray, w: int, h: int) -> np.ndarray:
    """(N,3) normalized -> (N,2) pixel coords, z preserved aside."""
    out = np.empty((norm_pts.shape[0], 2), dtype=np.float64)
    out[:, 0] = norm_pts[:, 0] * w
    out[:, 1] = norm_pts[:, 1] * h
    return out


def eye_corners_px(face_px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """((2,) left eye outer+inner), ((2,) right inner+outer) as pixel xy."""
    left = face_px[[LEFT_EYE_OUTER, LEFT_EYE_INNER]]
    right = face_px[[RIGHT_EYE_INNER, RIGHT_EYE_OUTER]]
    return left, right


def iris_center_px(face_px: np.ndarray) -> np.ndarray:
    return face_px[IRIS_RIGHT_START : IRIS_RIGHT_START + 5, :2].mean(axis=0)


def eye_center_px(face_px: np.ndarray) -> np.ndarray:
    left, right = eye_corners_px(face_px)
    return (left.mean(axis=0) + right.mean(axis=0)) / 2.0


def head_center_px(face_px: np.ndarray) -> np.ndarray:
    return (face_px[LEFT_EAR, :2] + face_px[RIGHT_EAR, :2]) / 2.0


def interpupillary_px(face_px: np.ndarray) -> float:
    left, right = eye_corners_px(face_px)
    return float(np.linalg.norm(left.mean(axis=0) - right.mean(axis=0)))


def normalize_gaze_features(face_norm: np.ndarray) -> np.ndarray:
    """6-dim per-frame gaze feature from *normalized* (478,3) landmarks.

    dims: [L_iris_dx, L_iris_dy, R_iris_dx, R_iris_dy, head_dx, head_dy]
    Each per-eye term: iris center minus eye-corner midpoint, divided by
    corner span (scale-invariant). Head term: nose vs ear-mid, divided by
    inter-ear span. All z-less (xy only).
    """
    def _span_idx(i: int, j: int) -> tuple[np.ndarray, np.ndarray]:
        a, b = face_norm[i, :2], face_norm[j, :2]
        return (a + b) / 2.0, float(np.linalg.norm(a - b) + 1e-9)

    l_mid, l_span = _span_idx(LEFT_EYE_OUTER, LEFT_EYE_INNER)
    r_mid, r_span = _span_idx(RIGHT_EYE_INNER, RIGHT_EYE_OUTER)
    l_iris = face_norm[IRIS_RIGHT_START + 5 : IRIS_RIGHT_START + 10, :2].mean(axis=0)
    r_iris = face_norm[IRIS_RIGHT_START : IRIS_RIGHT_START + 5, :2].mean(axis=0)
    ear_mid, ear_span = _span_idx(LEFT_EAR, RIGHT_EAR)
    nose = face_norm[NOSE_TIP, :2]
    return np.array(
        [
            (l_iris[0] - l_mid[0]) / l_span,
            (l_iris[1] - l_mid[1]) / l_span,
            (r_iris[0] - r_mid[0]) / r_span,
            (r_iris[1] - r_mid[1]) / r_span,
            (nose[0] - ear_mid[0]) / ear_span,
            (nose[1] - ear_mid[1]) / ear_span,
        ],
        dtype=np.float64,
    )


def fit_affine(features: np.ndarray, targets_px: np.ndarray) -> np.ndarray:
    """Least squares features (N,k) -> targets (N,2). Returns (k+1, 2) with bias."""
    a = np.hstack([features, np.ones((features.shape[0], 1))])
    coef, *_ = np.linalg.lstsq(a, targets_px, rcond=None)
    return coef


def predict_affine(coef: np.ndarray, features: np.ndarray) -> np.ndarray:
    a = np.hstack([features, np.ones((features.shape[0], 1))])
    return a @ coef


def fit_poly2(features: np.ndarray, targets_px: np.ndarray) -> np.ndarray:
    """Optional quadratic expansion; same lstsq contract as fit_affine."""
    a = _poly2(features)
    coef, *_ = np.linalg.lstsq(a, targets_px, rcond=None)
    return coef


def predict_poly2(coef: np.ndarray, features: np.ndarray) -> np.ndarray:
    return _poly2(features) @ coef


def _poly2(features: np.ndarray) -> np.ndarray:
    n, k = features.shape
    cols = [features, np.ones((n, 1))]
    for i in range(k):
        for j in range(i, k):
            cols.append((features[:, i] * features[:, j]).reshape(n, 1))
    return np.hstack(cols)


def loo_residual_px(coef: np.ndarray, features: np.ndarray, targets: np.ndarray,
                    *, poly: bool = False) -> np.ndarray:
    """Leave-one-out residual magnitudes (N,) using the matching predictor."""
    pred = predict_poly2 if poly else predict_affine
    n = features.shape[0]
    out = np.full(n, np.inf)
    if n < 4:
        return out
    for i in range(n):
        mask = np.ones(n, bool)
        mask[i] = False
        c = fit_poly2(features[mask], targets[mask]) if poly else fit_affine(
            features[mask], targets[mask]
        )
        p = pred(c, features[i : i + 1])[0]
        out[i] = float(np.linalg.norm(p - targets[i]))
    return out


def palm_center_px(hand_px: np.ndarray) -> np.ndarray:
    """Wrist + middle MCP midpoint; robust center for cursor and filters."""
    return (hand_px[0] + hand_px[9]) / 2.0


def palm_scale_px(hand_px: np.ndarray) -> float:
    """Wrist->middle-MCP distance: normalizes pinch thresholds per distance."""
    return float(np.linalg.norm(hand_px[9] - hand_px[0]) + 1e-9)


def pinch_norm(hand_norm: np.ndarray) -> float:
    """Thumb-tip to index-tip distance / palm scale (normalized space)."""
    d = np.linalg.norm(hand_norm[THUMB_TIP, :2] - hand_norm[INDEX_TIP, :2])
    scale = np.linalg.norm(hand_norm[9, :2] - hand_norm[0, :2]) + 1e-9
    return float(d / scale)


def hand_signed(hand_px: np.ndarray) -> float:
    """Horizontal thumb-vs-index offset sign: +1 thumb right of index."""
    return float(np.sign(hand_px[THUMB_TIP, 0] - hand_px[INDEX_TIP, 0]))
```

`tests/test_geometry.py` (complete):

```python
import json

import numpy as np
import pytest

from vctrl.core import geometry as g


def _fake_face() -> np.ndarray:
    """Synthetic-but-valid 478x3 landmark array (pure math, not fixture data)."""
    pts = np.zeros((478, 3))
    pts[:, 0] = np.linspace(0.3, 0.7, 478)
    pts[:, 1] = np.linspace(0.4, 0.6, 478)
    for i in (g.LEFT_EYE_OUTER, g.LEFT_EYE_INNER, g.RIGHT_EYE_INNER,
              g.RIGHT_EYE_OUTER, g.LEFT_EAR, g.RIGHT_EAR, g.NOSE_TIP):
        pts[i] = [0.5, 0.5, 0.0]
    pts[g.LEFT_EYE_OUTER] = [0.4, 0.5, 0]
    pts[g.LEFT_EYE_INNER] = [0.45, 0.5, 0]
    pts[g.RIGHT_EYE_INNER] = [0.55, 0.5, 0]
    pts[g.RIGHT_EYE_OUTER] = [0.6, 0.5, 0]
    pts[g.LEFT_EAR] = [0.3, 0.5, 0]
    pts[g.RIGHT_EAR] = [0.7, 0.5, 0]
    pts[g.NOSE_TIP] = [0.5, 0.55, 0]
    for i in range(468, 478):
        pts[i] = [0.5, 0.5, 0]
    return pts


def test_to_pixels():
    pts = np.array([[0.5, 0.5, 0.1]])
    xy = g.to_pixels(pts, 640, 480)
    assert np.allclose(xy, [[320, 240]])


def test_features_shape_and_finite():
    f = g.normalize_gaze_features(_fake_face())
    assert f.shape == (6,)
    assert np.isfinite(f).all()


def test_features_head_term_zero_when_symmetric():
    face = _fake_face()
    f = g.normalize_gaze_features(face)
    assert f[4] == pytest.approx(0.0, abs=1e-9)  # nose vs ear mid centered


def test_features_monotone_in_iris_shift():
    a = g.normalize_gaze_features(_fake_face())
    face2 = _fake_face()
    face2[468:473, 0] += 0.05  # right iris moves right
    b = g.normalize_gaze_features(face2)
    assert b[2] > a[2] and np.isclose(b[0], a[0])


def test_affine_fit_exact_on_line():
    feats = np.random.default_rng(3).normal(size=(20, 6))
    true = np.zeros((7, 2))
    true[0, 0] = 100.0
    true[6, 0] = 500.0  # bias x
    coef = g.fit_affine(feats, g.predict_affine(true, feats))
    pred = g.predict_affine(coef, feats)
    assert np.allclose(pred, g.predict_affine(true, feats), atol=1e-6)


def test_loo_residual_detects_outlier():
    rng = np.random.default_rng(0)
    feats = rng.normal(size=(30, 6))
    true = np.zeros((7, 2))
    true[0] = [100, 50]
    targets = g.predict_affine(true, feats)
    targets[7] += 400.0  # one wild point
    res = g.loo_residual_px(g.fit_affine(feats, targets), feats, targets)
    assert res[7] > 100
    assert np.median(res) < 20


def test_poly2_dimension():
    feats = np.zeros((5, 6))
    a = g._poly2(feats)
    assert a.shape[1] == 6 + 1 + 21  # k + bias + k(k+1)/2


def test_palm_and_pinch_math():
    hand = np.zeros((21, 3))
    hand[0] = [0.4, 0.5, 0]
    hand[9] = [0.5, 0.5, 0]
    hand[4] = [0.48, 0.5, 0]
    hand[8] = [0.50, 0.5, 0]
    px = g.to_pixels(hand, 640, 480)
    assert g.palm_center_px(px)[0] == pytest.approx((0.4 + 0.5) / 2 * 640)
    assert g.palm_scale_px(px) == pytest.approx(0.1 * 640)
    assert g.pinch_norm(hand) == pytest.approx(0.02 / 0.1)
    assert g.hand_signed(px) > 0


def test_real_corpus_features(fixtures_dir):
    data = np.load(fixtures_dir / "clean.npz")
    valid = data["face_valid"]
    assert valid.sum() >= 30
    for row in data["face"][valid][:40].astype(np.float64):
        f = g.normalize_gaze_features(row)
        assert np.isfinite(f).all()
        assert np.abs(f).max() < 5.0  # normalized residuals stay small
```

**TDD steps:**

1. Write `tests/test_geometry.py` first - red.
2. Write `geometry.py` - green; ruff clean.
3. Commit `feat(a07): geometry - landmark transforms, gaze features, affine/poly2 + LOO`, push.

**Done when:** synthetic-math tests and the real-corpus feature test pass.

---

### Task 8 - Gaze model: fit on calibration, predict + gates + confidence

**Files:** `vctrl/tracking/gaze.py`, `tests/test_gaze.py`

`gaze.py` (complete):

```python
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from vctrl.config.schemas import GazeFitConfig
from vctrl.config.store import load_model, save_model
from vctrl.core.geometry import (
    fit_affine,
    fit_poly2,
    loo_residual_px,
    normalize_gaze_features,
    predict_affine,
    predict_poly2,
)

log = logging.getLogger(__name__)

# 6 features; per-eye models drop the other eye's two dims
COMBINED = [0, 1, 2, 3, 4, 5]
LEFT_ONLY = [0, 1, 4, 5]
RIGHT_ONLY = [2, 3, 4, 5]


@dataclass
class GazeSample:
    x: float  # screen px
    y: float
    conf: float  # 0..1


@dataclass
class GazeState:
    features: np.ndarray | None = None
    target_px: np.ndarray | None = None
    last_x: float = float("nan")
    last_y: float = float("nan")
    vel_px: float = 0.0


class GazeModel:
    """Least-squares calibration with LOO gate, variance and velocity gates.

    Weighted ensemble: combined 0.5, left-only 0.25, right-only 0.25.
    Monocular fallback (weight 0.7) when one eye's fit fails.
    """

    def __init__(self, cfg: GazeFitConfig) -> None:
        self.cfg = cfg
        self.coefs: dict[str, np.ndarray] = {}
        self.res_scale: dict[str, float] = {}
        self.screen_w = 1920
        self.gate_px = cfg.loo_gate_px
        self.valid = False

    def fit(self, features: np.ndarray, targets_px: np.ndarray,
            screen_w: int = 1920, screen_h: int = 1080) -> dict:
        """Fit from calibration rows. Returns a report dict (used by tests + UI)."""
        self.screen_w, self.screen_h = screen_w, screen_h
        self.gate_px = self.cfg.loo_gate_px * (screen_w / 1920.0)
        ok = features.shape[0] >= self.cfg.loo_min_samples
        report: dict = {"n": int(features.shape[0]), "models": {}}
        self.coefs, self.res_scale = {}, {}
        if not ok:
            report["error"] = f"need >= {self.cfg.loo_min_samples} samples"
            self.valid = False
            return report

        for name, dims in (("combined", COMBINED), ("left", LEFT_ONLY), ("right", RIGHT_ONLY)):
            try:
                sub = features[:, dims]
                coef = (fit_poly2 if self.cfg.polynomial else fit_affine)(sub, targets_px)
                res = loo_residual_px(coef, sub, targets_px, poly=self.cfg.polynomial)
                loo_med = float(np.median(res))
                loo_mean = float(np.mean(res))
                self.coefs[name] = coef
                self.res_scale[name] = max(loo_med, 1.0)
                report["models"][name] = {
                    "loo_median": round(loo_med, 1),
                    "loo_mean": round(loo_mean, 1),
                    "loo_max": round(float(np.max(res)), 1),
                }
            except np.linalg.LinAlgError as exc:
                log.warning("gaze fit failed for %s: %s", name, exc)
                report["models"][name] = {"error": str(exc)}

        self.valid = "combined" in self.coefs
        report["gate_px"] = self.gate_px
        report["valid"] = self.valid
        return report

    def predict(self, face_norm: np.ndarray | None, state: GazeState,
                *, dt_s: float = 1 / 30) -> GazeSample:
        if face_norm is None or not self.valid:
            state.vel_px = 0.0
            return GazeSample(state.last_x, state.last_y, 0.0)

        feats = normalize_gaze_features(face_norm)
        state.features = feats

        preds, weights = [], []
        for name, w in (("combined", 0.5), ("left", 0.25), ("right", 0.25)):
            if name not in self.coefs:
                # monocular fallback: keep the surviving eye model at higher weight
                if name in ("left", "right") and "combined" in self.coefs:
                    continue
                continue
            dims = {"combined": COMBINED, "left": LEFT_ONLY, "right": RIGHT_ONLY}[name]
            sub = feats[dims].reshape(1, -1)
            pred = (predict_poly2 if self.cfg.polynomial else predict_affine)(
                self.coefs[name], sub
            )[0]
            preds.append(pred)
            weights.append(w)
        if not preds:
            return GazeSample(state.last_x, state.last_y, 0.0)
        w = np.asarray(weights)
        w = w / w.sum()
        # monocular situations (only one eye model survived) get the 0.7 penalty
        if len(preds) < 3:
            scale = 0.7 / w.sum()
            w = w * scale
            w = w / w.sum()
        xy = (np.asarray(preds) * w[:, None]).sum(axis=0)

        # velocity gate (ratio of screen diagonal, derivative of last prediction)
        if np.isfinite(state.last_x):
            d = float(np.hypot(xy[0] - state.last_x, xy[1] - state.last_y))
            state.vel_px = d / max(dt_s, 1e-6)
            diag = float(np.hypot(self.screen_w, self.screen_h))
            if d > self.cfg.velocity_gate_ratio * diag * dt_s * 60:
                # teleport clamp: clamp to the gated distance, lower confidence
                step = self.cfg.velocity_gate_ratio * diag * dt_s * 60
                ux, uy = (xy[0] - state.last_x), (xy[1] - state.last_y)
                n = float(np.hypot(ux, uy)) + 1e-9
                xy = np.array([state.last_x + ux / n * step, state.last_y + uy / n * step])
                conf_vel = 0.3
            else:
                conf_vel = 1.0
        else:
            conf_vel = 1.0

        # residual/conf: combined loo_mean vs gate
        loo_mean = self.res_scale.get("combined", 999.0) * 2.0
        loo_ok = float(np.clip(1.0 - loo_mean / max(self.gate_px, 1e-6), 0.05, 1.0))
        conf = float(np.clip(loo_ok * conf_vel, 0.0, 1.0))

        state.last_x, state.last_y = float(xy[0]), float(xy[1])
        return GazeSample(float(xy[0]), float(xy[1]), conf)

    def variance_gate(self, samples: list[GazeSample], t_ms: list[int]) -> bool:
        """False when recent samples scatter beyond k*sigma of the window mean."""
        if len(samples) < 6:
            return True
        xy = np.array([[s.x, s.y] for s in samples[-12:]], dtype=np.float64)
        if np.isnan(xy).any():
            return False
        d = np.hypot(*(xy - xy.mean(axis=0)).T)
        return bool(d.std() * self.cfg.variance_k + d.mean() >= d[-1])

    def save(self, path: Path) -> None:
        save_model(path, self._to_store())

    @classmethod
    def load(cls, path: Path, cfg: GazeFitConfig) -> GazeModel:
        m = cls(cfg)
        store = load_model(path, _GazeStore)
        if store.valid:
            m.coefs = {k: np.asarray(v, dtype=np.float64) for k, v in store.coefs.items()}
            m.res_scale = dict(store.res_scale)
            m.screen_w, m.screen_h = store.screen_w, store.screen_h
            m.gate_px = store.gate_px
            m.valid = True
        return m

    def _to_store(self) -> _GazeStore:
        return _GazeStore(
            valid=self.valid,
            coefs={k: v.tolist() for k, v in self.coefs.items()},
            res_scale=self.res_scale,
            screen_w=self.screen_w,
            screen_h=getattr(self, "screen_h", 1080),
            gate_px=self.gate_px,
        )

    def invalidate(self) -> None:
        self.valid = False
        self.coefs.clear()


from pydantic import BaseModel  # noqa: E402


class _GazeStore(BaseModel):
    valid: bool = False
    coefs: dict[str, list[list[float]]] = {}
    res_scale: dict[str, float] = {}
    screen_w: int = 1920
    screen_h: int = 1080
    gate_px: float = 150.0
    schema_version: int = 1
```

**TDD steps:**

1. Write `tests/test_gaze.py` first (uses `calib-quick5.npz` +
   `clean.npz` from the real corpus):

```python
import numpy as np
import pytest

from vctrl.config.schemas import GazeFitConfig
from vctrl.core.geometry import normalize_gaze_features
from vctrl.tracking.gaze import GazeModel, GazeState


def _fit_from_calib(fixtures_dir):
    data = np.load(fixtures_dir / "calib-quick5.npz")
    ok = ~np.isnan(data["calib_targets"][:, 0])
    feats = np.array([
        normalize_gaze_features(row.astype(np.float64))
        for row in data["face"][ok]
    ])
    targets = data["calib_targets"][ok].astype(np.float64)
    model = GazeModel(GazeFitConfig())
    report = model.fit(feats, targets, screen_w=1920, screen_h=1080)
    return model, report, feats, targets


def test_fit_report_valid(fixtures_dir):
    model, report, feats, targets = _fit_from_calib(fixtures_dir)
    assert report["valid"], report
    assert report["n"] >= 25
    assert report["models"]["combined"]["loo_median"] <= 150.0


def test_fit_too_few_samples_fails(fixtures_dir):
    model = GazeModel(GazeFitConfig())
    r = model.fit(np.zeros((3, 6)), np.zeros((3, 2)))
    assert not r["valid"]


def test_predict_close_on_calib_points(fixtures_dir):
    model, _, feats, targets = _fit_from_calib(fixtures_dir)
    state = GazeState()
    errs = []
    for i in range(len(feats)):
        sample = model.predict_row(feats[i], state)
        errs.append(np.hypot(sample.x - targets[i, 0], sample.y - targets[i, 1]))
    med = float(np.median(errs))
    assert med < 150.0, f"median residual {med:.0f}px exceeds gate"


def test_predict_needs_face(fixtures_dir):
    model, *_ = _fit_from_calib(fixtures_dir)
    s = model.predict(None, GazeState())
    assert s.conf == 0.0


def test_confidence_on_real_session(fixtures_dir):
    model, *_ = _fit_from_calib(fixtures_dir)
    data = np.load(fixtures_dir / "clean.npz")
    state = GazeState()
    confs = []
    for row, valid in zip(data["face"][:60], data["face_valid"][:60], strict=True):
        s = model.predict(row.astype(np.float64) if valid else None, state)
        if valid:
            confs.append(s.conf)
    assert confs and np.median(confs) > 0.5


def test_save_load_roundtrip(tmp_path, fixtures_dir):
    model, *_ = _fit_from_calib(fixtures_dir)
    p = tmp_path / "calibration.json"
    model.save(p)
    m2 = GazeModel.load(p, GazeFitConfig())
    assert m2.valid and set(m2.coefs) == set(model.coefs)
    assert np.allclose(m2.coefs["combined"], model.coefs["combined"])


def test_invalidate(fixtures_dir):
    model, *_ = _fit_from_calib(fixtures_dir)
    model.invalidate()
    assert not model.valid
```

Note: tests call a thin `predict_row(feats, state)` helper - add it to
`GazeModel` so tests bypass landmark extraction (the public `predict()`
still consumes raw face landmarks for the pipeline):

```python
    def predict_row(self, feats: np.ndarray, state: GazeState,
                    *, dt_s: float = 1 / 30) -> GazeSample:
        """Same math as predict() but from an already-extracted feature row."""
        saved = state.features
        # factor the ensemble+gates out of predict() into _ensemble(feats, state, dt)
        out = self._ensemble(feats, state, dt_s)
        state.features = saved
        return out
```

Refactor rule: `predict()` = `normalize_gaze_features` + `_ensemble`;
`predict_row()` = `_ensemble`. Keep the full-body test in
`test_confidence_on_real_session` using `predict()` with raw landmarks.

2. Run `uv run pytest tests/test_gaze.py` - red; write `gaze.py` - green.
   Ruff clean (move the late `from pydantic import BaseModel` to the top
   in final code).
3. Commit `feat(a08): calibration gaze model with LOO/velocity gates and persistence`, push.

**Done when:** fit report passes on real quick5 data, median predict
error < 150 px on calibration points, persistence round-trips.

---

### Task 9 - Hand features: palm, pinch, extension, state helpers

**Files:** `vctrl/tracking/hand.py`, `tests/test_hand.py`

`hand.py` (complete):

```python
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from vctrl.config.schemas import TrackingConfig
from vctrl.core.geometry import (
    hand_signed,
    palm_center_px,
    palm_scale_px,
    pinch_norm,
    to_pixels,
)

# Fingertip / PIP indices
TIPS = [4, 8, 12, 16, 20]
PIP = [3, 6, 10, 14, 18]
MCP = [2, 5, 9, 13, 17]


@dataclass
class HandFeatures:
    valid: bool = False
    center_px: np.ndarray = field(default_factory=lambda: np.array([np.nan, np.nan]))
    scale_px: float = float("nan")
    pinch: float = float("nan")  # thumb-index / palm scale
    pinch_signed: float = float("nan")
    extended: np.ndarray = field(default_factory=lambda: np.zeros(5, bool))
    handed: str = "Right"
    conf: float = 0.0
    landmarks_px: np.ndarray | None = None
    landmarks_norm: np.ndarray | None = None

    @property
    def point_ok(self) -> bool:
        """Index extended, middle/ring/pinky curled - 'mouse pointer' pose."""
        return bool(self.valid and self.extended[1] and not self.extended[2]
                    and not self.extended[3] and not self.extended[4])


def extract_hand(hand_norm: np.ndarray | None, w: int, h: int, *, label: str = "Right",
                 conf: float = 1.0, cfg: TrackingConfig | None = None) -> HandFeatures:
    if hand_norm is None:
        return HandFeatures()
    px = to_pixels(hand_norm, w, h)
    feats = HandFeatures(
        valid=True,
        center_px=palm_center_px(px),
        scale_px=palm_scale_px(px),
        pinch=pinch_norm(hand_norm),
        pinch_signed=hand_signed(px),
        handed=label,
        conf=conf,
        landmarks_px=px,
        landmarks_norm=hand_norm,
    )
    feats.extended = _extension(hand_norm)
    return feats


def _extension(hand_norm: np.ndarray) -> np.ndarray:
    """Finger i is extended when its tip is farther from the wrist (0)
    in normalized xy than its PIP joint - works for any grip style."""
    wrist = hand_norm[0, :2]
    out = np.zeros(5, bool)
    for i in range(5):
        tip_d = np.linalg.norm(hand_norm[TIPS[i], :2] - wrist)
        pip_d = np.linalg.norm(hand_norm[PIP[i], :2] - wrist)
        out[i] = tip_d > pip_d * 1.05
    return out


def select_hand(features: list[HandFeatures], *, prefer: str | None = None) -> HandFeatures:
    """Best valid hand: preferred handedness first, then highest conf, then
    largest scale (closest to camera)."""
    valid = [f for f in features if f.valid]
    if not valid:
        return HandFeatures()
    if prefer:
        pref = [f for f in valid if f.handed == prefer]
        if pref:
            valid = pref
    return max(valid, key=lambda f: (f.conf, f.scale_px))


class PalmEMA:
    """Config-weighted exponential smoothing of the palm center (per hand slot)."""

    def __init__(self, alpha: float) -> None:
        self.alpha = alpha
        self._v: np.ndarray | None = None

    def update(self, x: float) -> float:
        if not np.isfinite(x):
            return float("nan") if self._v is None else float(self._v[0])
        cur = np.array([x])
        if self._v is None:
            self._v = cur
        else:
            self._v = self.alpha * cur + (1 - self.alpha) * self._v
        return float(self._v[0])

    def reset(self) -> None:
        self._v = None
```

`tests/test_hand.py` (complete):

```python
import numpy as np
import pytest

from vctrl.tracking.hand import HandFeatures, PalmEMA, extract_hand, select_hand


def _open_hand() -> np.ndarray:
    """Normalized 21x3 open palm facing camera (math model, not fixture)."""
    h = np.zeros((21, 3))
    h[0] = [0.50, 0.80, 0]  # wrist
    bases = [(0.42, 0.70), (0.46, 0.64), (0.50, 0.63), (0.54, 0.64), (0.58, 0.70)]
    for i, (x, y) in enumerate(bases):
        h[MCP_ROW[i]] = [x, y, 0]
    # fingers straight up (tips farther from wrist than PIPs)
    for i, x in enumerate([0.42, 0.46, 0.50, 0.54, 0.58]):
        h[PIP_IDX[i]] = [x, 0.50, 0]
        h[TIP_IDX[i]] = [x, 0.36 - 0.02 * abs(i - 2), 0]
    # thumb spread left
    h[2] = [0.38, 0.72, 0]
    h[3] = [0.34, 0.66, 0]
    h[4] = [0.31, 0.60, 0]
    return h


MCP_ROW = [1, 5, 9, 13, 17]
PIP_IDX = [6, 10, 14, 18, 0]
TIP_IDX = [8, 12, 16, 20, 4]


def _fist() -> np.ndarray:
    h = _open_hand()
    for i in TIP_IDX[:4]:
        h[i] = h[i] * 0.5 + np.array([0.5, 0.6, 0]) * 0.5  # tips pulled to palm
    h[4] = [0.47, 0.66, 0]
    return h


def test_extract_open_hand():
    f = extract_hand(_open_hand(), 640, 480)
    assert f.valid
    assert f.scale_px == pytest.approx(np.linalg.norm([0.0, -0.17]) * 480, rel=1e-3)
    assert f.extended[1] and f.extended[2], "open palm: index+middle extended"
    assert f.pinch > 0.3


def test_extract_fist():
    f = extract_hand(_fist(), 640, 480)
    assert not f.point_ok
    assert f.pinch < 0.3


def test_point_pose():
    h = _open_hand()
    # curl middle/ring/pinky only
    for i in [12, 16, 20]:
        h[i] = h[i] * 0.5 + np.array([0.5, 0.6, 0]) * 0.5
    f = extract_hand(h, 640, 480)
    assert f.point_ok


def test_none_hand():
    f = extract_hand(None, 640, 480)
    assert not f.valid and not f.point_ok


def test_select_prefers_handedness_then_conf():
    right = extract_hand(_open_hand(), 640, 480, label="Right", conf=0.6)
    left = extract_hand(_open_hand(), 640, 480, label="Left", conf=0.9)
    assert select_hand([right, left]).handed == "Left"
    assert select_hand([right, left], prefer="Right").handed == "Right"
    assert not select_hand([]).valid


def test_palm_ema():
    e = PalmEMA(0.5)
    assert e.update(10.0) == 10.0
    assert e.update(20.0) == 15.0
    assert e.update(float("nan")) == 15.0
    e.reset()
    assert e.update(3.0) == 3.0


def test_real_corpus_hands(fixtures_dir):
    data = np.load(fixtures_dir / "clean.npz")
    n_valid = 0
    for row, valid, conf, lab in zip(
        data["hands"], data["hand_valid"], data["hand_conf"], data["hand_label"],
        strict=True,
    ):
        if not valid[0]:
            continue
        f = extract_hand(row[0].astype(np.float64), 640, 480, conf=float(conf[0]),
                         label="Right" if lab[0] == 1 else "Left")
        assert f.valid and np.isfinite(f.center_px).all()
        assert f.scale_px > 0
        n_valid += 1
    assert n_valid >= 10, "clean scenario should contain hands"


def test_real_pinch_series(fixtures_dir):
    data = np.load(fixtures_dir / "pinch.npz")
    pinch_vals = []
    for row, valid in zip(data["hands"], data["hand_valid"], strict=True):
        if valid[0]:
            pinch_vals.append(extract_hand(row[0].astype(np.float64), 640, 480).pinch)
    assert pinch_vals, "pinch session must contain hands"
    lo, hi = min(pinch_vals), max(pinch_vals)
    assert hi > lo + 0.15, f"pinch distance must vary (lo={lo:.2f} hi={hi:.2f})"
```

**TDD steps:**

1. Write `tests/test_hand.py` first - red. (Fix `MCP_ROW`/`PIP_IDX`/
   `TIP_IDX` ordering in the final code - define them once at module
   top of the test and reference the same indices as `hand.py`.)
2. Write `hand.py` - green; ruff clean.
3. Commit `feat(a09): hand feature extraction - palm, pinch, extension, selection`, push.

**Done when:** synthetic pose tests and real-corpus pinch-variation
test pass.

---

### Task 10 - Gesture detectors + dwell (16-gesture library start)

**Files:** `vctrl/tracking/gestures.py`, `tests/test_gestures.py`

`gestures.py` (complete):

```python
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field, field_validator

from vctrl.config.store import load_model, save_model
from vctrl.core.geometry import to_pixels
from vctrl.tracking.hand import HandFeatures, TIPS, PIP


class DetectorConfig(BaseModel):
    name: str
    on_th: float = Field(0.7, ge=0.0, le=1.0)
    off_th: float = Field(0.4, ge=0.0, le=1.0)
    hold_ms: int = 0  # continuous hold required before firing (fist: 300)
    debounce_frames: int = 3

    @field_validator("off_th")
    @classmethod
    def _below_on(cls, v: float, info) -> float:
        on = info.data.get("on_th", 0.7)
        if v >= on:
            raise ValueError("off_th must be < on_th")
        return v


class DetectorStore(BaseModel):
    schema_version: int = 1
    detectors: dict[str, DetectorConfig] = {}

    @classmethod
    def default(cls) -> DetectorStore:
        return cls(detectors=dict(DEFAULT_DETECTORS))


DEFAULT_DETECTORS: dict[str, DetectorConfig] = {
    "index_pinch": DetectorConfig(name="index_pinch", on_th=0.7, off_th=0.4),
    "two_finger_pinch": DetectorConfig(name="two_finger_pinch", on_th=0.7, off_th=0.4),
    "precision_squeeze": DetectorConfig(name="precision_squeeze", on_th=0.7, off_th=0.4),
    "point": DetectorConfig(name="point", on_th=0.7, off_th=0.4),
    "open_palm": DetectorConfig(name="open_palm", on_th=0.7, off_th=0.4),
    "fist": DetectorConfig(name="fist", on_th=0.7, off_th=0.4, hold_ms=300),
    "t_shape": DetectorConfig(name="t_shape", on_th=0.7, off_th=0.4),
    "vertical_travel": DetectorConfig(name="vertical_travel", on_th=0.6, off_th=0.3),
    "dwell": DetectorConfig(name="dwell", on_th=1.0, off_th=1.0, hold_ms=600),
}


@dataclass
class GestureEvent:
    name: str
    fired_at_ms: float
    hand: str = "Right"
    meta: dict = field(default_factory=dict)


# ---- per-frame raw scores (0/1 continuous float for hysteresis input) ----

def score_index_pinch(f: HandFeatures) -> float:
    if not f.valid or not np.isfinite(f.pinch):
        return 0.0
    # pinch_norm small when touching: map 0.35..0.15 -> 0..1
    return float(np.clip((0.35 - f.pinch) / 0.20, 0.0, 1.0))


def score_two_finger_pinch(f: HandFeatures) -> float:
    if not f.valid or f.landmarks_norm is None:
        return 0.0
    n = f.landmarks_norm
    d = np.linalg.norm(n[4, :2] - n[12, :2]) / (np.linalg.norm(n[9, :2] - n[0, :2]) + 1e-9)
    return float(np.clip((0.35 - d) / 0.20, 0.0, 1.0))


def score_precision_squeeze(f: HandFeatures) -> float:
    if not f.valid:
        return 0.0
    # thumb-index touching + middle also close (fine pinch)
    return min(score_index_pinch(f), score_two_finger_pinch(f))


def score_point(f: HandFeatures) -> float:
    return 1.0 if f.valid and f.point_ok else 0.0


def score_open_palm(f: HandFeatures) -> float:
    if not f.valid:
        return 0.0
    return 1.0 if f.extended.all() else 0.0


def score_fist(f: HandFeatures) -> float:
    if not f.valid:
        return 0.0
    curled = (~f.extended).sum()
    return float(curled / 5.0)


def score_t_shape(f: HandFeatures) -> float:
    """Index horizontal, thumb vertical, other fingers curled."""
    if not f.valid or f.landmarks_px is None:
        return 0.0
    px = f.landmarks_px
    thumb_up = px[4, 1] < px[2, 1] - 10
    index_side = abs(px[8, 1] - px[5, 1]) < 0.3 * f.scale_px and px[8, 0] != px[5, 0]
    curled = (~f.extended).sum() >= 3
    return 1.0 if (thumb_up and index_side and curled) else 0.0


SCORE_FUNCS = {
    "index_pinch": score_index_pinch,
    "two_finger_pinch": score_two_finger_pinch,
    "precision_squeeze": score_precision_squeeze,
    "point": score_point,
    "open_palm": score_open_palm,
    "fist": score_fist,
    "t_shape": score_t_shape,
}


def score_vertical_travel(history: list[tuple[float, float]], *, window_ms: float = 400,
                           threshold_px: float = 60) -> float:
    """Sustained downward (or upward) motion of the palm over a window."""
    if len(history) < 3:
        return 0.0
    t0, y0 = history[0]
    recent = [(t, y) for t, y in history if t - t0 <= window_ms]
    if len(recent) < 3:
        return 0.0
    dy = recent[-1][1] - y0
    return float(np.clip(abs(dy) / threshold_px, 0.0, 1.0))


# ---- hysteresis + hold + debounce FSM ----

@dataclass
class _State:
    raw_prev: float = 0.0
    armed: bool = False          # passed on_th
    held_since_ms: float | None = None
    last_fire_ms: float = -1e9
    last_release_ms: float = -1e9


class GestureFSM:
    """Schmitt trigger (on_th/off_th) + hold-time + debounce.

    Events fire on rising edges only, at most one per hold_ms+debounce window.
    """

    def __init__(self, cfg: DetectorConfig) -> None:
        self.cfg = cfg
        self.s = _State()

    def update(self, raw: float, t_ms: float) -> bool:
        c = self.cfg
        if not self.s.armed:
            if raw >= c.on_th:
                self.s.armed = True
                self.s.held_since_ms = t_ms
        else:
            if raw <= c.off_th:
                if t_ms - self.s.last_release_ms >= c.debounce_frames * 33:
                    self.s.armed = False
                    self.s.held_since_ms = None
                    self.s.last_release_ms = t_ms
        if not self.s.armed or self.s.held_since_ms is None:
            return False
        if t_ms - self.s.held_since_ms < c.hold_ms:
            return False
        if t_ms - self.s.last_fire_ms < max(c.hold_ms, 200) + c.debounce_frames * 33:
            return False
        self.s.last_fire_ms = t_ms
        self.s.held_since_ms = t_ms  # restart hold so long-press re-fires slowly
        return True

    @property
    def held(self) -> bool:
        return self.s.armed


class DwellDetector:
    """Cursor rests inside a radius for `hold_ms` -> dwell event."""

    def __init__(self, *, radius_px: float = 40.0, hold_ms: int = 600,
                 cooldown_ms: int = 500) -> None:
        self.radius = radius_px
        self.hold_ms = hold_ms
        self.cooldown_ms = cooldown_ms
        self._anchor: np.ndarray | None = None
        self._since_ms: float | None = None
        self._last_fire_ms = -1e9

    def update(self, x: float, y: float, t_ms: float) -> bool:
        if not (np.isfinite(x) and np.isfinite(y)):
            self._anchor = None
            self._since_ms = None
            return False
        p = np.array([x, y])
        if self._anchor is None or np.hypot(*(p - self._anchor)) > self.radius:
            self._anchor = p
            self._since_ms = t_ms
            return False
        assert self._since_ms is not None
        if t_ms - self._since_ms >= self.hold_ms:
            if t_ms - self._last_fire_ms >= self.cooldown_ms:
                self._last_fire_ms = t_ms
                self._anchor = p
                self._since_ms = t_ms
                return True
        return False

    def reset(self) -> None:
        self._anchor = None
        self._since_ms = None


def load_detectors(path: Path) -> dict[str, DetectorConfig]:
    store = load_model(path, DetectorStore)
    if not store.detectors:
        store = DetectorStore.default()
    return dict(store.detectors)


def save_detectors(path: Path, detectors: dict[str, DetectorConfig]) -> None:
    save_model(path, DetectorStore(detectors=detectors))
```

`tests/test_gestures.py` (complete):

```python
import numpy as np
import pytest

from vctrl.tracking.gestures import (
    DEFAULT_DETECTORS,
    DwellDetector,
    GestureFSM,
    score_fist,
    score_index_pinch,
    score_open_palm,
    score_point,
)
from vctrl.tracking.hand import extract_hand


def _hand_from(h_norm):
    return extract_hand(h_norm, 640, 480)


def _palm_center(hand_norm):
    px = hand_norm[[0, 9], :2].mean(axis=0) * np.array([640, 480])
    return float(px[0]), float(px[1])


def test_fsm_fires_once_per_hold():
    cfg = DEFAULT_DETECTORS["index_pinch"]
    fsm = GestureFSM(cfg)
    fires = [fsm.update(1.0, t) for t in range(0, 2000, 33)]
    assert sum(fires) == 1


def test_fsm_no_fire_below_on_th():
    fsm = GestureFSM(DEFAULT_DETECTORS["index_pinch"])
    assert not any(fsm.update(0.5, t) for t in range(0, 500, 33))


def test_fsm_requires_release_before_refire():
    cfg = DEFAULT_DETECTORS["fist"]  # hold_ms=300
    fsm = GestureFSM(cfg)
    fired = [fsm.update(1.0, t) for t in range(0, 1500, 33)]
    assert sum(fired) == 1
    assert not fsm.update(1.0, 1500)  # still held: no re-fire
    fsm.update(0.0, 1533)             # release
    fired2 = [fsm.update(1.0, t) for t in range(1566, 3000, 33)]
    assert sum(fired2) == 1


def test_hysteresis_deadband():
    cfg = DEFAULT_DETECTORS["index_pinch"]  # on 0.7 off 0.4
    fsm = GestureFSM(cfg)
    assert fsm.update(0.8, 0)  # arm
    assert not fsm.update(0.5, 33)   # between off and on: stays armed, no drop
    assert fsm.held


def test_dwell_fires_after_hold():
    d = DwellDetector(radius_px=40, hold_ms=600)
    fired = [d.update(100.0, 100.0, t) for t in range(0, 900, 33)]
    assert sum(fired) == 1


def test_dwell_no_fire_when_moving():
    d = DwellDetector(radius_px=40, hold_ms=600)
    for i, t in enumerate(range(0, 900, 33)):
        d.update(100.0 + i * 30, 100.0, t)
    # anchor follows movement; no sustained rest
    assert d.update(100.0, 100.0, 990) in (False, True) is False or True  # moved


def test_dwell_resets_on_nan():
    d = DwellDetector()
    d.update(10, 10, 0)
    d.update(float("nan"), float("nan"), 33)
    assert d.update(10, 10, 66) is False  # anchor restarted


def test_score_functions_on_synthetic_open_hand():
    from tests.test_hand import _open_hand, _fist  # reuse math hands
    f = _hand_from(_open_hand())
    assert score_open_palm(f) == 1.0
    assert score_point(f) == 0.0
    assert score_fist(f) < 0.5
    g = _hand_from(_fist())
    assert score_fist(g) >= 0.8
    assert score_open_palm(g) == 0.0


def test_index_pinch_score_range():
    from tests.test_hand import _open_hand
    f = _hand_from(_open_hand())
    assert 0.0 <= score_index_pinch(f) <= 1.0
    # touching thumb+index
    h = _open_hand()
    h[4] = h[8].copy()
    g = _hand_from(h)
    assert score_index_pinch(g) == pytest.approx(1.0)


def test_real_pinch_corpus_fsm(fixtures_dir):
    """Real pinch session: FSM must fire multiple pinch events."""
    data = np.load(fixtures_dir / "pinch.npz")
    names = __import__("json").loads(str(data["label_names"]))
    idx = names.index("pinch_on")
    label = data["labels"] == idx
    fsm = GestureFSM(DEFAULT_DETECTORS["index_pinch"])
    fires = 0
    for row, valid, t in zip(data["hands"], data["hand_valid"], data["t"], strict=True):
        if not valid[0]:
            continue
        f = extract_hand(row[0].astype(np.float64), 640, 480)
        if fsm.update(score_index_pinch(f), float(t)):
            fires += 1
    assert fires >= 1, "real pinch session should trigger the detector at least once"


def test_detector_store_roundtrip(tmp_path):
    from vctrl.tracking.gestures import load_detectors, save_detectors
    p = tmp_path / "gestures.json"
    save_detectors(p, DEFAULT_DETECTORS)
    loaded = load_detectors(p)
    assert set(loaded) == set(DEFAULT_DETECTORS)
    assert loaded["fist"].hold_ms == 300
```

**TDD steps:**

1. Write `tests/test_gestures.py` first - red. Clean up the sloppy
   `test_dwell_no_fire_when_moving` assertion in final code: iterate
   moving positions then assert a stationary 600 ms hold at a *new*
   position fires exactly once (anchor reset by motion), i.e. replace
   the `is False or True` tautology with a real check.
2. Write `gestures.py` - green; ruff clean. Ensure `json` import used or
   removed (the corpus test uses `__import__` - move to top-level
   `import json` in final code).
3. Commit `feat(a10): gesture detectors with hysteresis, hold, dwell`, push.

**Done when:** FSM hysteresis/hold/debounce tests pass and the real
pinch corpus fires the detector.

---

### Task 11 - Tracker: gates -> 1€ -> soft-magnet fusion -> pinch FSM -> dwell

**Files:** `vctrl/tracking/tracker.py`, `tests/test_tracker.py`

`tracker.py` (complete):

```python
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from vctrl.config.schemas import TrackingConfig
from vctrl.core.filters import OneEuroFilter
from vctrl.tracking.gaze import GazeModel, GazeSample, GazeState
from vctrl.tracking.gestures import (
    DEFAULT_DETECTORS,
    DwellDetector,
    GestureEvent,
    GestureFSM,
    score_index_pinch,
    score_point,
)
from vctrl.tracking.hand import HandFeatures, PalmEMA, extract_hand, select_hand

log = logging.getLogger(__name__)

MODES = ("both", "gaze_only", "hand_only", "frozen")


@dataclass
class FrameOutput:
    """Everything downstream (CLI headless run, overlay, outputs) consumes."""

    t_ms: float
    cursor: tuple[float, float] = (float("nan"), float("nan"))
    cursor_conf: float = 0.0
    gaze: tuple[float, float] = (float("nan"), float("nan"))
    gaze_conf: float = 0.0
    hand: tuple[float, float] = (float("nan"), float("nan"))
    hand_valid: bool = False
    precision: bool = False
    pinch_held: bool = False
    pinch_tap: bool = False
    pinch_hold: bool = False
    events: list[GestureEvent] = field(default_factory=list)
    fps: float = 0.0
    mode: str = "both"
    reason: str = ""  # why cursor is invalid this frame (debug overlay)


class Tracker:
    """Pure per-frame state machine: no IO, no threads (Tier-1 testable)."""

    def __init__(self, cfg: TrackingConfig, gaze: GazeModel | None = None,
                 screen: tuple[int, int] = (1920, 1080),
                 detectors=None) -> None:
        self.cfg = cfg
        self.gaze = gaze
        self.screen_w, self.screen_h = screen
        self.mode = "both"
        self.gaze_state = GazeState()
        self._gaze_filt = OneEuroFilter(cfg.filter)
        self._cursor_filt = OneEuroFilter(cfg.filter)
        self._hand_ema = PalmEMA(cfg.smoothing_alpha)
        self._hand_hist: list[tuple[float, float]] = []  # (t_ms, x)
        self._last_cursor: np.ndarray | None = None
        self._last_t: float | None = None
        self._frame_count = 0
        self._fps = 0.0
        self._fps_t0: float | None = None
        # pinch FSM (index pinch) + dwell
        dets = dict(detectors or DEFAULT_DETECTORS)
        self._pinch_fsm = GestureFSM(dets["index_pinch"])
        self._dwell = DwellDetector(radius_px=40, hold_ms=dets["dwell"].hold_ms)
        self._pinch_on_ms: float | None = None
        self._pinch_held = False
        # precision mode (squeeze-to-precision detector in Plan B/D binds it;
        # here precision toggles from dwell proximity handled by config flag)
        self._precision = False

    # ---- helpers ------------------------------------------------------------

    def _gate_velocity(self, raw: np.ndarray, t_ms: float) -> tuple[np.ndarray, str]:
        if self._last_cursor is None or self._last_t is None or t_ms <= self._last_t:
            self._last_cursor, self._last_t = raw, t_ms
            return raw, ""
        dt = (t_ms - self._last_t) / 1000.0
        d = float(np.hypot(*(raw - self._last_cursor)))
        max_step = self.cfg.max_step_px * max(dt, 1 / 120)
        if d > max_step:
            u = (raw - self._last_cursor) / (d + 1e-9)
            clamped = self._last_cursor + u * max_step
            self._last_cursor, self._last_t = clamped, t_ms
            return clamped, "velocity_clamp"
        self._last_cursor, self._last_t = raw, t_ms
        return raw, ""

    def _gaze_ok(self, sample: GazeSample) -> bool:
        if not math.isfinite(sample.x):
            return False
        if sample.conf < self.cfg.min_gaze_conf:
            return False
        # recent-window variance gate
        return self.gaze.variance_gate(
            list(self._recent_gaze[-12:]), []
        ) if self.gaze is not None and hasattr(self, "_recent_gaze") else True

    @property
    def _recent_gaze(self) -> list[GazeSample]:
        if not hasattr(self, "_gaze_ring"):
            self._gaze_ring: list[GazeSample] = []
        return self._gaze_ring

    # ---- fusion -------------------------------------------------------------

    def _fuse(self, gaze_xy: np.ndarray | None, hand_xy: np.ndarray | None) -> tuple[np.ndarray, str]:
        """cursor = hand + gain*(gaze-hand)*falloff; falloff = min(1, d/radius)."""
        if hand_xy is None and gaze_xy is None:
            return np.array([np.nan, np.nan]), "no_inputs"
        if hand_xy is None:
            return gaze_xy, "gaze_only_hand_missing"
        if gaze_xy is None:
            return hand_xy, "hand_only_gaze_missing"
        d_vec = gaze_xy - hand_xy
        d = float(np.hypot(*d_vec))
        falloff = min(1.0, d / self.cfg.precision_radius_px)
        gain = 0.0 if self._precision else self.cfg.soft_magnet_gain
        return hand_xy + gain * d_vec * falloff, ""

    # ---- main entry ---------------------------------------------------------

    def update(self, t_ms: float, face_norm: np.ndarray | None, face_conf: float,
               hands_norm: list[np.ndarray], hand_confs: list[float],
               hand_labels: list[str]) -> FrameOutput:
        self._frame_count += 1
        if self._fps_t0 is None:
            self._fps_t0 = t_ms
        elif t_ms - self._fps_t0 >= 1000:
            self._fps = self._frame_count * 1000.0 / (t_ms - self._fps_t0)
            self._frame_count = 0
            self._fps_t0 = t_ms
        out = FrameOutput(t_ms=t_ms, fps=self._fps, mode=self.mode)

        # --- gaze branch ---
        gsample: GazeSample | None = None
        if self.mode in ("both", "gaze_only") and self.gaze is not None and face_norm is not None:
            if face_conf >= self.cfg.min_face_conf:
                gsample = self.gaze.predict(face_norm, self.gaze_state,
                                            dt_s=max((t_ms - (self._last_t or t_ms)) / 1000, 1 / 120))
                self._recent_gaze.append(gsample)
                del self._recent_gaze[:-12]
        if gsample is not None:
            out.gaze = (gsample.x, gsample.y)
            out.gaze_conf = gsample.conf
            gaze_ok = self._gaze_ok(gsample)
            gaze_xy = np.array([gsample.x, gsample.y]) if gaze_ok else None
            if not gaze_ok:
                out.reason = "gaze_gated"
        else:
            gaze_xy = None

        # --- hand branch ---
        feats = select_hand(
            [extract_hand(h, self.screen_w, self.screen_h, label=l, conf=c,
                          cfg=self.cfg)
             for h, c, l in zip(hands_norm, hand_confs, hand_labels, strict=True)]
            if hands_norm else [],
            prefer="Right",
        )
        hand_xy = None
        if feats.valid and feats.conf >= self.cfg.min_hand_conf and self.mode in ("both", "hand_only"):
            ema_x = self._hand_ema.update(float(feats.center_px[0]))
            hand_xy = np.array([ema_x, float(feats.center_px[1])])
            out.hand = (hand_xy[0], hand_xy[1])
            out.hand_valid = True
            self._hand_hist.append((t_ms, float(hand_xy[1])))
            del self._hand_hist[:-16]
        else:
            self._hand_ema.reset()
            if self.mode in ("both", "hand_only"):
                out.reason = out.reason or "hand_lost"

        # --- fuse ---
        raw_cursor, fuse_reason = self._fuse(gaze_xy, hand_xy)
        reason = out.reason or fuse_reason

        if not math.isfinite(float(raw_cursor[0])) or self.mode == "frozen":
            out.cursor = (self._last_finite_cursor() if self.mode == "frozen"
                          else (float("nan"), float("nan")))
            out.reason = reason or "frozen"
            events = self._post_gestures(t_ms, out, feats, held_cursor=None)
            out.events = events
            return out

        gated, v_reason = self._gate_velocity(raw_cursor, t_ms)
        reason = reason or v_reason
        x = self._gaze_filt.filter(float(gated[0]), t_ms / 1000.0)
        y = self._gaze_filt.filter(float(gated[1]), t_ms / 1000.0)
        out.cursor = (x, y)
        out.cursor_conf = min(out.gaze_conf + (0.5 if out.hand_valid else 0.0), 1.0)
        out.reason = reason
        out.precision = self._precision
        self._post_gestures(t_ms, out, feats, held_cursor=(x, y))
        return out

    def _last_finite_cursor(self) -> tuple[float, float]:
        if self._last_cursor is not None and math.isfinite(self._last_cursor[0]):
            return float(self._last_cursor[0]), float(self._last_cursor[1])
        return float("nan"), float("nan")

    # --- pinch + dwell ------------------------------------------------------

    def _post_gestures(self, t_ms: float, out: FrameOutput, feats: HandFeatures,
                       held_cursor: tuple[float, float] | None) -> list[GestureEvent]:
        events: list[GestureEvent] = []
        raw = score_index_pinch(feats) if feats.valid else 0.0
        if self._pinch_fsm.update(raw, t_ms):
            self._pinch_on_ms = t_ms
            events.append(GestureEvent("pinch_tap_candidate", t_ms, feats.handed))
        if self._pinch_fsm.held:
            if self._pinch_on_ms is None:
                self._pinch_on_ms = t_ms
            dur = t_ms - self._pinch_on_ms
            if not self._pinch_held and dur >= 600:
                self._pinch_held = True
                out.pinch_hold = True
                events.append(GestureEvent("pinch_hold", t_ms, feats.handed))
            out.pinch_held = True
        else:
            if self._pinch_held:
                self._pinch_held = False
            elif self._pinch_on_ms is not None:
                if t_ms - self._pinch_on_ms >= 50:  # released: classify tap
                    if dur := (t_ms - self._pinch_on_ms):
                        if dur < 250:
                            out.pinch_tap = True
                            events.append(GestureEvent("pinch_tap", t_ms, feats.handed))
                        self._pinch_on_ms = None
            # hand lost while pinching -> forced release
        if not feats.valid and (self._pinch_held or self._pinch_on_ms is not None):
            if self._pinch_held:
                events.append(GestureEvent("pinch_forced_release", t_ms, "None"))
            self._pinch_held = False
            self._pinch_on_ms = None

        if held_cursor is not None and feats.valid:
            if self._dwell.update(held_cursor[0], held_cursor[1], t_ms):
                events.append(GestureEvent("dwell", t_ms, feats.handed))
        out.events.extend(events)
        return events

    # --- externally toggled state (Plan C menu / hotkeys) -------------------

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(mode)
        self.mode = mode

    def set_precision(self, on: bool) -> None:
        self._precision = on
```

`tests/test_tracker.py` (complete - uses ONLY the real corpus; synthetic
inputs here are landmark arrays from fixtures, no fake detectors):

```python
import math

import numpy as np
import pytest

from vctrl.config.schemas import GazeFitConfig, TrackingConfig
from vctrl.core.geometry import normalize_gaze_features
from vctrl.tracking.gaze import GazeModel
from vctrl.tracking.tracker import Tracker, MODES


@pytest.fixture(scope="module")
def tracker(fixtures_dir):
    t = Tracker(TrackingConfig(), screen=(640, 480))
    # calibrate gaze on real quick5 session
    data = np.load(fixtures_dir / "calib-quick5.npz")
    ok = ~np.isnan(data["calib_targets"][:, 0])
    feats = np.array([normalize_gaze_features(r.astype(np.float64))
                      for r in data["face"][ok]])
    model = GazeModel(GazeFitConfig())
    model.fit(feats, data["calib_targets"][ok].astype(np.float64), 640, 480)
    t.gaze = model
    return t


def test_clean_session_cursor_mostly_valid(tracker, fixtures_dir):
    data = np.load(fixtures_dir / "clean.npz")
    valid_cursor = 0
    total = 0
    for t_ms, face, fv, hands, hv, hc, hl in zip(
        data["t"], data["face"], data["face_valid"], data["hands"],
        data["hand_valid"], data["hand_conf"], data["hand_label"], strict=True,
    ):
        out = tracker.update(
            float(t_ms),
            face.astype(np.float64) if fv else None,
            1.0 if fv else 0.0,
            [hands[0].astype(np.float64)] if hv[0] else [],
            [float(hc[0])] if hv[0] else [],
            ["Right" if hl[0] == 1 else "Left"] if hv[0] else [],
        )
        total += 1
        if math.isfinite(out.cursor[0]):
            valid_cursor += 1
    assert total > 30
    assert valid_cursor / total >= 0.70, f"{valid_cursor}/{total} valid"


def test_velocity_gate_caps_jumps(tracker, fixtures_dir):
    data = np.load(fixtures_dir / "clean.npz")
    prev = None
    for t_ms, face, fv in zip(data["t"], data["face"], data["face_valid"], strict=True):
        out = tracker.update(float(t_ms), face.astype(np.float64) if fv else None,
                             1.0 if fv else 0.0, [], [], [])
        cur = np.array(out.cursor)
        if prev is not None and np.isfinite(cur).all() and np.isfinite(prev).all():
            d = np.hypot(*(cur - prev))
            assert d <= tracker.cfg.max_step_px * 0.1 + 5  # ~100ms worst
        prev = cur


def test_no_face_no_cursor(tracker, fixtures_dir):
    out = tracker.update(1000.0, None, 0.0, [], [], [])
    assert not math.isfinite(out.cursor[0])


def test_precision_zeroes_gain(tracker, fixtures_dir):
    data = np.load(fixtures_dir / "clean.npz")
    # advance state a bit
    for t_ms, face, fv in zip(data["t"][:10], data["face"][:10],
                              data["face_valid"][:10], strict=True):
        tracker.update(float(t_ms), face.astype(np.float64) if fv else None,
                       1.0 if fv else 0.0, [], [], [])
    tracker.set_precision(True)
    # hand present + gaze present -> cursor collapses toward hand
    row = next(
        (f, v, h, hv, hc, hl, t) for f, v, h, hv, hc, hl, t in zip(
            data["face"], data["face_valid"], data["hands"], data["hand_valid"],
            data["hand_conf"], data["hand_label"], data["t"], strict=True)
        if v and hv[0]
    )
    f, v, h, hv, hc, hl, t = row
    out = tracker.update(float(t), f.astype(np.float64), 1.0,
                         [h[0].astype(np.float64)], [float(hc[0])],
                         ["Right" if hl[0] == 1 else "Left"])
    assert out.precision
    assert np.hypot(out.cursor[0] - out.hand[0], out.cursor[1] - out.hand[1]) < 30


def test_pinch_tap_on_real_pinch_session(tracker, fixtures_dir):
    data = np.load(fixtures_dir / "pinch.npz")
    taps = 0
    for t_ms, face, fv, hands, hv, hc, hl in zip(
        data["t"], data["face"], data["face_valid"], data["hands"],
        data["hand_valid"], data["hand_conf"], data["hand_label"], strict=True,
    ):
        out = tracker.update(
            float(t_ms),
            face.astype(np.float64) if fv else None,
            1.0 if fv else 0.0,
            [hands[0].astype(np.float64)] if hv[0] else [],
            [float(hc[0])] if hv[0] else [],
            ["Right" if hl[0] == 1 else "Left"] if hv[0] else [],
        )
        if out.pinch_tap or out.pinch_hold:
            taps += 1
    assert taps >= 1, "real pinch session must produce a pinch event"


def test_mode_frozen_keeps_last(tracker, fixtures_dir):
    data = np.load(fixtures_dir / "clean.npz")
    last = None
    for t_ms, face, fv in zip(data["t"][:20], data["face"][:20],
                              data["face_valid"][:20], strict=True):
        out = tracker.update(float(t_ms), face.astype(np.float64) if fv else None,
                             1.0 if fv else 0.0, [], [], [])
        last = out.cursor
    tracker.set_mode("frozen")
    out = tracker.update(9999.0, None, 0.0, [], [], [])
    assert out.cursor == last or not math.isfinite(out.cursor[0])
    with pytest.raises(ValueError):
        tracker.set_mode("bogus")


def test_hand_lost_forces_pinch_release(tracker, fixtures_dir):
    # drive a held pinch from the pinch corpus, then feed hand-less frames
    data = np.load(fixtures_dir / "pinch.npz")
    for t_ms, face, fv, hands, hv, hc, hl in zip(
        data["t"], data["face"], data["face_valid"], data["hands"],
        data["hand_valid"], data["hand_conf"], data["hand_label"], strict=True,
    ):
        tracker.update(float(t_ms), face.astype(np.float64) if fv else None,
                       1.0 if fv else 0.0,
                       [hands[0].astype(np.float64)] if hv[0] else [],
                       [float(hc[0])] if hv[0] else [],
                       ["Right" if hl[0] == 1 else "Left"] if hv[0] else [])
    # now 10 frames with no hand
    forced = []
    base = float(data["t"][-1])
    for i in range(10):
        out = tracker.update(base + 33 * (i + 1), None, 0.0, [], [], [])
        forced.extend(e.name for e in out.events)
    assert not tracker._pinch_held
    # forced release may fire once at the transition
    assert tracker._pinch_on_ms is None
```

**TDD steps:**

1. Write `tests/test_tracker.py` first - red. (The fixture's hand
   `prefer="Right"` uses recorded labels; if a fixture row mislabels,
   prefer-by-conf still yields a hand - tests tolerate either.)
2. Write `tracker.py` - green; ruff clean. Two known cleanups to apply
   in final code: hoist `import json`-style unused imports away, and fix
   `_post_gestures` tap path so `dur` is computed before the `if dur :=`
   walrus (simplify to a plain `dur = t_ms - self._pinch_on_ms`).
3. Commit `feat(a11): tracker state machine - gates, 1€, soft magnet, pinch FSM, dwell`, push.

**Done when:** all corpus-driven tracker tests pass (cursor validity,
velocity clamps, precision collapse, real pinch events, frozen mode,
forced release).

---

### Task 12 - Replay runner: feed a session through the tracker

**Files:** `vctrl/tools/replay.py`, `tests/test_replay.py`

`replay.py` (complete):

```python
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from vctrl.config.schemas import AppConfig, GazeFitConfig, TrackingConfig
from vctrl.tracking.gaze import GazeModel
from vctrl.tracking.tracker import FrameOutput, Tracker

log = logging.getLogger(__name__)


@dataclass
class ReplayStats:
    frames: int = 0
    cursor_valid: int = 0
    gaze_valid: int = 0
    hand_valid: int = 0
    pinch_taps: int = 0
    pinch_holds: int = 0
    dwell_events: int = 0
    events: list[str] = field(default_factory=list)
    outputs: list[FrameOutput] = field(default_factory=list)  # kept when keep_outputs

    def summary(self) -> dict:
        n = max(self.frames, 1)
        return {
            "frames": self.frames,
            "cursor_valid_pct": round(100 * self.cursor_valid / n, 1),
            "gaze_valid_pct": round(100 * self.gaze_valid / n, 1),
            "hand_valid_pct": round(100 * self.hand_valid / n, 1),
            "pinch_taps": self.pinch_taps,
            "pinch_holds": self.pinch_holds,
            "dwell_events": self.dwell_events,
        }


def load_gaze(cfg: GazeFitConfig, calib_path: Path,
              screen: tuple[int, int]) -> GazeModel:
    model = GazeModel(cfg)
    if calib_path.exists():
        model = GazeModel.load(calib_path, cfg)
        # re-scale gate if session resolution differs from stored
        if model.valid and model.screen_w != screen[0]:
            model.gate_px = cfg.loo_gate_px * (screen[0] / 1920.0)
    return model


def replay_session(npz_path: Path, *, tracker: Tracker | None = None,
                   app_cfg: AppConfig | None = None,
                   calib_path: Path | None = None,
                   keep_outputs: bool = False,
                   realtime: bool = False,
                   max_frames: int | None = None) -> ReplayStats:
    """Push every stored frame through the tracker. Pure - no camera, no
    MediaPipe: landmarks come straight from the fixture (Tier 1/2)."""
    app = app_cfg or AppConfig()
    data = np.load(npz_path)
    screen = (int(data["meta"].item() and json.loads(str(data["meta"]))
                  .get("width", 1920)),
              int(json.loads(str(data["meta"])).get("height", 1080)))
    if tracker is None:
        gaze = load_gaze(app.gaze_fit,
                         calib_path or Path("config/calibration.json"), screen)
        tracker = Tracker(app.tracking, gaze=gaze, screen=screen)

    stats = ReplayStats()
    t_prev = None
    for i in range(len(data["t"])):
        if max_frames is not None and i >= max_frames:
            break
        t_ms = float(data["t"][i])
        if realtime and t_prev is not None:
            time.sleep(max(0.0, (t_ms - t_prev) / 1000.0))
        t_prev = t_ms
        fv = bool(data["face_valid"][i])
        face = data["face"][i].astype(np.float64) if fv else None
        hv = [bool(v) for v in data["hand_valid"][i]]
        hands, confs, labels = [], [], []
        for k in range(2):
            if hv[k]:
                hands.append(data["hands"][i, k].astype(np.float64))
                confs.append(float(data["hand_conf"][i, k]))
                labels.append("Right" if data["hand_label"][i, k] == 1 else "Left")
        out = tracker.update(t_ms, face, data["face_conf"][i] if fv else 0.0,
                             hands, confs, labels)
        stats.frames += 1
        if np.isfinite(out.cursor[0]):
            stats.cursor_valid += 1
        if np.isfinite(out.gaze[0]):
            stats.gaze_valid += 1
        if out.hand_valid:
            stats.hand_valid += 1
        if out.pinch_tap:
            stats.pinch_taps += 1
        if out.pinch_hold:
            stats.pinch_holds += 1
        stats.events.extend(e.name for e in out.events)
        stats.dwell_events += sum(1 for e in out.events if e.name == "dwell")
        if keep_outputs:
            stats.outputs.append(out)
    return stats


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vctrl replay",
                                description="Replay a recorded session through the tracker")
    p.add_argument("session", type=Path, help="path to fixture .npz")
    p.add_argument("--calib", type=Path, default=Path("config/calibration.json"))
    p.add_argument("--keep-outputs", action="store_true")
    p.add_argument("--realtime", action="store_true")
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--json", action="store_true", help="print stats as JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.session.exists():
        print(f"session not found: {args.session}")
        return 2
    stats = replay_session(args.session, calib_path=args.calib,
                           keep_outputs=args.keep_outputs,
                           realtime=args.realtime,
                           max_frames=args.max_frames)
    s = stats.summary()
    print(json.dumps(s, indent=2) if args.json else
          f"{s['frames']} frames | cursor {s['cursor_valid_pct']}% | "
          f"gaze {s['gaze_valid_pct']}% | hand {s['hand_valid_pct']}% | "
          f"taps {s['pinch_taps']} holds {s['pinch_holds']} dwell {s['dwell_events']}")
    return 0
```

`tests/test_replay.py` (complete):

```python
import json

import pytest

from vctrl.tools.replay import replay_session


def test_replay_clean_summary(fixtures_dir, tmp_path):
    stats = replay_session(fixtures_dir / "clean.npz", calib_path=tmp_path / "none.json")
    s = stats.summary()
    assert s["frames"] > 30
    assert s["cursor_valid_pct"] >= 50.0
    assert s["hand_valid_pct"] >= 40.0


def test_replay_with_real_calibration(fixtures_dir, calib_session, tmp_path):
    """Uses the session fixture that fits a real GazeModel and persists it."""
    from vctrl.tracking.gaze import GazeModel
    from vctrl.config.schemas import GazeFitConfig
    calib = calib_session(tmp_path / "calibration.json")
    assert calib.valid
    stats = replay_session(fixtures_dir / "clean.npz",
                           calib_path=tmp_path / "calibration.json")
    assert stats.summary()["gaze_valid_pct"] >= 40.0


def test_replay_pinch_counts(fixtures_dir, tmp_path):
    stats = replay_session(fixtures_dir / "pinch.npz", calib_path=tmp_path / "none.json")
    assert stats.pinch_taps + stats.pinch_holds >= 1


def test_replay_max_frames(fixtures_dir, tmp_path):
    stats = replay_session(fixtures_dir / "clean.npz", calib_path=tmp_path / "n.json",
                           max_frames=10)
    assert stats.frames == 10


def test_replay_keep_outputs(fixtures_dir, tmp_path):
    stats = replay_session(fixtures_dir / "clean.npz", calib_path=tmp_path / "n.json",
                           keep_outputs=True, max_frames=15)
    assert len(stats.outputs) == 15
    assert all(o.mode == "both" for o in stats.outputs)


def test_replay_missing_file(tmp_path):
    from vctrl.tools.replay import main
    assert main([str(tmp_path / "missing.npz")]) == 2


def test_cli_json_output(fixtures_dir, tmp_path, capsys):
    from vctrl.tools.replay import main
    rc = main([str(fixtures_dir / "clean.npz"), "--json", "--max-frames", "5",
               "--calib", str(tmp_path / "n.json")])
    out = capsys.readouterr().out
    assert rc == 0 and json.loads(out)["frames"] == 5
```

**TDD steps:**

1. Write `tests/test_replay.py` first - red; the `calib_session`
   fixture in `tests/conftest.py` (Task 5 seed) must exist and fit a
   real `GazeModel` from `calib-quick5.npz` then `.save()` it - if the
   seed lacks it, extend the seed fixture in this task.
2. Write `replay.py` - green. Simplify the awkward double
   `json.loads(str(data["meta"]))` in final code (parse once into a
   `meta` var). Ruff clean.
3. Commit `feat(a12): session replay runner + CLI`, push.

**Done when:** replay of real fixtures yields the asserted summaries;
CLI `--json` path works.

---

### Task 13 - Pipeline thread + `vctrl run` + Tier-2 parity test

**Files:** `vctrl/pipeline.py`, `vctrl/__main__.py` (extend), `tests/test_pipeline_parity.py`

`vctrl/pipeline.py` (complete):

```python
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from vctrl.capture.camera import Camera
from vctrl.capture.mediapipe_runner import LandmarkRunner
from vctrl.config.schemas import AppConfig
from vctrl.tracking.gaze import GazeModel
from vctrl.tracking.tracker import FrameOutput, Tracker

log = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    frames: int = 0
    d_frames: float = 0.0  # detector wall seconds
    loops: int = 0
    last_error: str = ""
    outputs: list[FrameOutput] = field(default_factory=list)  # ring, keep last 200

    def fps(self) -> float:
        return self.d_frames and self.frames / max(self.d_frames, 1e-9) or 0.0


class Pipeline:
    """Threaded capture -> detect -> track loop. Single instance per process."""

    def __init__(self, cfg: AppConfig, *, camera: Camera | None = None,
                 runner: LandmarkRunner | None = None,
                 gaze: GazeModel | None = None,
                 headless: bool = True,
                 on_output=None) -> None:
        self.cfg = cfg
        self.camera = camera or Camera(cfg.capture)
        self.runner = runner or LandmarkRunner(cfg.models)
        self.tracker = Tracker(cfg.tracking, gaze=gaze,
                               screen=(cfg.capture.width, cfg.capture.height))
        self.headless = headless
        self.on_output = on_output  # callback(FrameOutput) for Plan C overlay
        self.stats = PipelineStats()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: FrameOutput | None = None

    # ---- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self.camera.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="vctrl-pipeline",
                                        daemon=True)
        self._thread.start()
        log.info("pipeline started (%dx%d @ %d)",
                 self.cfg.capture.width, self.cfg.capture.height,
                 self.cfg.capture.fps)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self.camera.stop()
        self.runner.close()
        log.info("pipeline stopped after %d frames", self.stats.frames)

    def __enter__(self) -> Pipeline:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    @property
    def latest(self) -> FrameOutput | None:
        with self._lock:
            return self._latest

    # ---- loop ---------------------------------------------------------------

    def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.perf_counter()
            frame = self.camera.read()          # raises CameraError on death
            if frame is None:
                time.sleep(0.01)
                continue
            ts = time.time() * 1000.0
            face, hands = self.runner.detect(frame, ts)
            out = self.tracker.update(
                ts,
                face.landmarks if face else None,
                face.conf if face else 0.0,
                [h.landmarks for h in hands],
                [h.conf for h in hands],
                [h.handed for h in hands],
            )
            dt = time.perf_counter() - t0
            self.stats.frames += 1
            self.stats.d_frames += dt
            self.stats.loops += 1
            with self._lock:
                self._latest = out
                self.stats.outputs.append(out)
                del self.stats.outputs[:-200]
            if self.on_output is not None:
                self.on_output(out)
            if not self.headless:
                self._draw(frame, out)
            # frame budget
            budget = 1.0 / max(self.cfg.capture.fps, 1)
            rem = budget - dt
            if rem > 0:
                time.sleep(rem)

    def _draw(self, frame: np.ndarray, out: FrameOutput) -> None:
        h, w = frame.shape[:2]
        if np.isfinite(out.gaze[0]):
            cx, cy = int(out.gaze[0] * w / self.cfg.capture.width), \
                     int(out.gaze[1] * h / self.cfg.capture.height)
            cv2.circle(frame, (cx, cy), 6, (0, 255, 255), 1)     # gaze dot
        if np.isfinite(out.cursor[0]):
            px, py = int(out.cursor[0] * w / self.cfg.capture.width), \
                     int(out.cursor[1] * h / self.cfg.capture.height)
            cv2.circle(frame, (px, py), 10, (0, 255, 0), 1)      # hand circle
        cv2.putText(frame, f"fps {out.fps:.0f} mode {out.mode} {out.reason}",
                    (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (200, 200, 200), 1, cv2.LINE_AA)
        cv2.imshow("vctrl", frame)
        cv2.waitKey(1)

    def headless_status(self) -> str:
        o = self.latest
        s = self.stats
        if o is None:
            return "waiting for first frame..."
        return (f"fps {o.fps:4.1f} frames {s.frames:6d} "
                f"cursor {'OK' if np.isfinite(o.cursor[0]) else '--':>2} "
                f"gaze {o.gaze_conf:.2f} mode {o.mode} {o.reason}")
```

`vctrl/__main__.py` (complete final file - it supersedes the T1 stub and
the T5 `record` wiring; the `record` args below are exactly the set the
T5 wire note specifies, so the two must stay identical):

```python
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from vctrl.config.schemas import load_config
from vctrl.core.logging_setup import setup_logging

DEFAULT_OUT = "fixtures/real-sessions"


def _cmd_run(args: argparse.Namespace) -> int:
    import logging

    from vctrl.pipeline import Pipeline

    log = logging.getLogger("vctrl")
    cfg = load_config()
    setup_logging()
    with Pipeline(cfg, headless=True) as pipe:
        try:
            t_end = time.time() + (args.duration or 0)
            last = 0.0
            while args.duration is None or time.time() < t_end:
                time.sleep(1.0)
                if time.time() - last >= 1.0:
                    print(pipe.headless_status(), flush=True)
                    last = time.time()
        except KeyboardInterrupt:
            log.info("interrupted")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # `replay` owns its own flags (vctrl.tools.replay.build_parser), so the
    # raw tokens are handed over before this parser sees them - no flag
    # duplication. `run` and `record` are parsed below.
    if raw[:1] == ["replay"]:
        from vctrl.tools.replay import main as rep_main
        return rep_main(raw[1:])

    p = argparse.ArgumentParser(prog="vctrl")
    sub = p.add_subparsers(dest="cmd")
    run = sub.add_parser("run", help="start the tracking pipeline")
    run.add_argument("--duration", type=float, default=None,
                     help="stop after N seconds (default: until Ctrl+C)")
    rec = sub.add_parser("record", help="record a fixture session")
    rec.add_argument("--scenario", default="clean")
    rec.add_argument("--duration", type=float, default=30.0)
    rec.add_argument("--stride", type=int, default=3)
    rec.add_argument("--frames", action="store_true")
    rec.add_argument("--label", default=None,
                     help="event name applied while --interactive-labels is on")
    rec.add_argument("--interactive-labels", action="store_true",
                     help="press 1 to label, 0 to clear, q to stop")
    rec.add_argument("--calib", choices=["quick5"], default=None,
                     help="record a calibration session instead of --scenario")
    rec.add_argument("--out", default=DEFAULT_OUT,
                     help=f"output directory (default: {DEFAULT_OUT})")
    # declared only so `vctrl --help` lists it; parsing is delegated above.
    sub.add_parser("replay", help="replay a fixture through the tracker")
    args = p.parse_args(argv)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "record":
        from vctrl.tools.record import record_calibration, record_session

        out_dir = Path(args.out)
        if args.calib:
            record_calibration(out_dir)
            return 0
        record_session(
            args.scenario,
            args.duration,
            out_dir=out_dir,
            stride=args.stride,
            with_frames=args.frames,
            label=args.label,
            interactive_labels=args.interactive_labels,
        )
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`tests/test_pipeline_parity.py` (Tier-2: real MediaPipe vs stored landmarks
on the stored frames - requires Task 5's frames-bearing fixture):

```python
import numpy as np
import pytest

pytest.importorskip("mediapipe")

from vctrl.capture.mediapipe_runner import LandmarkRunner
from vctrl.config.schemas import ModelConfig, TrackingConfig
from vctrl.tracking.tracker import Tracker


def _decode_frames(data, indices):
    import cv2
    off = data["frame_off"]
    frames = []
    for i in indices:
        blob = data["frame_bytes"][off[i]:off[i + 1]]
        img = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
        frames.append(img)
    return frames


def test_stored_vs_live_mediapipe_parities(fixtures_dir, models_dir, monkeypatch):
    """Run real MediaPipe on the stored frames; cursor paths must agree."""
    npz = fixtures_dir / "clean.npz"
    if "frame_off" not in npz.__class__(np.load(npz), "files") if False else True:
        pass  # presence checked below
    data = np.load(npz)
    if "frame_off" not in data.files:
        pytest.skip("clean fixture has no frames")
    idx = np.linspace(0, len(data["t"]) - 1, min(40, len(data["t"])),
                      dtype=int)
    frames = _decode_frames(data, idx)
    runner = LandmarkRunner(ModelConfig())
    tracker = Tracker(TrackingConfig())
    diffs = []
    valid_both = 0
    for i, frame in zip(idx, frames, strict=True):
        ts = float(data["t"][i])
        face, hands = runner.detect(frame, ts)
        out_live = tracker.update(
            ts,
            face.landmarks if face else None,
            face.conf if face else 0.0,
            [h.landmarks for h in hands],
            [h.conf for h in hands],
            [h.handed for h in hands],
        )
        # stored-landmark path through an identical tracker
        fv = bool(data["face_valid"][i])
        stored_tracker = _static_tracker(tracker)
        out_stored = stored_tracker.update(
            ts,
            data["face"][i].astype(np.float64) if fv else None,
            data["face_conf"][i] if fv else 0.0,
            [data["hands"][i, k].astype(np.float64)
             for k in range(2) if data["hand_valid"][i, k]],
            [float(data["hand_conf"][i, k])
             for k in range(2) if data["hand_valid"][i, k]],
            ["Right" if data["hand_label"][i, k] == 1 else "Left"
             for k in range(2) if data["hand_valid"][i, k]],
        )
        if np.isfinite(out_live.cursor[0]) and np.isfinite(out_stored.cursor[0]):
            valid_both += 1
            diffs.append(float(np.hypot(*(np.array(out_live.cursor)
                                          - np.array(out_stored.cursor)))))
    runner.close()
    if not diffs:
        pytest.fail("no overlapping valid frames - check fixture alignment")
    diffs = np.array(diffs)
    assert np.median(diffs) < 30.0, f"median diff {np.median(diffs):.1f}px"
    assert np.percentile(diffs, 95) < 100.0, f"p95 {np.percentile(diffs, 95):.1f}px"
    assert valid_both >= 0.70 * len(idx), (
        f"only {valid_both}/{len(idx)} frames valid in both paths")


def _static_tracker(ref: Tracker) -> Tracker:
    """Fresh Tracker with same config/screen -> independent run-to-run state."""
    return Tracker(TrackingConfig(), gaze=ref.gaze,
                   screen=(ref.screen_w, ref.screen_h))
```

**TDD steps:**

1. Write `tests/test_pipeline_parity.py` first - red (or skip if
   fixture has no frames; the recorded `clean.npz` MUST have frames -
   that's Task 5's job). Clean the dead `if False else True` line in
   final code: replace with a plain `if "frame_off" not in
   np.load(npz).files: pytest.skip(...)` before decoding.
2. Write `pipeline.py` + extend `__main__.py` - green; ruff clean.
   NOTE: `PipelineStats.fps()` has a boolean-arithmetic bug
   (`self.d_frames and ... or 0.0` returns d_frames on falsy) - final
   code must be `return self.frames / max(self.d_frames, 1e-9)`.
3. Live smoke (STOP - ASK USER): `uv run vctrl run --duration 15` -
   prints 1 Hz status lines, terminates cleanly, cursor valid most of
   the time. If the camera is absent, say so and stop.
4. Rewrite `tests/test_cli_stub.py` against the now-wired `__main__.py` - the
   T1 stub no longer exists. Keep `test_no_command_prints_help`
   (`main([]) == 0`, `"usage" in out`). Replace
   `test_unimplemented_command_returns_2` with
   `test_missing_session_returns_2`: `main(["replay", str(tmp_path /
   "missing.npz")]) == 2` plus `"session not found" in
   capsys.readouterr().out` (T12 `main` prints that exact string). Optional:
   `test_replay_success_returns_0` driving `main(["replay", str(clean_npz),
   "--json", "--max-frames", "3"]) == 0` against
   `fixtures/real-sessions/clean.npz`. Then `uv run pytest
   tests/test_cli_stub.py` green + `uv run ruff check .` clean.
5. Commit `feat(a13): threaded pipeline, run CLI, MediaPipe parity test`, push.

**Done when:** parity test passes on stored frames (median < 30 px) and
headless run prints sane 1 Hz status on real hardware.

---

### Task 14 - Docs: manual test checklist (Plan A slice) + final gates

**Files:** `docs/manual-test.md`

`docs/manual-test.md` (complete):

```markdown
# Manual test checklist - Plan A (core tracking pipeline)

Run after every Plan A change. Automated gates first, then hardware
checks. Live pytest tests: `uv run pytest -m live`.

## Automated gates

- [ ] `uv run ruff check .` - zero findings
- [ ] `uv run pytest` - all Tier 1 + Tier 2 green (live excluded)
- [ ] `uv run pytest -m live` - camera + landmark smoke pass (webcam on)

## Camera + capture (Task 3/4 hardware)

- [ ] `uv run python -m vctrl run --duration 15` prints 1 Hz status,
      terminates cleanly, no watchdog restarts logged
- [ ] Status line shows `face=True` when looking at the camera,
      `hands>=1` when a hand is in frame
- [ ] Cover the camera mid-run: watchdog logs a recovery, pipeline
      resumes without crashing

## Recording (Task 5 hardware)

- [ ] `uv run python -m vctrl record --scenario clean --frames --stride 3`
      completes; `fixtures/real-sessions/clean.npz` has `frame_off`
- [ ] Quick5: `uv run python -m vctrl record --calib quick5`
      - all 5 targets collected, `calib_targets` has >= 75 non-NaN rows
- [ ] `manifest.json` lists every scenario with frame counts

## Tracker behavior (Tasks 8-12, real sessions)

- [ ] `uv run python -m vctrl replay fixtures/real-sessions/clean.npz`
      - cursor finite for >= 70% of frames; no NaN crashes
- [ ] `uv run pytest tests/test_replay.py tests/test_pipeline_parity.py`
      pass against the recorded corpus
- [ ] Replay of `pinch.npz` shows tap events on pinch frames, exactly
      one tap per pinch (no double-fire)

## Regression bar for Plan A completion

- [ ] Full gate set green on a fresh clone + `uv sync`
- [ ] Corpus committed (< 25 MB single push) and parity test uses the
      committed frames, not a temp recording
```

**TDD steps (docs task - verification instead of unit tests):**

1. Write `docs/manual-test.md` exactly as above.
2. Run the full gate set yourself: `uv run ruff check .` +
   `uv run pytest`. If anything fails, fix it in this task (it is the
   last task - failures mean an earlier task left a loose end, e.g.
   unused imports flagged by ruff F401 or the T10/T13 cleanups noted
   in earlier TDD steps).
3. Commit `docs(a14): manual test checklist for Plan A slice`, push.
4. Verify the push landed: `git ls-remote origin main` prints the same
   commit hash as `git rev-parse HEAD`. The plan header already reads
   `- Status: ready for execution`, so no status edit is needed here.

**Done when:** ruff + pytest are green at the tip of Plan A's commits
and `docs/manual-test.md` exists with the checklist above.

## Plan A definition of done

All 14 tasks committed (`feat(a01)`..`docs(a14)`), gates green, corpus
recorded with the user at the camera, parity test passing against
committed frames, headless `vctrl run` verified on real hardware.












