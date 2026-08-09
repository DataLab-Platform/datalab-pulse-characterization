"""Headless alignment of repeated pulse acquisitions."""

from __future__ import annotations

import dataclasses
import enum
import math
from collections.abc import Sequence

import numpy as np
from sigima.tools.signal import pulse as sigima_pulse

from .campaign import (
    PulseAcquisition,
    PulseCampaignResult,
    PulseShotResult,
    PulseStatus,
)


class PulseAlignmentMethod(str, enum.Enum):
    """Supported pulse-alignment landmarks."""

    HALF_HEIGHT = "50_percent_crossing"


@dataclasses.dataclass(frozen=True)
class PulseAlignmentParameters:
    """Host-independent settings for one alignment pass."""

    method: PulseAlignmentMethod | str = PulseAlignmentMethod.HALF_HEIGHT
    reference_x: float | None = None

    def __post_init__(self) -> None:
        """Normalize and validate the alignment settings."""
        try:
            method = PulseAlignmentMethod(self.method)
        except ValueError as error:
            raise ValueError("Unsupported pulse alignment method") from error
        object.__setattr__(self, "method", method)
        if self.reference_x is not None and not math.isfinite(self.reference_x):
            raise ValueError("Alignment reference must be finite or None")


@dataclasses.dataclass(frozen=True)
class PulseAlignmentRecord:
    """Alignment decision and applied shift for one acquisition."""

    shot_index: int
    aligned: bool
    landmark_x: float | None
    shift_x: float | None
    reason: str

    def __post_init__(self) -> None:
        """Validate one immutable alignment decision."""
        if self.shot_index < 1:
            raise ValueError("Alignment shot index must be positive")
        if not isinstance(self.aligned, bool):
            raise TypeError("Alignment state must be a bool")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Alignment reason must be non-empty")
        if self.aligned:
            if self.landmark_x is None or self.shift_x is None:
                raise ValueError("Aligned shots require a landmark and shift")
            if not math.isfinite(self.landmark_x) or not math.isfinite(self.shift_x):
                raise ValueError("Alignment landmark and shift must be finite")
        else:
            if self.landmark_x is not None and not math.isfinite(self.landmark_x):
                raise ValueError("Alignment landmark must be finite")
            if self.shift_x is not None:
                raise ValueError("Unaligned shots cannot carry a shift")


@dataclasses.dataclass(frozen=True)
class PulseAlignmentResult:
    """Raw and aligned campaigns with one decision record per shot."""

    method: PulseAlignmentMethod
    reference_x: float | None
    raw_acquisitions: Sequence[PulseAcquisition]
    aligned_acquisitions: Sequence[PulseAcquisition]
    records: Sequence[PulseAlignmentRecord]

    def __post_init__(self) -> None:
        """Freeze and validate the parallel result sequences."""
        method = PulseAlignmentMethod(self.method)
        raw = tuple(self.raw_acquisitions)
        aligned = tuple(self.aligned_acquisitions)
        records = tuple(self.records)
        if not raw or not (len(raw) == len(aligned) == len(records)):
            raise ValueError("Alignment result sequences must be non-empty and equal")
        if self.reference_x is not None and not math.isfinite(self.reference_x):
            raise ValueError("Alignment result reference must be finite or None")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "raw_acquisitions", raw)
        object.__setattr__(self, "aligned_acquisitions", aligned)
        object.__setattr__(self, "records", records)

    @property
    def aligned_count(self) -> int:
        """Return the number of acquisitions shifted onto the reference."""
        return sum(record.aligned for record in self.records)

    def mean_acquisition(self, *, aligned: bool) -> PulseAcquisition:
        """Average the alignable subset on one shared acquisition grid."""
        source = self.aligned_acquisitions if aligned else self.raw_acquisitions
        selected = tuple(
            acquisition
            for acquisition, record in zip(source, self.records)
            if record.aligned
        )
        if not selected:
            raise ValueError("Pulse aggregation requires an alignable acquisition")
        reference_grid = selected[0].x
        mean_y = np.zeros(reference_grid.size, dtype=float)
        for acquisition in selected:
            if np.array_equal(acquisition.x, reference_grid):
                mean_y += acquisition.y
            else:
                mean_y += np.interp(
                    reference_grid,
                    acquisition.x,
                    acquisition.y,
                    left=float(acquisition.y[0]),
                    right=float(acquisition.y[-1]),
                )
        mean_y /= len(selected)
        state = "Aligned" if aligned else "Raw"
        return PulseAcquisition(
            x=reference_grid,
            y=mean_y,
            title=f"{state} pulse campaign mean",
        )


def _acquisition_shot_index(acquisition: PulseAcquisition, position: int) -> int:
    """Return the same shot identity used by campaign analysis."""
    return position if acquisition.shot_index is None else acquisition.shot_index


def _validate_parallel_campaigns(
    acquisitions: tuple[PulseAcquisition, ...],
    campaign: PulseCampaignResult,
) -> None:
    """Require one analysis row with matching identity for every acquisition."""
    if len(acquisitions) != len(campaign.shots):
        raise ValueError("Alignment acquisitions and analysis must have equal length")
    for position, (acquisition, shot) in enumerate(
        zip(acquisitions, campaign.shots),
        start=1,
    ):
        if _acquisition_shot_index(acquisition, position) != shot.shot_index:
            raise ValueError("Alignment acquisition and analysis shot indices differ")


