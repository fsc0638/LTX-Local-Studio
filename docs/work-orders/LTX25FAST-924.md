# LTX25FAST-924 — LTX 2.5 Fast 相容性與畫質基準

## 目標

讓 LTX 2.3 與官方 LTX 2.5 Fast 在同一套 worker 契約下並存；2.5 權重不完整時必須顯示不可用，
不得把正式 2.3 產線切走。以相同提示詞、種子、畫幅、幀數與參照圖建立可重現 A/B 畫質測試。

## 驗收基準

- `ltx25-fast` 保留現有 LTX 的角色、導演、時間線、sequence 與品質閘門契約。
- 2.5 使用官方 split checkpoint：transformer、Gemma 4 text encoder、video/audio VAE、spatial upscaler。
- 任一必要元件缺少時 catalog 顯示 unavailable，worker 不接受 GPU 任務。
- 既有 `ltx23-distilled` 預設與全部測試不退步。
- 真模型 A/B 固定同提示詞、seed、解析度、幀數、參照圖；記錄 runtime、成品大小、CJ、SJ、MQ 與人工盲評。

## 進度

### 已完成

- 建立 `wo/ltx25fast-924` 隔離分支與 worktree。
- 確認官方 LTX-2 checkout 已支援 2.5 split checkpoint；主機有 3.3 TiB 可用磁碟與 121 GiB 統一記憶體。
- 加入 2.5 Fast 模型註冊、權重完整性閘門、split-checkpoint launcher 與無權重相容測試。
- 沙盒模型選單可辨識完整 LTX 影片介面；2.5 缺權重時不可選，2.3 仍為預設。
- 建立固定 seed／解析度／參照圖的三案 A/B 畫質規格於 `docs/LTX25_FAST_EVALUATION.md`。
- 無權重驗證：Python 448 tests、Node 100 tests、TypeScript、production build 全數通過。

### 未完成

- 下載官方 gated LTX 2.5 權重（約 66 GiB）。
- 執行 GB10 真模型 smoke test 與 2.3/2.5 A/B 畫質測試。
- 依實測結果決定 diffusion VAE 或 conv VAE，以及是否啟用 DFR。

### 需要阿寶做的事

- 核准模型下載與隔離實機測試後，再使用主機既有的 Hugging Face 登入狀態下載；不在聊天中提供 token。
