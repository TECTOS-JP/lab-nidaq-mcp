# Changelog

## 0.1.0 - 2026-07-21

First release. Safety design was fixed before implementation began and is kept
in `docs/SAFETY_DESIGN.md`; the implementation is not allowed to deviate from
it.

### Backend

- Replace the template Echo backend with a fail-closed NI-DAQmx backend.
- Add explicit output opt-in, mandatory safe values, interlock enforcement,
  pre-task analog range checks, `SAFE`, and safe idempotent close behavior.
- Device capabilities are keyed on product type, and the declared `model` is
  checked against the hardware's real `product_type` on first access. DAQmx
  device names are assignable in NI MAX, so keying on the name would let a
  device inherit another model's physical limits.
- Add experimental USB-6009 and USB-6210 instrument definitions.

### Finite bulk acquisition

- Add `ACQUIRE <ai-channel> <samples> <rate_hz>`. Samples are written to a
  compressed `.npz` holding both the waveform and its metadata, and `query`
  returns an artifact reference. A waveform never travels through the frozen
  `query() -> str` contract as data.
- The reference's `sha256` is computed by reading the written file back, so it
  describes what is on disk rather than what was intended.
- Requires `lab-executor-mcp` 2.36.0 or newer to ingest the artifact into a
  bundle. The cross-check test skips against older releases.

### Measured hardware limits

Recorded in the README because they are not obvious from the specifications:

- USB-6009 reports `Onboard device memory overflow` at its specified 48 kS/s
  maximum on this host; 10 kS/s was reliable. A capability table's maximum is a
  specified figure, not a guarantee that a host can sustain it.
- An unconnected differential input rails rather than reading zero. Constant
  data from an acquisition usually means a floating terminal, not a failure.

### Safety

- Tests never open a DAQmx task. The suite passes with `nidaqmx` uninstallable,
  so reaching hardware from a test is structurally impossible rather than a
  convention.
