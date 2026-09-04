# OpenClaw 工單提示詞與工作規則

本檔與 `OPENCLAW_WORK_ORDERS.html` 由 `docs/tools/gen_openclaw_prompts.py` 產生；要改提示詞請改產生器再重跑，不要直接編輯。

這份文件是 OpenClaw（LINE 上的「老皮」）執行製片平台工單時的工作規則與提示詞正本。規格本體在 `docs/PRODUCTION_ROADMAP.md`。
提示詞可複製整段貼進 LINE；`背景任務：` 前綴會讓 bridge 直接放進背景（上限 15 分鐘），完成後用 `查詢 JOB-xxxx` 取結果。

## 工作規則（每張工單都適用）

0. 主 checkout `/home/kwayrdc/LTX Local Studio` **永遠停在 main**；不在裡面 checkout 其他分支或改檔 — 正式站、`ltx-git-sync`、dev preview 都靠它。每張工單在自己的 worktree `~/LTX-worktrees/wo-<工單號小寫>` 工作（`git worktree add … -b wo/<id> origin/main`，`ln -s` 主 checkout 的 `node_modules`）。
1. 只在 `wo/<工單號小寫>` 分支 commit 與 push；**絕不 push、merge、rebase 到 main**。main 一推就由 `ltx-git-sync` 自動部署正式站。合併只有人做。
2. 不重啟 `ltx-web`、`ltx-api`、`ltx-cloudflared`；正式站 3000／API 8787 不可占用，dev server 只用 3001；不動 `/opt/studio` 權重。
3. 系統層級動作（apt、`systemctl --user enable/start`、`/etc`、unit 檔啟用）先發核准區塊；需要 sudo 的指令列給人自己跑。
4. 15 分鐘紀律：每則任務結束於乾淨狀態 — commit（訊息以「<工單號>: 」開頭）、push 分支、更新 `docs/work-orders/<工單號>.md` 進度區（已完成／未完成／需要人做的事）。
5. 驗收是獨立的一則任務，不修改程式；每條 PASS／FAIL 附證據；最後一行「<工單號> 可合併」或「<工單號> 退回」。
6. 合併：在主 checkout `git fetch origin && git merge --ff-only origin/wo/<id> && git push origin main`；由人在主機執行。之後 `git worktree remove ~/LTX-worktrees/wo-<id> && git branch -d wo/<id>`。

## 第 0 步：開工設定（只傳一次）

```text
阿寶要開一條長期工作線，請把下面寫進 USER.md（active directives）與 MEMORY.md，之後每個「工單」任務都照做：
1. 專案：LTX Local Studio，目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。規格在 docs/PRODUCTION_ROADMAP.md，工作規則在 docs/OPENCLAW_WORK_ORDERS.md。
2. 分支紀律：主 checkout 永遠停在 main、不在裡面 checkout 其他分支或改檔；每張工單在自己的 worktree ~/LTX-worktrees/wo-<小寫工單號>（分支 wo/<小寫工單號>，ln -s 主 checkout 的 node_modules）工作；絕對不 push、merge、rebase 到 main — main 一推就由 ltx-git-sync 自動部署到正式站 ltx.mikamiu.studio。合併只有阿寶做。
3. 服務紀律：不重啟 ltx-web、ltx-api、ltx-cloudflared；正式站 3000 與 API 8787 不可占用，dev server 只用 3001；不動 /opt/studio 的模型權重。
4. 系統層級動作（apt、systemctl enable/start、/etc、unit 檔啟用）先發核准區塊；需要 sudo 的指令列出來給阿寶自己跑。
5. 15 分鐘紀律：每則任務在 15 分鐘內結束於乾淨狀態 — commit、push 分支、更新 docs/work-orders/<工單號>.md 的進度區（已完成／未完成／需要阿寶做的事），回報做到哪。
6. 回報格式：改了哪些檔、跑了什麼測試與結果、卡點、下一步；沒全過驗收自檢不說「完成」。
確認寫入後，回覆你記下了哪幾條。
```

## 繼續模板

把 `{id}` 換成工單號：

