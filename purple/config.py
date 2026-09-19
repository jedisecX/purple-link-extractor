from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULTS = {
    "database": "purple.db",
    "import": {
        "recursive": False,
        "batch_size": 1000,
        "accepted_schemes": ["http", "https"],
    },
    "output": {"directory": "./output"},
    "logging": {"level": "INFO"},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class ImportConfig:
    recursive: bool = False
    batch_size: int = 1000
    accepted_schemes: list[str] = field(default_factory=lambda: ["http", "https"])


@dataclass
class OutputConfig:
    directory: str = "./output"


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class Config:
    database: str = "purple.db"
    import_cfg: ImportConfig = field(default_factory=ImportConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @property
    def db_path(self) -> Path:
        return Path(self.database)


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    data: dict = dict(DEFAULTS)
    candidates = []
    if path:
        candidates.append(Path(path))
    else:
        candidates.extend(
            [
                Path("purple.yaml"),
                Path("purple.yml"),
                Path.cwd() / "purple.yaml",
            ]
        )
    for p in candidates:
        if p.is_file():
            with p.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            data = _merge(data, loaded)
            break
    if overrides:
        data = _merge(data, overrides)

    imp = data.get("import") or {}
    return Config(
        database=str(data.get("database") or "purple.db"),
        import_cfg=ImportConfig(
            recursive=bool(imp.get("recursive", False)),
            batch_size=int(imp.get("batch_size", 1000)),
            accepted_schemes=[s.lower() for s in (imp.get("accepted_schemes") or ["http", "https"])],
        ),
        output=OutputConfig(directory=str((data.get("output") or {}).get("directory") or "./output")),
        logging=LoggingConfig(level=str((data.get("logging") or {}).get("level") or "INFO")),
    )
