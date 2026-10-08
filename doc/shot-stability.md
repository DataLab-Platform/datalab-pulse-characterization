# Shot-to-Shot Stability

[← Documentation index](README.md)

This method describes how a repeated pulsed source, such as a pulsed laser, a pulse generator or an accelerator bunch, changes from one shot to the next. The [pulse campaign](pulse-campaign.md) describes each shot; this method describes the time series formed by the shots. Its amplitude and energy statistics are inspired by ISO 11554, without claiming compliance.

Recipe: `org.datalab.pulse-characterization:shot-stability`, version 1.0.0.

## Run

Select the signals, then choose **Plugins > Pulse & Transient Characterization > Run shot-to-shot stability...**, or use the **Shot-to-shot stability** method of the **Applications** catalog. **Open stability example** opens the demonstration.

## Inputs

The inputs and analysis parameters are those of the [pulse campaign](pulse-campaign.md#inputs). The method adds the rolling-window length, the regime-change settings and the histogram bins. Only `VALID` shots enter the statistics; the others are listed in one `excluded_shots` warning.

## Results

| Output | Type | Content |
| --- | --- | --- |
| `arrival_time_vs_shot` | Signal | 50 % arrival time versus shot, with the metrics table |
| `amplitude_vs_shot` | Signal | Amplitude versus shot |
| `integral_vs_shot` | Signal | Pulse integral (energy proxy) versus shot |
| `rolling_jitter` | Signal | Rolling standard deviation of the detrended arrival time |
| `arrival_time_adev` | Signal | Timing Allan deviation versus averaging length |
| `amplitude_adev` | Signal | Relative amplitude Allan deviation versus averaging length |
| `arrival_time_distribution` | Signal | Histogram of the detrended arrival time |

The `stability_metrics` table gives the jitter, the drifts, the relative amplitude and energy stability, the Allan deviation at one shot and its minimum, and the regime change when one is found.

## Method

- **Arrival time:** the 50 % crossing of each valid shot, from the trigger. Its spread is the trigger-referenced timing jitter.
- **Drift:** a linear trend of the arrival time or amplitude versus the shot index, typical of a thermal warm-up.
- **Detrended jitter:** the spread of the arrival time once the drift is removed.
- **Amplitude and energy stability:** relative standard deviation and peak-to-peak spread of the amplitude and of the integral. The integral is proportional to the pulse energy for a linear detector.
- **Allan deviation:** overlapping two-sample deviation of averages of `m` consecutive valid shots, taken as evenly spaced. White noise decreases as `m^-1/2` and a drift grows as `m`: the minimum gives the averaging length beyond which averaging stops helping.
- **Regime change:** the shot that best splits the detrended arrival times into two segments with different variances, by a Gaussian log-likelihood ratio. It is reported above a threshold (25 by default), with at least 30 shots per segment.

## Demonstration

The **Synthetic laser warm-up campaign** holds 600 Gaussian pulses of 301 samples over 10 µs. The arrival time drifts by 60 ns and the amplitude by 5 % over the campaign. The timing jitter rises from 15 ns to 50 ns after shot 400, and two shots have no pulse.

The validation suite checks the detected change within 5 shots, the jitter before and after it within 15 % of the simulated offsets, and both drifts within 20 %.

## Limits

The arrival time is referenced to the acquisition trigger: trigger jitter and source jitter are not separated. The [two-channel method](two-channel-delay.md) does that. Only one regime change is searched; gradual changes show in the rolling jitter only.