```text
背景任務：【工單 <id> · 繼續】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，不切分支）。git fetch origin，到 worktree ~/LTX-worktrees/wo-<id 小寫>（沒有就 git worktree add ~/LTX-worktrees/wo-<id 小寫> wo/<id 小寫> 並 ln -s 主 checkout 的 node_modules），rebase 到 origin/main，讀 docs/work-orders/<id>.md 的進度區與最近三個 commit，從第一個未完成項接著做。規則、分支紀律、15 分鐘紀律與回報格式同「<id> · 執行」那一則；規格仍是 docs/PRODUCTION_ROADMAP.md「<id>」節。
```

## A 專案層與階段導覽（純前端）

### A1 Bible 與繼承（M）

執行：

```text
背景任務：【工單 A1 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「A1」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-a1 不存在就 git worktree add ~/LTX-worktrees/wo-a1 -b wo/a1 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-a1 wo/a1，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-a1 裡做。讀 docs/work-orders/A1.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/a1 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. lib/production-factory.ts：工作單格式 v2 — plan.version=2、plan.bible（character／music／output／directing／lyric_offset_seconds=-0.9）、shot.pinned[]；新增 projectBible()（Bible → request 投影）、pin/unpin、reprojectShots()（只動 draft／queued／failed 且跳過 pinned）、v1→v2 匯入遷移（bible 為空、全部欄位視為釘住）。shot.request 必須仍是完整可攜的 /api/v1/jobs body。
2. components/production-factory.tsx：頂部專案面板（角色重用 CharacterLock、不限 i2v；音樂重用 MV 時間軸的音樂選擇器；輸出規格）；「新增空白鏡頭」改成從 Bible 投影的「新增鏡頭」，無 Bible 時提示先設定；每欄位籤「繼承／此鏡覆寫」可還原；每鏡「全部設定」抽屜列出 request 全部欄位與即將送出的 JSON，改動即打 /api/v1/validate。
3. app/page.tsx：「加入製片工廠」在計畫沒有 Bible 時用當下角色／音樂／規格建立 Bible，不只複製進單鏡。
4. tests/production-factory.test.mjs 新增 ≥6 個測試：投影、釘住後重新投影不覆蓋、v1 匯入、v2 匯出匯入逐 byte 相同、running／succeeded 不被重新投影、改 Bible 提示覆寫鏡數。
5. docs/PRODUCTION_FACTORY.md 更新工作單格式 v2 與 Bible 說明。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「A1: 」開頭）、push wo/a1、更新 docs/work-orders/A1.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 A1 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-a1 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-a1 wo/a1 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「A1」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
額外檢查：用 tests/fixtures 或手寫一份 v1 工作單 JSON 匯入不報錯；匯出 JSON 每鏡 request 都能通過 curl POST http://127.0.0.1:8787/api/v1/validate（需登入 cookie 或 service key，拿不到就標為「未能執行」而非 FAIL）。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「A1 可合併」或「A1 退回」。
```

### A2 階段導覽與狀態板（M）

執行：

```text
背景任務：【工單 A2 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「A2」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-a2 不存在就 git worktree add ~/LTX-worktrees/wo-a2 -b wo/a2 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-a2 wo/a2，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-a2 裡做。讀 docs/work-orders/A2.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/a2 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. components/stage-rail.tsx（新）：左側七階段 00 企劃 Bible／01 分鏡／02 關鍵格／03 拍攝／04 審片／05 後製／06 組片交付，各一顆狀態籤（未開始／進行中／待人決定／通過），狀態由計畫資料在客戶端算出；02、04、05 標「本期未啟用」而非空頁；手機寬度變 stepper。
2. components/status-board.tsx（新）：每個計畫一列 — 卡在哪個階段、上一步結論、下一步誰負責；作為首頁。
3. app/page.tsx：TabKey 改為階段；00＝A1 專案面板；01＝現有 MV 時間軸＋LRC＋cue 搬入並加鏡頭清單；03＝現有工廠佇列；06＝現有 sequence 組片＋下載；「生成」改名「沙盒」放階段列下方視覺降級，功能一個不少；「環境」改名「工站」先只顯示現有資訊。三種語系（zh-TW／en／ja）文案都要補。
4. 不做審片、關鍵格、後製的頁面內容。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「A2: 」開頭）、push wo/a2、更新 docs/work-orders/A2.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 A2 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-a2 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-a2 wo/a2 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「A2」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
額外檢查：以 375px 寬度截圖階段列（可用 npm run dev:web -- --port 3001 起 dev server，3000 是正式站不可用）確認 stepper 可操作；沙盒頁的命令預覽、診斷資訊仍在。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「A2 可合併」或「A2 退回」。
```

