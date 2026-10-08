"""DataLab Desktop adapter contract tests."""

from __future__ import annotations

from importlib import resources
from types import SimpleNamespace

import numpy as np
import pytest
from datalab.adapters_metadata import TableAdapter
from datalab.env import execenv
from datalab.gui.actionhandler import ActionCategory
from datalab.gui.plugins.recipe_inputs import RecipeInputDialog
from datalab.objectmodel import get_uuid
from datalab.plugins import PluginCapability
from datalab.plugins.recipe_binding import RecipeReadinessStatus
from datalab.plugins.recipes import RECIPE_RUN_RECORD_OPTION, RecipeRunRecord
from datalab.tests import datalab_test_app_context
from guidata.dataset import update_dataset
from sigima.objects import SignalObj, create_signal

from datalab_pulse_characterization import PLUGIN_ID, PLUGIN_NAME
from datalab_pulse_characterization.adapters import desktop as desktop_adapter
from datalab_pulse_characterization.core import metadata_key
from datalab_pulse_characterization.demo import (
    EXAMPLES,
    PULSE_DEMO,
    STABILITY_DEMO,
)
from datalab_pulse_characterization.workflow import (
    CHANNEL_METADATA_KEY,
    PULSE_CAMPAIGN_RECIPE,
    PULSE_STABILITY_RECIPE,
    RECIPES,
    STEP_RESPONSE_RECIPE,
    TWO_CHANNEL_DELAY_RECIPE,
    PulseCampaignRecipeParameters,
    TwoChannelDelayRecipeParameters,
)

SHOT_METADATA_KEY = metadata_key("shot")


def _no_assignment_dialog(_dialog: RecipeInputDialog) -> bool:
    """Fail when DataLab asks the user to assign inputs that metadata define."""
    pytest.fail("The selected signals should be assigned from their metadata")


def _pulse(title: str, shot: int, center: float = 4.0) -> SignalObj:
    """Create one explicit square-pulse recipe input."""
    x = np.linspace(0.0, 10.0, 101)
    y = 4.0 * ((x >= center) & (x <= center + 2.0))
    signal = create_signal(title, x, y, units=("us", "V"))
    signal.metadata[SHOT_METADATA_KEY] = shot
    return signal


def _parameters() -> PulseCampaignRecipeParameters:
    """Return deterministic parameters for the explicit test pulses."""
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.use_explicit_ranges = True
    parameters.xstartmin = 0.0
    parameters.xstartmax = 1.0
    parameters.xendmin = 9.0
    parameters.xendmax = 10.0
    parameters.denoise = False
    return parameters


def test_plugin_descriptor() -> None:
    """The entry point exposes stable SDK metadata and its headless recipe."""
    plugin_class = desktop_adapter.PulseTransientCharacterizationPlugin
    assert plugin_class.get_plugin_id() == "org.datalab.pulse-characterization"
    assert plugin_class.PLUGIN_INFO.version == "0.2.0"
    assert plugin_class.PLUGIN_INFO.capabilities == frozenset(
        {
            PluginCapability.APPLICATION,
            PluginCapability.PROCESSING,
        }
    )
    assert plugin_class.get_recipes() == RECIPES
    assert plugin_class.get_examples() == EXAMPLES
    # DataLab's generic interaction runs every recipe
    assert plugin_class.get_recipe_launchers() == {}
    assert {recipe_id for example in EXAMPLES for recipe_id in example.recipe_ids} == {
        recipe.recipe_id for recipe in RECIPES
    }
    assert PULSE_DEMO.recipe_ids == (PULSE_CAMPAIGN_RECIPE.recipe_id,)
    assert STABILITY_DEMO.recipe_ids == (
        PULSE_STABILITY_RECIPE.recipe_id,
        PULSE_CAMPAIGN_RECIPE.recipe_id,
    )
    for recipe in RECIPES:
        assert recipe.check_inputs is not None
        assert all(slot.title and slot.description for slot in recipe.inputs)
    # Two channels are paired by shot number, which is therefore required
    for slot in TWO_CHANNEL_DELAY_RECIPE.inputs:
        assert [(item.key, item.required) for item in slot.metadata] == [
            (SHOT_METADATA_KEY, True),
            (CHANNEL_METADATA_KEY, False),
        ]
    assert plugin_class.PLUGIN_INFO.documentation_url == (
        "https://github.com/DataLab-Platform/datalab-pulse-characterization"
    )
    assert PULSE_CAMPAIGN_RECIPE.version == "1.1.0"
    assert PULSE_CAMPAIGN_RECIPE.parameter_class is PulseCampaignRecipeParameters


