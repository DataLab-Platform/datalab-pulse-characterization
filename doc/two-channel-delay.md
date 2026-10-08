# Two-Channel Delay and Jitter

[← Documentation index](README.md)

This method measures the delay and the relative timing jitter between a reference channel and a measured channel acquired on the same shots. The reference may be a fast photodiode monitoring a laser, or a trigger output; the measured channel may be a detector after a cable.

Recipe: `org.datalab.pulse-characterization:two-channel-delay`, version 1.0.0.

## Run

Select the signals of both channels, then choose **Plugins > Pulse & Transient Characterization > Run two-channel delay...**, or use the **Two-channel delay and jitter** method of the **Applications** catalog. **Open two-channel example** opens the demonstration.

## Inputs

- Two slots, `reference` and `measured`, with at least three signals each.
- Every signal carries a positive shot number in `plugin.org.datalab.pulse-characterization.shot`. Shots are paired by this number only, never by input order or title. A shot number repeated within one channel is an error.
- The channel label in `plugin.org.datalab.pulse-characterization.channel` is optional. When the signals carry exactly two labels, the first one in sorted order is proposed as the reference. You can change the roles.
- Both channels use the same X unit. The cross-correlation delay also needs the same sampling interval; acquisitions may start at different X values.

To set shot numbers and channel labels on your own signals, see [Use your own signals](getting-started.md#use-your-own-signals).

A shot present in one channel only is kept as `MISSING_REFERENCE` or `MISSING_MEASURED`, with a `missing_channel` warning. A shot with a channel that is not `VALID` is kept with its status, with an `invalid_pair` warning. Neither enters the statistics.

## Results

| Output | Type | Content |
| --- | --- | --- |
| `delay_vs_shot` | Signal | CFD delay versus shot, with both tables |
| `xcorr_delay_vs_shot` | Signal | Cross-correlation delay versus shot |
| `delay_distribution` | Signal | Histogram of the CFD delay |
| `amplitude_correlation` | Signal | Measured versus reference amplitude, sorted by reference amplitude |

The `delay_summary` table gives the pair counts, delays, relative, per-channel and common-mode jitters, correlations and gain. The `pair_metrics` table has one row per shot with both channel statuses, crossings, delays and amplitudes.

## Method

Each channel is analyzed as in the [pulse campaign](pulse-campaign.md#method). For each shot where both channels are `VALID`:

- the **CFD delay** is the difference of the 50 % crossings, a constant-fraction timing that does not depend on the amplitude;
- the **cross-correlation delay** maximizes the correlation of the baseline-subtracted waveforms, refined by parabolic interpolation. When the pulse shapes differ, it differs from the CFD delay by a constant, but has the same jitter.

A trigger jitter shifts both channels together: it shows in the jitter of each channel but cancels in their difference. With `t_ref` and `t_meas` the arrival times:

```text
var(t_meas - t_ref) = var(independent jitter)
cov(t_ref, t_meas)  = var(common jitter)
```

The relative jitter therefore isolates the jitter of the measured channel, for instance the transit-time spread of a detector. The covariance estimates the common-mode jitter. Amplitude and integral correlations and the amplitude gain show whether the measured channel follows the source.

## Demonstration

The **Synthetic two-channel delay campaign** holds 300 shots. The reference is a 1.5 ns Gaussian pulse; the measured channel is an asymmetric detector pulse delayed by 37.5 ns. Both share a 1 ns trigger jitter, and the detector adds 0.2 ns of its own. Three detector acquisitions are missing and two have no pulse. Each channel shows about 1 ns of jitter, while the relative jitter is about 0.2 ns.

The validation suite checks the delay within 0.1 ns, the relative jitter within 15 % and the common-mode jitter within 10 % of the simulated values.

## Limits

Instruments without a common trigger, more than two channels and time-base calibration are out of scope, as is the comparison of acquisition configurations.