## B 主機端專案與音訊（PostgreSQL）

### B0 PostgreSQL 基礎與遷移（M）

執行：

```text
背景任務：【工單 B0 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「B0」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-b0 不存在就 git worktree add ~/LTX-worktrees/wo-b0 -b wo/b0 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-b0 wo/b0，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-b0 裡做。讀 docs/work-orders/B0.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/b0 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
分五個子步驤，寫進 docs/work-orders/B0.md 逐項勾：
(1) 先檢查 psql -d ltx_studio -c 'select 1' 能否連線。不能 → 不要自己 apt；把 docs/PRODUCTION_ROADMAP.md B0 節「主機（由人執行）」那四行指令原封回給阿寶，附說明「peer auth、只走 unix socket」，並在這裡停下回報。能連線才往下。
(2) db/migrations/0001_baseline.sql（jobs、accounts、cloudflare_enrollments 三表，jsonb + (snapshot->>'owner_id') 等表達式索引）、schema_migrations 表、local_backend.py 啟動時套用 migration；環境變數 LTX_DATABASE_URL 與 LTX_TEST_DATABASE_URL，沒設就報錯不啟動（不要 fallback 回 sqlite）。
(3) production_store.py、user_auth.py、auth_http.py 改用 psycopg（apt 的 python3-psycopg 3.1），方法名與回傳形狀不變；tests/conftest.py 連 ltx_studio_test、每個測試在交易內並回滾；五個既有 test_*.py 全過。
(4) scripts/migrate-sqlite-to-postgres.py：只讀 sqlite → 寫 Postgres → 逐表筆數比對 → 印報告；提供 --dry-run；不刪 sqlite 檔。只在 ltx_studio_test 上實際演練一次並回報筆數；正式切換由阿寶決定時間，不在這一則做。
(5) scripts/git-sync-main.sh 的 sync_active_jobs 改打 ltx-api 的 GET http://127.0.0.1:8787/api/internal/active-jobs（新端點，只回應 127.0.0.1，回 {count}）；infra/systemd/ltx-backup.service＋.timer（每日 pg_dump 到 data/backups/）只建立檔案，enable 需核准區塊。
注意：scripts/clear-media.py 也讀 sqlite，要一起改。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「B0: 」開頭）、push wo/b0、更新 docs/work-orders/B0.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && bash tests/test_git_sync.sh；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 B0 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-b0 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-b0 wo/b0 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「B0」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && bash tests/test_git_sync.sh。
額外檢查：ss -ltn 沒有 5432；psql -d ltx_studio_test -c '\dt' 列出三表；migrate 腳本 --dry-run 的筆數報告貼上；git-sync 的 sync_active_jobs 在 ltx-api 未啟動新端點時的行為是否安全（應視為「有任務」而拒絕重啟，不是崩掉）。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「B0 可合併」或「B0 退回」。
```

### B1 主機端耐久佇列（L）

執行：

