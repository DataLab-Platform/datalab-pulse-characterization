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
the shot number. The recipe returns an amplitude-vs-shot `SignalObj` and a
per-shot `TableResult` attached to that signal.

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
serialized as `null` at the workflow boundary. Phase 5.2 is deliberately
single-channel and headless; the campaign simulator, alignment, Desktop/Web
registration, and multi-channel comparison belong to later phases.
