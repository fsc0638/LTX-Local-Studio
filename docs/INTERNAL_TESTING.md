# 內部測試與寄信待辦

決策日期：2026-08-30。使用者決定先不升級 Cloudflare，以本機註冊帳號及密碼進行內部測試。
此決策不是匿名模式，也沒有授權解除 Cloudflare Access 或對外開放註冊。

> 同日後續更新：管理者已授權並啟用 [註冊同步 Cloudflare Access](CLOUDFLARE_ACCOUNT_SYNC.md)。新註冊會加入專用清單；外部登入加上真實 Access 身份驗證與同信箱帳號綁定，正式 HTTPS Origin 已開放。仍無 SMTP、未升級方案、未解除 Access。下文「僅允許管理者／不自動同步／Origin 尚未開放」為啟用前的歷史紀錄，以連結文件的啟用紀錄為準。

## 帳號規則

- `LTX_USER_AUTH_ENABLED=1`：保留登入、密碼雜湊、8 小時工作階段、CSRF、使用者素材／任務隔離及配額。
- `LTX_AUTH_MODE=internal`：註冊後不寄信、不建立驗證 token、不自動登入，返回登入頁輸入帳密即可使用。
- `LTX_REGISTRATION_ENABLED=1`：允許新增帳號；改成 `0` 只關閉新註冊，不影響既有帳號登入。
- 姓名、帳號、密碼與 Email 仍需填寫；密碼僅保存 scrypt 加鹽雜湊。
- 密碼最短 8、最長 128 字元，英數即可，不要求特殊符號；既有長密碼及符號仍可使用，不變更既有帳號密碼。
- 登入、註冊與重設表單的密碼／確認密碼欄位預設遮蔽，可個別用小眼睛顯示或隱藏；中英日提示同步，顯示切換不提交表單也不保存明文。
- 原本等待 Email 驗證的帳號也可登入，但停用帳號、錯誤密碼及未註冊帳號仍拒絕。
- Email 只有格式驗證，**沒有證明信箱所有權**。資料庫的 `verified_at` 保持空值，API `email_verified=false`。
- 不寄驗證信／重寄信／重設密碼信；相關頁面會說明暫停原因。忘記密碼須請主機管理者協助，不以重新註冊覆寫密碼，也不提供公開的免認證重設入口。
- 重複帳號或 Email 回覆 `409 account_unavailable`，不覆寫原資料。
- 網页保留繁中／英文／日文及既有風格，登入前後顯示內部測試標示。

## 本機設定

在忽略於 Git 的 `.env.local` 使用：

```dotenv
LTX_USER_AUTH_ENABLED=1
LTX_AUTH_MODE=internal
LTX_REGISTRATION_ENABLED=1
LTX_PUBLIC_ORIGIN=http://localhost:3000
LTX_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
LTX_INTERNAL_API_ORIGIN=http://127.0.0.1:8787
```

