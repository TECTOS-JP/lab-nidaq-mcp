# Implementation notes

Replaced the Echo template with a device-level NI-DAQmx backend following
`SAFETY_DESIGN.md`. Resource, wire, and configuration parsing are strict and
case-sensitive. All DAQmx imports and task construction are isolated in four
hardware hooks; the mock overrides those hooks and records writes in memory.

The physical allowlist is intentionally limited to the two devices measured in
the safety design: `Dev1` (USB-6210) and `Dev2` (USB-6009). Tests do not import
or exercise DAQmx tasks and no physical output or reset operation was used.

The bundled definitions are `experimental`. The only uncertainty is the final
installed interlock wiring and safe values, which the safety design explicitly
leaves site-specific; configuration therefore requires those choices rather
than inferring them.

The supplied virtual environment does not contain the `hatchling` build
backend. Consequently `python -m build` attempts to download it into an
isolated environment and cannot do so with network access disabled. The same
command with `--no-isolation` also confirms that `hatchling.build` is absent.
Tests and both Ruff checks pass; packaging metadata retains the template's
Hatch backend and strict sdist allowlist rather than replacing it with a
different build system merely to mask the environment omission.

## 2026-07-20 safety review fixes

- Safe shutdown no longer consults the interlock. Both `SAFE` and `close()`
  attempt every declared safe-value write; ordinary AO and DO writes remain
  fail-closed on an unsatisfied or unreadable interlock.
- Capabilities are keyed by declared product type instead of assignable DAQmx
  device name. Every configured device must declare `model`, and the backend
  verifies the hardware-reported `product_type` through a lazy hardware hook
  before the first hardware operation, caching only successful matches.
- The resolved capability supplies the physical AO range for both validation
  and DAQmx task construction. The backend contains no USB-6009 range literal.
- The mock overrides the product-type hook. All added regression coverage and
  verification remain in-memory and do not construct DAQmx tasks.

This supersedes the earlier notes that described capabilities as a `Dev1` /
`Dev2` allowlist, counted four hardware hooks, and reported Hatchling missing.
