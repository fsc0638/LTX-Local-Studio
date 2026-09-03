# LTX Local Studio

## 媒體生成主機模式

這台主機負責 LTX 影片生成；角色、音樂、企劃、行銷與正式素材庫由另一個專案管理。
新增 `/api/v1` 後端呼叫介面，提供認證、冪等提交、進度查詢、參照圖上傳與影片下載。
目前程式契約 v1.2.0：新增服務帳號、Email 驗證後重新登入、個人素材隔離與模型轉接器清單；保留 v1.1 的 LTX 請求格式。
新成品必須通過完整解碼／幀數／尺寸／FPS／片長／音軌檢查；黑畫面與近似靜止畫面僅供審片警告。
任務紀錄保存在本機 SQLite；不自動訓練或更新模型。現有 UI 保留作操作與診斷。
詳見 [跨專案 Worker API](docs/WORKER_API.md) 與 [Node 後端用戶端](examples/worker-client.mjs)。

帳號功能的正式啟用另需 SMTP、舊媒體私有化與部署驗收；修改程式不會自動移除既有 Cloudflare Access 保護。
請先閱讀 [帳號、網域與模型設定](docs/ACCOUNTS_AND_MODELS.md)。

2026-08-30 決策：先採 `LTX_AUTH_MODE=internal` 進行內部帳號測試，暫不購買 Cloudflare Workers Paid、不寄驗證信。
註冊後仍需帳密登入，Email 不假標為已驗證，素材隔離與 CSRF 保留。詳見 [內部測試與 Cloudflare 升級待辦](docs/INTERNAL_TESTING.md)。

同日後續已啟用 [新註冊同步 Cloudflare Access](docs/CLOUDFLARE_ACCOUNT_SYNC.md)：本機註冊後加入專用信箱清單，外部須先通過 Cloudflare 信箱驗證，再用相同信箱的本機帳號登入。無需啟用 SMTP；真實 OTP 收信仍待使用者驗收，既有帳號不會自動補入名單。

A local-first web console for securely running LTX-2 and LTX-2.3 video generation on your own GPU.

LTX Local Studio combines a multilingual browser UI, a local job API, and an LTX worker bridge. The current verified configuration targets LTX-2.3 Distilled on NVIDIA GB10 with BF16 and SDPA.

## Features

- Traditional Chinese, English, and Japanese UI
- Local registration, verified email, fresh login, password reset and private account workspaces
- Host-installed video/image/text adapters sharing one account and job API
- Text-to-video prompt workflow
- Resolution, frame rate, duration, seed, precision, and memory controls
- Real-time job progress and persistent local output history
- Production Factory shot queue with validation, pause/resume, retry, JSON handoff, and per-shot output review
- MP4 preview and generated poster frames
- Local-only model weights and outputs
- Environment-based paths for portable GitHub use

## Requirements

- Linux with a supported NVIDIA GPU
- Node.js 22.13 or newer
- Python 3.12 or newer
- A working LTX-2/LTX-2.3 checkout and virtual environment
- LTX-2.3, spatial upscaler, and Gemma model files

## Local setup

1. Install the web dependencies:

   ```bash
   npm install
   ```

2. Copy the environment template:

   ```bash
   cp .env.example .env.local
   ```

3. Set `LTX_REPO_ROOT`, `LTX_PYTHON`, `LTX_PUBLIC_ORIGIN` and SMTP in `.env.local`. Keep registration closed until delivery has been tested. Existing installations must first follow the private-media migration in [account setup](docs/ACCOUNTS_AND_MODELS.md).

4. Start the UI and local inference API:

   ```bash
   npm run dev
   ```

5. Open `http://localhost:3000`.

## Cloudflare remote access

The repository includes a same-origin Cloudflare Tunnel configuration. The public hostname routes the UI to port 3000 and routes `/api/*` plus `/generated/*` to the loopback-only model API on port 8787.

After creating a named tunnel and an Access-protected hostname, copy `infra/cloudflare/config.yml.example` to the ignored `infra/cloudflare/config.yml`, fill in the tunnel UUID, credentials path, and hostname, then run:

```bash
npm run build:cloudflare
npm run start:cloudflare
```

See [Cloudflare setup](docs/CLOUDFLARE.md) for the account-side security requirements. Never publish the hostname before its Cloudflare Access policy is active.

The first [Production Factory](docs/PRODUCTION_FACTORY.md) control layer batches standard `/api/v1/jobs` requests without creating project-specific model routes. It runs one validated shot at a time, pauses on failure, resumes after refresh, and exports a portable JSON production manifest.

Optional [registration-to-Access synchronization](docs/CLOUDFLARE_ACCOUNT_SYNC.md) appends new registered emails once to a dedicated Cloudflare EMAIL list, preserves dashboard revocations, and binds external Access identity to the local account. It is off by default for new installations and enabled on this host. Adding an email does not itself send an OTP or verify ownership; users request a code on the Cloudflare login page. The dedicated token must be rotated before November 29, 2026 (Asia/Taipei).

## Repository safety

This repository intentionally excludes:

- model checkpoints and Hugging Face caches
- generated videos, poster frames, and logs
- `.env.local`, credentials, tokens, and tunnel configuration
- dependencies and build output

Never expose port 8787 directly to the internet. For remote access, place authentication, rate limiting, and a same-origin HTTPS gateway in front of the loopback-only API. See [Remote access architecture](docs/REMOTE_ACCESS.md).

## Project layout

```text
app/                   Multilingual web interface
components/ui/         Styled UI primitives
data/worker/outputs/   Private generated outputs (ignored by Git)
data/worker/           Local account/job databases and private migration backups
local_adapters/        Trusted administrator-installed model adapters
scripts/dev.sh         Local UI + API launcher
scripts/run-ltx-2.3.sh Portable LTX runner
local_backend.py       Loopback-only job API
extract_poster.py      Video poster extraction
docs/                  Architecture documentation
```

## Status

The local text-to-video workflow is functional. Cloudflare Tunnel support is included; a Cloudflare domain, named tunnel, and Access allow policy are required before remote access becomes active.
