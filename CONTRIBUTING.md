# Contributing

## Setup and Checks

Install the project in editable mode, in a Python environment where DataLab 1.3 or later is available, then run the checks before submitting a change:

```bash
python -m pip install -e ".[test]"
python -m ruff check .
python -m pytest
```

## Architecture

Dependencies point inward:

```text
adapters -> workflow -> core
```

- `core` holds the scientific code: per-shot analysis on Sigima pulse features, quality classification, alignment, the five methods and their simulators. It works on immutable NumPy acquisitions and does not import DataLab. `core.metadata` owns the `plugin.org.datalab.pulse-characterization.*` keys.
- `workflow` turns the core into headless DataLab recipes, registered in `RECIPES`. It converts inputs and parameters, checks selections, builds the output signals and tables, and turns invalid shots into diagnostics. It never imports GUI modules.
- `adapters/desktop.py` and `adapters/web.py` declare the actions, examples, tools and welcome tiles. The run actions call DataLab's generic recipe launcher; DataLab's `RecipeRunner` owns validation, transactional commit and provenance. `adapters/web.py` also records the verified DataLab-Web matrix.
- `simulator.py` exposes `core.oscilloscope` as a DataLab instrument. `demo.py` declares one generated example per method.

| Method | Core | Workflow | Demonstration simulator |
| --- | --- | --- | --- |
| Pulse campaign | `core.campaign`, `core.alignment` | `workflow.campaign` | `core.simulation` |
| Shot-to-shot stability | `core.stability` | `workflow.stability` | `core.simulation` with `timing_drift` |
| Step response | `core.step_response` | `workflow.step_response` | `core.step_simulation` |
| Two-channel delay | `core.two_channel` | `workflow.two_channel` | `core.two_channel_simulation` |
| Pulse-height spectrum | `core.spectroscopy` | `workflow.spectroscopy` | `core.spectrum_simulation` |

The analysis processes one acquisition at a time and never builds a 2D stack of the campaign. It reports progress after each shot, so cancellation waits for one shot at most. Simulators reuse the production analysis path: they never assign measured features. `tests/unit/test_architecture.py` checks the layer boundaries.

## Tests

- `tests/unit`: core, workflow and adapters.
- `tests/validation`: generated demonstrations against their simulator truth.
- `tests/integration`: installed wheel, hot reload, rollback and DataLab workspace round trip.

`benchmarks` holds explicit scripts that pytest does not collect. See [Qualification](doc/qualification.md).

## Maintenance

- **Screenshots:** regenerate `doc/images/*.png` with the plugin installed in DataLab's environment:

  ```bash
  python -m scripts.take_screenshots
  ```

- **Benchmarks:** see [Alignment benchmark](doc/qualification.md#alignment-benchmark).
- **DataLab-Web:** the wheel embeds this README. DataLab-Web bundles the wheel and checks its size and SHA-256 (`src/runtime/bundledPlugins.ts`): update them when bumping the plugin version.

## Branches

Day-to-day work lands on `develop`, the default branch: open pull requests against it. `main` is the release branch. It will be created at the first release, once the DataLab version that provides the plugin SDK is published; after that, `develop` is merged into `main` only to cut a release. This is the same model as DataLab, Sigima and DataLab-Web.
