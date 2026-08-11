"""Thin DataLab-Web adapter for the bundled Pulse workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from datalab.plugin_examples import PluginExampleData
from datalab.plugins import PluginBase, PluginCapability, PluginInfo
from datalab.recipes import (
    RecipeExecutionContext,
    RecipeInputs,
    RecipeOutcome,
    RecipeValidationError,
)
from sigima.objects import SignalObj

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..demo import PULSE_DEMO, apply_parameter_values, build_simulated_campaign
from ..workflow import (
    PULSE_CAMPAIGN_RECIPE,
    PulseCampaignRecipeParameters,
)

WEB_STATUS = "verified"
DATALAB_WEB_VERSION = "0.8.0"
PYODIDE_VERSION = "0.26.4"


class PulseTransientCharacterizationWebPlugin(PluginBase):
    """Declare the Pulse application contract supported by DataLab-Web."""

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
    RECIPES = (PULSE_CAMPAIGN_RECIPE,)
    EXAMPLES = (PULSE_DEMO,)

    def create_actions(self) -> None:
        """Application actions are provided by DataLab-Web's generic host."""

    @classmethod
    def materialize_example(cls, example_id: str) -> PluginExampleData | None:
        """Build the deterministic browser qualification campaign."""
        cls.get_example(example_id)
        if example_id != PULSE_DEMO.id:
            return None
        signals, parameter_values = build_simulated_campaign()
        return PluginExampleData(signals, parameter_values)


def get_web_manifest() -> dict[str, str]:
    """Return the explicit browser bundle and compatibility contract."""
    return {
        "plugin_id": PLUGIN_ID,
        "plugin_version": __version__,
        "web_status": WEB_STATUS,
        "datalab_web_version": DATALAB_WEB_VERSION,
        "pyodide_version": PYODIDE_VERSION,
        "recipe_id": PULSE_CAMPAIGN_RECIPE.recipe_id,
        "recipe_version": PULSE_CAMPAIGN_RECIPE.version,
    }


def build_recipe_inputs(signals: Sequence[SignalObj]) -> RecipeInputs:
    """Map browser-selected signals to the shared campaign recipe slot."""
    signal_values = tuple(signals)
    if any(not isinstance(signal, SignalObj) for signal in signal_values):
        raise RecipeValidationError("Pulse Web inputs must be signal objects")
    if len(signal_values) < 2:
        raise RecipeValidationError("Pulse Web inputs require at least two signals")
    return {"signals": signal_values}


def _set_parameter_values(
    parameters: PulseCampaignRecipeParameters,
    parameter_values: Mapping[str, object],
) -> None:
    """Apply browser parameter values after validating every public name."""
    apply_parameter_values(parameters, parameter_values)


def run_pulse_campaign_recipe(
    signals: Sequence[SignalObj],
    parameter_values: Mapping[str, object] | None = None,
    context: RecipeExecutionContext | None = None,
) -> RecipeOutcome:
    """Run the shared recipe for browser-imported signals without GUI calls."""
    parameters = PulseCampaignRecipeParameters()
    _set_parameter_values(parameters, dict(parameter_values or {}))
    return PULSE_CAMPAIGN_RECIPE.run(
        build_recipe_inputs(signals),
        parameters,
        context or RecipeExecutionContext(),
    )


__all__ = [
    "DATALAB_WEB_VERSION",
    "PULSE_DEMO",
    "PYODIDE_VERSION",
    "PulseTransientCharacterizationWebPlugin",
    "WEB_STATUS",
    "build_recipe_inputs",
    "build_simulated_campaign",
    "get_web_manifest",
    "run_pulse_campaign_recipe",
]
