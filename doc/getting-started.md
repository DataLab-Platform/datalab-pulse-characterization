# Getting Started

[← Documentation index](README.md)

This page shows where the plugin appears in DataLab, how to run the demo campaign, and how to prepare your own signals. DataLab Desktop and DataLab-Web work the same way.

![DataLab with the amplitude of the 500-shot demo campaign and its metrics table](images/overview.png)

## Where to Find the Plugin

- **Plugins > Pulse & Transient Characterization** menu of the signal panel: open the examples, run the methods and open the [oscilloscope simulator](simulator.md).
- **Applications** catalog, opened by the **Pulse & Transient Characterization** tile of the welcome page. It lists each method with the inputs it expects, tells whether the current selection can run it, and offers its examples. **Try with this example** opens an example, prefills the parameters and runs the method.
- **Open demo campaign** tile of the welcome page.

## Run the Demo Campaign

1. Choose **Plugins > Pulse & Transient Characterization > Open demo campaign**. DataLab generates 500 synthetic shots and selects them.
2. Choose **Run pulse campaign...**.
3. Accept the parameters.

DataLab adds the amplitude versus shot with a per-shot metrics table, and the raw and aligned mean pulses. The amplitude shows a slow drift and the 11 deliberate anomalies of the campaign. [Single-channel pulse campaign](pulse-campaign.md) explains each result.

Each method checks the selection before the run: shot numbers, number of shots, samples per step, common X unit for two channels. DataLab asks you to assign the signals only when the selection is ambiguous or invalid.

## Other Examples

| Menu item | Example | Methods |
| --- | --- | --- |
| **Open stability example** | Laser warm-up: 600 pulses with drifts and a jitter increase | [Shot-to-shot stability](shot-stability.md), [pulse campaign](pulse-campaign.md) |
| **Open step-response example** | 64 steps of an 80 MHz amplifier with a 0.35 damping ratio | [Step response](step-response.md) |
| **Open two-channel example** | Reference and detector channels, 1 ns common and 0.2 ns detector jitter | [Two-channel delay](two-channel-delay.md) |
| **Open gamma spectrum example** | NaI(Tl) events from Cs-137 and Co-60 sources | [Pulse-height spectrum](pulse-height-spectrum.md) |

All examples are generated in memory. Run them with the matching **Run ...** item of the menu.

## Use Your Own Signals

The methods read two metadata entries on each signal:

| Key | Value | Use |
| --- | --- | --- |
| `plugin.org.datalab.pulse-characterization.shot` | Positive integer shot number | Required by the two-channel method, which pairs shots by this number. Optional elsewhere: the input order gives the shot number |
| `plugin.org.datalab.pulse-characterization.channel` | Channel label, for instance `CH1` | Optional. The two-channel method uses it to propose the reference and measured channels |

Set them with **Edit > Metadata > Add metadata...**. While the plugin is active, the **Known keys** list offers both keys. When a key is missing, the method status in the **Applications** catalog points to this dialog.

To read the shot number from titles such as `CH1 shot 001`, select the signals and set:

| Field | Value |
| --- | --- |
| Metadata key | `plugin.org.datalab.pulse-characterization.shot` |
| Value pattern | `{title}` |
| Extraction pattern | `shot\s*(\d+)` |
| Conversion | Integer |

`CH1 shot 001` gives `1`. The preview shows each value before you click OK. When the signals are already in shot order, the value pattern `{index}` numbers them 1, 2, 3... in the order of the selection.

For the channel label, use the extraction pattern `^(CH\d+)`, the String conversion and the key `plugin.org.datalab.pulse-characterization.channel`. You can also select the signals of one channel and type its label, for instance `CH1`, as the value pattern; then repeat for the other channel.
