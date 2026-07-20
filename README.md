# lab-nidaq-mcp

NI-DAQmx instrument backend for [lab-executor-mcp](https://github.com/TECTOS-JP/lab-executor-mcp). Version 0.1 supports software-timed, single-point analog input, digital input, analog output, and digital output on the agreed USB-6009 and USB-6210 devices. Waveforms, streaming, triggers, counters, and timers are out of scope.

Resources are device-level and case-sensitive: `DAQ::Dev1` and `DAQ::Dev2`. Commands select a channel:

```text
READ AI ai0
READ DI port0/line0
INFO model
WRITE AO ao0 2.5
WRITE DO port1/line0 1
SAFE
```

## Safety model

Outputs are disabled unless explicitly declared in configuration. Every declared output requires an explicit `safe_value`; the software never assumes zero is safe. A configured interlock is read immediately before every ordinary output write, and a mismatch or read failure refuses the write. Safe-value writes from `SAFE` and `close()` deliberately bypass the interlock and attempt every declared output. Analog output values are checked against both the declared range and the model capability before a DAQmx task is created. Writes are never automatically retried.

### Mandatory installation requirement (D9)

The USB-6009 and USB-6210 cannot be assigned a programmable power-up output state. Software therefore cannot guarantee an output level after a host crash, USB disconnection, or loss of host control. **The installer is responsible for wiring the external circuit so that a high-impedance output line is the safe state.** This is an installation requirement, not a guarantee made by this backend. `support_level` remains `experimental` until output operation and this wiring requirement are verified on the installed hardware.

## Configuration

```yaml
devices:
  Dev2:
    model: "USB-6009"
    interlock: none
    analog_inputs:
      ai0: {range: [-10, 10]}
    analog_outputs:
      ao0:
        range: [0, 5]
        safe_value: 0.0
    digital_outputs:
      port1/line0:
        safe_value: 0
```

`model` and `interlock` are mandatory. The declared model selects physical capabilities and must match the DAQmx `product_type` read on first hardware access. Use the explicit interlock string `none`, or configure `{line: "port0/line7", require: 1}`. An interlock line cannot also be declared as an output.

```powershell
lab-nidaq --config nidaq.yaml --dry-run
lab-nidaq --config nidaq.yaml
```

The entry point is `lab_executor.backends: nidaq`, with routing prefix `DAQ::`.

## Measured hardware limits

The capability table's maximum sample rate is the device's specified figure.
It is not a guarantee that a given host can sustain it, and this backend does
not pretend otherwise: a rate the hardware cannot keep up with surfaces as a
transport error carrying DAQmx's own diagnosis, rather than silently returning
short or duplicated data.

Measured on this hardware on 2026-07-20:

- **USB-6210 at 250 kS/s** — 10,000 samples acquired without error.
- **USB-6009 at its specified 48 kS/s maximum** — DAQmx reports
  `Onboard device memory overflow` (`-200361`). The device has little onboard
  memory and transfers over interrupts, so the specified maximum is not
  reachable for buffered reads on this host. 10 kS/s was reliable.

An unconnected differential input rails rather than reading zero. A USB-6210
input with nothing attached returned a constant 10.974836 V across all 10,000
samples, while a USB-6009 single-ended input on the same code path returned
genuine ADC noise (9 distinct values, σ≈2.2 mV). Constant data from an
acquisition usually means the terminal is floating, not that acquisition
failed; bias unused differential inputs to AI GND if you need a meaningful
reading.

## Development

Tests use only `MockNiDaqBackend`; they never construct a DAQmx task. Run:

```powershell
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m build
```

## License

MIT
