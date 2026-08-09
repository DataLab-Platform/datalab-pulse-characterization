# Pulse & Transient Characterization

Analyze repeated pulse acquisitions, timing and shot-to-shot stability

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
single-channel; multi-channel comparison belongs to a later phase.

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
point. The action requires at least two selected signals, opens the shared
parameter DataSet, and delegates output, anchored-result, rollback, and
provenance handling to `RecipeRunner`. Installed-wheel, hot-reload, unattended
form, cancellation, rollback, and native HDF5 round-trip gates exercise the
real host integration.

DataLab-Web bundles the same plugin as a size- and SHA-256-checked pure-Python
wheel. Its adapter reports `verified` only for DataLab-Web 0.8.0, Pyodide
0.26.4, plugin 0.1.0, and recipe 1.1.0. The browser gate executes the
deterministic 500-shot campaign, checks all visible curves and the 500-row
metrics table, and enforces explicit retained-data and WASM budgets. See
[`doc/web-qualification.md`](doc/web-qualification.md) for the evidence and
scope.
