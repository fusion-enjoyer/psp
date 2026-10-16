"""Ready-made Deck layouts. "genel" is the default config itself."""
from __future__ import annotations

import shutil
from pathlib import Path

from .. import config

HERE = Path(__file__).resolve().parent
TITLES = {"genel": "Genel (varsayılan)", "yayinci": "Yayıncı (OBS)",
          "gelistirici": "Geliştirici (VS Code)", "muzik": "Müzik"}


def names() -> list[str]:
    return ["genel"] + sorted(p.stem for p in HERE.glob("*.yaml"))


def text(name: str) -> str:
    if name == "genel":
        return config.DEFAULT_YAML
    path = HERE / f"{name}.yaml"
    if name not in names() or not path.exists():
        raise config.ConfigError(f"bilinmeyen profil '{name}' ({', '.join(names())})")
    return path.read_text(encoding="utf-8")


def apply(name: str, target: Path) -> Path | None:
    """Writes the profile over target, keeping the old file as deck.yaml.bak.
    Returns the backup path (None when there was nothing to back up)."""
    body = text(name)
    config.normalize(config.yaml.safe_load(body))  # never write a broken profile
    backup = None
    if target.exists():
        backup = target.with_name(target.name + ".bak")
        shutil.copy2(target, backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".yaml.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(target)
    return backup
