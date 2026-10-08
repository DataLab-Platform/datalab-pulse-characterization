# Step Response

[← Documentation index](README.md)

This method describes the response of a system, such as an amplifier, a probe, a cable or a detector front end, to a fast input step. It follows the vocabulary of IEEE 181 on transitions and pulses, without claiming compliance.

Recipe: `org.datalab.pulse-characterization:step-response`, version 1.0.0.

## Run

Select the signals, then choose **Plugins > Pulse & Transient Characterization > Run step response...**, or use the **Step response** method of the **Applications** catalog. **Open step-response example** opens the demonstration.

## Inputs

One signal per step, from the baseline before the transition to the settled level after the ringing, with the shot conventions of the [pulse campaign](pulse-campaign.md#inputs). Steps that are not `VALID` are not averaged and are listed in an `excluded_shots` warning.

**Parameters:** baseline and final plateau ranges, minimum SNR per shot, lower and upper reference levels, settling tolerance, state-level histogram bins, instrument rise time, ringing detection threshold.

## Results

| Output | Type | Content |
| --- | --- | --- |
| `mean_step` | Signal | Aligned mean step, with the metrics table |
| `settling_error` | Signal | Absolute error to the high level, in percent, versus time after the 50 % crossing |
| `second_order_model` | Signal | Step of the equivalent second-order system, aligned on the 50 % crossing |

The `step_metrics` table gives the state levels, amplitude, noise, rise times, overshoot, undershoot and preshoot, settling time, ringing and bandwidths. Frequencies are in MHz when the X unit is a known time unit (`s`, `ms`, `us`, `ns`, `ps`), else in cycles per X unit. A warning tells when the waveform does not settle within the record.

## Method

1. Each acquisition is analyzed as a step and aligned on its 50 % crossing, as in the [pulse campaign](pulse-campaign.md#method). Averaging the aligned steps reduces the noise without smearing the transition by the trigger jitter.
2. The low and high state levels are the modes of the histograms of the lower and upper halves of the waveform range (IEEE 181 histogram method), refined by the mean of the samples around each mode.
3. The rise time runs from the 10 % to the 90 % level. When the rise time of the acquisition system is known, the corrected rise time is `sqrt(t_r**2 - t_instrument**2)`, valid for Gaussian-like responses.
4. Overshoot, undershoot and preshoot are in percent of the amplitude. The settling time runs from the 50 % crossing to the last exit from a tolerance band (2 % by default).
5. Ringing is measured on the settling error. Its zero crossings give the damped frequency `f_d`. The logarithmic decrement of the extrema gives the damping ratio `zeta` of an equivalent second-order system; the overshoot gives a second estimate, `zeta = -ln(OS) / sqrt(pi**2 + ln(OS)**2)`.
6. The natural frequency is `f_n = f_d / sqrt(1 - zeta**2)`, and the -3 dB bandwidth of the model is `f_n * sqrt(1 - 2 zeta**2 + sqrt(4 zeta**4 - 4 zeta**2 + 2))`. The single-pole rule `0.35 / t_r` is also given; it underestimates the bandwidth of underdamped systems.

## Demonstration

The **Synthetic amplifier step response** holds 64 steps of 1 V through a second-order amplifier with an 80 MHz natural frequency and a 0.35 damping ratio, about 31 % overshoot. The oscilloscope has a 0.7 ns rise time, 0.3 ns trigger jitter and 10 mV noise.

The validation suite checks, against the noiseless truth, the rise times within 3 %, the overshoot within 1 point, the settling time within 5 %, the ringing frequency within 3 % and the damping ratio within 6 %.

## Limits

The second-order model describes the dominant ringing only. Reflections, multiple resonances and slew-rate limiting are not modeled. The rise-time correction is only approximate for non-Gaussian instrument responses.