def test_plugin_declares_packaged_welcome_tiles() -> None:
    """The application and demo tiles use icons shipped with the package."""
    plugin_class = desktop_adapter.PulseTransientCharacterizationPlugin
    icons = resources.files("datalab_pulse_characterization") / "icons"

    tiles = plugin_class.get_welcome_tiles()

    assert plugin_class.PLUGIN_INFO.icon == desktop_adapter.PLUGIN_ICON
    assert [(tile.id, tile.launcher) for tile in tiles] == [
        ("application", None),
        ("demo-campaign", "open_demo_campaign"),
    ]
    assert tiles[0].title == PLUGIN_NAME
    assert [tile.icon for tile in tiles] == [
        desktop_adapter.PLUGIN_ICON,
        desktop_adapter.DEMO_ICON,
    ]
    assert (icons / "pulse_characterization.svg").is_file()
    assert (icons / "pulse_demo.svg").is_file()


def test_welcome_tiles_open_application_page_and_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default tile opens the catalog page; the demo tile opens the demo."""
    plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
    shown_pages: list[str] = []
    plugin.main = SimpleNamespace(show_applications=shown_pages.append)
    monkeypatch.setattr(
        plugin, "open_demo_campaign", lambda: desktop_adapter.PULSE_DEMO
    )

    assert plugin.launch_welcome_tile("application") is None
    assert shown_pages == [PLUGIN_ID]
    assert plugin.launch_welcome_tile("demo-campaign") is desktop_adapter.PULSE_DEMO


def test_desktop_adapter_materializes_demo_campaign() -> None:
    """The Desktop demo matches the Web qualification campaign contract."""
    plugin_class = desktop_adapter.PulseTransientCharacterizationPlugin

    data = plugin_class.materialize_example("demo")

    assert data is not None
    assert len(data.objects) == 500
    assert all(SHOT_METADATA_KEY in signal.metadata for signal in data.objects)
    assert data.values_for(PULSE_CAMPAIGN_RECIPE.recipe_id)["use_explicit_ranges"]


def test_desktop_adapter_launches_full_demo_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Desktop opens, selects, and plots the complete 500-shot campaign."""
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window
        added_notifications: list[None] = []
        selection_sizes: list[int] = []
        window.signalpanel.SIG_OBJECT_ADDED.connect(
            lambda: added_notifications.append(None)
        )
        window.signalpanel.objview.SIG_SELECTION_CHANGED.connect(
            lambda: selection_sizes.append(
                len(window.signalpanel.objview.get_sel_objects())
            )
        )
        monkeypatch.setattr(window, "confirm_memory_state", lambda: True)

        opened = plugin.launch_example("demo")

        signals = window.signalpanel.objmodel.get_all_objects()
        items = [
            window.signalpanel.plothandler.get(get_uuid(signal)) for signal in signals
        ]
        assert opened is desktop_adapter.PULSE_DEMO
        assert len(signals) == 500
        assert window.signalpanel.objview.get_sel_objects() == signals
        assert added_notifications == [None]
        assert selection_sizes == [500]
        assert all(item is not None and item.isVisible() for item in items)
        window.reset_all()


