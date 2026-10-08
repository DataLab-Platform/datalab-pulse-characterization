# Qualification

[← Documentation index](README.md)

The plugin is **Alpha**: it is validated on synthetic data with known truth, in DataLab Desktop and DataLab-Web. Stable also needs documented real acquisitions and an independent scientific review of the conventions. None of these steps is metrological validation.

## Synthetic Validation

`tests/validation` compares each generated demonstration with its simulator truth. The tolerances are in the Demonstration section of each method page. For the [pulse campaign](pulse-campaign.md#demonstration), the 500 shots must give exactly 489 `VALID` shots and the 11 expected flags.

`tests/integration` builds the wheel, installs it in a temporary folder and loads the plugin through its entry point. It also covers hot reload, the parameter form, cancellation, rollback, and a save and reload in a DataLab workspace with provenance.

## Alignment Benchmark

[`benchmarks/benchmark_alignment.py`](../benchmarks/benchmark_alignment.py) measures the generation, analysis and alignment of the 500-shot campaign (501 samples per shot, seed `20260809`). It reports elapsed time, Python allocation peak, status mismatches against the truth, and the spread of the theoretical 50 % crossings before and after alignment. It defines no pass/fail budget.

Both runners use local Sigima and Pulse wheels and record their SHA-256. The browser runner uses DataLab-Web's bare benchmark page, with Pyodide 0.26.4 on Chromium's main thread; it does not include the React interface or the host commit.

```powershell
Push-Location ..\Sigima
python scripts/run_with_env.py python -m build --wheel
Pop-Location
python -m build --wheel
python benchmarks/run_cpython_wheels.py --output benchmarks/results/cpython-windows-2026-08-09.json
node benchmarks/run_pyodide_browser.mjs --output benchmarks/results/pyodide-browser-2026-08-09.json
```

Set `DATALAB_WEB_ROOT` or `SIGIMA_ROOT` when these checkouts are not next to this one. Reference run on 2026-08-09, on one Windows host:

| Metric | CPython | Browser Pyodide |
| --- | ---: | ---: |
| Generation | 0.124 s | 0.424 s |
| Analysis | 5.560 s | 11.228 s |
| Alignment and means | 0.053 s | 0.103 s |
| Total | 5.737 s | 11.755 s |
| Throughput | 87.15 shots/s | 42.54 shots/s |
| Python allocation peak | 9,489,906 B | 8,681,312 B |
| WASM heap growth | n/a | 0 B |

Both hosts aligned 489 valid shots and found every expected status. Alignment reduced the spread of the theoretical crossings from 0.0809 to 0.0049, below the 0.02 sampling interval. Alignment took about 0.9 % of the time: feature extraction dominates. Cross-correlation alignment waits for a real campaign that shows a residual timing error. Raw reports are in [`benchmarks/results`](../benchmarks/results/).

## DataLab-Web

The Web adapter reports `verified` only for this matrix:

| Component | Version |
| --- | --- |
| DataLab-Web | 0.9.0 |
| Pyodide | 0.26.4 |
| Pulse plugin | 0.2.0 |
| Pulse campaign recipe | 1.1.0 |
| Stability, step response, two-channel and spectrum recipes | 1.0.0 |

DataLab-Web's `tests/e2e/application_methods.spec.ts` opens each example through its deep link, runs its method from the **Applications** dialog and checks the outputs in the object tree. The two-channel example must bind its channels from their labels without asking. For the 500-shot campaign, a Playwright gate also requires:

- visible **Pulse amplitude vs shot**, **Raw pulse campaign mean** and **Aligned pulse campaign mean** curves;
- the **Pulse campaign shot metrics** table with 500 rows, and 489 `VALID` and aligned shots;
- an incremental WASM heap of at most 64 MiB, and exactly 24,032 bytes of retained output arrays.

Python bridge tests inject failures while inserting inputs and outputs, and require an exact rollback. The reference run on 2026-08-11 grew the WASM heap by 0 bytes.
