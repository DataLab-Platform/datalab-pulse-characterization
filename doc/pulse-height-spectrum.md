# Pulse-Height Spectrum

[← Documentation index](README.md)

This method turns triggered detector events into an energy spectrum, calibrates it with known gamma-ray lines and measures the energy resolution, as in gamma-ray spectroscopy with a scintillation detector.

Recipe: `org.datalab.pulse-characterization:pulse-height-spectrum`, version 1.0.0.

## Run

Select the events, then choose **Plugins > Pulse & Transient Characterization > Run pulse-height spectrum...**, or use the **Pulse-height spectrum** method of the **Applications** catalog. **Open gamma spectrum example** opens the demonstration.

## Inputs

One signal per triggered event: a pre-trigger baseline followed by the detector pulse, of either polarity.

**Parameters:** energy estimator (charge or peak height), pre-trigger fraction, integration gate, detection threshold, pile-up ratio, saturation detection, spectrum bins, peak-search smoothing, and energies of the calibration lines (Cs-137 and Co-60 by default).

## Results

| Output | Type | Content |
| --- | --- | --- |
| `raw_spectrum` | Signal | Counts versus charge or peak height, with both tables |
| `energy_spectrum` | Signal | Counts versus calibrated energy (keV) |
| `calibration_curve` | Signal | Line energies versus fitted centroids |
| `resolution_vs_energy` | Signal | `FWHM / E` (%) versus energy |

The `spectrum_summary` table gives the event counts per status, the calibration gain and offset, and the resolution exponent. The `calibration_peaks` table has one row per line, with centroid, calibrated centroid and residual, FWHM, resolution and net counts.

## Method

In a scintillator coupled to a photomultiplier, the charge of each pulse is proportional to the energy deposited in the crystal. A fully absorbed gamma ray gives a photopeak; a gamma ray that scatters once and escapes gives a Compton continuum. The photopeak width comes mainly from photoelectron statistics, so the relative resolution `FWHM / E` scales about as `E^-1/2`.

1. For each event, the baseline and its noise are measured before the trigger. The polarity is the sign of the largest deviation.
2. The peak height and the charge are measured. The charge integrates the baseline-subtracted pulse from its onset, over an optional gate: a gate of a few decay constants collects nearly all the charge and limits the baseline noise.
3. Events are classified: `SATURATED` when samples reach the digitizer limits, `BELOW_THRESHOLD` when the peak is below the threshold (5 baseline RMS by default), `PILE_UP` when a second pulse exceeds 10 % of the first, else `ACCEPTED`.
4. Accepted events are histogrammed. The most prominent peaks, as many as calibration lines, are matched in increasing order to the line energies. Each is fitted by a Gaussian on a linear background, with Poisson weights.
5. A linear fit of energy versus centroid gives the calibration. The resolution at each line is `gain * FWHM / E`. A log-log fit of resolution versus energy gives the scaling exponent, about -0.5 when photoelectron statistics dominate.

## Demonstration

The **Synthetic NaI(Tl) gamma spectrum** holds 2,500 events of 256 samples over 2 µs, with negative pulses of 20 ns rise and 230 ns decay. Gamma rays come from Cs-137 (661.657 keV) and Co-60 (1173.228 and 1332.492 keV). They are fully absorbed or Compton scattered (Klein-Nishina), then smeared with a resolution of 7 % at 662 keV scaling as `E^-1/2`. One percent of events pile up, and 0.5 % are cosmic-ray muons that saturate the digitizer.

The validation suite checks the calibration gain within 2 %, every calibrated line within 5 keV, the resolution at each line within 20 %, and a scaling exponent between -1 and -0.2.

## Limits

The model has one Compton scattering per event, and no backscatter peak, X-ray escape, light-yield nonlinearity or count-rate effects. Undetected pile-up of small pulses distorts the spectrum, as in real systems. The peak search assumes that the calibration photopeaks are the most prominent features of the spectrum.
