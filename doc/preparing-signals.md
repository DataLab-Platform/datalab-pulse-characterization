# Preparing Your Own Signals

The Pulse methods read two metadata entries on the signals:

| Key | Value | Use |
| --- | --- | --- |
| `plugin.org.datalab.pulse-characterization.shot` | Positive integer shot number | Required by the two-channel delay method, which pairs the shots of both channels by this number; optional for the other methods, where input order defines the shot number |
| `plugin.org.datalab.pulse-characterization.channel` | Channel label, for instance `CH1` | Optional, two-channel delay method: proposes the reference and measured channels |

DataLab, on Desktop and on the Web, sets them with **Edit > Metadata > Add metadata...**. When a key is missing, the status of the method in the **Applications** window points to this dialog, and the status is updated as soon as the metadata change. In the dialog, the **Known keys** list offers the keys above while the Pulse plugin is active: choosing one copies it into **Metadata key**.

## Shot Number Read From the Titles

For signals titled like `CH1 shot 001`, select them and set:

| Field | Value |
| --- | --- |
| Metadata key | `plugin.org.datalab.pulse-characterization.shot` |
| Value pattern | `{title}` |
| Extraction pattern | `shot\s*(\d+)` |
| Conversion | Integer |

`CH1 shot 001` gives `1`. The preview shows the value of every selected signal before you click OK. Signals whose title does not match are left unchanged, unless **If no match** is set to report an error.

When the signals are already in shot order, the value pattern `{index}` with the Integer conversion numbers them 1, 2, 3... in the order of the selection.

## Channel Labels

For the same titles, use the extraction pattern `^(CH\d+)` with the String conversion and the key `plugin.org.datalab.pulse-characterization.channel`. Otherwise, select the signals of one channel and type its label, for instance `CH1`, as the value pattern; then repeat for the other channel.
