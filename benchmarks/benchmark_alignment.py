"""Benchmark 500-shot pulse analysis and half-height alignment."""

from __future__ import annotations

import argparse
import dataclasses
import gc
import json
import platform
import time
import tracemalloc
from collections import Counter
from importlib.metadata import PackageNotFoundError, version

import numpy as np

from datalab_pulse_characterization.core import (
    PulseProfile,
    PulseSimulationParameters,
    align_pulse_campaign,
    analyze_pulse_campaign,
    simulate_pulse_campaign,
)


@dataclasses.dataclass(frozen=True)
class BenchmarkConfiguration:
    """Campaign size and repetition count for one benchmark report."""

    shot_count: int = 500
    sample_count: int = 501
    repetitions: int = 1
    seed: int = 20260809

    def __post_init__(self) -> None:
        """Reject configurations that cannot exercise the simulator."""
        for name, value in dataclasses.asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if self.shot_count < 2:
            raise ValueError("shot_count must be at least 2")
        if self.sample_count < 21:
            raise ValueError("sample_count must be at least 21")
        if self.repetitions < 1:
            raise ValueError("repetitions must be positive")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")


def _simulation_parameters(
    configuration: BenchmarkConfiguration,
) -> PulseSimulationParameters:
    """Build the representative scenario or a small anomaly-free probe."""
    if configuration.shot_count == 500:
        return PulseSimulationParameters(
            sample_count=configuration.sample_count,
            seed=configuration.seed,
        )
    return PulseSimulationParameters(
        shot_count=configuration.shot_count,
        sample_count=configuration.sample_count,
        jitter_transition_shot=max(1, configuration.shot_count // 2),
        missing_shots=(),
        low_snr_shots=(),
        saturated_shots=(),
        multiple_pulse_shots=(),
        outlier_shots=(),
        seed=configuration.seed,
    )


def _package_version(distribution: str) -> str | None:
    """Return an installed distribution version when metadata is available."""
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def _truth_x50(truth, parameters: PulseSimulationParameters) -> float:
    """Return the commanded rising half-height crossing for one profile."""
    rise_scale = parameters.pulse_width
    if truth.profile is PulseProfile.ASYMMETRIC:
        rise_scale *= parameters.asymmetric_rise_factor
    return truth.center - np.sqrt(2.0 * np.log(2.0)) * rise_scale


def _quality_report(simulation, campaign, alignment) -> dict[str, object]:
    """Measure status fidelity and residual truth-landmark dispersion."""
    aligned_positions = [
        index for index, record in enumerate(alignment.records) if record.aligned
    ]
    raw_truth_x50 = np.array(
        [
            _truth_x50(simulation.truth.shots[index], simulation.parameters)
            for index in aligned_positions
        ]
    )
    aligned_truth_x50 = np.array(
        [
            raw_truth_x50[position] + float(alignment.records[index].shift_x)
            for position, index in enumerate(aligned_positions)
        ]
    )
    raw_std = float(np.std(raw_truth_x50))
    aligned_std = float(np.std(aligned_truth_x50))
    status_counts = Counter(shot.status.value for shot in campaign.shots)
    status_mismatch_count = sum(
        measured.status is not expected.expected_status
        for measured, expected in zip(campaign.shots, simulation.truth.shots)
    )
    return {
        "aligned_shot_count": alignment.aligned_count,
        "alignment_reference_x": alignment.reference_x,
        "raw_truth_x50_std_x": raw_std,
        "aligned_truth_x50_std_x": aligned_std,
        "residual_truth_x50_std_ratio": aligned_std / raw_std if raw_std else 0.0,
        "status_counts": dict(sorted(status_counts.items())),
        "status_mismatch_count": status_mismatch_count,
    }


def run_benchmark(configuration: BenchmarkConfiguration) -> dict[str, object]:
    """Run generation, analysis, and alignment with no pass/fail budget."""
    parameters = _simulation_parameters(configuration)
    generation_elapsed_s = 0.0
    analysis_elapsed_s = 0.0
    alignment_elapsed_s = 0.0
    simulation = campaign = alignment = None

    gc.collect()
    tracemalloc_started = False
    baseline_bytes = peak_bytes = None
    try:
        tracemalloc.start()
        tracemalloc_started = True
        baseline_bytes = tracemalloc.get_traced_memory()[0]
    except (RuntimeError, NotImplementedError):
        tracemalloc_started = False

    try:
        for _ in range(configuration.repetitions):
            started_at = time.perf_counter()
            simulation = simulate_pulse_campaign(parameters)
            generation_elapsed_s += time.perf_counter() - started_at

            started_at = time.perf_counter()
            campaign = analyze_pulse_campaign(
                simulation.acquisitions,
                simulation.analysis_parameters,
            )
            analysis_elapsed_s += time.perf_counter() - started_at

            started_at = time.perf_counter()
            alignment = align_pulse_campaign(simulation.acquisitions, campaign)
            alignment.mean_acquisition(aligned=False)
            alignment.mean_acquisition(aligned=True)
            alignment_elapsed_s += time.perf_counter() - started_at
        if tracemalloc_started:
            peak_bytes = tracemalloc.get_traced_memory()[1]
    finally:
        if tracemalloc_started:
            tracemalloc.stop()

    assert simulation is not None and campaign is not None and alignment is not None
    input_bytes = sum(
        acquisition.x.nbytes + acquisition.y.nbytes
        for acquisition in simulation.acquisitions
    )
    total_elapsed_s = generation_elapsed_s + analysis_elapsed_s + alignment_elapsed_s
    return {
        "benchmark": "pulse-campaign-x50-alignment",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "sigima": _package_version("sigima"),
        "pulse": _package_version("datalab-pulse-characterization"),
        "platform": platform.platform(),
        "configuration": dataclasses.asdict(configuration),
        "input_bytes": input_bytes,
        "generation_elapsed_s_per_run": (
            generation_elapsed_s / configuration.repetitions
        ),
        "analysis_elapsed_s_per_run": analysis_elapsed_s / configuration.repetitions,
        "alignment_elapsed_s_per_run": (
            alignment_elapsed_s / configuration.repetitions
        ),
        "total_elapsed_s_per_run": total_elapsed_s / configuration.repetitions,
        "shots_per_s": (
            configuration.shot_count * configuration.repetitions / total_elapsed_s
        ),
        "peak_incremental_python_bytes": (
            None
            if peak_bytes is None or baseline_bytes is None
            else peak_bytes - baseline_bytes
        ),
        "memory_measurement": (
            "tracemalloc peak after garbage collection; null when unavailable"
        ),
        "quality": _quality_report(simulation, campaign, alignment),
    }


def _parse_arguments() -> BenchmarkConfiguration:
    """Parse explicit benchmark-size overrides."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shot-count", type=int, default=500)
    parser.add_argument("--sample-count", type=int, default=501)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260809)
    arguments = parser.parse_args()
    return BenchmarkConfiguration(
        shot_count=arguments.shot_count,
        sample_count=arguments.sample_count,
        repetitions=arguments.repetitions,
        seed=arguments.seed,
    )


def main() -> None:
    """Print stable JSON suitable for archiving by either Python host."""
    print(json.dumps(run_benchmark(_parse_arguments()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
