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
