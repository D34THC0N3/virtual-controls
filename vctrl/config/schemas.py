from __future__ import annotations

from pydantic import BaseModel, Field


class CameraConfig(BaseModel):
    device: int = Field(default=0, ge=0)
    width: int = Field(default=640, gt=0)
    height: int = Field(default=480, gt=0)
    fps: int = Field(default=30, gt=0)
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
    cursor: SignalFilterConfig = Field(
        default_factory=lambda: SignalFilterConfig(min_cutoff=1.2, beta=0.01)
    )


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
