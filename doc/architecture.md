# Architecture

`datalab_pulse_characterization` uses inward-facing dependencies:

```text
adapters -> workflow -> core
```

- `core` owns host-independent domain behavior and does not import DataLab.
- `workflow` may use DataLab's headless recipe contracts, but not GUI modules.
- `adapters/desktop.py` is the installed DataLab plugin entry point.
- `adapters/web.py` records Web support explicitly and starts as unsupported.

The package root exposes identity metadata without importing a host adapter.
`tests/unit/test_architecture.py` checks these boundaries as the project grows.

## Pulse campaign flow

```text
SignalObj inputs
	-> workflow.campaign (SDK validation and metadata)
	-> core.campaign (Sigima PulseFeatures plus plugin metrics and diagnostics)
	-> amplitude-vs-shot SignalObj
	-> anchored per-shot TableResult
```

`core.campaign` operates only on immutable NumPy acquisitions and Sigima pulse
features. It owns baseline selection, polarity-oriented integration, raw-noise
SNR, deterministic quality classification, and robust amplitude outliers.
`core.metadata` owns the `plugin.org.datalab.pulse-characterization.*`
namespace.

`workflow.campaign` converts DataLab recipe inputs and guidata parameters into
the core types. It preserves explicit shot numbers, translates invalid shots
into structured `RecipeDiagnostic` values, builds the anchor and table, and
normalizes non-finite numbers for strict JSON serialization. It does not import
GUI modules or register host actions.

An acquisition for which Sigima cannot extract pulse features remains in the
batch as an explainable `NO_PULSE` row with null feature columns. The core emits
progress after every independently analyzed shot; the workflow checks the SDK
cancellation callback at that boundary, limiting cancellation latency to one
shot.

The batch processes one acquisition at a time and does not construct a 2-D
campaign stack. Phase 5.2 does not include synthetic campaign generation,
alignment, host UI integration, or multi-channel analysis.

## Synthetic campaign flow

```text
PulseSimulationParameters
	-> core.simulation (seeded NumPy generation)
	-> PulseAcquisition[500] + PulseSimulationTruth
	-> core.campaign (unchanged production analysis path)
	-> explainable status comparison
```

`core.simulation` depends on the same immutable acquisition and parameter types
as production analysis. It does not duplicate feature extraction or quality
classification. The returned `analysis_parameters` describe the thresholds
used to compare generated truth with `core.campaign`; all measured features and
statuses still come from the normal Sigima-backed path.

Simulation truth is test and demonstration evidence only. It is not imported by
the workflow recipe and does not weaken the requirement for documented real
acquisitions and scientific review before a stable release.
