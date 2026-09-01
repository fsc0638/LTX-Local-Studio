# LTX 影片生成主機：跨專案 API v1

目前程式契約版本：**1.4.0**。固定路徑 `/api/v1/*`；不建立任何特定專案專用通道。
1.4 新增：參照圖片自動比例、分鏡提示詞、LRC／音樂時間軸、最長180秒分段組片；詳見 [MV時間軸](MV_TIMELINE.md)。單鏡仍遵守原本主機幀數上限，負面提示詞能力未改變。
機器可讀 OpenAPI：`GET /api/v1/openapi.json`（需 Bearer 或已驗證帳號 session）；定義來源 `worker_schema.py`。
正式站的版本以實際部署為準；1.2 帳號啟用前須完成 [部署檢查](ACCOUNTS_AND_MODELS.md)。
新增欄位向後相容，呼叫端應忽略不認識的回應欄位；不相容改動另開 `/api/v2`。
版本化 profile 已發行的值不得就地變更，新的調校應使用新 profile 名稱。

這台機器是 GPU 媒體生成 worker；不是角色、音樂、行銷或社群資產的主資料庫。
既有網站保留作為本機操作／排錯面板。另一個專案應由自己的後端呼叫此 API，不能把密鑰放在瀏覽器。

## 責任邊界

| 製作／資產專案 | 本機 LTX worker |
|---|---|
| 使用者、角色設定、角色 LoRA 選用規劃、歌曲、腳本、分鏡、提示詞版本 | 接收最終提示詞、必要參照檔、支援的推論參數 |
| 行銷／社群素材、審片、資產授權與訓練同意 | GPU 執行、技術進度、錯誤、耗時與輸出檔案 |
| 多鏡頭排程、重試決策、剪輯、配原曲、最終資產庫 | 一次一個 GPU 任務；忙碌回 409，不偷偷並行 |
| 保存正式 MP4 及素材關聯 | 保留工作副本與可追溯的任務紀錄，不自動刪除 |

`external.project_id/asset_id/shot_id/request_id` 只是追蹤標籤，不是權限隔離。
`external` 整個物件與其中所有欄位都可省略。只送提示詞與生成參數即可使用，不需要登錄專案或 GitHub repo。
worker key 仍只適用於你管理的可信後端，擁有全主機權限；**不能發給一般註冊使用者**。
啟用帳號模式後，瀏覽器只能查看自己的上傳、任務與成品。`tenant_isolation: false` 指專案標籤不隔離，
`user_asset_isolation: true` 指已驗證瀏覽器帳號的資源隔離。不要把全權 key 誤認為個人 API key。

## 認證與連線

本機地址：`http://127.0.0.1:8787`。跨網路沿用 `https://ltx.mikamiu.studio` 與既有 Tunnel。
不要把 8787 綁到公網，也不要把 Cloudflare Access 改成 Bypass。

本機先建立一次密鑰：

```bash
python3 scripts/init-worker-key.py
```

密鑰儲存在 `data/worker/api-key`，權限 0600，不列印、不加入 Git、不覆寫既有密鑰。
支援 `LTX_WORKER_API_KEY_FILE` 或伺服器 secret manager 的 `LTX_WORKER_API_KEY`。
另一個專案須經安全管道取得密鑰並存到**後端**秘密設定；不能寫入 Git、前端環境變數、URL 或提示詞。

可信後端呼叫 `/api/v1/*` 時使用：

```http
Authorization: Bearer <worker-api-key>
```

跨 Cloudflare 時，還需要該 Access 應用核准的 Service Token，通常是：

```http
CF-Access-Client-Id: <service-token-client-id>
CF-Access-Client-Secret: <service-token-secret>
```

在 Access 以 Service Auth policy 授權指定 token；不要取代或移除現有人的登入規則。
建議只授權 `/api/v1/*` 的應用範圍，保留管理 UI 的人員登入限制。
只建立 Service Token 而沒有相應政策，並不會自動獲准。
此版本沒有改動 Cloudflare 帳號、政策或發行外部 Service Token；外部端到端接通仍需完成這一步。
[Cloudflare 官方 Service Token 文件](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)

