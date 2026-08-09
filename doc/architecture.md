# Architecture

`datalab_pulse_characterization` uses inward-facing dependencies:

```text
adapters -> workflow -> core
```

- `core` owns host-independent domain behavior and does not import DataLab.
- `workflow` may use DataLab's headless recipe contracts, but not GUI modules.
- `adapters/desktop.py` is the installed DataLab plugin entry point.
- `adapters/web.py` records the exact verified DataLab-Web/Pyodide matrix.

The package root exposes identity metadata without importing a host adapter.
`tests/unit/test_architecture.py` checks these boundaries as the project grows.

## Pulse campaign flow

```text
SignalObj inputs
	-> workflow.campaign (SDK validation and metadata)
	-> core.campaign (Sigima PulseFeatures plus plugin metrics and diagnostics)
	-> core.alignment (observed valid lower median x50 plus interpolation)
	-> amplitude-vs-shot SignalObj
	-> matched raw/aligned campaign means
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
campaign stack. Alignment also uses one acquisition at a time; its raw and
aligned means are accumulated over the same valid subset. The sole registered
recipe represents repeated shots from one channel under one acquisition
configuration. It neither infers channel/configuration identity nor computes
comparisons across them. The deferred contracts and activation gates are
recorded in [`deferred-scope.md`](deferred-scope.md).

`core.alignment` keeps raw and aligned acquisitions side by side with one
immutable decision record per shot. It aligns only `VALID` shots on their
polarity-aware rising 50% crossing and retains all non-valid or unalignable
shots unchanged. The default reference is the observed median crossing, using
the lower of the two middle observations for an even count. Consequently,
disjoint X domains cannot place the reference between every acquisition;
incompatible valid domains receive an explicit skip record instead of aborting
the campaign.
Linear interpolation preserves each per-shot X grid and uses constant edge
values outside the shifted source range. Aggregation resamples onto the first
aligned X grid and never materializes a 2-D stack.

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
