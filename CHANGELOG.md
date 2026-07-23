# Changelog

## 0.1.2 - 2026-07-22

外部レビュー (Codex) で指摘された P1 / P3 への対応。

### DAQmx 呼び出しがサーバ全体を止めていた (P1)

`query` / `write` は `timeout_ms` を捨て、同期の DAQmx 呼び出しを async
メソッド上で直接実行していた。長い測定中はサーバが応答不能になり (停止要求・
状態確認・別機器の操作も返せない)、時間制限も効かなかった。

- ハードウェアに触れる各分岐を `asyncio.to_thread` でワーカースレッドへ退避。
  イベントループが取得中も応答を続ける。
- `timeout_ms` を DAQmx read の timeout へ反映。単点読みは caller の値、
  `ACQUIRE` は取得時間 (samples/rate) + caller 値をマージンとして渡す。

実機 USB-6210 で 200,000 サンプル @ 250 kS/s の取得中 (0.87 秒) に、別タスクの
heartbeat が 56 回進むことを実測した。従来はこの間ループが固まっていた。

### テストがリポジトリ直下へ書いていた (P3)

`test_cli_dry_run` が `.test_nidaq_config.yaml` をソース直下に作成していた。
読み取り専用環境で失敗し、並列実行で名前が衝突する。pytest の `tmp_path` へ
変更した。

## 0.1.1 - 2026-07-21

First release. Safety design was fixed before implementation began and is kept
in `docs/SAFETY_DESIGN.md`; the implementation is not allowed to deviate from
it.

0.1.0 reached TestPyPI only. Installing it revealed that declaring an analog
input demanded an `artifact_dir`, forcing waveform storage on users who only
ever call `READ AI`. The requirement now belongs to `ACQUIRE`, which is the
only command that writes an artifact, and it reports a clear error rather than
failing an assertion.

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
