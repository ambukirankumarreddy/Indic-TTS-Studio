"""Engine registry."""

import logging
from typing import Dict, List, Optional

from .base import Engine, SynthSettings, Voice, MODELS_DIR  # noqa: F401
from .parler_engine import ParlerEngine
from .sherpa_engines import PiperEngine, KokoroEngine
from .edge_engine import EdgeEngine
from .syspin_engine import SyspinEngine

_log = logging.getLogger(__name__)
_ENGINES: Dict[str, Engine] = {}


def _optional_engine_classes():
    """Engines whose libraries may be absent; failures never break app start-up."""
    classes = []
    try:
        from .voxcpm_engine import VoxCPMEngine
        classes.append(VoxCPMEngine)
    except Exception as e:  # pragma: no cover
        _log.warning("VoxCPM engine unavailable: %s", e)
    return classes


def all_engines() -> List[Engine]:
    if not _ENGINES:
        core = (ParlerEngine, EdgeEngine, PiperEngine, KokoroEngine, SyspinEngine)
        for cls in core + tuple(_optional_engine_classes()):
            e = cls()
            _ENGINES[e.id] = e
    return list(_ENGINES.values())


def get_engine(engine_id: str) -> Optional[Engine]:
    all_engines()
    return _ENGINES.get(engine_id)


def find_voice(key: str) -> Optional[Voice]:
    """key = 'engine_id:voice_id'"""
    if ":" not in key:
        return None
    eid, vid = key.split(":", 1)
    e = get_engine(eid)
    return e.get_voice(vid) if e else None