啟用帳號模式後，瀏覽器可用本服務的 HttpOnly cookie 呼叫相同 v1 API；變更操作須提供
`/api/auth/session` 回傳的 `X-CSRF-Token`。Cookie 不跨網域分享；外部專案按鈕只是開啟服務，不是 SSO。
舊 `/api/jobs`、`/api/assets`、`/generated/*` 也套用帳號授權。舊版 `public/` 與建置目錄中的私人媒體必須先搬移，避免靜態檔案層繞過 API。

## API

| 動作 | 介面 | 回應 |
|---|---|---|
| 查詢模型、限制與能力 | `GET /api/v1/capabilities` | 200 JSON |
| 已安裝模型與參數格式 | `GET /api/v1/models` | 模型 ID、媒體類型、可用狀態、參數 schema |
| 讀取機器可讀契約 | `GET /api/v1/openapi.json` | OpenAPI 3.1 JSON |
| 預檢參數、不啟動GPU | `POST /api/v1/validate` | 200；完整解析後參數與有效秒數 |
| 上傳參照圖 | `POST /api/v1/assets?name=reference.png` | 201；保存 `id` |
| 列出／下載參照檔 | `GET /api/v1/assets`、`GET /api/v1/assets/{id}/file` | 已授權素材；下載需認證 |
| 送出任務 | `POST /api/v1/jobs` | 202；保存 `id` 和 `status_url` |
| 列出任務 | `GET /api/v1/jobs?limit=30&offset=0` | 分頁已授權歷史；limit 1–100 |
| 查進度／結果 | `GET /api/v1/jobs/{id}` | 200；`status`、`progress`、`artifacts` |
| 取消任務 | `POST /api/v1/jobs/{id}/cancel` | 202 取消中；已終止回200，不重啟 |
| 下載影片 | `GET /api/v1/jobs/{id}/video?download=1` | MP4；支援 Range／HEAD |
| 下載通用產出 | `GET /api/v1/jobs/{id}/artifact?download=1` | MP4／PNG／UTF-8 TXT；支援 Range／HEAD |

上傳是原始二進位，不是 multipart：`Content-Type: image/png`，body 為檔案 bytes。
可上傳 PNG／JPEG／WebP／MP4，每檔 50 MiB、共用素材庫 2 GiB；目前只有圖片可作生成條件。
MP4 上傳僅保存，**不是 V2V**。不接受遠端 URL、任意本機路徑或外部 callback URL，避免 SSRF 與任意檔案讀取。

### 送出影片任務

最小請求（仍需要下列 Authorization 與 Idempotency-Key headers）：

```json
{"prompt":"A quiet ocean sunrise, fixed camera.","profile":"preview-v1","duration_seconds":2}
```

`POST /api/v1/validate` 接受相同 body，不需 Idempotency-Key、不建立任務、不占GPU。
它仍驗證 I2V 參照圖是否存在；不保證所選尺寸能在剩餘記憶體中順利完成。

```http
POST /api/v1/jobs
Content-Type: application/json
Idempotency-Key: mv01-shot006-take001
Authorization: Bearer <worker-api-key>
```

```json
{
  "external": {
    "project_id": "creative-studio",
    "asset_id": "mv01",
    "shot_id": "shot006",
    "request_id": "take001"
  },
  "model": "ltx23-distilled",
  "mode": "t2v",
  "prompt": "A single medium close-up. The character releases a slow breath. The camera remains still.",
  "width": 768,
  "height": 512,
  "duration_seconds": 4,
  "fps": 24,
  "seed": 42,
  "audio": false,
  "offload": false
}
```

I2V 改為 `"mode": "i2v"`，另帶上傳回傳的 `"image_id": "..."`。
參照使用第 0 幀；`image_strength` 可設0–1，預設0.8；T2V 不接受圖片條件。
目前不接受角色 LoRA、音樂母帶、姿態／影片條件等額外欄位。
需要精準角色時，另一個專案先用角色圖工具製作核准的「每鏡起始圖」，再傳到 worker。

