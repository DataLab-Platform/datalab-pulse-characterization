# Deferred Pulse scope

## V1: one channel, one configuration

The single-channel campaign recipe `org.datalab.pulse-characterization:single-channel-campaign`, the shot-to-shot stability, step-response and pulse-height spectrum recipes analyze an ordered set of repeated acquisitions from **one channel** under **one acquisition configuration**. The caller is responsible for providing that homogeneous campaign. These recipes do not infer channel or configuration identity from titles or metadata, and they do not reject a mixed campaign. Their metrics describe variation within one campaign; they must not be interpreted as inter-channel timing or as a comparison between acquisition configurations.

## V2: two channels (delivered, Alpha)

The `org.datalab.pulse-characterization:two-channel-delay` recipe activates the first part of V2 with this reviewed input contract:

- **Identity:** two input slots, `reference` and `measured`. Shots are paired by the positive shot number in `plugin.org.datalab.pulse-characterization.shot`, required on every signal of both channels. A shot number repeated within one channel is an error.
- **Channel labels:** `plugin.org.datalab.pulse-characterization.channel` only proposes slot bindings; it is never used to pair shots.
- **Missing channel:** a shot present in one channel only is kept in the per-shot table as `MISSING_REFERENCE` or `MISSING_MEASURED` and raises a `missing_channel` warning. A shot whose reference or measured acquisition is not `VALID` is kept with its status and raises an `invalid_pair` warning. Neither enters the statistics.
- **Units and grids:** both channels must share their X unit. The cross-correlation delay additionally requires the same sampling interval; acquisitions may start at different X values.
- **Delivered quantities:** CFD and cross-correlation delays, relative jitter, per-channel and common-mode jitter, timing, amplitude and integral correlations, and amplitude gain. Conventions are documented in [`two-channel-delay.md`](two-channel-delay.md).

Deterministic multi-channel truth validates these conventions in the test suite. Documented real acquisitions and an independent scientific review are still required before a stable release, as for every recipe. Synchronization between instruments without a common trigger, more than two channels and time-base calibration remain out of scope.

## Deferred V3: configuration comparison

Configuration A/B/C comparison is still outside the scope. It requires stable configuration identifiers and provenance, a comparable acquisition protocol, and explicit rules for aggregating quality classes and scientific metrics. The future result contract must expose values and uncertainty without silently declaring a configuration "best".

V3 starts only after those semantics and representative datasets are reviewed. It requires a new versioned recipe contract and the same Desktop/Web qualification as the existing recipes; it is not activated by grouping several runs in a host UI.