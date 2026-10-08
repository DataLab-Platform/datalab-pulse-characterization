"""DataLab Desktop plugin adapter.

DataLab runs the recipes through its generic interaction: it assigns the
selected signals to the recipe inputs (channels from their metadata), checks
them, edits the parameters, then runs the recipe.
"""

from __future__ import annotations

from datalab.config import _
from datalab.plugins import PluginBase, PluginCapability, PluginInfo
from datalab.plugins.examples import PluginExample, PluginExampleData
from datalab.plugins.recipes import RecipeOutcome
from datalab.plugins.tiles import WelcomeTile

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..demo import (
    EXAMPLES as DEMO_EXAMPLES,
)
from ..demo import (
    PULSE_DEMO,
    SPECTRUM_DEMO,
    STABILITY_DEMO,
    STEP_RESPONSE_DEMO,
    TWO_CHANNEL_DEMO,
    materialize_generated_example,
)
from ..simulator import OSCILLOSCOPE_SIMULATOR_TOOL, OscilloscopeSimulator
from ..workflow import (
    PULSE_CAMPAIGN_RECIPE,
    PULSE_HEIGHT_RECIPE,
    PULSE_STABILITY_RECIPE,
    STEP_RESPONSE_RECIPE,
    TWO_CHANNEL_DELAY_RECIPE,
)
from ..workflow import (
    RECIPES as WORKFLOW_RECIPES,
)

PLUGIN_ICON = "datalab_pulse_characterization:icons/pulse_characterization.svg"
DEMO_ICON = "datalab_pulse_characterization:icons/pulse_demo.svg"


class PulseTransientCharacterizationPlugin(PluginBase):
    """Expose the plugin to DataLab Desktop."""

    PLUGIN_INFO = PluginInfo(
        id=PLUGIN_ID,
        name=PLUGIN_NAME,
        version=__version__,
        description=PLUGIN_DESCRIPTION,
        icon=PLUGIN_ICON,
        capabilities=(
            PluginCapability.APPLICATION,
            PluginCapability.PROCESSING,
        ),
        documentation_url=(
            "https://github.com/DataLab-Platform/datalab-pulse-characterization"
        ),
    )
    RECIPES = WORKFLOW_RECIPES
    EXAMPLES = DEMO_EXAMPLES
    TOOLS = (OSCILLOSCOPE_SIMULATOR_TOOL,)
    WELCOME_TILES = (
        WelcomeTile(
            id="application",
            title=PLUGIN_NAME,
            description=PLUGIN_DESCRIPTION,
            icon=PLUGIN_ICON,
        ),
        WelcomeTile(
            id="demo-campaign",
            title=_("Open demo campaign"),
            description=_("Generate and select the synthetic 500-shot pulse campaign"),
            icon=DEMO_ICON,
            launcher="open_demo_campaign",
        ),
    )

    @classmethod
    def materialize_example(cls, example_id: str) -> PluginExampleData | None:
        """Build one deterministic demonstration campaign in memory."""
        cls.get_example(example_id)
        return materialize_generated_example(example_id)

    def oscilloscope_simulator(self) -> OscilloscopeSimulator:
        """Return a new oscilloscope simulator."""
        return OscilloscopeSimulator()

    def open_demo_campaign(self) -> PluginExample | None:
        """Open the demonstration campaign from the plugin menu."""
        return self.launch_example(PULSE_DEMO.id)

    def open_stability_demo(self) -> PluginExample | None:
        """Open the laser warm-up stability demonstration."""
        return self.launch_example(STABILITY_DEMO.id)

    def open_step_response_demo(self) -> PluginExample | None:
        """Open the amplifier step-response demonstration."""
        return self.launch_example(STEP_RESPONSE_DEMO.id)

    def open_two_channel_demo(self) -> PluginExample | None:
        """Open the two-channel delay demonstration."""
        return self.launch_example(TWO_CHANNEL_DEMO.id)

    def open_spectrum_demo(self) -> PluginExample | None:
        """Open the gamma-ray spectroscopy demonstration."""
        return self.launch_example(SPECTRUM_DEMO.id)

    def run_campaign(self) -> RecipeOutcome | None:
        """Analyze and align the selected pulse acquisitions."""
        return self.start_recipe(PULSE_CAMPAIGN_RECIPE.recipe_id)

    def run_stability(self) -> RecipeOutcome | None:
        """Analyze the shot-to-shot stability of the selected signals."""
        return self.start_recipe(PULSE_STABILITY_RECIPE.recipe_id)

    def run_step_response(self) -> RecipeOutcome | None:
        """Analyze the step response of the selected signals."""
        return self.start_recipe(STEP_RESPONSE_RECIPE.recipe_id)

    def run_spectrum(self) -> RecipeOutcome | None:
        """Build the pulse-height spectrum of the selected events."""
        return self.start_recipe(PULSE_HEIGHT_RECIPE.recipe_id)

    def run_two_channel(self) -> RecipeOutcome | None:
        """Measure the delay between the two selected channels."""
        return self.start_recipe(TWO_CHANNEL_DELAY_RECIPE.recipe_id)

    def create_actions(self) -> None:
        """Create the Pulse example and recipe actions."""
        handler = self.signalpanel.acthandler
        with handler.new_menu(PLUGIN_NAME.replace("&", "&&")):
            self.open_demo_action = handler.new_action(
                _("Open demo campaign"),
                triggered=self.open_demo_campaign,
                tip=_("Generate and select the synthetic 500-shot pulse campaign"),
                select_condition="always",
            )
            self.open_stability_demo_action = handler.new_action(
                _("Open stability example"),
                triggered=self.open_stability_demo,
                tip=_("Generate and select a synthetic laser warm-up campaign"),
                select_condition="always",
            )
            self.open_step_response_demo_action = handler.new_action(
                _("Open step-response example"),
                triggered=self.open_step_response_demo,
                tip=_("Generate and select synthetic amplifier step responses"),
                select_condition="always",
            )
            self.open_two_channel_demo_action = handler.new_action(
                _("Open two-channel example"),
                triggered=self.open_two_channel_demo,
                tip=_("Generate and select a synthetic two-channel campaign"),
                select_condition="always",
            )
            self.open_spectrum_demo_action = handler.new_action(
                _("Open gamma spectrum example"),
                triggered=self.open_spectrum_demo,
                tip=_("Generate and select synthetic scintillation events"),
                select_condition="always",
            )
            self.run_campaign_action = handler.new_action(
                _("Run pulse campaign..."),
                triggered=self.run_campaign,
                tip=_("Analyze and align the selected repeated pulse acquisitions"),
                select_condition="at_least_one",
                separator=True,
            )
            self.run_stability_action = handler.new_action(
                _("Run shot-to-shot stability..."),
                triggered=self.run_stability,
                tip=_("Measure timing jitter, drifts and amplitude stability"),
                select_condition="at_least_one",
            )
            self.run_step_response_action = handler.new_action(
                _("Run step response..."),
                triggered=self.run_step_response,
                tip=_("Measure rise time, overshoot, settling and ringing"),
                select_condition="at_least_one",
            )
            self.run_two_channel_action = handler.new_action(
                _("Run two-channel delay..."),
                triggered=self.run_two_channel,
                tip=_("Measure delay and relative jitter between two channels"),
                select_condition="at_least_one",
            )
            self.run_spectrum_action = handler.new_action(
                _("Run pulse-height spectrum..."),
                triggered=self.run_spectrum,
                tip=_("Build, calibrate and analyze an energy spectrum"),
                select_condition="at_least_one",
            )
