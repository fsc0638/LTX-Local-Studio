# MV 時間軸與 180 秒組片（API 1.4）

本機媒體 worker 的通用能力，不依賴特定企劃、角色或行銷專案。沿用既有帳號、Cloudflare 外層保護、素材隔離及 `/api/v1/jobs` 契約。所有素材與生成留在本機；沒有新增大型模型下載、訓練、雲端媒體服務。

## 使用方式

1. 在生成頁直接匯入 PNG/JPEG/WebP，或在素材庫選擇圖片。介面自動切到圖片生成，依上傳後經 EXIF 方向校正的尺寸設定比例。
2. 常見比例使用既有精確比例預設；非標準比例用「跟隨參照圖片」，後端在 256–1536、64px 對齊及最多 1,048,576 像素範圍內找最接近畫幅。顯示原比例、實際尺寸與誤差，參照圖採等比例留邊，不拉伸或裁切。極端比例不保證能完全相同。
3. 設定總秒數。單鏡超過 `max_frames/FPS` 時自動採分段組片，最多 180 秒；不降低 FPS、不循環既有片段、不以凍格補時。
4. 「MV 時間軸」可上傳音樂，或選擇已有音樂；支援 WAV/MP3/FLAC/M4A/OGG，單檔 50 MiB、最多 10 分鐘、單音軌、mono/stereo。素材庫維持 2 GiB 上限。
5. 設定音樂起點；「使用音樂剩餘長度」以 180 秒為上限。音樂不足會拒絕生成，不循環拉長。超過所需長度只使用指定區段，AAC 是一次有損轉碼，不是原始音訊位元直拷。
6. 匯入 UTF-8 `.lrc` 或貼上歌詞，時間相對成片起點。支援 `[mm:ss.xx]`、多時間戳、`[offset:+100]` 毫秒偏移、常見歌曲 metadata；同時刻合併、乱序排序。拒絕負時間、錯誤時間碼、逐字 Enhanced LRC。單檔最多 16000 字元／120 時間戳。
7. 每個動作 cue 填時間、主要動作，可覆寫運鏡／情緒／表演；最多60個。全域設定包含景別、角度、運鏡、情緒、演出方式，組合成實際送進模型的提示詞。
8. 點「預覽分鏡（不生成）」確認每鏡时间、歌詞與完整提示詞。設定變動後會提醒預覽過期；計畫由後端重新驗證，不相信用戶端提交的鏡頭長度。
9. 生成進度顯示第幾鏡／總鏡數、組片、技術驗證；支援既有取消及重啟中斷紀錄。預設總任務時限沿用主機值（3600秒，可明確設到7200秒），長片不保證能在每一種解析度下於期限完成。

## 音樂用途：不能混為一談

- **連續配樂（預設）**：原曲只用於最終聲軌，不進影片推論。分鏡／歌詞文字可影響表演意圖，但沒有聲音驅動或精準對嘴。
- **音訊驅動表演（實驗）**：每鏡擷取對應原曲，使用現有 checkpoint 的 audio VAE 編碼，將音訊 latent 在兩個 diffusion stages 固定，透過模型的影音注意力影響影片生成。不是只把聲音貼到影片。最終聲軌仍用連續原曲，不用 VAE 重生音樂。
- 音訊驅動沿用官方 A2Vid 的 frozen-audio 機制，搭配本機 **Distilled 8+3** 日程，是本專案的實驗適配；不能宣稱是官方 Dev A2Vid 的已驗證替代。
- **精準對嘴尚無保證**：LRC 只有逐句時間，不含音素；說話／演唱選項是表演指令。咬字、拖音、多角色、動畫臉、舞步及切鏡連戲需人工檢查。先用清楚的單人正面短段；需要精準嘴型時仍需另行評估專用模型。

## 180 秒的真實意義

`single` 保留既有 `8n+1`／主機幀數限制。`sequence` 的最終幀數為 `ceil(duration_seconds * fps)`，每鏡推論向上取 `8n+1`，組片只去掉明確的推論尾部多餘幀，保留原定有效幀。180秒／24 FPS 成片為4320幀，不是把481幀改容器FPS。

分鏡切點由 LRC／動作cue 與每鏡最大秒數產生，再受主機 frame cap 限制。全片最多120鏡。每鏡沿用同一核准參照作起始圖（若有），seed 依鏡號遞增；這不等於角色100%一致或同一段動作無縫延長。

每鏡先完整解碼驗證，全部通過才組片，再驗證最终影片的長度、幀數、FPS、尺寸、音軌；不發布不完整長片。取消／錯誤時保留私人工作目錄，既有刪除機制會一併可復原封存鏡頭、參照片及音樂片段。重啟不自動重新消耗 GPU；任務標為 interrupted，需新請求重新生成，尚無局部鏡頭續跑。

## 通用 API 範例

```json
{
  "prompt": "An adult performer stands beside a calm ocean at sunset.",
  "model": "ltx23-distilled",
  "render_mode": "sequence",
  "mode": "i2v",
  "image_id": "替換成自己的圖片素材ID",
  "aspect_ratio": "source",
  "duration_seconds": 180,
  "segment_seconds": 10,
  "fps": 24,
  "audio": true,
  "directing": {
    "shot_size": "mcu",
    "angle": "three_quarter",
    "camera": "locked",
    "emotion": "longing",
    "performance": "singing"
  },
  "timeline": {
    "audio_id": "替換成自己的音樂素材ID",
    "audio_start_seconds": 0,
    "audio_mode": "condition",
    "lrc": "[00:00.00]第一句歌詞\n[00:04.50]第二句歌詞",
    "cues": [{"time": 4.5, "action": "抬起視線，手掌緩慢張開", "directing": {"emotion": "hope"}}]
  }
}
```

先 POST `/api/v1/validate`，再以相同 JSON 及 `Idempotency-Key` POST `/api/v1/jobs`。不接受上游直接指定路徑、URL、shell命令、預製segments。Cookie 請求仍需 Origin + CSRF；service key 是主機級權限。音樂及圖片都檢查所有者，使用中的素材不能刪除。

## 製作依據

本機先前報告 `AI_MV_Production_Research_2026-08-30.md` 第1、5、6節：景別／角度／運鏡／情緒分開；每鏡一個主要動作；Breathing Frame 定義為敘事留白、微動態與構圖空間，不是正式模型控制參數；最終母帶連續铺底。

技術參考：[官方 A2Vid](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-pipelines/src/ltx_pipelines/a2vid_two_stage.py)、[官方 Distilled](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-pipelines/src/ltx_pipelines/distilled.py)、[LatentSync 專用嘴型路線](https://github.com/bytedance/LatentSync)。未複製或安裝第三方整套 MV 工具。
