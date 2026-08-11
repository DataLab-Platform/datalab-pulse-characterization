# DataLab-Web Qualification

The Pulse Web adapter is tested against one explicit browser matrix:

| Component             | Version |
| --------------------- | ------- |
| DataLab-Web           | 0.9.0   |
| Pyodide               | 0.26.4  |
| Pulse plugin          | 0.1.0   |
| Pulse campaign recipe | 1.1.0   |

## Visible workflow gate

The Playwright gate boots DataLab-Web's worker-hosted Pyodide runtime, creates
the documented deterministic 500-shot campaign, and executes the shared
headless recipe. The Web host transactionally commits three signal outputs,
attaches the shot metrics `TableResult` to the amplitude anchor, and persists
one `RecipeRunRecord` on every output.

The browser test then uses the normal React object tree, Plotly view, and
Results panel to require all of the following visible evidence:

- **Pulse amplitude vs shot**, **Raw pulse campaign mean**, and
  **Aligned pulse campaign mean** line traces;
- the **Pulse campaign shot metrics** table with 500 rows and 23 columns;
- all six explainable statuses, with 489 `VALID` shots and 489 aligned shots.

Separate Python bridge gates inject failures during demo-input and recipe-output
insertion and require exact object-tree rollback. They also verify the anchored
table, all status counts, output UUIDs, and shared recipe provenance.

## Pyodide memory budget

Memory is measured after creating the inputs and running Python garbage
collection, so Pyodide startup, package installation, and simulator temporary
arrays are outside the increment. The recipe must satisfy both limits:

- incremental WASM linear heap: at most 64 MiB;
- retained output signal arrays: exactly 24,032 bytes for this fixed campaign.

The qualified Windows/Chromium run on 2026-08-11 retained 4,008,000 bytes of
input arrays, grew the WASM heap by 0 bytes, and retained 24,032 bytes of output
arrays.
DataLab-Web's retained-data counter has a regression gate ensuring a signal's
`data` alias does not count its Y array twice.

## Scope

This gate qualifies browser distribution, execution, host commit, visible
rendering, deterministic status recovery, and demo-workspace memory. It does
not establish calibrated metrology, scientific validation on real instruments,
or support for multi-channel/configuration comparison. After this evidence was
recorded, a separate reviewed manifest change advanced `web_status` from
`untested` to `verified`; that status applies only to the version matrix above.