def test_demo_values_seed_the_recipes_designed_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The demo's analysis values reach its own recipes, not the others."""
    edited: list[PulseCampaignRecipeParameters] = []

    def cancel(parameters, parent) -> bool:
        edited.append(parameters)
        return False

    monkeypatch.setattr(PulseCampaignRecipeParameters, "edit", cancel)
    monkeypatch.setattr(RecipeInputDialog, "exec", _no_assignment_dialog)
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window
        monkeypatch.setattr(window, "confirm_memory_state", lambda: True)
        plugin.launch_example(PULSE_DEMO.id)
        signals = window.signalpanel.objmodel.get_all_objects()

        values = plugin.example_parameter_values(
            PULSE_CAMPAIGN_RECIPE.recipe_id, signals
        )
        assert values["use_explicit_ranges"] is True
        for recipe in (PULSE_STABILITY_RECIPE, STEP_RESPONSE_RECIPE):
            assert plugin.example_parameter_values(recipe.recipe_id, signals) == {}

        assert plugin.run_campaign() is None
        (parameters,) = edited
        assert parameters.use_explicit_ranges is True
        assert parameters.denoise == values["denoise"]
        assert len(window.signalpanel) == 500
        window.reset_all()


def test_desktop_entry_points_require_registered_plugin() -> None:
    """Methods need the Desktop window they act on."""
    plugin = desktop_adapter.PulseTransientCharacterizationPlugin()

    for entry_point in (plugin.run_campaign, plugin.run_two_channel):
        with pytest.raises(RuntimeError, match="registered"):
            entry_point()


def test_desktop_action_commits_curves_table_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The visible action runs the shared recipe on the selected campaign."""
    inputs = (_pulse("Shot 10", 10, 3.9), _pulse("Shot 20", 20, 4.1))
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        for signal in inputs:
            window.signalpanel.add_object(signal, set_current=False)
        window.set_current_panel("signal")
        window.signalpanel.objview.select_objects(inputs)

        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window
        handler = window.signalpanel.acthandler
        with handler.new_category(ActionCategory.PLUGINS):
            plugin.create_actions()

        def edit(parameters, parent) -> bool:
            update_dataset(parameters, _parameters())
            return True

        monkeypatch.setattr(PulseCampaignRecipeParameters, "edit", edit)
        monkeypatch.setattr(RecipeInputDialog, "exec", _no_assignment_dialog)

        handler.selected_objects_changed([], [])
        assert not plugin.run_campaign_action.isEnabled()
        handler.selected_objects_changed([], list(inputs))
        assert plugin.run_campaign_action.isEnabled()
        plugin.run_campaign_action.trigger()

        assert len(window.signalpanel) == 5
        outputs = window.signalpanel.objmodel.get_all_objects()[2:]
        assert [signal.title for signal in outputs] == [
            "Pulse amplitude vs shot",
            "Raw pulse campaign mean",
            "Aligned pulse campaign mean",
        ]
        assert window.get_current_panel() == "signal"
        assert window.signalpanel.objview.get_sel_objects() == [outputs[-1]]
        assert window.signalpanel.objview.get_current_object() is outputs[-1]
        anchor = outputs[0]
        tables = list(TableAdapter.iterate_from_obj(anchor))
        assert len(tables) == 1
        assert tables[0].result.title == "Pulse campaign shot metrics"
        assert [row[0] for row in tables[0].result.data] == [10, 20]
        records = [
            RecipeRunRecord.from_dict(
                signal.get_metadata_option(RECIPE_RUN_RECORD_OPTION)
            )
            for signal in outputs
        ]
        assert all(record == records[0] for record in records[1:])
        assert records[0].recipe_id == PULSE_CAMPAIGN_RECIPE.recipe_id


def _select(window, signals) -> None:
    """Add signals to the signal panel and select them."""
    for signal in signals:
        window.signalpanel.add_object(signal, set_current=False)
    window.set_current_panel("signal")
    window.signalpanel.objview.select_objects(signals)


def test_desktop_action_cancellation_preserves_campaign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling the parameter form leaves all selected signals unchanged."""
    inputs = (_pulse("Shot 1", 1), _pulse("Shot 2", 2))
    monkeypatch.setattr(
        PulseCampaignRecipeParameters, "edit", lambda *_args, **_kwargs: False
    )
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        _select(window, inputs)
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window

        outcome = plugin.run_campaign()

        assert outcome is None
        assert window.signalpanel.objmodel.get_all_objects() == list(inputs)