未設定時：model=`ltx23-distilled`、mode=`t2v`、width=768、height=512、frames=49、fps=24、seed=42、audio=true、offload=false。
`prompt` 上限 4000 字元、width/height 為 256–1536 且是 64 倍數；整數欄位不得傳浮點或字串。

### 版本化生成預設

| profile | 尺寸 | 幀數／FPS | 音訊 | 用途 |
|---|---|---|---|---|
| `compat-v1`（預設） | 768×512 | 49／24 | true | 保留舊請求行為 |
| `preview-v1` | 512×320 | 49／24 | false | 低解析度試鏡 |
| `landscape-v1` | 1024×576 | 97／24 | false | 16:9 橫式素材起點 |
| `portrait-v1` | 576×1024 | 97／24 | false | 9:16 直式素材起點 |

明確傳入的尺寸、音訊、幀數／秒數等會覆寫 profile；回應 `resolved_parameters` 記錄最終值。
這些是可重現的參數組，不是經大量盲測後的最佳品質承諾。原先不帶 profile 的客戶端不會被改成無音訊。
預設安裝仍是 `ltx23-distilled`；固定第一階段8步、第二階段3步。不把不支援的 steps／guidance／negative_prompt 假裝接通。新增模型以 `/api/v1/models` 為準，參數位於各模型的 `parameters`。
`audio=false` 停用音訊解碼與輸出，並非移除模型所有聯合音訊推論。

### 冪等與排程

- 同一 `external.project_id`＋`Idempotency-Key`＋相同請求，回 200 和原任務，不重新生產。
- 不傳 project_id 時使用預設 scope；不同可信後端請使用 UUID 或具辨識度的 key，避免互撞。已登入瀏覽器帳號會再按 user ID 隔離 key，不能跨帳號重播他人的任務；project_id 本身不是租戶邊界。
- 同一 key 改提示詞／尺寸／其他欄位，回 409 `idempotency_conflict`。新 take 使用新 key。
- 另一任務佔用 GPU，回 409 `worker_busy`，`Retry-After: 5`；上游持有待處理佇列。
- 生成通常超過普通 HTTP 請求時間，所以 submit 很快回任務 ID；不要等待一次 HTTP 呼叫直接產出 MP4。
- 建議上游每 2–5 秒輪詢；暫時網路錯誤可漸增間隔。重送 submit 時保持相同 body／key。
- 終止狀態：`succeeded`、`failed`、`interrupted`、`cancelled`。中斷不自動重試；查清原因後另開新 take。
- `timeout_seconds`：30–7200秒，預設3600（主機可用 `LTX_JOB_TIMEOUT_SECONDS` 調整預設）。包含載入、推論、解碼與驗證。
- 即使推論沒有任何新log，watchdog仍會取消／逾時終止所屬程序群；直到停止前GPU名額不釋出。
- 取消回202代表已接收，繼續輪詢直到 cancelled；完成與取消競爭時以先完成的狀態為準。完成後取消不刪檔。
- SIGTERM/SIGINT 正常關閉會停止推論；Linux 模型程序也設定父程序死亡訊號，避免API突然死亡留下GPU推論。
  [Linux parent-death signal 說明](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html)
- 錯誤的 `error.code` 包含 `generation_failed`、`generation_timeout`、`quality_check_failed`、`validation_timeout`、`worker_error`、`worker_restarted`、`worker_shutdown`、`cancelled`。
  `retryable` 只是提示，不會自動執行；真正重新生產必須使用新 key。忙碌或網路不明時則沿用原 key 重送。
- 接單前檢查剩餘磁碟至少5GiB，不足回503 `insufficient_disk`；不會自動刪掉既有影片。
- 主機必須保持開機、不休眠、API 與 Tunnel 正常執行。尚未設定開機自啟或外部監控。

### 結果

