# Deferred Pulse scope

Pulse V1 analyzes an ordered set of repeated acquisitions from **one channel**
under **one acquisition configuration**. The caller is responsible for
providing that homogeneous campaign. The recipe does not infer channel or
configuration identity from titles or metadata, and it does not reject a mixed
campaign that lacks an explicit identity contract.

The plugin therefore registers only
`org.datalab.pulse-characterization:single-channel-campaign`. Its metrics,
quality flags, alignment, representative means, and per-shot table describe
variation within that one campaign. They must not be interpreted as
inter-channel timing or as a comparison between acquisition configurations.

## Deferred V2: multiple channels

The following capabilities are deliberately not part of V1:

- CH1-to-CH2 and general inter-channel delay;
- timing jitter across channels;
- cross-correlation delay;
- amplitude and integral correlation across channels;
- missing-channel detection.

V2 starts only after a reviewed input contract preserves campaign, shot, and
channel identity together. It must define synchronization, missing-channel
semantics, X-grid and unit compatibility, and the behavior of unmatched shots.
Each timing/correlation convention then needs deterministic multi-channel truth,
documented real acquisitions, and scientific review before it can be claimed.
Desktop and Web must also repeat their visible-output, rollback, provenance,
round-trip, and memory gates for the expanded data model.

## Deferred V3: configuration comparison

Configuration A/B/C comparison is also outside V1. It requires stable
configuration identifiers and provenance, a comparable acquisition protocol,
and explicit rules for aggregating quality classes and scientific metrics.
The future result contract must expose values and uncertainty without silently
declaring a configuration "best".

V3 starts only after those semantics and representative datasets are reviewed.
It requires a new versioned recipe contract and the same Desktop/Web
qualification as V1; it is not activated by grouping several current V1 runs
in a host UI.