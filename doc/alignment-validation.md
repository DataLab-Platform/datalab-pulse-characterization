# Pulse Alignment and Performance

## Headless Contract

`align_pulse_campaign()` aligns shots classified as `VALID` on their
polarity-aware rising 50% crossing. It uses `PulseFeatures.x50` when available
and falls back to Sigima's full-waveform `find_crossing_at_ratio()` for valid
step or square pulses whose extracted `x50` is absent. The default reference is
the observed median crossing; an even number of landmarks uses the lower of
the two middle observations. Callers may provide another finite reference. A
valid acquisition whose X range does not contain the chosen reference remains
unchanged and receives an explicit skip record instead of aborting the
campaign.

Each waveform is translated by linear interpolation on its original X grid.
Samples requested beyond the source range use the corresponding constant edge
value. The source acquisitions remain immutable. Non-valid shots are retained
unchanged and receive an explicit skip record. A campaign with no valid shot is
still reportable with `reference_x=None` and no comparative means. A valid shot
whose crossing cannot be measured is also retained with an explicit reason.

The recipe aggregates the same alignable subset twice and emits **Raw pulse
campaign mean** and **Aligned pulse campaign mean**. This gives users a direct
raw/aligned comparison without materializing 500 recipe outputs. Aggregation
uses the first aligned acquisition's X grid and linearly resamples other alignable
shots onto it with the same constant-edge convention. It accumulates a
streaming mean rather than a campaign stack. The shot table records whether
each acquisition was aligned, its half-height landmark, and the applied X
shift or skip reason. The recipe contract is version `1.1.0`.

Cross-correlation is not implemented. Half-height alignment is deterministic,
explainable, stable on flat-topped pulses, polarity-aware, and has no
template-selection convention.

## Benchmark Method

[`benchmarks/benchmark_alignment.py`](../benchmarks/benchmark_alignment.py)
measures deterministic generation, production analysis, and alignment plus the
two means. It reports elapsed time, Python allocation peak when `tracemalloc` is
available, truth/status mismatches, and theoretical `x50` dispersion. It defines no
pass/fail performance budget. Alignment quality is measured independently from
the implementation: the simulator's commanded profile and center define the
theoretical rising 50% crossing before and after the recovered shift.

The representative configuration contains 500 shots of 501 samples with seed
`20260809`. Both host runners inject the local Sigima `1.1.6` and Pulse `0.1.0`
wheels and record their SHA-256 hashes. The browser measurement uses
DataLab-Web's established bare-browser benchmark host
(`tests/benchmark/bench1/browser/index.html`): Pyodide `0.26.4` runs on
Chromium's main thread with the benchmark project's anti-throttling flags.

```powershell
Push-Location ..\Sigima
python scripts/run_with_env.py python -m build --wheel
Pop-Location
python -m build --wheel
python benchmarks/run_cpython_wheels.py `
	--output benchmarks/results/cpython-windows-2026-08-09.json
node benchmarks/run_pyodide_browser.mjs `
	--output benchmarks/results/pyodide-browser-2026-08-09.json
```

Set `DATALAB_WEB_ROOT` or `SIGIMA_ROOT` when those sibling checkouts are not in
their default directories. This matches DataLab-Web's pinned Pyodide and avoids
macro/notebook workers, but it does not include React, recipe dispatch, or host
commit time.

## Reference Observation

Measurements recorded on 2026-08-09 on the same Windows host:

| Metric | CPython | Browser Pyodide |
| --- | ---: | ---: |
| Generation | 0.124 s | 0.424 s |
| Analysis | 5.560 s | 11.228 s |
| Alignment and means | 0.053 s | 0.103 s |
| Total | 5.737 s | 11.755 s |
| Throughput | 87.15 shots/s | 42.54 shots/s |
| Python allocation peak | 9,489,906 B | 8,681,312 B |
| WASM heap growth | n/a | 0 B |

Both hosts aligned 489 valid shots, reproduced every expected status, and
reduced theoretical `x50` deviation from `0.0808869` to `0.00485714`, a 94%
reduction below the simulation's `0.02` sampling interval. Alignment and
aggregation took about 0.9% of total time on both hosts; feature extraction
dominates.

These single-run observations are evidence, not performance guarantees. The
synthetic profiles do not include trigger artifacts, ringing, quantization, or
instrument transfer functions. Because simple half-height alignment already
reduces the independent timing metric below one sample at small incremental
cost, cross-correlation is deferred until a documented real campaign shows
residual timing or shape error
that justifies its additional conventions and cost.

Raw reports are archived in
[`benchmarks/results`](../benchmarks/results/).