# Two-Channel Delay Recipe

```text
org.datalab.pulse-characterization:two-channel-delay
```

This recipe measures the delay and the relative timing jitter between a reference channel (for instance a fast photodiode monitoring a laser, or a trigger output) and a measured channel (for instance a detector after a cable), acquired on the same shots. It implements the first part of the V2 scope described in [`deferred-scope.md`](deferred-scope.md).

## Input Contract

- Two slots, `reference` and `measured`, each with at least three signals carrying a shot number.
- Every signal carries a positive shot number in `plugin.org.datalab.pulse-characterization.shot`. Shots are paired by this number only; input order and titles are never used. A shot number repeated within one channel is an error.
- A shot present in one channel only is reported as `MISSING_REFERENCE` or `MISSING_MEASURED` with a `missing_channel` warning.
- `plugin.org.datalab.pulse-characterization.channel` is optional. When the candidates carry exactly two channel labels, the first label in sorted order is proposed as the reference. This is a binding convenience: both hosts let the user change the roles. Before the run, the input check validates the shot numbers of each channel and requires a common X unit.
- Both channels must use the same X unit; the cross-correlation delay also requires the same sampling interval.

## Physical Principle

Each channel is analyzed with the single-channel campaign analysis. For each shot where both channels are `VALID`:

- the **CFD delay** is the difference of the 50 % crossings, a constant-fraction timing insensitive to amplitude;
- the **cross-correlation delay** maximizes the correlation of the baseline-subtracted waveforms, refined by parabolic interpolation. When the two pulse shapes differ, it differs from the CFD delay by a constant, but both share the same jitter.

A trigger jitter shifts both channels together: it appears in the jitter of each channel but cancels in their difference. With `t_ref` and `t_meas` the arrival times:

```text
var(t_meas - t_ref) = var(independent jitter)
cov(t_ref, t_meas)  = var(common jitter)
```

The relative jitter therefore isolates the measured channel's own jitter (for instance the transit-time spread of a detector), and the covariance estimates the common-mode jitter. Amplitude and integral correlations and the amplitude gain show whether the measured channel follows the source fluctuations.

## Outputs

| Output ID | Type | Meaning |
| --- | --- | --- |
| `delay_vs_shot` | Signal | CFD delay versus shot; anchor object |
| `xcorr_delay_vs_shot` | Signal | Cross-correlation delay versus shot |
| `delay_distribution` | Signal | Histogram of the CFD delay |
| `amplitude_correlation` | Signal | Measured versus reference amplitude, sorted by reference amplitude |

Two tables are attached to `delay_vs_shot`: `delay_summary` (pair counts, delays, relative, per-channel and common-mode jitters, correlations, gain) and `pair_metrics` (one row per shot with both channel statuses, crossings, delays and amplitudes).

## Demonstration

The **Synthetic two-channel delay campaign** contains 300 shots. The reference is a 1.5 ns Gaussian pulse; the measured channel is an asymmetric detector pulse delayed by 37.5 ns. Both share a 1 ns trigger jitter, the detector adds 0.2 ns of its own, three detector acquisitions are missing and two contain no pulse. Each channel shows about 1 ns of jitter while the relative jitter is about 0.2 ns. The validation suite checks the delay within 0.1 ns, the relative jitter within 15 % and the common-mode jitter within 10 % of the simulated offsets.

## Limits

Real acquisitions and an independent scientific review of these conventions are still required, as for the other recipes: the project remains Alpha. Configuration comparison (V3) remains out of scope.
