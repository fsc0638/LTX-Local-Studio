# Cloudflare Tunnel deployment

> 2026-08-30：已授權並啟用 [新註冊同步 Cloudflare Access](CLOUDFLARE_ACCOUNT_SYNC.md)，保留管理者 Allow 規則並新增精確 EMAIL 清單與 One-time PIN。未升級方案、未修改 DNS／Tunnel、未開放匿名註冊。
> 本機 `internal` 帳號流程保留；外部增加 Access JWT 與同信箱本機登入。以下較早的媒體測試數據與儲存路徑屬舊版紀錄，帳號版素材隔離以 [帳號設定](ACCOUNTS_AND_MODELS.md) 為準。

This deployment keeps the GPU worker, model weights, API, and generated media on the local machine. Cloudflare receives an outbound tunnel connection and exposes one authenticated HTTPS hostname.

## Required values

- A domain active in Cloudflare DNS
- A subdomain such as `ltx.example.com`
- A named Cloudflare Tunnel
- The email addresses or identity-provider group allowed to sign in

## Security order

1. In Cloudflare Zero Trust, create a self-hosted application for the full hostname.
2. Add a restrictive Allow policy for the intended users. Access applications are deny-by-default, but verify the policy before publishing the route.
3. Create a named tunnel and install its connector on the model machine.
4. Enable **Protect with Access** for the published application route so the connector validates Access tokens.
5. Point the public hostname at the local UI service only through the tunnel. Do not create router port-forwarding rules.

## Local configuration

`scripts/cloudflare-stack.sh` uses a system `cloudflared` installation when available and otherwise falls back to the Git-ignored `.tools/cloudflared` executable included on the model machine.

Authenticate and create a tunnel with the official `cloudflared` client:

```bash
cloudflared tunnel login
cloudflared tunnel create ltx-local-studio
cloudflared tunnel route dns ltx-local-studio ltx.example.com
```

Copy the configuration template:

```bash
cp infra/cloudflare/config.yml.example infra/cloudflare/config.yml
```

Replace the tunnel UUID, credentials file path, and all three `ltx.example.com` entries. The real configuration is ignored by Git because it contains device-specific identifiers and paths.

The template pins the connector to HTTP/2 so it also works on networks that block outbound QUIC/UDP port 7844.

Set the deployed origin in `.env.local` while keeping the API on loopback:

```env
LTX_API_HOST=127.0.0.1
LTX_API_PORT=8787
LTX_ALLOWED_ORIGINS=https://ltx.example.com
```

Build the browser bundle with same-origin API URLs and launch the UI, local model API, and tunnel:

```bash
npm run build:cloudflare
npm run start:cloudflare
```

## Route map

| Public path | Local destination |
| --- | --- |
| `/api/*` | `http://127.0.0.1:8787` |
| `/generated/*` | `http://127.0.0.1:8787` |
| all other paths | `http://127.0.0.1:3000` |

The hostname must remain fully protected by Cloudflare Access. The local Python API also enforces service accounts, ownership and quotas; neither authentication layer should be disabled for public access.

## 新增使用者（繁體中文）

目前為雙層登入的私人服務，不是開放匿名註冊網站。

1. 新使用者先在本機受控的 `/auth/register` 入口註冊；啟用後首次註冊自動追加至 `ltx-registered-users`，不需要修改管理者政策。
2. 註冊顯示同步成功後，在其他裝置開啟 `https://ltx.mikamiu.studio/`。
3. 使用相同信箱在 Cloudflare 要求一次性驗證碼，完成驗證後，再登入本機帳號密碼。
4. 既有帳號不追溯同步；須由管理者明確加入清單。撤權時從所有 Allow 資格移除並撤銷既有 Access 工作階段，系統不會因再次登入而自動加回。

不要將 Include 改成 Everyone，也不要僅以 Login Methods = One-time PIN 作為允許條件；那會擴大到所有符合該登入方式的人。

