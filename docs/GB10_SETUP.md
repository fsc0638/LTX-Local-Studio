# GB10 模型與工具安裝

對應「虛擬片廠 Agent 架構」的部署章節：LLM／VLM 走 OpenAI（GPT-5.6，high），其餘全部裝在 GB10。
腳本在 `infra/gb10/`，在 GB10 上依序執行；每支都可重跑、都以驗證結束。**不改 app 程式，不註冊 adapter。**

## 前提

- 現有 LTX venv 可用，且 `.env.local` 有 `LTX_PYTHON`（或執行時 `export LTX_PYTHON=...`）。新 venv 會鎖定同一個 torch 版本與 wheel index，避免在 aarch64 上重新摸索 CUDA build。
- 目前使用者有 sudo（建立 `/opt/studio`、apt 裝 ffmpeg／libsndfile1）。
- 磁碟餘量 ≥ 120 GB（影像模型約 75 GB、其餘約 10 GB）。
- 選配 `python3-dev`：沒有它，whisper 跑起來會噴 `Python.h: 沒有此一檔案或目錄`（triton 想 JIT 編 CUDA kernel），會靜默 fallback、不影響正確性，但可能吃掉速度。
- **執行 `40-imagegen.sh` 時不能有 LTX 任務在跑**：Qwen-Image-Edit 與 LTX 無法同時放進 128 GB。

## 順序

| 腳本 | 做什麼 | 驗證輸出 | 要記下的數字 |
|---|---|---|---|
| `00-preflight.sh` | 檢查 aarch64、GPU、記憶體、磁碟、python3-venv；偵測 LTX torch；建 `/opt/studio` | 一行 torch 版本與 index | 無 |
| `10-openai.sh` | 讀 `/opt/studio/secrets/openai`（0600，由人建立）；打一次 structured output、一次看圖 | `OpenAI OK: model=... effort=...` | 兩次 usage 的 token 數 |
| `20-vision.sh` | `venvs/vision`：DINOv2-L、CLIP ViT-L/14、RAFT、facenet-pytorch（InsightFace 選裝） | 每個模型一行 ok | 無 |
| `30-audio.sh` | `venvs/audio`：librosa、stable-ts（whisper large-v3） | 給 `STUDIO_TEST_AUDIO` 時印 BPM 與 beat 數；給 `STUDIO_TEST_LYRICS` 時輸出逐字 SRT | BPM 與人工抽查 10 個 beat 的誤差 |
| `40-imagegen.sh` | `venvs/imagegen`：Qwen-Image-Edit-2509、Z-Image-Turbo、Lightning 8 步 LoRA；跑兩個 smoke | `z-image-turbo: ... generate Ns, peak G GB`、`qwen-image-edit-2509: ... generate Ns, peak G GB` | **兩個 generate 秒數與 peak GB**：LP 預算公式的輸入 |
| `50-post.sh` | 進 `venvs/vision`：LaMa、Real-ESRGAN（含權重）、RIFE（clone，權重需手動放） | `lama: (256, 256)`、`realesrgan: (1024, 1024, 3)` | 無 |

環境變數：`STUDIO_ROOT`（預設 `/opt/studio`）、`STUDIO_OPENAI_MODEL`（預設 `gpt-5.6`）、`STUDIO_OPENAI_EFFORT`（預設 `high`）、
`STUDIO_TORCH_INDEX_URL` / `STUDIO_TORCH_SPEC`（不想跟 LTX venv 對齊時才設）。所有權重落在 `/opt/studio/models`（`HF_HOME`、`TORCH_HOME` 指過去）。

## 執行

在 GB10 上，於本 repo 根目錄執行。每一步結束再看下一步，不要串成一行——中間有兩個需要人介入的點（建 key 檔、確認 LTX 閒置）。

```bash
cd /path/to/LTX-Local-Studio
git pull --ff-only
```

`LTX_PYTHON` 已在 `.env.local` 時可略過這行；否則指向現有 LTX venv 的 python：

```bash
export LTX_PYTHON=/path/to/LTX-2/.venv/bin/python
```

**1. 前置檢查**（不裝東西，只建目錄）：

```bash
bash infra/gb10/00-preflight.sh
```

**2. OpenAI 連線。**先由人建立 key 檔，腳本只讀路徑、不印內容：

```bash
sudo install -d -m 700 -o "$(id -un)" /opt/studio/secrets
umask 077 && printf '%s' 'sk-...' > /opt/studio/secrets/openai
bash infra/gb10/10-openai.sh
```

**3. 嵌入與音訊**（可與 LTX 任務並行，只佔數 GB）：

```bash
bash infra/gb10/20-vision.sh
bash infra/gb10/30-audio.sh
```

