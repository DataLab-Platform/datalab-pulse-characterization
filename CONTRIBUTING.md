# Contributing

Install the project in editable mode and run its checks before submitting a
change:

```bash
python -m pip install -e ".[test]"
python -m pytest
python -m ruff check .
```

Keep domain algorithms in `core`, headless orchestration in `workflow`, and
host-specific behavior in `adapters`. Add focused tests at the same layer as
the behavior under test.

## Branches

Day-to-day work lands on `develop`, the default branch: open pull requests against it. `main` is the release branch. It will be created at the first release, once the DataLab version that provides the plugin SDK is published; after that, `develop` is merged into `main` only to cut a release. This is the same model as DataLab, Sigima and DataLab-Web.
