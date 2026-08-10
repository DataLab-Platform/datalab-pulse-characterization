"""DataLab Desktop plugin adapter."""

from __future__ import annotations

from datalab.config import _
from datalab.gui.recipe_runner import RecipeCommitError, RecipeRunner
from datalab.plugins import PluginBase, PluginCapability, PluginInfo
from datalab.recipes import RecipeOutcome, RecipeValidationError

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..workflow import (
    PULSE_CAMPAIGN_RECIPE,
    PulseCampaignRecipeParameters,
)
from ..workflow import (
    RECIPES as WORKFLOW_RECIPES,
)

MINIMUM_SELECTED_SIGNAL_COUNT = 2


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
        documentation_url=(
            "https://github.com/DataLab-Platform/datalab-pulse-characterization"
        ),
    )
    RECIPES = WORKFLOW_RECIPES
    RECIPE_LAUNCHERS = {
        PULSE_CAMPAIGN_RECIPE.recipe_id: "run_campaign_from_selection",
    }

    @staticmethod
    def can_run_campaign(_selected_groups, selected_objects) -> bool:
        """Return whether the selected signals form a repeated campaign."""
        return len(selected_objects) >= MINIMUM_SELECTED_SIGNAL_COUNT

    def edit_campaign_parameters(
        self,
        parameters: PulseCampaignRecipeParameters | None = None,
    ) -> PulseCampaignRecipeParameters | None:
        """Edit Pulse campaign parameters with the Desktop as dialog parent."""
        if self.main is None:
            raise RuntimeError("Plugin must be registered before editing parameters")
        if parameters is None:
            parameters = PulseCampaignRecipeParameters()
        elif not isinstance(parameters, PulseCampaignRecipeParameters):
            raise TypeError("Parameters must be PulseCampaignRecipeParameters")
        if parameters.edit(parent=self.main):
            return parameters
        return None

    def run_campaign_from_selection(self) -> RecipeOutcome | None:
        """Edit parameters and run the shared recipe on selected signals."""
        if self.main is None:
            raise RuntimeError("Plugin must be registered before running a recipe")
        selected_signals = tuple(
            self.signalpanel.objview.get_sel_objects(include_groups=True)
        )
        if not self.can_run_campaign((), selected_signals):
            self.show_warning(_("Select at least two signals for a Pulse campaign"))
            return None
        parameters = self.edit_campaign_parameters()
        if parameters is None:
            return None
        try:
            return RecipeRunner(self.main).run(
                PULSE_CAMPAIGN_RECIPE,
                {"signals": selected_signals},
                parameters,
            )
        except (RecipeCommitError, RecipeValidationError) as error:
            self.show_error(str(error))
            return None

    def create_actions(self) -> None:
        """Create the complete single-channel Pulse campaign action."""
        handler = self.signalpanel.acthandler
        with handler.new_menu(PLUGIN_NAME):
            self.run_campaign_action = handler.new_action(
                _("Run pulse campaign..."),
                triggered=self.run_campaign_from_selection,
                tip=_("Analyze and align the selected repeated pulse acquisitions"),
                select_condition=self.can_run_campaign,
            )