```text
背景任務：【工單 B1 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「B1」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-b1 不存在就 git worktree add ~/LTX-worktrees/wo-b1 -b wo/b1 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-b1 wo/b1，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-b1 裡做。讀 docs/work-orders/B1.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/b1 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
前提：B0 已合併且 psql -d ltx_studio_test 可連；否則停下回報。
1. db/migrations/0002_factory.sql：projects／shots／takes 三表，欄位與外鍵照規格；takes.job_id 外鍵指向 jobs。
2. local_backend.py：/api/v1/factory/projects（CRUD、匯入匯出工作單 v2）、/projects/{id}/shots、/projects/{id}/run 與 /pause、/shots/{id}/takes；全部只編排 — 每鏡走既有 validate → jobs，external{project_id, asset_id, shot_id, request_id} 由 API 填；「鏡狀態＋take＋job」一個交易。排程迴圈在 ltx-api 內：一次一個 GPU job，worker_busy 保留順位重試，失敗／取消／中斷暫停整條線；API 重啟後從資料庫狀態續跑。租戶＝owner_id；管理員暫停；每帳號佇列上限可設。
3. worker_schema.py：工作單 v2 的伺服器端驗證。
4. lib/factory-client.ts（新）＋ components/production-factory.tsx 改讀寫 API；localStorage 只留 UI 偏好；首次載入若有本機 v1／v2 計畫，提供「上傳到主機」一次性搬移。
5. tests/test_factory_api.py：租戶隔離、冪等重送、暫停不殺 job、續跑。docs/PRODUCTION_FACTORY.md 與 docs/WORKER_API.md 補 API。
這張很大：優先順序 1→2→3→5→4，每個子步驤一個 commit。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「B1: 」開頭）、push wo/b1、更新 docs/work-orders/B1.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 B1 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-b1 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-b1 wo/b1 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「B1」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
額外檢查：用兩個測試帳號各建一個專案，A 查不到 B 的（403／404）；同一鏡同一 Idempotency-Key 重送兩次只產生一個 job。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「B1 可合併」或「B1 退回」。
```

### B2 音訊服務 MA／LS（M）

執行：

```text
背景任務：【工單 B2 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「B2」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-b2 不存在就 git worktree add ~/LTX-worktrees/wo-b2 -b wo/b2 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-b2 wo/b2，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-b2 裡做。讀 docs/work-orders/B2.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/b2 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. services/audio/server.py：跑在 /opt/studio/venvs/audio（缺 web 框架就 pip 裝進該 venv，這不是系統層級）；只 bind 127.0.0.1:8790；POST /beats {path} 回 tempo、beat 時間、段落與能量曲線；POST /align {path, lyrics, language} 回逐字時間；path 必須在 uploads/ 或 data/ 之下否則 400。
2. local_backend.py：POST /api/v1/audio/analyze {audio_id, lyrics?, language?}，檢查 asset 所有權 → 解析路徑 → 呼叫服務 → 結果快取在 asset（同檔不重算）；回傳附 lyric_offset_seconds（Bible 預設 −0.9）與說明「常數偏移，非隨機誤差」；服務不可用回 503 不影響生成。
3. infra/systemd/ltx-audio.service：只建立檔案；enable 需核准區塊，收到核准才 systemctl --user enable --now。
4. tests/test_audio_service.py：用 tests/fixtures 合成音（不下載模型也能跑的部分），與一個標記為需真模型的整合測試。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「B2: 」開頭）、push wo/b2、更新 docs/work-orders/B2.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 B2 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-b2 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-b2 wo/b2 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「B2」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'。
額外檢查：用 uploads/ 裡三首沖縄 wav 之一打 /beats，BPM 與 docs/GB10_SETUP.md 記錄一致（104.2 等）；curl 從非 loopback 位址打 8790 應連不上。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「B2 可合併」或「B2 退回」。
```

### B3 自動分鏡（M）

執行：

```text
背景任務：【工單 B3 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「B3」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-b3 不存在就 git worktree add ~/LTX-worktrees/wo-b3 -b wo/b3 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-b3 wo/b3，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-b3 裡做。讀 docs/work-orders/B3.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/b3 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. lib/breakdown.ts（純函式）：輸入 beats／sections／lyric lines／segment_seconds／Bible directing 預設，輸出鏡頭清單與 cue；規則：段落邊界 ＞ 歌詞行起點（已扣偏移）＞ 每鏡上限；切點吸附最近拍點（±1 拍）；純器樂段產生 breathing 鏡；每鏡 cue 時間＝鏡起點、主要動作留空。
2. components/breakdown-editor.tsx：01 分鏡頁 — 波形＋拍點網格＋段落色帶、歌詞行貼在對時位置、鏡頭清單可合併／拆分／改；「預覽分鏡」沿用既有。
3. tests/breakdown.test.mjs：166 秒、segment_seconds=10 → 17–24 鏡、無一鏡超上限、切點全在拍點；合併兩鏡後 cue 重算。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「B3: 」開頭）、push wo/b3、更新 docs/work-orders/B3.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 B3 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-b3 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-b3 wo/b3 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「B3」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「B3 可合併」或「B3 退回」。
```

