"""Headless recipe registry."""

from __future__ import annotations

from datalab.recipes import (
    RecipeCardinality,
    RecipeDescriptor,
    RecipeInputSlot,
    RecipeObjectType,
)

from .. import PLUGIN_ID, __version__
from .campaign import PulseCampaignRecipeParameters, run_pulse_campaign

PULSE_CAMPAIGN_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:single-channel-campaign",
    plugin_version=__version__,
    title="Single-channel pulse campaign",
    version="1.1.0",
    description=(
        "Extract Sigima pulse features, align valid shots at their 50% crossings, "
        "and consolidate explainable diagnostics across repeated acquisitions."
    ),
    inputs=(
        RecipeInputSlot(
            "signals",
            RecipeObjectType.SIGNAL,
            RecipeCardinality.MANY,
        ),
    ),
    parameter_class=PulseCampaignRecipeParameters,
    run=run_pulse_campaign,
)

RECIPES: tuple[RecipeDescriptor, ...] = (PULSE_CAMPAIGN_RECIPE,)

__all__ = ["PULSE_CAMPAIGN_RECIPE", "RECIPES"]
