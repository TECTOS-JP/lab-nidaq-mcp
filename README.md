# lab-nidaq-mcp

[lab-executor-mcp](https://github.com/TECTOS-JP/lab-executor-mcp) 用の NI-DAQmx 機器バックエンドです。v0.1 は、合意済みの USB-6009 / USB-6210 に対する**ソフトウェアタイミングの単点** AI / DI / AO / DO をサポートします。波形・ストリーミング・外部トリガ・カウンタ / タイマは対象外です。

リソースは**機器単位・大文字小文字を区別**します(`DAQ::Dev1` / `DAQ::Dev2`)。チャネルはコマンド側で指定します。

```text
READ AI ai0
READ DI port0/line0
INFO model
WRITE AO ao0 2.5
WRITE DO port1/line0 1
SAFE
```

## 安全モデル

出力は、設定で明示的に宣言されない限り無効です。宣言された出力にはすべて `safe_value` の明示が必須で、**0 が安全だとソフトウェアが推測することはありません**。インターロックを設定した場合は、通常の出力書き込みの直前に必ず読み取り、不一致または読み取り失敗なら書き込みを拒否します。ただし `SAFE` と `close()` による安全値への駆動は、**意図的にインターロックを迂回**して宣言済みの全出力へ試みます(インターロックが落ちた瞬間に安全化まで止まると本末転倒なため)。アナログ出力値は、DAQmx タスクを作る前に**宣言レンジと機種の物理レンジの両方**で検査します。書き込みは自動リトライしません。

### 設置要件(D9・必須)

USB-6009 / USB-6210 は、電源投入時の出力状態をプログラムで設定できません。したがってソフトウェアは、ホストのクラッシュ・USB 切断・制御喪失の後の出力レベルを保証できません。**出力ラインが高インピーダンスになったときに安全側へ倒れるよう、外部回路を配線するのは設置者の責任です。** これはこのバックエンドが保証する事項ではなく、設置要件です。`support_level` は、出力動作とこの配線要件を実機で確認するまで `experimental` のままです。

## 設定

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

`model` と `interlock` は必須です。宣言した `model` が物理能力を決め、初回ハードウェア接触時に読み取る DAQmx の `product_type` と一致しなければなりません。インターロックは明示文字列 `none`、または `{line: "port0/line7", require: 1}` を指定します。インターロックのラインを出力として宣言することはできません。

```powershell
lab-nidaq --config nidaq.yaml --dry-run
lab-nidaq --config nidaq.yaml
```

エントリポイントは `lab_executor.backends: nidaq`、ルーティング接頭辞は `DAQ::` です。

## 実測で判明したハードウェアの限界

能力表の最大サンプルレートは**機器の仕様値**であり、任意のホストでそれを維持できる保証ではありません。このバックエンドはそれを取り繕わず、ハードウェアが追随できないレートは、短いデータや重複データを黙って返すのではなく、DAQmx 自身の診断を載せた transport エラーとして表面化させます。

このハードウェアでの実測(2026-07-20):

- **USB-6210 で 250 kS/s** — 10,000 サンプルをエラーなく取得。
- **USB-6009 で仕様上の最大 48 kS/s** — DAQmx が `Onboard device memory overflow`(`-200361`)を返す。オンボードメモリが小さくインタラプト転送のため、このホストではバッファ読み出しで仕様値に到達しない。10 kS/s は安定。

**未接続の差動入力は、ゼロではなくレールに張り付きます。** 何もつないでいない USB-6210 の入力は 10,000 サンプルすべて 10.974836 V 一定を返し、一方 USB-6009 の単端入力は同じコード経路で実際の ADC ノイズ(9 種の値・σ≈2.2 mV)を返しました。取得値が一定なのは端子が浮いている徴候であって取得失敗ではありません。意味のある値が要るなら、未使用の差動入力を AI GND にバイアスしてください。

## 開発

テストは `MockNiDaqBackend` のみを使い、DAQmx タスクを一度も生成しません。

```powershell
python -m pytest -q
python -m ruff check src tests
python -m ruff format --check src tests
python -m build
```

## ライセンス

MIT