成功時 `artifacts[0].url` 是同一 worker origin 下、需要認證的 MP4 路徑。
新產出附帶 `sha256` 和 `size_bytes`。上游下載後核對，再保存到自己的磁碟／S3／R2／資產庫。
不要把 worker 的帶認證下載 URL 直接當成前端公開影片 URL；由上游後端取回並提供自己權限下的預覽。
目前不支援 webhook，也不會把影片自動推送到未指定的第三方儲存。

`measured_media.video_seconds` 為影片串流長度；`container_seconds` 可因音訊尾端而不同。
量測失敗或舊紀錄沒有量測時，不得把設定秒數標示為實測。

### 成品技術驗證

新產出先寫入私有 `data/worker/work/{job_id}/`，完整解碼驗證後才原子移入輸出資料夾；生成中的半成品不再位於網頁公開目錄。
`quality_control.version=full-decode-v1`，`passed=true` 才能標示新任務 succeeded：

- 核對完整解碼幀數、寬高、FPS、時間戳遞增、實際片長；少幀／尺寸或時間不符直接失敗。
- 依 audio 設定驗證音軌有無，解碼音訊；影音尾長差列警告。
- 32×18 灰階縮圖統計近黑畫面（平均亮度<8且標準差<4）與近似靜止畫面（相鄰平均差<0.5），只作警告。
- 縮圖建立失敗不否定可解碼的影片，回 `poster_unavailable`；使用者仍可下載合格MP4。
- 生成檔SHA256與來源參數可供上游驗收。任何警告都不表示角色、美感、動作、音樂節拍已通過審片；`visual_review_required=true`。

黑色轉場、刻意靜止鏡頭可能觸發警告，不能因此自動刪除作品。
舊檔未重新解碼，不補造QC通過標記；其 quality_control 可能是 null。

## 單鏡時長

v1.3 的預設主機上限為 **481 幀**。`GET /api/v1/capabilities` 回傳目前值，UI 依此顯示最長秒數。這是資源管控設定，不是 LTX 全系列的絕對極限，也不是記憶體／內容品質保證。

| FPS | 481 幀的時間 |
|---|---|
| 8 | 約 60.125 秒（實驗性長片、低流暢度） |
| 16 | 約 30.063 秒（實驗性長片） |
| 24 | 約 20.042 秒 |
| 30 | 約 16.033 秒 |

API 可接受 8–60 FPS，但低 FPS 換取時長不等於同等動作品質或已驗證最佳設定。
`duration_seconds` 與 `frames` 只能選一個。秒數向上對齊到合法 `8n+1` 幀，不足一個合法片段時至少9幀；最後回傳實際設定。
例如 20秒／24FPS → 481幀 → 約20.042秒；在預設上限下，20秒／30FPS 超過481幀，回400，**不偷偷縮短**。

網頁現已提供秒數預設、自訂秒數與「最長可選」。切換 FPS 保留要求的秒數，超限時顯示錯誤並阻止送出；不再使用原本的 `min(257, ...)` 靜默截短。
播放器若只顯示整秒，也不能單憑「0:09」判斷是否少幀，應比較檔案的 frames／FPS／duration。

2026-08-30 實際檢查既有任務 `2ef606e0bf37`：請求257幀／30FPS，檔案也確實257幀／30FPS、8.5667秒；該檔案沒有編碼少幀，片長來自提交的幀數／FPS。

