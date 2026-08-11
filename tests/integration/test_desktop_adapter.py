"""DataLab Desktop adapter contract tests."""

from __future__ import annotations

import numpy as np
import pytest
from datalab.adapters_metadata import TableAdapter
from datalab.env import execenv
from datalab.gui.actionhandler import ActionCategory
from datalab.objectmodel import get_uuid
from datalab.plugins import PluginCapability
from datalab.recipes import RECIPE_RUN_RECORD_OPTION, RecipeRunRecord
from datalab.tests import datalab_test_app_context
from sigima.objects import SignalObj, create_signal

from datalab_pulse_characterization.adapters import desktop as desktop_adapter
from datalab_pulse_characterization.core import metadata_key
from datalab_pulse_characterization.workflow import (
    PULSE_CAMPAIGN_RECIPE,
    PulseCampaignRecipeParameters,
)

SHOT_METADATA_KEY = metadata_key("shot")


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
    assert plugin_class.PLUGIN_INFO.version == "0.1.0"
    assert plugin_class.PLUGIN_INFO.capabilities == frozenset(
        {
            PluginCapability.APPLICATION,
            PluginCapability.PROCESSING,
        }
    )
    assert plugin_class.get_recipes() == (PULSE_CAMPAIGN_RECIPE,)
    assert plugin_class.get_examples() == (desktop_adapter.PULSE_DEMO,)
    assert plugin_class.get_recipe_launchers() == {
        PULSE_CAMPAIGN_RECIPE.recipe_id: "run_campaign_from_selection"
    }
    assert plugin_class.PLUGIN_INFO.documentation_url == (
        "https://github.com/DataLab-Platform/datalab-pulse-characterization"
    )
    assert PULSE_CAMPAIGN_RECIPE.version == "1.1.0"
    assert PULSE_CAMPAIGN_RECIPE.parameter_class is PulseCampaignRecipeParameters


def test_desktop_adapter_materializes_demo_campaign() -> None:
    """The Desktop demo matches the Web qualification campaign contract."""
    plugin_class = desktop_adapter.PulseTransientCharacterizationPlugin

    data = plugin_class.materialize_example("demo")

    assert data is not None
    assert len(data.objects) == 500
    assert all(SHOT_METADATA_KEY in signal.metadata for signal in data.objects)
    assert data.parameter_values["use_explicit_ranges"] is True


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


def test_desktop_parameter_editor_prefills_demo_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After opening the demo, the parameter form starts from its values."""
    plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
    plugin.main = object()
    plugin.last_example_data = plugin.materialize_example("demo")
    monkeypatch.setattr(
        PulseCampaignRecipeParameters, "edit", lambda _self, *, parent: True
    )

    parameters = plugin.edit_campaign_parameters()

    assert parameters is not None
    assert parameters.use_explicit_ranges is True
    assert parameters.denoise == plugin.last_example_data.parameter_values["denoise"]


@pytest.mark.parametrize("accepted", [True, False])
def test_desktop_adapter_edits_campaign_parameters(
    accepted: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter returns accepted parameters and preserves cancellation."""
    plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
    parent = object()
    plugin.main = parent
    parameters = _parameters()
    edit_calls: list[object] = []

    def edit(_self, *, parent):
        edit_calls.append(parent)
        return accepted

    monkeypatch.setattr(PulseCampaignRecipeParameters, "edit", edit)

    result = plugin.edit_campaign_parameters(parameters)

    assert edit_calls == [parent]
    assert result is parameters if accepted else result is None


def test_desktop_parameter_editor_requires_registered_plugin() -> None:
    """The adapter cannot parent a modal form before Desktop registration."""
    plugin = desktop_adapter.PulseTransientCharacterizationPlugin()

    with pytest.raises(RuntimeError, match="registered"):
        plugin.edit_campaign_parameters()


def test_desktop_form_opens_in_unattended_application() -> None:
    """The parameter DataSet opens successfully in a DataLab window."""
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window

        parameters = plugin.edit_campaign_parameters()

        assert isinstance(parameters, PulseCampaignRecipeParameters)


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
        window.signalpanel.objview.select_objects(inputs)

        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window
        handler = window.signalpanel.acthandler
        with handler.new_category(ActionCategory.PLUGINS):
            plugin.create_actions()
        monkeypatch.setattr(plugin, "edit_campaign_parameters", _parameters)

        handler.selected_objects_changed([], [inputs[0]])
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


def test_desktop_action_cancellation_preserves_campaign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling the parameter form leaves all selected signals unchanged."""
    inputs = (_pulse("Shot 1", 1), _pulse("Shot 2", 2))
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        for signal in inputs:
            window.signalpanel.add_object(signal, set_current=False)
        window.signalpanel.objview.select_objects(inputs)
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window
        monkeypatch.setattr(plugin, "edit_campaign_parameters", lambda: None)

        outcome = plugin.run_campaign_from_selection()

        assert outcome is None
        assert window.signalpanel.objmodel.get_all_objects() == list(inputs)


def test_desktop_action_reports_invalid_metadata_without_partial_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recipe validation errors return without committing any output."""
    inputs = (_pulse("Shot 1", 1), _pulse("Invalid shot", 2))
    inputs[1].metadata[SHOT_METADATA_KEY] = 0
    errors: list[str] = []
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        for signal in inputs:
            window.signalpanel.add_object(signal, set_current=False)
        window.signalpanel.objview.select_objects(inputs)
        plugin = desktop_adapter.PulseTransientCharacterizationPlugin()
        plugin.main = window
        monkeypatch.setattr(plugin, "edit_campaign_parameters", _parameters)
        monkeypatch.setattr(plugin, "show_error", errors.append)

        outcome = plugin.run_campaign_from_selection()

        assert outcome is None
        assert window.signalpanel.objmodel.get_all_objects() == list(inputs)
        assert len(errors) == 1
        assert SHOT_METADATA_KEY in errors[0]
