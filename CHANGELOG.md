# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Establish the independent DataLab plugin package and layered architecture.
- Add the headless single-channel campaign recipe backed by Sigima pulse
	features.
- Add polarity-oriented integral, raw-baseline SNR, and explainable quality
	diagnostics with strict JSON-friendly outputs.
- Add a deterministic 500-shot Gaussian/asymmetric campaign simulator with
	exact drift, jitter, noise, and anomaly truth.
- Add polarity-aware 50% crossing alignment, matched raw/aligned campaign
	means, and per-shot alignment audit values to recipe contract `1.1.0`.
- Record report-only 500-shot performance and alignment-quality measurements
	under CPython and browser-main-thread Pyodide.
