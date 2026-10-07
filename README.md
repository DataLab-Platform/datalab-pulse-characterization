# Pulse & Transient Characterization

Analyze repeated pulse acquisitions: timing, stability, step response, delays and spectra.

The plugin offers five methods, each with its own generated demonstration:

| Recipe | Physical question | Demonstration |
| --- | --- | --- |
| Single-channel pulse campaign | Which shots are valid, and what is the representative pulse? | 500 shots with drifts, jitter and explainable anomalies |
| Shot-to-shot stability | How large are the timing jitter, the drifts and the energy fluctuations, and when do they change? | Laser warm-up: 600 pulses with drifts and a jitter increase |
| Step response | What are the rise time, overshoot, settling time, ringing and bandwidth of a system? | 64 steps of an 80 MHz, 0.35-damped amplifier |
| Two-channel delay and jitter | What is the delay between two channels, and which part of the jitter is common? | Reference and detector channels, 1 ns common and 0.2 ns detector jitter |
| Pulse-height spectrum | What is the energy calibration and resolution of a detector? | NaI(Tl) events from Cs-137 and Co-60 sources |

The new methods are documented in [`doc/shot-stability.md`](doc/shot-stability.md), [`doc/step-response.md`](doc/step-response.md), [`doc/two-channel-delay.md`](doc/two-channel-delay.md) and [`doc/pulse-height-spectrum.md`](doc/pulse-height-spectrum.md). Every demonstration is validated against its simulator truth in `tests/validation`. None of these conventions claims compliance with a standard.

## Development

```bash
python -m pip install -e ".[test]"
python -m pytest
python -m ruff check .
```

Installing the project registers `org.datalab.pulse-characterization` through the
`datalab.plugins` entry-point group. Put host-independent algorithms in `core`,
compose them into headless recipes in `workflow`, and keep DataLab or browser
integration in `adapters`. The generated architecture test preserves these
dependency boundaries as the plugin grows.

## Single-channel campaign recipe

The headless recipe
`org.datalab.pulse-characterization:single-channel-campaign` accepts an ordered
series of signals. Inputs may carry a positive integer shot number in
`plugin.org.datalab.pulse-characterization.shot`; otherwise input order defines
the shot number. Recipe contract `1.1.0` returns an amplitude-vs-shot
`SignalObj`, raw and half-height-aligned campaign means, and a per-shot
`TableResult` attached to the amplitude signal.

Sigima remains the authority for pulse shape, polarity, amplitude, offset, rise
and fall times, FWHM, and `x0`/`x50`/`x100`. The plugin adds these explicit
non-normative conventions:

- **Integral:** trapezoidal integral of
	`polarity * (raw_signal - raw_baseline_mean)`.
- **SNR:** `20*log10(amplitude / baseline_noise_rms)`. Step signals use the
	initial baseline; square signals combine the initial and final baselines.
- **Quality:** `NO_PULSE`, `SATURATED`, `MULTIPLE_PULSES`, and `LOW_SNR` are
	evaluated in that order. Valid shots may then become `OUTLIER` from their
	amplitude modified Z-score. Every rejected row records its reason, threshold,
	and triggering values.

If Sigima cannot extract features from a flat acquisition, the shot remains in
the campaign as `NO_PULSE`; Sigima-specific columns are `null` and the extraction
reason is retained in its diagnostic.

Non-finite core values such as the infinite SNR of a noiseless acquisition are
serialized as `null` at the workflow boundary. The recipe is deliberately
limited to one channel and one acquisition configuration. Inter-channel timing is provided by the separate two-channel recipe, under the identity contract recorded in
[`doc/deferred-scope.md`](doc/deferred-scope.md); configuration comparison remains deferred.

Valid shots are aligned on their polarity-aware rising 50% crossing before the
aligned mean is computed. The reference is the observed median crossing; for
an even number of landmarks, it is the lower of the two middle observations.
Non-valid or unalignable shots remain unchanged and are excluded from both raw
and aligned means, so the comparison always uses the same subset. A valid shot
whose X domain does not contain the reference is reported with its measured
crossing and an explicit skip reason. Differently sampled inputs are resampled
onto the first aligned X grid for aggregation. See
[`doc/alignment-validation.md`](doc/alignment-validation.md) for interpolation,
audit records, no-valid-shot behavior, and the 500-shot CPython/Pyodide
measurements.

## Deterministic 500-shot simulation

Phase 5.3 adds a host-independent demonstration campaign with exact per-shot
truth:

```python
from datalab_pulse_characterization.core import (
	analyze_pulse_campaign,
	simulate_pulse_campaign,
)

simulation = simulate_pulse_campaign()
analysis = analyze_pulse_campaign(
	simulation.acquisitions,
	simulation.analysis_parameters,
)
```

The default seed produces 500 alternating Gaussian and asymmetric pulses with
slow baseline and amplitude drift. Timing jitter increases after shot 300.
Eleven acquisitions deliberately cover missing pulses, low SNR, saturation,
double pulses, and amplitude outliers. The matching analysis settings recover
489 `VALID` shots and all 11 expected explainable flags.

See [`doc/simulation.md`](doc/simulation.md) for the model, exact anomaly
distribution, truth fields, and limitations.

## Desktop and Web hosts

DataLab Desktop registers **Run pulse campaign...** through the plugin entry
point. The action starts DataLab's generic recipe launcher on the selected signals (the campaign needs at least two), opens the shared
parameter DataSet, and delegates output, anchored-result, rollback, and
provenance handling to `RecipeRunner`. Installed-wheel, hot-reload, unattended
form, cancellation, rollback, and native HDF5 round-trip gates exercise the
real host integration.

The plugin also declares two tiles with `WELCOME_TILES` in the Applications section of the DataLab welcome page: **Pulse & Transient Characterization** opens its page in the **Applications** catalog, and **Open demo campaign** generates and selects the synthetic 500-shot campaign. When the section is short of room, **Open demo campaign** moves to the menu of the main tile.

The plugin menu opens each of the five examples and runs each of the five recipes. Every recipe declares what it expects (minimum shot count, required shot-number metadata, channel hint) and checks the selection before the run: one acquisition per shot, enough samples for a step, a common X unit for two channels. The run actions delegate to DataLab's generic recipe launcher, which asks for an assignment only when the selection is ambiguous or invalid; for **Run two-channel delay...**, the reference and measured channels are proposed from their channel labels. The **Applications** catalog presents each method with its expected inputs, a live status for the current selection, and the examples designed for it; **Try with this example** opens such an example, prefills the method parameters, and runs the method. The laser warm-up campaign serves both the stability and the single-channel campaign methods.

DataLab-Web bundles the same plugin as a size- and SHA-256-checked pure-Python
wheel. Its adapter reports `verified` only for DataLab-Web 0.9.0, Pyodide
0.26.4 and plugin 0.2.0, with the campaign recipe 1.1.0 and the four other recipes 1.0.0. The browser gate executes the
deterministic 500-shot campaign, checks all visible curves and the 500-row
metrics table, and enforces explicit retained-data and WASM budgets. See
[`doc/web-qualification.md`](doc/web-qualification.md) for the evidence and
scope.
