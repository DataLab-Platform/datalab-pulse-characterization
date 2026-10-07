"""DataLab plugin package."""

PLUGIN_DESCRIPTION = (
    "Analyze repeated pulse acquisitions: timing, stability, step response, "
    "delays and spectra"
)
PLUGIN_ID = "org.datalab.pulse-characterization"
PLUGIN_NAME = "Pulse & Transient Characterization"
__version__ = "0.2.0"

__all__ = [
    "PLUGIN_DESCRIPTION",
    "PLUGIN_ID",
    "PLUGIN_NAME",
    "__version__",
]