def test_desktop_action_explains_invalid_metadata_without_partial_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid shot number is named before any computation."""
    inputs = (_pulse("Shot 1", 1), _pulse("Invalid shot", 2))
    inputs[1].metadata[SHOT_METADATA_KEY] = 0
    dialogs: list[RecipeInputDialog] = []

    def cancel(dialog: RecipeInputDialog) -> bool:
        dialogs.append(dialog)
        return False

    monkeypatch.setattr(RecipeInputDialog, "exec", cancel)
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        _select(window, inputs)
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window

        readiness = plugin.assess_recipe(PULSE_CAMPAIGN_RECIPE.recipe_id)
        outcome = plugin.run_campaign()

        assert readiness.status is RecipeReadinessStatus.NOT_READY
        assert outcome is None
        assert window.signalpanel.objmodel.get_all_objects() == list(inputs)
        (dialog,) = dialogs
        assert not dialog.ok_button.isEnabled()
        assert SHOT_METADATA_KEY in dialog.issues_label.text()


def test_desktop_two_channel_example_runs_with_channel_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two-channel example opens, binds channels from metadata and runs."""
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window
        handler = window.signalpanel.acthandler
        with handler.new_category(ActionCategory.PLUGINS):
            plugin.create_actions()
        monkeypatch.setattr(window, "confirm_memory_state", lambda: True)
        monkeypatch.setattr(RecipeInputDialog, "exec", _no_assignment_dialog)
        monkeypatch.setattr(
            TwoChannelDelayRecipeParameters,
            "edit",
            lambda _self, *, parent: True,
        )

        plugin.open_two_channel_demo_action.trigger()
        assert len(window.signalpanel.objview.get_sel_objects()) == 597
        outcome = plugin.run_two_channel()

        assert outcome is not None
        assert [output.id for output in outcome.objects] == [
            "delay_vs_shot",
            "xcorr_delay_vs_shot",
            "delay_distribution",
            "amplitude_correlation",
        ]
        anchor = outcome.objects[0].value
        titles = [table.result.title for table in TableAdapter.iterate_from_obj(anchor)]
        assert titles == ["Two-channel delay summary", "Two-channel pair metrics"]
        window.reset_all()


def test_single_channel_label_leaves_the_channel_split_to_the_user() -> None:
    """Without two channel labels, DataLab asks which signals are the reference."""
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        signals = tuple(_pulse(f"CH1 shot {shot}", shot) for shot in (1, 2, 3))
        for signal in signals:
            signal.metadata[CHANNEL_METADATA_KEY] = "CH1"
        _select(window, signals)
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window

        readiness = plugin.assess_recipe(TWO_CHANNEL_DELAY_RECIPE.recipe_id)

        assert readiness.status is RecipeReadinessStatus.NEEDS_ASSIGNMENT


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.id)
def test_generated_examples_target_their_recipes(example) -> None:
    """Every generated example carries values only for its own recipes."""
    plugin_class = desktop_adapter.PulseTransientCharacterizationPlugin
    recipes = {recipe.recipe_id: recipe for recipe in plugin_class.get_recipes()}

    data = plugin_class.materialize_example(example.id)

    assert all(isinstance(signal, SignalObj) for signal in data.objects)
    assert all(SHOT_METADATA_KEY in signal.metadata for signal in data.objects)
    assert set(data.parameter_values) == set(example.recipe_ids)
    for recipe_id, values in data.parameter_values.items():
        parameters = recipes[recipe_id].parameter_class()
        assert all(hasattr(parameters, name) for name in values)
