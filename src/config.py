"""Project configuration and path helpers.

Every other module reads its settings from here, so the notebooks and
``main.py`` always use the same paths, year range and keyword list.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_FILE = "config.yaml"


def find_project_root(start: Path | None = None) -> Path:
    """Return the folder that contains ``data/``.

    Works from the repository root, from ``notebooks/`` and from ``src/``.
    """
    current = (start or Path.cwd()).resolve()

    for candidate in [current, *current.parents]:
        if (candidate / "data").is_dir() and (candidate / CONFIG_FILE).is_file():
            return candidate

    for candidate in [current, *current.parents]:
        if (candidate / "data").is_dir():
            return candidate

    raise FileNotFoundError("Could not find the project root (no data/ folder found)")


@dataclass(frozen=True)
class Paths:
    """Absolute paths to the three data layers."""

    root: Path
    raw: Path
    interim: Path
    processed: Path

    def ensure(self) -> "Paths":
        """Create the interim and processed folders if they do not exist."""
        self.interim.mkdir(parents=True, exist_ok=True)
        self.processed.mkdir(parents=True, exist_ok=True)
        return self


def load_config(root: Path | None = None) -> dict:
    """Load ``config.yaml`` and add the resolved project root under ``root``."""
    project_root = Path(root).resolve() if root else find_project_root()
    config_path = project_root / CONFIG_FILE

    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    config["root"] = project_root
    return config


def get_paths(config: dict) -> Paths:
    """Build the :class:`Paths` object described by ``config['paths']``."""
    root = Path(config["root"])
    paths = config.get("paths", {})

    return Paths(
        root=root,
        raw=root / paths.get("raw", "data/raw"),
        interim=root / paths.get("interim", "data/interim"),
        processed=root / paths.get("processed", "data/processed"),
    )


def year_range(config: dict) -> tuple[int, int]:
    """Return the ``(min_year, max_year)`` accepted by the schema."""
    years = config.get("years", {})
    return int(years.get("min", 2023)), int(years.get("max", 2026))


def technology_terms(config: dict) -> list[str]:
    """Return the shared technology keyword list."""
    return list(config.get("technology_filter", {}).get("terms", []))
