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
	`verified` for the pinned 0.9.0 / Pyodide 0.26.4 matrix after visible-output,
	transaction, wheel-integrity, and memory gates passed.
- Freeze the V1 scope at one channel and one acquisition configuration; defer
	inter-channel timing and configuration comparison until their data,
	scientific-validation, and host-qualification gates are defined.
- Connect the DataLab Applications catalog to the existing Pulse workflow and
	project documentation.
- Add a dedicated plugin icon and two DataLab welcome page tiles: one opens the Pulse application page, the other opens the demo campaign.
- Add a shot-to-shot stability recipe: trigger-referenced timing jitter, timing and amplitude drifts, amplitude and energy stability, overlapping Allan deviations and jitter regime-change detection, with a generated laser warm-up demonstration.
- Add a step-response recipe: histogram state levels, rise time with instrument correction, overshoot, settling time, ringing frequency, damping ratio and bandwidth of the equivalent second-order system, with a generated amplifier demonstration.
- Activate the two-channel part of V2: a recipe pairing reference and measured channels by shot number to measure CFD and cross-correlation delays, relative and common-mode jitter and amplitude correlation, with missing-channel diagnostics and a generated demonstration.
- Add a pulse-height spectrum recipe: event classification (threshold, pile-up, saturation), charge or peak-height spectrum, Gaussian photopeak fits, linear energy calibration and energy resolution, with a generated NaI(Tl) Cs-137/Co-60 demonstration.
- Add an opt-in linear timing drift to the campaign simulator, keeping the default campaign bitwise identical.
- Declare what each recipe expects (slot titles and descriptions, minimum shot counts, required shot-number metadata) and check selections before the run, so DataLab can tell whether the current selection is usable and why.
- Let DataLab's generic launcher run the recipes on Desktop, replacing the two-channel role dialog; reference and measured channels are still proposed from their labels.
- Pair the laser warm-up demonstration with both the stability and single-channel campaign methods; example parameter values are now keyed by method.
- Document how to set shot numbers and channel labels on your own signals with DataLab's Add metadata dialog (`doc/preparing-signals.md`).
- Add an oscilloscope simulator tool, in DataLab Desktop and DataLab-Web: a laser pulse, an amplifier step or a delayed pulse pair seen through a time base, vertical scales and an n-bit ADC, with a live view, and acquisitions tagged for the Pulse methods (`doc/oscilloscope-simulator.md`).