官方託管 LTX-2.3 Fast 在部分解析度與 FPS 組合列有20秒；這不是本機 distilled 設定已經驗證可跑20秒的證據。
主機管理者可在 `.env.local` 設定 `LTX_MAX_FRAMES` 後重新啟動 API，允許 257–1201 間的 `8n+1` 整數；例如601幀可接受20秒／30FPS。提高上限會增加運算時間與記憶體壓力，應另作目標解析度壓力測試，不會由網頁自動提高。20秒以上會標示實驗性，不能把降低 FPS 延長片長當成同等流暢度與一致性。
[LTX-2.3 官方 API 規格](https://docs.ltx.io/models/ltx-2-3)

整支 MV 可由上游分鏡、逐鏡生成及剪輯；整片時長不受單鏡幀數限制。

## 比例與負面提示詞

UI 使用 `9:16`、`16:9`、`1:1`、`4:3`、`3:4`、`3:2` 比例，不再要求手填寬高。通用 API 新增 `aspect_ratio`，依 capabilities 中的實際尺寸生成，例如 `9:16` 對應576×1024、`16:9` 對應1024×576；均為精確比例且符合二階段生成的64倍數。原有 `width`／`height` API 保留相容，但不可和 `aspect_ratio` 同送。

```json
{"prompt":"A calm ocean, gentle waves, fixed camera.","aspect_ratio":"16:9","duration_seconds":20,"fps":24,"audio":false}
```

本機只有 Distilled v1.1 checkpoint，官方設定是 CFG=1，兩階段只編碼正面提示詞。UI 改為明確能力說明，不再顯示無效的空白負面欄位。API 對非空 `negative_prompt` 回400；真正的負面條件需要另外安裝 Dev checkpoint 和 guided pipeline，不能僅解除欄位 disabled 或把負面文字附加到正面提示詞冒充實作。
[LTX-2.3 官方模型說明](https://huggingface.co/Lightricks/LTX-2.3)

## 登出可靠性

本站登出會撤銷當前 cookie 對應的本機 session，清除瀏覽器 cookie；已過期或重複登出仍回200。有效 session 仍須正確 CSRF，且不取消 Cloudflare JWT 與 Origin 檢查。跨頁籤輪替 cookie 導致 `csrf_failed` 時，前端重新讀取 session，最多重試一次；其他錯誤不重送寫入。

同源頁籤會收到不含身份／token 的登出通知；回上一頁或重新聚焦時重查身份，避免舊畫面看起來仍登入。外網另有「含 Cloudflare 登出」，先確認本站登出成功，才導向同源 `/cdn-cgi/access/logout`；localhost 不顯示這個選項。此官方端點也會撤銷該 Cloudflare 團隊其他應用的登入狀態，UI 已提示。沒有移除允許名單、重設密碼或代替使用者退出目前帳號。
[Cloudflare 登出機制](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/#log-out-as-a-user)

## 其他 GitHub 專案的角色位置

- [Qwen-Image／Image-Edit](https://github.com/QwenLM/Qwen-Image)：由創作專案管理角色圖、表情、新構圖與起始圖。
- [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)：後續需要姿態／深度／動作控制時，再增加明確的 worker 能力。
- [LTX Trainer](https://github.com/Lightricks/LTX-2/tree/main/packages/ltx-trainer)：經授權的訓練另作隔離工作，不與服務中影片推論爭用GPU。

可以跨 repo 整合，通常透過 API／檔案契約，而不是把各專案合併成一個大 Git repo。
上述模型未因此被自動下載或安裝；既有平面角色的母版、版號、授權都留在上游。
v1.2 已提供圖片／文字／影片轉接器介面，共用本 worker 的单一執行名額；實際其他模型仍須另行安裝與驗收，不會同時執行兩個模型任務。

## 本機資料與維運

- `data/worker/jobs.sqlite3`：任務、參數、外部 ID、狀態與來源指紋；重啟可查，不保存完整企劃。
- `uploads/`：送來的私人工作參照；`data/worker/outputs/`：通過驗證的私人產出、預覽和sidecar。舊public與build檔案須依帳號部署文件搬移。
- `data/worker/work/`：新任務的私有log、未通過驗證／中斷的暫存檔。保留供排錯，不自動刪除；舊log未搬動。
- 自訂 `LTX_WORK_DIR` 必須位於非公開位置，且與輸出目錄同一個檔案系統，才能原子發布。主機啟動會檢查。
- 正式資產及審片評語由上游專案持有。沒有「所有輸出自動回訓」或每日安裝新模型。
- 模型先記檔名、大小、修改時間，不宣稱已驗證完整權重SHA；本地程式與參照圖有SHA256。
- 開始、結束、階段轉換與持續有log時至少每2秒的進度會落盤；沒有新log不偽造進度。重啟未完成任務標記 interrupted。
- 一次只啟動一個 API 程序服務此 GPU；同一專案以檔案鎖阻止第二個API程序，即使換連接埠也會拒絕。不同專案／其他GPU程式仍需由主機管理者協調，不能當作全機GPU排程器。
- SQLite開啟WAL，備份應在停服務後複製或用SQLite備份工具，不只複製正在寫入的主檔。
- 不自動刪除上游尚未收取的影片。後續可在上游確認入庫後，加入有範圍的保留／清理政策。

## 接到另一專案

`examples/worker-client.mjs` 是無第三方依賴的 Node 後端用戶端，支援提交、狀態、上傳與串流下載。
請求不跟隨重新導向，避免把密鑰帶往其他網址；看到登入頁表示 Cloudflare 服務授權尚未完成。

```js
import { LTXWorker } from './worker-client.mjs';

const worker = new LTXWorker({
  baseUrl: process.env.LTX_WORKER_BASE_URL,
  apiKey: process.env.LTX_WORKER_API_KEY,
  accessClientId: process.env.CF_ACCESS_CLIENT_ID,
  accessClientSecret: process.env.CF_ACCESS_CLIENT_SECRET,
});
const capabilities = await worker.capabilities();
// 上游先保存這個 request body 和 key，網路重試不要每次換 key。
const job = await worker.submit({
  prompt: 'A quiet ocean sunrise, fixed camera.',
  profile: 'preview-v1', duration_seconds: 4, fps: 24, audio: false,
}, 'mv01-shot006-take001');
// 保存 job.id；由上游背景排程輪詢，不阻塞前端請求。
const status = await worker.job(job.id);
if (status.status === 'succeeded') {
  const video = await worker.video(job.id);
  // 將 video.body 串流保存至你自己的資產庫，再給前端你的影片URL。
}
```

測試：使用已安裝 PyAV／Pillow／PyTorch 的 LTX Python 執行 `python -m unittest discover -s tests -v`。
契約測試另使用該環境現有的 jsonschema。Node用戶端測試：`node --test tests/worker-client.test.mjs`。
API單元測試不啟動GPU訓練，也不更動真實作品；真實生成另由人工小樣驗證。

可重跑的 GPU 小樣驗收（需要主機閒置，會保留測試產出）：

```bash
node examples/worker-smoke.mjs                         # 只驗證參數，不生成
node examples/worker-smoke.mjs --generate --audio      # 一秒T2V與音訊
node examples/worker-smoke.mjs --generate --profile portrait-v1 --reference /absolute/path/to/approved.jpg
```

腳本只由你手動執行，從後端環境或私有key檔讀取密鑰、不列印；會驗證冪等、成品QC、SHA256與Range下載。
若腳本中斷，先用 `outputs/worker-acceptance/*.request.json` 的原 key/body 查詢或重送；不要不明狀態下另開新take。

## 本機實測紀錄（2026-08-30）

- 透過 Node 後端用戶端呼叫 v1，任務 `9b6187e7c21d`。
- 請求1秒、384×256、24FPS、無音訊 → 合法25幀；檔案量測1.041667秒。
- 生成耗時41.7秒，輸出86,971 bytes；下載SHA256一致，Range下載成功。
- 相同body／key重送回原任務，沒有第二次生成。
- 重啟API後，仍可查詢／下載同一任務，重送同一請求仍回原任務。
- 第二個API程序即使指定不同埠也被檔案鎖拒絕，未啟動第二個GPU worker。
- 24項Python測試及2項Node用戶端測試通過；本次沒有改動前端畫面。
- 未帶本機worker key回401；公網未登入仍回Cloudflare302，Access保護未移除。
- 這是本機短片整合測試，不是外網第二台機器的端到端測試，也不是20秒效能測試。
