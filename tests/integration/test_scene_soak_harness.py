from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_scene_soak_harness_samples_the_renderer_process_without_a_leak_threshold() -> None:
    result = subprocess.run(
        (
            sys.executable,
            str(PROJECT_ROOT / "tools" / "scene_soak.py"),
            "--duration-seconds",
            "1.0",
            "--sample-interval-seconds",
            "0.2",
            "--warmup-frames",
            "2",
            "--width",
            "160",
            "--height",
            "90",
        ),
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=15.0,
    )
    metrics = json.loads(result.stdout)

    assert metrics["process_id"] != os.getpid()
    assert metrics["rendered_frames"] > 1
    assert len(metrics["samples"]) >= 5
    assert metrics["peak_working_set_bytes"] > 0
    assert metrics["peak_private_bytes"] > 0
    assert "tail_private_slope_bytes_per_second" in metrics