### B4 LLM 編劇草稿（S）

執行：

```text
背景任務：【工單 B4 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「B4」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-b4 不存在就 git worktree add ~/LTX-worktrees/wo-b4 -b wo/b4 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-b4 wo/b4，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-b4 裡做。讀 docs/work-orders/B4.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/b4 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. local_backend.py：POST /api/v1/factory/shots/{id}/draft — 主機端呼叫 OpenAI（key 讀 /opt/studio/secrets/openai，權限 0600，瀏覽器永遠拿不到）；輸入 Bible 描述、該鏡導演參數、歌詞行、前後鏡；structured output 只允許 {prompt, primary_action}；usage 寫進 project；每專案 token 上限，超過回 429。
2. UI：每鏡「起草」按鈕填進可編輯文字框；草稿不覆蓋用戶已改過（pinned）的提示詞；OpenAI 不可用時按鈕停用並說明。
3. 測試用 mock，不打真 API。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「B4: 」開頭）、push wo/b4、更新 docs/work-orders/B4.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 B4 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-b4 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-b4 wo/b4 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「B4」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「B4 可合併」或「B4 退回」。
```

## C 裁判與審片

### C1 裁判服務 CJ／SJ／MQ（M）

執行：

```text
背景任務：【工單 C1 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「C1」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-c1 不存在就 git worktree add ~/LTX-worktrees/wo-c1 -b wo/c1 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-c1 wo/c1，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-c1 裡做。讀 docs/work-orders/C1.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/c1 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. services/judge/server.py：跑在 /opt/studio/venvs/vision；只 bind 127.0.0.1:8791；POST /score {media_path, references[paths], style_anchor_path?}：抽幀每秒 1 幀；CJ 有臉用 facenet 對參照表取最大相似度、無臉退 DINOv2，回每幀與中位數；SJ 用 CLIP 對風格錨中位數；MQ 用 RAFT 光流幅度統計＋黑幀／靜止比例。只回數字，不判通過。path 必須在 uploads/、outputs/ 或 data/ 之下。
2. local_backend.py：job succeeded 後自動送判，結果寫進 take.scores（B1 的 takes 表）；判分失敗只標「未判分」不影響 job 狀態。
3. infra/systemd/ltx-judge.service 只建檔，enable 需核准。
4. tests/test_judge_service.py：合成圖（同色塊 vs 不同色塊）驗方向正確；真模型整合測試單獨標記。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「C1: 」開頭）、push wo/c1、更新 docs/work-orders/C1.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 C1 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-c1 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-c1 wo/c1 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「C1」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'。
額外檢查：同一張圖對自己 CJ face 接近 1.0；nvidia-smi 顯示服務常駐記憶體約 2 GB 以內。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「C1 可合併」或「C1 退回」。
```

### C2 Take 模型（S）

執行：

```text
背景任務：【工單 C2 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「C2」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-c2 不存在就 git worktree add ~/LTX-worktrees/wo-c2 -b wo/c2 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-c2 wo/c2，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-c2 裡做。讀 docs/work-orders/C2.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/c2 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. 以 B1 的 takes 表為基礙：verdict 狀態機 pending → accepted／rejected／overridden；shot.accepted_take_id；「修改／重做」（既有 reopenFactoryShot）改為建立新 take；退回必填 reason，reason 自動以「避免：…」接到下一 take 的 prompt 末尾，累積不覆蓋，用戶可改。
2. 既有的成品刪除（回收區）→ 該 take 標 deleted，鏡與其他 take 不受影響。
3. 測試涵蓋兩次退回累積、刪除隔離、accepted_take_id 唯一。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「C2: 」開頭）、push wo/c2、更新 docs/work-orders/C2.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 C2 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-c2 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-c2 wo/c2 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「C2」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「C2 可合併」或「C2 退回」。
```

### C3 審片頁（M）

執行：

