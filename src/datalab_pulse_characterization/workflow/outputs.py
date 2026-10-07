"""Output helpers shared by the Pulse recipes."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from sigima.objects import NO_ROI, SignalObj, TableResult, create_signal

from .campaign import OUTPUT_ROLE_METADATA_KEY, _metric

#: Seconds per supported time unit, used to express frequencies in hertz.
SECONDS_PER_UNIT = {
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "µs": 1e-6,
    "ns": 1e-9,
    "ps": 1e-12,
}


def signal_output(
    title: str,
    x: np.ndarray,
    y: np.ndarray,
    role: str,
    *,
    units: tuple[str, str],
    labels: tuple[str, str],
) -> SignalObj:
    """Create one signal output carrying its stable output role."""
    output = create_signal(
        title,
        np.asarray(x, dtype=float),
        np.asarray(y, dtype=float),
        units=units,
        labels=labels,
    )
    output.metadata[OUTPUT_ROLE_METADATA_KEY] = role
    return output


def metrics_table(
    title: str,
    kind: str,
    rows: Sequence[tuple[str, object, str]],
    attrs: Mapping[str, object],
) -> TableResult:
    """Build a Metric/Value/Unit table with JSON-safe values."""
    data = [
        [name, _metric(value) if isinstance(value, float) else value, unit]
        for name, value, unit in rows
    ]
    return TableResult(
        title=title,
        kind=kind,
        headers=["Metric", "Value", "Unit"],
        data=data,
        roi_indices=[NO_ROI] * len(data),
        attrs={"normative": False, **attrs},
    )


def frequency(value: float, x_unit: str) -> tuple[float, str]:
    """Express a frequency in MHz for known time units, else in 1/X unit."""
    seconds = SECONDS_PER_UNIT.get(x_unit)
    if seconds is None:
        return value, f"1/{x_unit}" if x_unit else "1/X"
    return value / seconds / 1e6 if math.isfinite(value) else value, "MHz"


def histogram(values: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray]:
    """Return histogram bin centers and counts of finite values."""
    finite = values[np.isfinite(values)]
    counts, edges = np.histogram(finite, bins=bins)
    return 0.5 * (edges[:-1] + edges[1:]), counts.astype(float)


__all__ = ["frequency", "histogram", "metrics_table", "signal_output"]