def _half_height_landmark(
    acquisition: PulseAcquisition,
    shot: PulseShotResult,
) -> float | None:
    """Return Sigima's polarity-aware rising 50 percent crossing."""
    assert shot.features is not None
    if shot.features.x50 is not None and math.isfinite(shot.features.x50):
        return float(shot.features.x50)
    try:
        crossing = sigima_pulse.find_crossing_at_ratio(
            acquisition.x,
            acquisition.y,
            ratio=0.5,
            start_range=(shot.features.xstartmin, shot.features.xstartmax),
            end_range=(shot.features.xendmin, shot.features.xendmax),
            signal_shape=shot.features.signal_shape,
        )
    except (ValueError, sigima_pulse.PulseAnalysisError):
        return None
    return None if crossing is None else float(crossing)


def _align_acquisition(
    acquisition: PulseAcquisition,
    shift_x: float,
) -> PulseAcquisition:
    """Translate one waveform by interpolation on its original X grid."""
    query_x = acquisition.x - shift_x
    aligned_y = np.interp(
        query_x,
        acquisition.x,
        acquisition.y,
        left=float(acquisition.y[0]),
        right=float(acquisition.y[-1]),
    )
    return PulseAcquisition(
        x=acquisition.x,
        y=aligned_y,
        title=acquisition.title,
        shot_index=acquisition.shot_index,
    )


def _skip_reason(shot: PulseShotResult) -> str:
    """Explain why one acquisition was retained without alignment."""
    reason = f"Skipped {shot.status.value} acquisition"
    if shot.status is PulseStatus.VALID:
        reason += ": 50% crossing unavailable"
    return reason


def _default_reference(landmarks: dict[int, float]) -> float:
    """Return the observed median, using the lower middle landmark when even."""
    ordered_landmarks = sorted(landmarks.values())
    return ordered_landmarks[(len(ordered_landmarks) - 1) // 2]


def align_pulse_campaign(
    acquisitions: Sequence[PulseAcquisition],
    campaign: PulseCampaignResult,
    parameters: PulseAlignmentParameters | None = None,
) -> PulseAlignmentResult:
    """Align valid pulses on a robust common half-height crossing.

    Non-valid shots remain byte-for-byte unchanged in the aligned sequence and
    carry an explicit skip reason. Valid shots use Sigima's polarity-aware
    rising 50 percent crossing. The default reference is the observed median,
    using the lower middle landmark for an even count; interpolation keeps
    every acquisition on its original X grid.
    """
    acquisitions = tuple(acquisitions)
    if not acquisitions or not all(
        isinstance(acquisition, PulseAcquisition) for acquisition in acquisitions
    ):
        raise TypeError("Alignment requires a non-empty PulseAcquisition sequence")
    if not isinstance(campaign, PulseCampaignResult):
        raise TypeError("Alignment requires a PulseCampaignResult")
    if parameters is None:
        parameters = PulseAlignmentParameters()
    if not isinstance(parameters, PulseAlignmentParameters):
        raise TypeError("Alignment requires PulseAlignmentParameters")
    _validate_parallel_campaigns(acquisitions, campaign)

    landmarks: dict[int, float] = {}
    for acquisition, shot in zip(acquisitions, campaign.shots):
        if shot.status is PulseStatus.VALID and shot.features is not None:
            landmark_x = _half_height_landmark(acquisition, shot)
            if landmark_x is not None:
                landmarks[shot.shot_index] = landmark_x
    if not landmarks:
        return PulseAlignmentResult(
            method=parameters.method,
            reference_x=None,
            raw_acquisitions=acquisitions,
            aligned_acquisitions=acquisitions,
            records=tuple(
                PulseAlignmentRecord(
                    shot_index=shot.shot_index,
                    aligned=False,
                    landmark_x=None,
                    shift_x=None,
                    reason=_skip_reason(shot),
                )
                for shot in campaign.shots
            ),
        )
    reference_x = (
        _default_reference(landmarks)
        if parameters.reference_x is None
        else parameters.reference_x
    )

    aligned_acquisitions: list[PulseAcquisition] = []
    records: list[PulseAlignmentRecord] = []
    for acquisition, shot in zip(acquisitions, campaign.shots):
        landmark_x = landmarks.get(shot.shot_index)
        if landmark_x is None or not (
            float(acquisition.x[0]) <= reference_x <= float(acquisition.x[-1])
        ):
            aligned_acquisitions.append(acquisition)
            reason = _skip_reason(shot)
            if landmark_x is not None:
                reason = "Skipped VALID acquisition: reference outside X range"
            records.append(
                PulseAlignmentRecord(
                    shot_index=shot.shot_index,
                    aligned=False,
                    landmark_x=landmark_x,
                    shift_x=None,
                    reason=reason,
                )
            )
            continue
        shift_x = reference_x - landmark_x
        aligned_acquisitions.append(_align_acquisition(acquisition, shift_x))
        records.append(
            PulseAlignmentRecord(
                shot_index=shot.shot_index,
                aligned=True,
                landmark_x=landmark_x,
                shift_x=shift_x,
                reason=(
                    f"Aligned 50% crossing at {landmark_x:g} "
                    f"to reference {reference_x:g}"
                ),
            )
        )
    return PulseAlignmentResult(
        method=parameters.method,
        reference_x=reference_x,
        raw_acquisitions=acquisitions,
        aligned_acquisitions=aligned_acquisitions,
        records=records,
    )


__all__ = [
    "PulseAlignmentMethod",
    "PulseAlignmentParameters",
    "PulseAlignmentRecord",
    "PulseAlignmentResult",
    "align_pulse_campaign",
]
