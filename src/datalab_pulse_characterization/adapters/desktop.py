"""DataLab Desktop plugin adapter."""

from __future__ import annotations

import sigima.proc.signal as sips
from datalab.config import _
from datalab.plugins import PluginBase, PluginCapability, PluginInfo

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..workflow import RECIPES as WORKFLOW_RECIPES


class PulseTransientCharacterizationPlugin(PluginBase):
    """Expose the plugin to DataLab Desktop."""

    PLUGIN_INFO = PluginInfo(
        id=PLUGIN_ID,
        name=PLUGIN_NAME,
        version=__version__,
        description=PLUGIN_DESCRIPTION,
        capabilities=(
            PluginCapability.APPLICATION,
            PluginCapability.PROCESSING,
        ),
    )
    RECIPES = WORKFLOW_RECIPES

    def register_computations(self) -> None:
        """Register the sample processing owned by this plugin."""
        self.signalpanel.processor.register_1_to_1(
            sips.derivative,
            _("Derivative"),
            feature_id="org.datalab.pulse-characterization:sample-processing",
            owner_plugin_id=self.plugin_id,
        )

    def create_actions(self) -> None:
        """Create plugin actions after the DataLab panels are ready."""