```text
背景任務：【工單 C3 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「C3」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-c3 不存在就 git worktree add ~/LTX-worktrees/wo-c3 -b wo/c3 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-c3 wo/c3，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-c3 裡做。讀 docs/work-orders/C3.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/c3 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. 04 審片頁：每鏡 take 並排；三條分數 vs Bible 門檻線（C4 前顯示「未校準」用暫定值並標示）；VLM 一句話（主機端 gpt-5.6 呼叫，走 B4 同一 key 與 usage 記帳）＋「我不同意」；接受／退回（必填原因）；紅燈下按接受 → overridden 並記錄誰、何時。
2. 抽屜：逐幀 CJ 曲線、相鄰鏡嚴格模式（fpr 1% 門檻）、本鏡門檻覆寫。
3. 否決＝take 不自動成為 accepted_take_id、不進 06；不阻止用戶接受。裁判服務關閉時頁面仍可用，分數欄顯示未判分。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「C3: 」開頭）、push wo/c3、更新 docs/work-orders/C3.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 C3 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-c3 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-c3 wo/c3 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「C3」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
額外檢查：用兩個不同角色的參照各生成一個 take，換臉的那個是否紅燈且未自動進組片。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「C3 可合併」或「C3 退回」。
```

### C4 門檻校準（S）

執行：

```text
背景任務：【工單 C4 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「C4」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-c4 不存在就 git worktree add ~/LTX-worktrees/wo-c4 -b wo/c4 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-c4 wo/c4，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-c4 裡做。讀 docs/work-orders/C4.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/c4 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. 檢查 calibration/ 是否存在且 ≥2 個角色資料夾、每個 ≥10 張；不足就列出缺什麼並停下回報，不要自己找圖湊數。
2. 足夠時：/opt/studio/venvs/vision/bin/python infra/gb10/tools/calibrate_embeddings.py --root calibration --out calibration_report.json；把 fpr 5% 門檻寫進 Bible 預設、fpr 1% 當相鄰鏡嚴格值；UI 加「匯入校準報告」讀 JSON 進 bible.thresholds；C3 門檻線不再標「未校準」；無臉圖列出並在 UI 標示。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「C4: 」開頭）、push wo/c4、更新 docs/work-orders/C4.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 C4 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-c4 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-c4 wo/c4 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「C4」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「C4 可合併」或「C4 退回」。
```

## D 多工站

### D1 imagegen adapter 與 GPU 租約（L）

執行：

```text
背景任務：【工單 D1 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「D1」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-d1 不存在就 git worktree add ~/LTX-worktrees/wo-d1 -b wo/d1 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-d1 wo/d1，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-d1 裡做。讀 docs/work-orders/D1.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/d1 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. local_adapters/imagegen.py：Qwen-Image-Edit-2509、Z-Image-Turbo 註冊成 media_type image 的 adapter；參數 steps（預設 8）、seed、references（1–3 個 image_id）、lightning、size，經 model_registry.py 檢查；不接受路徑。
2. services/imagegen/server.py：跑在 /opt/studio/venvs/imagegen，只 bind 127.0.0.1:8792；模型常駐、閒置 N 分鐘釋放；infra/systemd/ltx-imagegen.service 只建檔，enable 需核准。
3. local_backend.py 大工站租約：同時只有 LTX 或 imagegen 持有 GPU；切換前必須釋放（imagegen 卸模型、LTX 無進行中 job）；裁判、音訊、後製不受限。
4. tests/test_imagegen_adapter.py、tests/test_gpu_lease.py（租約用假工站測互斥與交棒）。
絕對不要在有 LTX job 進行中時載入 Qwen（61 GB）；先查 GET /api/internal/active-jobs。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「D1: 」開頭）、push wo/d1、更新 docs/work-orders/D1.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 D1 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-d1 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-d1 wo/d1 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「D1」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'。
額外檢查：LTX job 進行中送 imagegen job → 排隊不 OOM；連續 20 張只付一次載入（看服務日誌）；閒置超時後 nvidia-smi 無 imagegen 程序。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「D1 可合併」或「D1 退回」。
```

### D2 關鍵格階段（M）

執行：

