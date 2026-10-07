# Shot-to-Shot Stability Recipe

```text
org.datalab.pulse-characterization:shot-stability
```

This recipe characterizes how a repeated pulsed source (for instance a pulsed laser, a pulse generator or an accelerator bunch) changes from one shot to the next. Where the single-channel campaign recipe describes each shot, this recipe describes the time series formed by the shots. Its amplitude and energy statistics are inspired by ISO 11554, which defines pulse energy stability for lasers; the recipe does not claim compliance.

## Physical Quantities

- **Arrival time:** the 50 % crossing of each valid shot, measured from the acquisition origin, that is from the trigger. Its spread is the trigger-referenced timing jitter.
- **Drift:** a linear trend of the arrival time or amplitude versus the shot index, typical of thermal warm-up.
- **Detrended jitter:** the spread of the arrival time once the linear drift is removed.
- **Amplitude and energy stability:** the relative standard deviation and peak-to-peak spread of the amplitude and of the pulse integral, which is proportional to the pulse energy for a linear detector.
- **Allan deviation:** the overlapping two-sample deviation of averages of `m` consecutive shots. White noise decreases as `m^-1/2` while a drift grows as `m`; the minimum gives the averaging length beyond which averaging no longer helps.
- **Regime change:** the single shot that best splits the detrended arrival times into two segments with different variances, by a Gaussian log-likelihood ratio. The change is reported only above a configurable threshold (25 by default, with at least 30 shots per segment).

## Inputs and Outputs

The recipe accepts the same `signals` slot and analysis parameters as the single-channel campaign, and adds the rolling-window length, regime-change settings and histogram bins. Only `VALID` shots enter the statistics; the excluded shots are listed in one `excluded_shots` warning. Allan deviations treat consecutive valid shots as evenly spaced samples.

| Output ID | Type | Meaning |
| --- | --- | --- |
| `arrival_time_vs_shot` | Signal | 50 % arrival time versus shot; anchor object |
| `amplitude_vs_shot` | Signal | Amplitude versus shot |
| `integral_vs_shot` | Signal | Pulse integral (energy proxy) versus shot |
| `rolling_jitter` | Signal | Rolling standard deviation of the detrended arrival time |
| `arrival_time_adev` | Signal | Timing Allan deviation versus averaging length |
| `amplitude_adev` | Signal | Relative amplitude Allan deviation versus averaging length |
| `arrival_time_distribution` | Signal | Histogram of the detrended arrival time |

The `stability_metrics` table, attached to `arrival_time_vs_shot`, reports the jitter, drifts, relative amplitude and energy stability, the Allan deviation at one shot and its minimum, and the regime change when detected.

## Demonstration

The **Synthetic laser warm-up campaign** contains 600 Gaussian pulses sampled on 301 points over 10 µs. The arrival time drifts by 60 ns over the campaign and the amplitude by 5 %. The timing jitter rises from 15 ns to 50 ns after shot 400, and two shots have no pulse. The validation suite checks the detected change within 5 shots, the jitter before and after it within 15 % of the simulated offsets, and both drifts within 20 %.

## Limits

The arrival time is referenced to the acquisition trigger: trigger jitter and source jitter are not separated (see the two-channel recipe for that). A single regime change is searched; gradual changes appear in the rolling jitter only.
