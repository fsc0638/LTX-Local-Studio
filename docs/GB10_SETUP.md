# GB10 模型與工具安裝

對應「虛擬片廠 Agent 架構」的部署章節：LLM／VLM 走 OpenAI（GPT-5.6，high），其餘全部裝在 GB10。
腳本在 `infra/gb10/`，在 GB10 上依序執行；每支都可重跑、都以驗證結束。**不改 app 程式，不註冊 adapter。**

## 前提

- 現有 LTX venv 可用，且 `.env.local` 有 `LTX_PYTHON`（或執行時 `export LTX_PYTHON=...`）。新 venv 會鎖定同一個 torch 版本與 wheel index，避免在 aarch64 上重新摸索 CUDA build。
- 目前使用者有 sudo（建立 `/opt/studio`、apt 裝 ffmpeg／libsndfile1）。
- 磁碟餘量 ≥ 120 GB（影像模型約 75 GB、其餘約 10 GB）。
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
- RIFE 權重（作者以雲端連結發布）需手動放到 `/opt/studio/tools/rife/train_log`。
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