```text
背景任務：【工單 D2 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「D2」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-d2 不存在就 git worktree add ~/LTX-worktrees/wo-d2 -b wo/d2 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-d2 wo/d2，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-d2 裡做。讀 docs/work-orders/D2.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/d2 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. 02 關鍵格頁：鏡頭清單變縮圖格；「產生全部關鍵格」整批：每鏡依 directing.angle 選參照（既有 select_reference 邏輯）→ imagegen job → C1 判分 → 綠／黃／紅；紅自動換 seed 重生一次再請人看；核准圖成為該鏡 image_id 並在籤上標「來自關鍵格」。
2. 介面明確顯示「現在是關鍵格階段／拍攝階段」與切換代價（336 s）。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「D2: 」開頭）、push wo/d2、更新 docs/work-orders/D2.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 D2 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-d2 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-d2 wo/d2 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「D2」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「D2 可合併」或「D2 退回」。
```

### D3 後製 adapter VX（M）

執行：

```text
背景任務：【工單 D3 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「D3」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-d3 不存在就 git worktree add ~/LTX-worktrees/wo-d3 -b wo/d3 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-d3 wo/d3，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-d3 裡做。讀 docs/work-orders/D3.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/d3 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. 先檢查 /opt/studio/tools/rife/train_log 是否有權重；沒有就回報阿寶並跳過 RIFE、只做 ESRGAN 與 LaMa。
2. 對核准的 take 提供三個 post job：補幀（RIFE 到目標 FPS）、放大（Real-ESRGAN ×4 或沿用 LTX x2）、清理（LaMa，用戶畫遮罩）；輸入是本機 take 檔而非上傳；輸出成新 take 版本；完成後自動過 MQ。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「D3: 」開頭）、push wo/d3、更新 docs/work-orders/D3.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 D3 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-d3 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-d3 wo/d3 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「D3」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「D3 可合併」或「D3 退回」。
```

### D4 工站排程與 LP 預算（M）

執行：

```text
背景任務：【工單 D4 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「D4」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-d4 不存在就 git worktree add ~/LTX-worktrees/wo-d4 -b wo/d4 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-d4 wo/d4，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-d4 裡做。讀 docs/work-orders/D4.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/d4 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. 排程器：待跑 job 依工站分群、同工站連續做、做完交棒（用 D1 租約）。
2. 工站頁：誰坐 GPU、佇列、切換 ETA。
3. LP 預算＝Σ 每鏡 generate 秒 + 切換次數 × 載入秒 + OpenAI usage；數字來自 docs/GB10_SETUP.md 與 jobs.runtime_seconds 滾動平均；超預算是警告不擋。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「D4: 」開頭）、push wo/d4、更新 docs/work-orders/D4.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 D4 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-d4 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-d4 wo/d4 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「D4」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
額外檢查：混合 12 張關鍵格 + 12 鏡 LTX 的佇列恰好切換 1 次。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「D4 可合併」或「D4 退回」。
```

### D5 組片與 EDL（S）

執行：

```text
背景任務：【工單 D5 · 執行】
專案目錄 "/home/kwayrdc/LTX Local Studio"（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「D5」節當規格。
開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-d5 不存在就 git worktree add ~/LTX-worktrees/wo-d5 -b wo/d5 origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-d5 wo/d5，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-d5 裡做。讀 docs/work-orders/D5.md 的進度區（沒有就建立）。
硬規則：主 checkout "/home/kwayrdc/LTX Local Studio" 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/d5 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。
這一則的工作：
1. 06 組片：只取每鏡 accepted_take_id，依拍點排時間軸，原曲連續鋪底（既有 sequence 組片）；任一鏡無 accepted take → 按鈕停用並列出哪幾鏡。
2. 匯出 MP4 + shot manifest／EDL JSON：每鏡 prompt、seed、參照指紋、模型版本、take 裁決；manifest 能還原每鏡完整 request（與 A1 匯出格式相容）。
時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「D5: 」開頭）、push wo/d5、更新 docs/work-orders/D5.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。
```

驗收：

```text
背景任務：【工單 D5 · 驗收】
專案目錄 "/home/kwayrdc/LTX Local Studio"（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-d5 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-d5 wo/d5 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。
依 docs/PRODUCTION_ROADMAP.md「D5」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py' && node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json。
任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「D5 可合併」或「D5 退回」。
```