`30-audio.sh` 帶測試素材才會驗到拍點與對時，建議做：

```bash
STUDIO_TEST_AUDIO=/path/song.wav STUDIO_TEST_LYRICS=/path/lyrics.txt STUDIO_TEST_LANG=zh \
  bash infra/gb10/30-audio.sh
```

**4. 影像生成。**先確認沒有排隊或執行中的任務，輸出必須是 `0`：

```bash
sqlite3 -readonly data/worker/jobs.sqlite3 \
  "SELECT count(*) FROM jobs WHERE json_extract(snapshot,'\$.status') IN ('queued','running');"
```

確認為 `0` 後再跑。首次會下載約 75 GB，可中斷續傳：

```bash
bash infra/gb10/40-imagegen.sh
```

**5. 後期工具**：

```bash
bash infra/gb10/50-post.sh
```

跑完保留兩組數字：`40-imagegen.sh` 最後兩行的 `generate` 秒數與 `peak` GB（LP 預算公式的輸入），以及下一節校準報告的門檻。

## 首次實測（GB10，2026-09-04）

環境：aarch64、NVIDIA GB10、driver 580.126.09、統一記憶體 121 GB、torch 2.11.0+cu130（對齊 LTX venv）。
裝完 `/opt/studio` 共 107 GB（hf 權重 88 GB、三個 venv 15 GB、whisper 2.9 GB）。

**LP 預算公式的輸入**：

```
z-image-turbo:        load  75.5s, generate 12.9s (8 steps, 1024px),               peak 23.3 GB
qwen-image-edit-2509: load 336.2s, generate 25.8s (8 steps, 768px, 1 ref, cfg 1.0), peak 61.2 GB
```

Qwen 的 load 是 generate 的 13 倍，編排器若每個 shot 重載模型，成本會被載入時間支配 — 常駐或批次化是必要的。
peak 61.2 GB 也再次確認它與 LTX 不能同時在記憶體裡。

**OpenAI**（`10-openai.sh`）：structured output 52 in / 93 out（其中 reasoning 73）；vision 21 in / 5 out（reasoning 0）。
兩次都通過，但都不能拿來估成本 — 探針太簡單。另外探針回的 `model_seen` 是 `ChatGPT` 而非 `gpt-5.6`：
**這個欄位不是驗證訊號**，模型不可靠地知道自己的 API model id。真正的證據是 API 收下 `model: "gpt-5.6"` 沒回 404。

**節拍**（`30-audio.sh`，沖縄／三線リフで帰ろう）：104.2 BPM、285 beats，間距穩定在 0.576 s，與 BPM 自洽。
是否對齊真正的下拍仍待人工抽查。

## 對時精度：先扣掉常數偏移

用帶時間碼的 `.lrc` 當 ground truth，可以把「人工抽查 10 個 beat」升級成可量測的誤差分布。
方法上有個坑：**不能用 segment index 比對** — stable-ts 會把 40 行歌詞併成 7 個 segment，逐行對逐 segment 會得到完全錯誤的數字。
要拿逐字時間、依字元位置映回歌詞行。

三首沖縄專輯歌曲（歌詞來自 Mikamiu.Studio 的 `17_Music｜音樂與音訊/02_Lyrics｜歌詞/`）：

| 歌曲 | 行數 | 偏移（中位數） | 去偏移後 p50 | p90 | 最大 |
|---|---|---|---|---|---|
| 三線リフで帰ろう | 40 | −0.61s | 0.42s | 1.63s | 13.34s |
| 結いビート | 31 | −0.93s | 0.20s | 0.50s | 2.81s |
| エイサーの足音 | 40 | −0.91s | 0.38s | 1.04s | 1.29s |

三首都出現 −0.9s 上下的一致偏移。兩種解釋這批資料分不出來：stable-ts 系統性提早約 0.9 秒，
或這批 LRC 的時間碼是「該開始讀」而非「該開始唱」（同專輯多半同一套工具產出，後者更可能）。
分辨方法：拿一首有商業字幕的歌來對，或人工聽三個點。**在分辨出來之前，LS 應把它當可校正的常數偏移，
而不是隨機誤差** — 扣掉偏移後 p90 只有 0.5～1.0s，實際精度比原始數字好得多。

已知資料問題：`三線リフで帰ろう.lrc` 前三行時間碼是壞的（標 0.00 / 0.87 / 2.07，實唱 10.4 / 12.6 / 14.8），
上表 13.34s 的最大誤差全來自這三行，不是對時失敗。

### 2026-09-06 複測：門檻怎麼定才對

B2 驗收在對時這條退回，追查後的三件事值得留著，免得有人重跑同樣的實驗。

