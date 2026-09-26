from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)


def load_model[M: BaseModel](
    path: Path, model_type: type[M], defaults: M | None = None
) -> M:
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
