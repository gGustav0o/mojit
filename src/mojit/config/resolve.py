"""Pure precedence and source-relative path resolution."""

from __future__ import annotations

import os
from pathlib import Path

from mojit.config.models import (
    DEFAULT_EFFECT,
    DEFAULT_FONT,
    DEFAULT_FPS,
    DEFAULT_MARGIN,
    DEFAULT_ORIENTATION,
    DEFAULT_SCENE,
    DEFAULT_SEED,
    ConfigOverrides,
    ConfigValidationError,
    ResolvedConfig,
)


def _absolute_path(value: str | Path, *, base: Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    return Path(os.path.normpath(candidate))


def resolve_config(
    cli: ConfigOverrides,
    file: ConfigOverrides,
    *,
    cwd: Path,
    config_dir: Path | None,
    debug: bool = False,
) -> ResolvedConfig:
    """Resolve CLI, file, and default values without reading external state."""
    if not isinstance(cwd, Path) or not cwd.is_absolute():
        raise ConfigValidationError("cwd must be an absolute Path")
    if config_dir is not None and (
        not isinstance(config_dir, Path) or not config_dir.is_absolute()
    ):
        raise ConfigValidationError("config_dir must be an absolute Path")

    if cli.font is not None:
        font = _absolute_path(cli.font, base=cwd)
    elif file.font is not None:
        if config_dir is None:
            raise ConfigValidationError("config_dir is required for a config font path")
        font = _absolute_path(file.font, base=config_dir)
    else:
        font = DEFAULT_FONT

    effect = cli.effect if cli.effect is not None else file.effect
    orientation = cli.orientation if cli.orientation is not None else file.orientation
    fps = cli.fps if cli.fps is not None else file.fps
    margin = cli.margin if cli.margin is not None else file.margin
    seed = cli.seed if cli.seed is not None else file.seed
    scene = cli.scene if cli.scene is not None else file.scene
    scene_layers = None if cli.scene is not None else file.scene_layers

    return ResolvedConfig(
        effect=effect if effect is not None else DEFAULT_EFFECT,
        orientation=orientation if orientation is not None else DEFAULT_ORIENTATION,
        font=font,
        fps=fps if fps is not None else DEFAULT_FPS,
        margin=margin if margin is not None else DEFAULT_MARGIN,
        seed=seed if seed is not None else DEFAULT_SEED,
        scene=scene if scene is not None else DEFAULT_SCENE,
        scene_layers=scene_layers,
        debug=debug,
    )