**這個指標是決定性的，不是會跳動的。** 同樣輸入跑三次，p90 三次都一模一樣（變動 0.000 s）。
驗收與開發量到不同數字的原因是**百分位算法不同**，不是隨機：

| 歌（排除壞行後） | nearest-rank | 線性內插 | exclusive |
|---|---|---|---|
| 三線リフで帰ろう | 1.030 | 1.024 | 1.046 |
| 結いビート | 0.500 | 0.500 | 0.556 |
| エイサーの足音 | **1.040** | **0.923** | 1.027 |

エイサー 那一格，同一份殘差、三種都合法的算法，跨在 1.0 s 兩側。**規格因此必須指定算法**；
現在指定 nearest-rank。

**VAD 試過，更差，不要再試。** stable-ts 的 `vad=True` 理論上有助於長器樂空白，實測是災難：

```
現況    三線 1.030   結い 0.500   エイサー 1.040
加 VAD  三線 51.5    結い 80.6    エイサー 74.9      （7/7 segments failed to align）
```

唱歌素材裡人聲與伴奏重疊，VAD 的語音／非語音判斷整段錯位。

**誤差分布**（去偏移後，換算成 104 BPM 的拍數）：

| | p50 | p75 | p90 | max | ≤0.5s | ≤1.0s | ≤1.5s |
|---|---|---|---|---|---|---|---|
| 三線リフで帰ろう (n=37) | 0.38s / 0.7拍 | 0.69s | 1.03s / 1.8拍 | 1.57s | 21/37 | 32/37 | 36/37 |
| 結いビート (n=31) | 0.20s / 0.3拍 | 0.30s | 0.50s / 0.9拍 | 2.81s | 27/31 | 29/31 | 30/31 |
| エイサーの足音 (n=40) | 0.39s / 0.7拍 | 0.79s | 1.04s / 1.8拍 | 1.29s | 23/40 | 36/40 | 40/40 |

**p50 全部在一拍以內**：典型的行對得相當準，這是對時本身的品質。
**p90 約 1.8 拍**，而它的尾巴由少數 LRC 本身不準的行主導 —— 用它單獨當硬門檻，量到的是歌詞檔
品質而不是對時品質。所以驗收改成 **p50 ≤ 0.5 s 且 p90 ≤ 1.5 s**：前者守典型準確度，後者當安全網，
1.5 s 是「幾乎所有行都收得住」的自然邊界（36/37、30/31、40/40）。


## 校準（第 1 期最值得先做的實驗）

裁判門檻不能沿用架構頁的 0.80／0.85，每個嵌入模型尺度不同。準備：

```
calibration/
  <角色A>/  正面、側面、不同光線、含幾張 Qwen-Image-Edit 生成的同角色圖  (≥ 10 張)
  <角色B>/  同上
  ...       至少 2 個角色；同角色配對來自同資料夾，不同角色配對來自跨資料夾
```

```bash
/opt/studio/venvs/vision/bin/python infra/gb10/tools/calibrate_embeddings.py --root calibration --out calibration_report.json
```

報告對 `face_facenet`、`dinov2_large`、`clip_vit_l14`、`lab_mean_delta_e` 各給：同／異配對分布、fpr 1% 與 5% 的門檻與對應 tpr、EER 點。
建議把 fpr 5% 的門檻寫進 Bible 當起始值，fpr 1% 當「相鄰 shot」的嚴格值。沒偵測到臉的圖會列出來，那些 shot 只能靠 DINOv2。

## 這裡沒做的事

- 沒有把影像模型註冊成 `local_adapters`，沒有裁判 loopback 服務，沒有 Agent 編排器。這些是程式變更，另案。
- RIFE 權重（作者以雲端連結發布）需手動放到 `/opt/studio/tools/rife/train_log`。首次實測後仍未放。
- 嵌入門檻校準未跑：缺 `calibration/` 素材。
- ComfyUI 沒裝。第一版用 diffusers 官方 pipeline，行為可控、可量測；需要節點式工作流再加。

## 授權對照

| 元件 | 授權 | 商用備註 |
|---|---|---|
| Qwen-Image-Edit-2509、Z-Image-Turbo、Lightning LoRA | Apache-2.0 | 可 |
| DINOv2 | Apache-2.0 | 可 |
| CLIP ViT-L/14、facenet-pytorch（VGGFace2 權重）、stable-ts、RIFE | MIT | 可 |
| Real-ESRGAN | BSD-3 | 可 |
| LaMa | Apache-2.0 | 可 |
| InsightFace 預訓練模型 | 非商用 | **選裝；商用以 facenet-pytorch 為主** |
| LTX-2、Gemma-3 | 各自條款 | 現有，商用前確認 |
