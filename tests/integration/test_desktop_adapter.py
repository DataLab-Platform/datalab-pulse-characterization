"""Contract tests for the generated DataLab plugin."""

from datalab.plugins import PluginCapability

from datalab_pulse_characterization.adapters import desktop
from datalab_pulse_characterization.workflow import PULSE_CAMPAIGN_RECIPE


def test_plugin_descriptor() -> None:
    """The generated entry point exposes stable SDK metadata."""
    plugin_class = desktop.PulseTransientCharacterizationPlugin
    assert plugin_class.get_plugin_id() == "org.datalab.pulse-characterization"
    assert plugin_class.PLUGIN_INFO.version == "0.1.0"
    assert plugin_class.PLUGIN_INFO.capabilities == frozenset(
        {
            PluginCapability.APPLICATION,
            PluginCapability.PROCESSING,
        }
    )
    assert plugin_class.RECIPES == (PULSE_CAMPAIGN_RECIPE,)
