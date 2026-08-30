# 服務帳號、可更換網域與模型介面

程式契約：v1.2.0。這台機器是獨立媒體生產服務，不綁定某個 GitHub 專案。
本次不自動更改 Cloudflare Access、不下載模型、不寄送真實郵件，也不自動遷移既有素材。

## 1. 使用者流程

以下為 `LTX_AUTH_MODE=verified_email` 的正式驗證模式。2026-08-30 起先使用可切換的 `internal` 免郵件測試模式：
保留註冊、帳密登入與私有資料；不寄信、不自動登入、不偽造信箱驗證。詳見 [內部測試與升級待辦](INTERNAL_TESTING.md)。

外部專案的設定按鈕 → 本服務登入／註冊 → 填姓名、帳號、密碼、Email → 收驗證信
→ 點信中連結並按「驗證電子郵件」→ **重新輸入帳號密碼登入** → 上傳、生成、預覽、下載。

- Email 驗證證明可接收該信箱郵件，不是實名身分驗證，也不是每次登入的 MFA。
- 帳號：3–32 個英文字母／數字／`_.-`，不區分大小寫；姓名1–80字；密碼8–128字元，英數即可、不強制特殊符號，也保留較長密語與符號。
- 未驗證者不能登入或生成。驗證連結一次有效、30分鐘過期；點驗證不建立 session。
- 工作階段8小時；cookie 為 host-only、HttpOnly、SameSite=Lax，HTTPS 使用 Secure 與 `__Host-` 名稱前綴，阻止其他子網域植入 Domain cookie。
- 有重寄驗證信、忘記密碼與重設功能。重設後撤銷該帳號原有工作階段，再重新登入。
- 密碼用 scrypt N=2^17/r=8/p=1 與隨機 salt；session 與驗證 token 僅保存雜湊。
- 網頁使用既有白底、黑字、珊瑚粉／青綠與方角設計；繁中／英文／日文，自訂風格選單。

### 保護範圍

帳號只能讀取自己的素材、任務、影片／圖片／文字與下載，包含舊 UI 路由。
舊的無 owner 資料不會自動交給第一位註冊者，只能由主機管理者／可信 worker key 存取。
SQLite `data/worker/accounts.sqlite3` 與 `jobs.sqlite3`、uploads 和 outputs 應一起備份，停機複製或使用 SQLite backup API；不要只複製仍在寫入中的單一 DB。

worker key 仍是**全主機管理級**的可信後端密鑰，不是一般帳號金鑰，不可交給所有註冊者。
應用層有登入／寄信頻率限制、雜湊運算同時最多2件、每帳號預設每日20件任務、全機單一生成任務。
上傳庫目前是全機2 GiB總量，不是每人2 GiB；公開規模成長前仍需評估容量與濫用防護。
這是本機服務基礎，不宣稱已完成 SaaS 的付費、管理員 UI、完整稽核、CAPTCHA 或每帳號 API key。

## 2. 正式寄信設定（仍需管理者提供）

在被 Git 忽略的 `.env.local` 設定，下列欄位不可放在前端 `NEXT_PUBLIC_*`：

| 設定 | 用途 |
|---|---|
| `LTX_USER_AUTH_ENABLED=1` | 啟用本機帳號保護；預設1 |
| `LTX_AUTH_MODE=verified_email` | 預設正式驗證；`internal` 僅供可信內部免郵件測試 |
| `LTX_PUBLIC_ORIGIN=https://ltx.mikamiu.studio` | 當前服務 canonical origin；無路徑 |
| `LTX_REGISTRATION_ENABLED=0` | 部署檢查期間保持關閉，驗收後才改1 |
| `LTX_SMTP_HOST`、`LTX_SMTP_PORT` | 郵件供應商的 SMTP 主機／埠 |
| `LTX_SMTP_SECURITY=starttls` 或 `ssl` | 強制 TLS；一般587或465，以供應商為準 |
| `LTX_SMTP_USERNAME` | 供應商提供的寄信帳號 |
| `LTX_SMTP_PASSWORD_FILE` | 私有0600檔案中的 SMTP／應用程式密碼 |
| `LTX_SMTP_FROM` | 已獲供應商授權的寄件地址 |
| `LTX_INTERNAL_API_ORIGIN=http://127.0.0.1:8787` | 網站伺服器端的 API 代理，不是公網 URL |
| `LTX_USER_DAILY_JOB_LIMIT=20` | 每帳號最近24小時的任務接受量，包含失敗任務 |

請先告知供應商與寄件地址，**不要在聊天貼 SMTP 密碼**。從本機秘密檔案或 secret manager 設定。
SMTP 憑證不會傳給生成子程序。驗證 token 放在郵件連結的 URL fragment，不進入 HTTP 路徑或 Referer；頁面讀取後移除 fragment，不寫入 localStorage。

在 `verified_email` 模式，未設定 SMTP 時註冊保持關閉。只有明確設定 `internal` 才能不寄信註冊；兩種模式都不會回傳假驗證連結或自動把帳號標為已驗證。
`email_ready` 僅表示設定齊全，**不代表郵件已送达**。須以真實信箱驗收寄送、收件匣／垃圾郵件、連結及新登入。
寄信失敗後帳號可能仍處於未驗證狀態；稍後使用重寄功能，勿建立重複帳號。

## 3. 舊安裝的安全搬移與部署順序

