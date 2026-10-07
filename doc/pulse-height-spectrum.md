# Pulse-Height Spectrum Recipe

```text
org.datalab.pulse-characterization:pulse-height-spectrum
```

This recipe turns triggered detector events into an energy spectrum, calibrates it with known gamma-ray lines and measures the energy resolution, as in gamma-ray spectroscopy with a scintillation detector.

## Physical Principle

In a scintillator coupled to a photomultiplier, the charge of each pulse is proportional to the energy deposited in the crystal. A monoenergetic gamma ray produces a full-energy photopeak when it is completely absorbed, and a Compton continuum, up to the Compton edge, when it scatters once and escapes. The width of the photopeak comes mainly from the statistics of the photoelectrons, so the relative resolution `FWHM / E` scales approximately as `E^-1/2`.

## Computation

1. For each event, the baseline and its noise are measured over the pre-trigger window. The polarity is the sign of the largest deviation.
2. The peak height and the charge (integral of the baseline-subtracted pulse, from the pulse onset and over an optional gate) are measured. Integrating over a gate of a few decay constants collects nearly all the charge while limiting the integrated baseline noise.
3. Events are classified: `SATURATED` when samples reach the digitizer limits, `BELOW_THRESHOLD` when the peak is below the detection threshold (5 baseline RMS by default), `PILE_UP` when the event contains a second pulse more prominent than 10 % of the first, else `ACCEPTED`.
4. Accepted events are histogrammed. The most prominent peaks of the smoothed spectrum, as many as there are calibration lines, are matched in increasing order to the line energies, and each is fitted by a Gaussian on a linear background with Poisson weights.
5. A linear least-squares fit of energy versus centroid gives the calibration. The resolution at each line is `gain * FWHM / E`, and a log-log fit of resolution versus energy gives the scaling exponent (about -0.5 when photoelectron statistics dominate).

## Outputs

| Output ID | Type | Meaning |
| --- | --- | --- |
| `raw_spectrum` | Signal | Counts versus charge or peak height; anchor object |
| `energy_spectrum` | Signal | Counts versus calibrated energy (keV) |
| `calibration_curve` | Signal | Line energies versus fitted centroids |
| `resolution_vs_energy` | Signal | `FWHM / E` (%) versus energy |

Two tables are attached to `raw_spectrum`: `spectrum_summary` (event counts per status, calibration gain and offset, resolution exponent) and `calibration_peaks` (one row per line with centroid, calibrated centroid and residual, FWHM, resolution and net counts).

## Demonstration

The **Synthetic NaI(Tl) gamma spectrum** contains 2,500 triggered events digitized on 256 samples over 2 µs, with negative pulses of 20 ns rise and 230 ns decay constants. Gamma rays come from Cs-137 (661.657 keV) and Co-60 (1173.228 and 1332.492 keV). They are fully absorbed or Compton scattered following the Klein-Nishina distribution, then smeared with a 7 % resolution at 662 keV scaling as `E^-1/2`. One percent of events pile up and 0.5 % are cosmic-ray muons that saturate the digitizer.

The validation suite checks the calibration gain within 2 %, every calibrated line within 5 keV, the resolution at each line within 20 % (about 350 counts per photopeak) and a scaling exponent between -1 and -0.2.

## Limits

The model has one Compton scattering per event and no backscatter peak, X-ray escape, light-yield nonlinearity or count-rate effects. Undetected pile-up of small pulses distorts the spectrum, as in real systems. The peak search assumes that the calibration photopeaks are the most prominent features of the spectrum.
