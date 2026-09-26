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
