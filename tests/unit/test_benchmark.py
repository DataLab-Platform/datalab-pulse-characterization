"""Tests for the explicit pulse benchmark harness."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from benchmarks.benchmark_alignment import BenchmarkConfiguration, run_benchmark

ROOT = Path(__file__).parents[2]
EXPECTED_WHEEL_HASHES = {
    "pulse_wheel_sha256": (
        "785db2cc3abbe2c4c496516ccd34996af37ac764d8f568a6a14608e81bbc0a0f"
    ),
    "sigima_wheel_sha256": (
        "2264d7d32411a03bbe51269b3a448a7c78ede6e92ec6c1caedb1526974f09ae7"
    ),
}


def test_small_benchmark_reports_time_memory_quality_and_truth() -> None:
    """The harness measures a complete run without imposing a host budget."""
    report = run_benchmark(
        BenchmarkConfiguration(
            shot_count=12,
            sample_count=101,
            repetitions=1,
            seed=17,
        )
    )

    assert report["configuration"] == {
        "shot_count": 12,
        "sample_count": 101,
        "repetitions": 1,
        "seed": 17,
    }
    assert report["input_bytes"] == 12 * 101 * 2 * 8
    assert report["generation_elapsed_s_per_run"] > 0.0
    assert report["analysis_elapsed_s_per_run"] > 0.0
    assert report["alignment_elapsed_s_per_run"] > 0.0
    assert report["total_elapsed_s_per_run"] > 0.0
    assert report["shots_per_s"] > 0.0
    assert report["peak_incremental_python_bytes"] > 0
    assert report["pulse"] == "0.1.0"
    quality = report["quality"]
    assert quality["aligned_shot_count"] == 12
    assert quality["status_counts"] == {"VALID": 12}
    assert quality["status_mismatch_count"] == 0
    assert quality["aligned_truth_x50_std_x"] <= quality["raw_truth_x50_std_x"]


@pytest.mark.parametrize(
    ("filename", "backend"),
    [
        ("cpython-windows-2026-08-09.json", "cpython"),
        ("pyodide-browser-2026-08-09.json", "pyodide_browser_main_thread"),
    ],
)
def test_archived_500_shot_reports_are_strict_and_scientifically_consistent(
    filename: str,
    backend: str,
) -> None:
    """Checked-in evidence retains its host identity and truth checks."""
    report = json.loads((ROOT / "benchmarks" / "results" / filename).read_text())

    assert report["benchmark"] == "pulse-campaign-x50-alignment"
    assert report["backend"] == backend
    assert report["configuration"] == {
        "repetitions": 1,
        "sample_count": 501,
        "seed": 20260809,
        "shot_count": 500,
    }
    assert report["pulse"] == "0.1.0"
    assert report["sigima"] == "1.1.6"
    assert report["quality"]["aligned_shot_count"] == 489
    assert report["quality"]["status_mismatch_count"] == 0
    assert report["quality"]["residual_truth_x50_std_ratio"] < 0.1
    assert len(report["pulse_wheel_sha256"]) == 64
    assert len(report["sigima_wheel_sha256"]) == 64
    if backend == "pyodide_browser_main_thread":
        assert report["pyodide_version"] == "0.26.4"


def test_archived_reports_share_exact_wheel_provenance() -> None:
    """Both host observations identify the same immutable wheel artifacts."""
    reports = [
        json.loads((ROOT / "benchmarks" / "results" / filename).read_text())
        for filename in (
            "cpython-windows-2026-08-09.json",
            "pyodide-browser-2026-08-09.json",
        )
    ]

    for report in reports:
        measured_at = datetime.fromisoformat(
            report["measured_at"].replace("Z", "+00:00")
        )
        assert measured_at.utcoffset() is not None
        assert {
            key: report[key] for key in EXPECTED_WHEEL_HASHES
        } == EXPECTED_WHEEL_HASHES