使用者共用同一台 GPU，但帳號模式會檢查素材／任務所有權與配額；通過 Cloudflare 不等於取得其他帳號的素材。同步僅追加信箱，不會替使用者寄送或代填驗證碼。完整操作與驗收狀態見 [同步設定](CLOUDFLARE_ACCOUNT_SYNC.md)。

## 檔案上下載

- 素材頁可上傳 PNG / JPEG / WebP / MP4，單檔 **50 MiB**。素材庫總量上限 **2 GiB**；低於 **5 GiB** 剩餘磁碟空間時拒絕新上傳。
- 圖片可選「用於圖片生成」，使用第 0 幀、參照強度 0.8；影片目前只支援保存、預覽、下載，尚未接入影片轉影片。
- 素材和產出都有下載連結；影音端點支援 Range/HEAD，可拖曳播放進度，不需重新下載整段。
- 原始檔存於專案 `uploads/`，產出在 `public/generated/`，皆排除 Git。沒有自動清理或使用者隔離；管理者需自行安排備份與清理。
- 媒體與 JSON 回應使用 `Cache-Control: private, no-store`。不要另設 Cache Everything 規則快取私人檔案。
- Cloudflare Free 的一般請求上傳上限為 100 MB；本系統另設較低的 50 MiB 應用程式限制。若需大檔，應另實作分塊上傳，不要移除 Access 或直接暴露本機埠。

## GPU、效能與 94% 錯誤修正

請從能存取 NVIDIA GPU 的**主機終端**啟動服務，不要在無 GPU 權限的受限執行環境中執行。伺服器 `/api/health` 應顯示 `runtime.cuda_available: true` 及 `NVIDIA GB10`；啟動時會檢查，每個生成程序也會再次檢查，禁止默默退回 CPU。GPU 權限修復後需重新啟動服務。

本次失敗紀錄顯示 CPU 推論：第一階段約 351 秒、第二階段約 563 秒，最後在音訊聲碼器因 FP32 輸入/BF16 bias 不一致而失敗。`scripts/run_local.py` 現在將音訊聲碼器建為 FP32，主要模型與音訊 VAE 仍採 BF16；不修改模型權重檔或上游套件。適配器依賴目前上游 AudioDecoder 的內部 builder 介面，升級 LTX 套件後須重新跑測試。

2026-08-30 修正後實測：768×512 / 49 幀 / 24 FPS / seed 42 / BF16 / 無 CPU offload / 有音訊，GPU 完整生成約 **56.32 秒**。提示詞為海浪日出；這不是同提示詞的嚴格 A/B 測試，也不保證所有提示詞與設定都有相同時間。

圖片參照端到端測試：上傳既有 `ltx-2.3-smoke-first-frame.png`，以 384×256 / 17 幀 / 24 FPS / 有音訊生成成功，約 **41.43 秒**，JPEG 預覽亦成功建立。PNG 與 MP4 上傳後下載的位元組比對一致；Range 請求回覆 206。未登入的外部素材與產出端點仍回覆 Cloudflare Access 登入轉址，沒有放寬存取政策。

快速試詞可用頁面的 **384×256 / 17 幀** 預設，再提高畫質與秒數。短片、較少幀和較低解析度通常能减少推論工作量。保留 CPU offload 關閉（有記憶體不足才開）；不要同時跑多個重型 GPU 工作。遠端電腦只傳設定和媒體，推論仍在主機；網路會影響素材上傳、預覽下載及狀態查詢，不會替 GPU 加速。進度為階段加權估計，不是剩餘時間預測。

下一步可評估常駐模型 worker，減少每次重載模型的成本；需額外記憶體管理與失敗復原，尚未實作。

## 驗證

```bash
# 使用原始 venv 的 Python 路徑，不要 resolve 成 /usr/bin/python。
"$LTX_PYTHON" -m unittest discover -s tests -v
npm run build:cloudflare
curl http://127.0.0.1:8787/api/health
```

官方參考：[Access policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/)、[One-time PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/)、[Cloudflare upload limits](https://developers.cloudflare.com/workers/platform/limits/#request-and-response-limits)、[PyTorch AMP](https://docs.pytorch.org/docs/stable/amp.html)。
