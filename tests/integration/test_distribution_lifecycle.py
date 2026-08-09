"""Installed distribution, reload, and persistence qualification."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from datalab.adapters_metadata import TableAdapter
from datalab.config import Conf
from datalab.env import execenv
from datalab.gui.actionhandler import ActionCategory
from datalab.gui.recipe_runner import RecipeRunner
from datalab.objectmodel import get_uuid
from datalab.plugins import PluginRegistry
from datalab.recipes import RECIPE_RUN_RECORD_OPTION, RecipeRunRecord
from datalab.tests import datalab_test_app_context
from sigima.objects import SignalObj, create_signal

from datalab_pulse_characterization import PLUGIN_ID, PLUGIN_NAME
from datalab_pulse_characterization.adapters.desktop import (
    PulseTransientCharacterizationPlugin,
)
from datalab_pulse_characterization.core import metadata_key
from datalab_pulse_characterization.workflow import (
    PULSE_CAMPAIGN_RECIPE,
    PulseCampaignRecipeParameters,
)

PROJECT_ROOT = Path(__file__).parents[2]
SHOT_METADATA_KEY = metadata_key("shot")


def _pulse(title: str, shot: int, center: float) -> SignalObj:
    """Create one deterministic Pulse recipe input."""
    x = np.linspace(0.0, 10.0, 101)
    y = 4.0 * ((x >= center) & (x <= center + 2.0))
    signal = create_signal(title, x, y, units=("us", "V"))
    signal.metadata[SHOT_METADATA_KEY] = shot
    return signal


def _parameters() -> PulseCampaignRecipeParameters:
    """Return stable explicit ranges for the deterministic inputs."""
    parameters = PulseCampaignRecipeParameters()
    parameters.signal_shape = "square"
    parameters.use_explicit_ranges = True
    parameters.xstartmin = 0.0
    parameters.xstartmax = 1.0
    parameters.xendmin = 9.0
    parameters.xendmax = 10.0
    parameters.denoise = False
    return parameters


def _pulse_plugins() -> list[PulseTransientCharacterizationPlugin]:
    """Return active Pulse plugin instances."""
    return [
        plugin
        for plugin in PluginRegistry.get_plugins()
        if plugin.plugin_id == PLUGIN_ID
    ]


def test_wheel_installs_and_resolves_entry_point_outside_checkout(tmp_path) -> None:
    """A built wheel imports its plugin and recipe from an isolated target."""
    wheel_dir = tmp_path / "wheel"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            os.fspath(wheel_dir),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = tuple(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1

    install_dir = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-deps",
            "--target",
            os.fspath(install_dir),
            os.fspath(wheels[0]),
        ],
        check=True,
    )
    probe = """
import importlib
import importlib.metadata as metadata
import json

distribution = next(metadata.distributions(path=[INSTALL_DIR]))
entry_point = next(
    value
    for value in distribution.entry_points
    if value.group == "datalab.plugins"
)
plugin_class = entry_point.load()
recipe = plugin_class.get_recipes()[0]
module = importlib.import_module(plugin_class.__module__)
print(json.dumps({
    "entry_point": entry_point.name,
    "module_file": module.__file__,
    "plugin_id": plugin_class.get_plugin_id(),
    "recipe_id": recipe.recipe_id,
    "recipe_version": recipe.version,
}))
""".replace("INSTALL_DIR", repr(os.fspath(install_dir)))
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (os.fspath(install_dir), environment.get("PYTHONPATH", ""))
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "entry_point": "datalab_pulse_characterization",
        "module_file": os.fspath(
            install_dir / "datalab_pulse_characterization" / "adapters" / "desktop.py"
        ),
        "plugin_id": PLUGIN_ID,
        "recipe_id": PULSE_CAMPAIGN_RECIPE.recipe_id,
        "recipe_version": "1.1.0",
    }


def test_entry_point_plugin_reload_keeps_one_instance_and_menu() -> None:
    """Desktop hot reload replaces the Pulse plugin without action leaks."""
    original_plugins_enabled = Conf.main.plugins_enabled.get(True)
    original_enabled_list = Conf.main.plugins_enabled_list.get(None)
    Conf.main.plugins_enabled.set(True)
    Conf.main.plugins_enabled_list.set(None)
    try:
        with (
            execenv.context(unattended=True),
            datalab_test_app_context(console=False, exec_loop=False) as window,
        ):
            window.reload_plugins()
            plugins_before = _pulse_plugins()
            assert len(plugins_before) == 1
            plugin_before = plugins_before[0]
            assert any(
                "entry point 'datalab_pulse_characterization'" in source
                for source in plugin_before.__class__.__plugin_discovery_sources__
            )

            window.reload_plugins()

            plugins_after = _pulse_plugins()
            assert len(plugins_after) == 1
            assert plugins_after[0] is not plugin_before
            menus = [
                action
                for action in window.signalpanel.get_category_actions(
                    ActionCategory.PLUGINS
                )
                if hasattr(action, "title") and action.title() == PLUGIN_NAME
            ]
            assert len(menus) == 1
    finally:
        Conf.main.plugins_enabled.set(original_plugins_enabled)
        if original_enabled_list is None:
            Conf.main.plugins_enabled_list.remove()
        else:
            Conf.main.plugins_enabled_list.set(original_enabled_list)


def test_pulse_outputs_survive_native_h5_round_trip(tmp_path) -> None:
    """Output UUIDs, recipe provenance, and anchored metrics survive HDF5."""
    inputs = (_pulse("Shot 10", 10, 3.9), _pulse("Shot 20", 20, 4.1))
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        for signal in inputs:
            window.signalpanel.add_object(signal, set_current=False)
        outcome = RecipeRunner(window).run(
            PULSE_CAMPAIGN_RECIPE,
            {"signals": inputs},
            _parameters(),
        )
        input_uuids = {get_uuid(signal) for signal in inputs}
        output_uuids = {output.id: get_uuid(output.value) for output in outcome.objects}
        records = {
            output.id: RecipeRunRecord.from_dict(
                output.value.get_metadata_option(RECIPE_RUN_RECORD_OPTION)
            )
            for output in outcome.objects
        }
        anchor = outcome.objects[0].value
        table_payload = next(TableAdapter.iterate_from_obj(anchor)).result.to_dict()

        filename = tmp_path / "pulse-round-trip.h5"
        window.save_h5_workspace(os.fspath(filename))
        window.load_h5_workspace([os.fspath(filename)], reset_all=True)

        assert all(
            window.find_object_by_uuid(value) is not None for value in input_uuids
        )
        for output_id, output_uuid in output_uuids.items():
            loaded = window.find_object_by_uuid(output_uuid)
            assert loaded is not None
            assert (
                RecipeRunRecord.from_dict(
                    loaded.get_metadata_option(RECIPE_RUN_RECORD_OPTION)
                )
                == records[output_id]
            )
        loaded_anchor = window.find_object_by_uuid(output_uuids["amplitude_vs_shot"])
        loaded_tables = list(TableAdapter.iterate_from_obj(loaded_anchor))
        assert len(loaded_tables) == 1
        loaded_payload = loaded_tables[0].result.to_dict()
        assert {
            key: value for key, value in loaded_payload.items() if key != "data"
        } == {key: value for key, value in table_payload.items() if key != "data"}
        for expected_row, loaded_row in zip(
            table_payload["data"], loaded_payload["data"]
        ):
            assert len(loaded_row) == len(expected_row)
            for expected_value, loaded_value in zip(expected_row, loaded_row):
                if expected_value is None:
                    assert loaded_value == ""
                else:
                    assert loaded_value == expected_value