某些靜態伺服器會在 API rewrite 前回傳 `public/` 或 `dist/client/` 檔案。
所以加登入頁並不足以保護舊影片，必須先將私人檔案移出靜態目錄。

1. 保留 Cloudflare Access 現有保護，確認沒有執行中任務，備份 DB／素材。
2. 停止 API 與 UI。先執行 `python3 scripts/secure-media.py` 看搬移計畫；確認後用 `--apply`。
3. 工具搬移（不覆寫／刪除檔案內容）：
   - `public/generated/` → `data/worker/legacy-outputs/`
   - `public/media/` → `data/worker/legacy-media/`
   - `dist/client/generated/` → `data/worker/legacy-build-generated/`
   - `dist/client/media/` → `data/worker/legacy-build-media/`
4. 搬移以同檔案系統的 exclusive hard link + unlink 執行；不同檔案系統會失敗，不偷偷复制或覆蓋。中斷可能留下兩個名稱，依 `data/worker/migrations/*.json` 與實際檔案檢查，不盲目重跑。
5. 原檔內容仍可由新位置與 journal 找回。復原到 public 會再次公開檔案，僅能在停止對外服務時處理。
6. 設定帳號與 SMTP，執行 `python3 scripts/check-service-layout.py`、`npm run build`，再啟動新 API／UI。API與正式UI啟動前都會檢查舊公開檔案。
7. 保持舊 Access 保護，在獲准網路用真實信箱測一次註冊→驗證→重新登入→生成→下載；確認別的帳號與未登入請求均無法讀取。
8. 完成後才規劃「一般新使用者如何通過 Cloudflare」的政策：目前 Access 允許清單可能先擋住他們。應明確保留管理面與可信後端邊界，不能直接全部 Bypass。此步需要另行確認及部署測試。

新成品位置預設 `data/worker/outputs/`；暫存與 logs 在私有 `data/worker/work/`。
不要以 Nginx alias、靜態主機或新的 Tunnel route 直接公開 `data/`，下載必須通過 API。
直接 `npm run dev:web` 只供 loopback UI 開發；對外部署須走完整 preflight，不可把開發伺服器當正式入口。

## 4. 日後更換子網域

1. 管理者更新 DNS／Tunnel 與憑證／Access 應用主機名稱。
2. 改 `LTX_PUBLIC_ORIGIN=https://新子網域`，若維護額外來源則更新 `LTX_ALLOWED_ORIGINS`；移除不再信任的來源。
3. 重啟 API 讀新設定。前端一律使用相對 `/api` 與下載 URL，**不必改任何專案專用程式碼**。
4. 外部專案只改服務網址設定。Cookie不跨網域，新網址要重新登入；帳號／素材／任務DB仍沿用。
5. 舊郵件指向舊網域，需保留受控遷移期或在新網址重寄。不要讓已棄用網域的驗證連結落入別人控制。

不要把任意來訪的 Host／X-Forwarded-Host 用來生成驗證信；程式只用受信的 `LTX_PUBLIC_ORIGIN`。
若内部 API 埠／位置改動，再改 `LTX_INTERNAL_API_ORIGIN` 並重建／重啟 UI proxy；單純公共子網域變更不需此步。

## 5. 其他專案的連線按鈕

在對方專案保存「媒體服務網址」，按鈕直接導向 `${serviceOrigin}/auth/login` 或 `${serviceOrigin}/`。
新視窗連結加 `rel="noopener noreferrer"`；不傳密碼、session、主機 key 或 Email驗證token。
使用者在本服務完成帳號流程後即可操作已安裝模型。這是**跨專案入口，不是 SSO 或 OAuth 授權**。
若未來要「對方專案自己送出帳號名下任務」，還需設計個人 API key／OAuth consent；本次不把管理級 worker key 當作替代品。

## 6. 更換影片、圖片或文字模型

目前真實預設仍是 `ltx23-distilled`。未安裝的模型不顯示，也不聲稱已載入 LTX-2／其他圖片模型。
`GET /api/v1/models` 回傳已註冊的模型、輸出类型、模式與參數 schema；前端按 schema 顯示設定。
原LTX保留原先頂層欄位／profile；新增模型使用：

```json
{"model":"管理者已註冊的ID","mode":"generate","prompt":"你的提示詞","parameters":{}}
```

只使用同一組 `/api/v1/jobs`、查進度、取消與 `/artifact` 下載；不需為不同專案或模型建立新通道。
輸出目前支援 MP4、單張PNG、UTF-8 TXT。影片做完整解碼技術驗證；PNG解碼／尺寸檢查；TXT非空／UTF-8／1MiB上限。
檢查通過不代表角色一致、沒有幻覺或藝術品質合格，仍需人工審片。

安裝流程見 [本機轉接器規格](../local_adapters/README.md)。安裝模型本身仍需要相容程式、權重、授權與記憶體，
「無痛切換」指帳號、網址與 API 不更換，**不是任意 GitHub 模型都能零設定執行**。
沒有自動更新權重、持續訓練或允許網路呼叫者提交 shell 命令。

## 測試與本次部署狀態

Python 帳號／媒體／原LTX流程測試使用臨時資料庫，寄信使用測試替身；不代表真實 SMTP 或新模型已部署。
建議驗收命令（使用現有模型 Python venv）：

```bash
python -m unittest discover -s tests -v
node --test tests/worker-client.test.mjs
npx tsc --noEmit --incremental false
```

安全參考：[OWASP 密碼儲存](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、
[OWASP 登入設計](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)。
