# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

First version of the Pulse & Transient Characterization plugin.

Methods:

- Single-channel pulse campaign: per-shot features from Sigima, integral and SNR, explainable quality flags, and raw and aligned mean pulses with a per-shot metrics table.
- Shot-to-shot stability: timing jitter, drifts, amplitude and energy stability, Allan deviations and detection of a jitter regime change.
- Step response: state levels, rise time with instrument correction, overshoot, settling time, ringing, damping ratio and bandwidth.
- Two-channel delay and jitter: CFD and cross-correlation delays, relative and common-mode jitter, and amplitude correlation, with shots paired by number.
- Pulse-height spectrum: event classification, charge or peak-height spectrum, photopeak fits, energy calibration and resolution.
- Selection checks before every run, with clear diagnostics.

Tools and examples:

- Oscilloscope simulator: laser pulses, amplifier steps or delayed pulse pairs through a time base, vertical scales and an ADC, with a live view and acquisitions ready for the methods.
- One generated demonstration per method, validated against its simulator truth.
- Guide to set shot numbers and channel labels on your own signals.

DataLab integration:

- DataLab Desktop: plugin menu, Applications catalog, welcome page tiles, and results saved with their provenance in DataLab workspaces.
- DataLab-Web: the same methods, verified for DataLab-Web 0.9.0 and Pyodide 0.26.4.

Quality:

- CPython and browser benchmarks of the 500-shot campaign and its alignment.
