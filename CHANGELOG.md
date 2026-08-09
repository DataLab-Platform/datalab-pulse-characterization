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
- Register the campaign as a transactional DataLab Desktop action and qualify
	the installed wheel, parameter form, hot reload, rollback, provenance, and
	native HDF5 round trip.
- Add a DataLab-Web adapter and deterministic browser campaign, promoted to
	`verified` for the pinned 0.8.0 / Pyodide 0.26.4 matrix after visible-output,
	transaction, wheel-integrity, and memory gates passed.
- Freeze the V1 scope at one channel and one acquisition configuration; defer
	inter-channel timing and configuration comparison until their data,
	scientific-validation, and host-qualification gates are defined.
