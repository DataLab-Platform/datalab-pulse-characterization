"""Run the Pulse benchmark from the local Pulse and Sigima wheels."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PULSE_ROOT = HERE.parent
DEV_ROOT = PULSE_ROOT.parent
SIGIMA_ROOT = Path(os.environ.get("SIGIMA_ROOT", DEV_ROOT / "Sigima"))


def _find_wheel(directory: Path, prefix: str) -> Path:
    """Return the lexically latest matching wheel."""
    matches = sorted(directory.glob(f"{prefix}*.whl"))
    if not matches:
        raise FileNotFoundError(f"No {prefix}*.whl found under {directory}")
    return matches[-1].resolve()


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one wheel."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_arguments() -> argparse.Namespace:
    """Parse the optional report destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    """Load wheels in isolation, run the benchmark, and serialize provenance."""
    arguments = _parse_arguments()
    pulse_wheel = _find_wheel(PULSE_ROOT / "dist", "datalab_pulse_")
    sigima_wheel = _find_wheel(SIGIMA_ROOT / "dist", "sigima-1.1.6-")
    sys.path[:0] = [str(pulse_wheel), str(sigima_wheel)]

    import sigima
    from benchmark_alignment import BenchmarkConfiguration, run_benchmark

    import datalab_pulse_characterization

    if str(pulse_wheel) not in datalab_pulse_characterization.__file__:
        raise RuntimeError("Pulse was not imported from the selected wheel")
    if str(sigima_wheel) not in sigima.__file__:
        raise RuntimeError("Sigima was not imported from the selected wheel")

    report = run_benchmark(BenchmarkConfiguration())
    report.update(
        backend="cpython",
        measured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        pulse_wheel_sha256=_sha256(pulse_wheel),
        sigima_wheel_sha256=_sha256(sigima_wheel),
    )
    serialized = f"{json.dumps(report, indent=2, sort_keys=True)}\n"
    if arguments.output is None:
        sys.stdout.write(serialized)
    else:
        arguments.output.resolve().write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
