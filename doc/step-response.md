# Step-Response Recipe

```text
org.datalab.pulse-characterization:step-response
```

This recipe characterizes the response of a system (amplifier, probe, cable, detector front end) to a fast input step. It follows the vocabulary of IEEE 181 on transitions, pulses and related waveforms; it does not claim compliance.

## Computation

1. Each acquisition is analyzed as a `step` and aligned on its 50 % crossing, like in the campaign recipe. Averaging the aligned valid steps reduces random noise by the square root of their number without smearing the transition by the trigger jitter.
2. The low and high state levels are the modes of the histograms of the lower and upper halves of the waveform range (IEEE 181 histogram method), refined by the mean of the samples around each mode.
3. The rise time is the duration between the 10 % and 90 % reference levels. When the rise time of the acquisition system is known, the corrected rise time is `sqrt(t_r**2 - t_instrument**2)`, valid for Gaussian-like responses.
4. Overshoot, undershoot and preshoot are expressed in percent of the amplitude. The settling time is measured from the 50 % crossing to the last time the waveform leaves a tolerance band (2 % by default).
5. Ringing is measured on the settling error `y - high`. Its zero crossings give the half-period, hence the damped frequency `f_d`. The logarithmic decrement of successive extrema above the noise gives the damping ratio `zeta` of an equivalent second-order system; the overshoot gives a second estimate `zeta = -ln(OS) / sqrt(pi**2 + ln(OS)**2)`.
6. The natural frequency is `f_n = f_d / sqrt(1 - zeta**2)` and the -3 dB bandwidth of the second-order model is `f_n * sqrt(1 - 2 zeta**2 + sqrt(4 zeta**4 - 4 zeta**2 + 2))`. The single-pole rule `0.35 / t_r` is also reported; it underestimates the bandwidth of underdamped systems.

## Outputs

| Output ID | Type | Meaning |
| --- | --- | --- |
| `mean_step` | Signal | Aligned mean step; anchor object |
| `settling_error` | Signal | Absolute error to the high level in percent, versus time after the 50 % crossing |
| `second_order_model` | Signal | Step of the equivalent second-order system, aligned on the 50 % crossing |

The `step_metrics` table, attached to `mean_step`, reports the state levels, amplitude, noise, rise times, aberrations, settling time, ringing and bandwidths. Frequencies are expressed in MHz when the X unit is a known time unit (`s`, `ms`, `us`, `ns`, `ps`), else in cycles per X unit. Warnings report excluded steps and a waveform that does not settle within the record.

## Demonstration

The **Synthetic amplifier step response** contains 64 steps of 1 V through a second-order amplifier with an 80 MHz natural frequency and a 0.35 damping ratio (about 31 % overshoot), observed by an oscilloscope with a 0.7 ns rise time, 0.3 ns trigger jitter and 10 mV noise. The validation suite checks the rise times within 3 %, the overshoot within 1 point, the settling time within 5 %, the ringing frequency within 3 % and the damping ratio within 6 % of the noiseless truth.

## Limits

The equivalent second-order model describes the dominant ringing only. Reflections, multiple resonances and nonlinear slew-rate limiting are not modeled, and the quadrature correction is only an approximation for non-Gaussian instrument responses.
