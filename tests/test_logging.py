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
