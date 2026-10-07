# Oscilloscope Simulator

The Pulse application includes a simulated oscilloscope. It is a DataLab tool: open it from the Pulse page of the **Applications** catalog (**Tools** section), or from the **Plugins > Pulse & Transient Characterization** menu of the signal panel. It works the same way in DataLab Desktop and DataLab-Web.

The window shows the oscilloscope screen on the left and the settings on the right. Every change of a setting refreshes the screen. **Live** refreshes it continuously: each refresh is a new trigger, so jitter and noise show as on a real oscilloscope. **Acquire** records a series of triggers and adds them to the workspace, in a new group per acquisition; the window stays open for the next acquisition.

## Settings

Connect a source first (**Source** tab), then set the oscilloscope (**Oscilloscope** tab). Settings that do not apply to the selected source are greyed out.

- **Source.**
  - Laser pulse seen by a photodiode: Gaussian or asymmetric pulse, with an optional linear drift of its time and amplitude over one acquisition.
  - Amplifier step response: response of a second-order system, set by its natural frequency and damping ratio.
  - Pulse pair: a reference pulse on CH1 and the delayed, wider pulse of a detector on CH2.
  - For every source: amplitude, amplitude jitter and trigger jitter. The pulse pair adds the detector delay, gain, pulse width and its own jitter.
- **Oscilloscope.**
  - Horizontal: time base (ns/div, ten divisions), sample rate and trigger position. The trigger is at t = 0; the trigger position is the part of the record before it.
  - Vertical: scale (V/div, eight divisions) and offset of CH1 and CH2, ADC resolution and input noise. The offset is the voltage at the center of the screen.
  - Acquisition: number of triggers per acquisition, and the random seed.

The ADC codes the screen only: a trace that leaves the screen is clipped, then quantized on 2^bits levels. The summary below the screen gives the peak of each channel and its number of clipped samples. Times are in ns and voltages in V, for every source.

The seed and the acquisition number fix the noise and jitter of each acquisition: the same settings give the same acquisitions in a new session.

One acquisition is limited to 5 million samples (all signals together), which keeps DataLab-Web within the browser memory.

## Acquired Signals

Signals are named `CH1 shot 001`, `CH1 shot 002`, and so on; with the pulse pair, the CH2 signals follow the CH1 ones. Each signal carries the metadata the Pulse methods expect:

- `plugin.org.datalab.pulse-characterization.shot`: the trigger number, from 1;
- `plugin.org.datalab.pulse-characterization.channel`: `CH1` or `CH2`;
- `plugin.org.datalab.pulse-characterization.synthetic` and `.simulation_seed`, which record the simulated origin.

So an acquisition can be analyzed right away:

| Source | Methods |
| --- | --- |
| Laser pulse | Single-channel pulse campaign, shot-to-shot stability |
| Amplifier step response | Step response |
| Pulse pair | Two-channel delay and jitter |

The two-channel method measures the delay between 50 % crossings. With the default asymmetric detector pulse, this delay is shorter than the delay between pulse peaks set in the source.

## Limits

The trigger is external and synchronized with the source: there is no trigger level, slope or rearm logic. There is no bandwidth limit, no probe model and no acquisition mode other than a series of single triggers. The simulator helps learning the methods and checking a workflow; it does not replace measurements on a real bench.