上例是 loopback 測試配置，HTTP cookie 不適合作為正式 HTTPS 部署配置。
SMTP 欄位不用填；`internal` 是明確選項，不會因 SMTP 失敗而自動降級。
缺省仍是 `verified_email`；拼錯模式會拒絕啟動。
切換設定後必須重啟 API；網站透過 `/api/auth/config` 取得目前模式，單改前端文字不算啟用。
啟動前仍需通過 `scripts/check-service-layout.py`；舊公開媒體須依 [安全搬移](ACCOUNTS_AND_MODELS.md#3-舊安裝的安全搬移與部署順序) 處理，不可略過檢查。

## Cloudflare Access 會不會影響？

**會。Cloudflare 與本機登入是兩層獨立的檢查。**

| 入口 | Cloudflare Access | 本機帳號 |
|---|---|---|
| 本機 `localhost` | 不經過 | 必須註冊並登入 |
| 經安全配置的內網入口或 SSH 本機連接埠轉送 | 不經過 | 必須註冊並登入 |
| `https://ltx.mikamiu.studio` | 先檢查允許名單 | 通過外層後仍需本機登入 |

目前 Access 只允許管理者信箱。其他人就算在本機註冊，也不會自動加入 Access 名單。
若日後讓外部測試者使用，需另行確認精確的允許名單與正式 HTTPS／Origin 配置；不可直接全部 Bypass。
Cloudflare Access 本身可能要求登入或電子郵件 PIN，與本機「不寄驗證信」不同。
本機服務綁定 loopback，不代表其他電腦可以直接連其區網 IP；內網分享還需要可信入口、HTTPS 與明確 Origin。不要公開模型 API 的 8787 埠。

## 已記錄的 Cloudflare 現況與未來升級

2026-08-30 控制台唯讀檢查結果（未修改、未購買）：

- `mikamiu.studio` 位於正確帳號，DNS 使用 Cloudflare；操作者為完整超級管理員，API 存取開啟。
- Workers 目前 Free；Email Sending 頁面要求 Workers Paid。網域 Free 與 Zero Trust Free 都不能替代 Workers Paid。
- 當時方案頁顯示 US$5／月起加用量費用。**不是現在扣款的授權**；正式啟用前須重查費率並取得使用者同意。
- Email Sending 寄信網域、SPF／DKIM／DMARC／必要退信 DNS、`Email Sending: Edit` 專用 Token 尚未完成。
- 既有 Token 用於 Tunnel 或建置，不能當作寄信專用 Token；不得將其內容記入此文件。
- `ltx-local-studio` Tunnel 健康，路由為本機管理；網站到 3000，`/api/*` 和 `/generated/*` 到 8787。
- Access 應用保護整個 `ltx.mikamiu.studio`，僅允許管理者信箱。

未來採 Cloudflare 寄信的順序：

1. 使用者同意後升級 Workers Paid；不得直接購買。
2. 加入選定的寄信網域並驗證必要 DNS，保留既有網站／收信設定。
3. 建立同帳號、最小權限 `Email Sending: Edit` 的 Token，安全保存在本機私有秘密檔案。
4. SMTP：`smtp.mx.cloudflare.net`、465、`LTX_SMTP_SECURITY=ssl`，帳號為文字 `api_token`；密碼使用該 Token。
5. 先關閉新註冊、切回 `LTX_AUTH_MODE=verified_email`，設定正式 HTTPS origin，重啟並驗收寄信→驗證→重新登入。
6. 未驗證帳號與其測試工作階段不能通過正式驗證要求；透過重寄驗證流程完成驗證，不批次偽造 `verified_at`。
7. 驗收通過後再開放註冊，並獨立評估外部 Access 名單。

參考：[Email Service 計費](https://developers.cloudflare.com/email-service/platform/pricing/)、[SMTP](https://developers.cloudflare.com/email-service/api/send-emails/smtp/)。費率及 Beta 服務能力以啟用時官方資料為準。

## 本次實際啟用與驗收

2026-08-30 已在此主機啟用，不只是 UI 預覽：

- 本機正式模式網站：`http://localhost:3000/auth/login`；開發預覽：`http://localhost:3001/auth/login`。
- 兩者共用同一個真實模型 API `127.0.0.1:8787` 與 `data/worker/accounts.sqlite3`。
- `.env.local` 已設定 `LTX_AUTH_MODE=internal`、開放註冊、啟用帳號保護、使用同源 `/api`。
- 帳號寫入操作的允許來源目前只包含 localhost／127.0.0.1 的 3000／3001。
  **正式網域的 Origin 尚未開放本次內部註冊登入**；即使通過 Cloudflare 外層，現在也應改用本機入口測試。
  日後遠端測試需獨立確認 Access 名單、正式 HTTPS origin 與 Secure cookie，不能只新增一個 Email 就視為完整啟用。
- 本機 API 已以主機權限重新啟動，CUDA 可用、裝置 NVIDIA GB10；未在本次驗收提交昂貴的真實 GPU 生成任務。
- 切換前已確認沒有生成中任務；舊 `.env.local`、worker 狀態與舊網站建置保存在被 Git 忽略的 `data/backups/internal-20260830.CbNty6/`。
- 共 38 個舊公開媒體檔案移入 `data/worker/legacy-*` 私有目錄，刪除內容 0；搬移紀錄 `data/worker/migrations/media-1788096372651986047.json`。
  舊的無 owner 素材不自動指派給第一位註冊者，普通帳號看不到不代表內容遺失。
- Cloudflare Tunnel、DNS、Access 及付費方案完全未修改。

驗收證據：64 項 Python 測試、2 項 Node 用戶端測試、TypeScript、定向 UI lint、隔離建置與私有目錄 preflight 通過。
透過實際 3000／3001 網站代理完成：無信註冊→不自動登入→帳密登入→cookie／CSRF→模型與參數驗證 API→真實圖片上傳下載→跨帳號／未登入拒絕→登出失效。
另外確認舊成品不再能被靜態網站直接讀取；正式來源目前回覆 `origin_not_allowed`，符合本機限定設定。
驗收用臨時帳號與小型圖片已清理，沒有移除既有使用者資料。測試結果不代表藝術品質、GPU 片段或郵件送達驗收。
