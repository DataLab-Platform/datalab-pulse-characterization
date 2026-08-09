# Pulse & Transient Characterization

Analyze repeated pulse acquisitions, timing and shot-to-shot stability

## Development

```bash
python -m pip install -e ".[test]"
python -m pytest
python -m ruff check .
```

Installing the project registers `org.datalab.pulse-characterization` through the
`datalab.plugins` entry-point group. Put host-independent algorithms in `core`,
compose them into headless recipes in `workflow`, and keep DataLab or browser
integration in `adapters`. The generated architecture test preserves these
dependency boundaries as the plugin grows.
