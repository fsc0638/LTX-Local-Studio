"""One source of truth for the OpenClaw work-order prompts.

Emits docs/OPENCLAW_WORK_ORDERS.md (rules + prompts) and docs/OPENCLAW_WORK_ORDERS.html
(the same prompts with copy buttons and LINE length counts). Edit the prompts here, then:

    python3 docs/tools/gen_openclaw_prompts.py

Lives under docs/ on purpose: scripts/*.py changes make git-sync schedule an ltx-api restart.
"""
import html, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

REPO = '"/home/kwayrdc/LTX Local Studio"'

PRE = (
"背景任務：【工單 {id} · 執行】\n"
"專案目錄 " + REPO + "（路徑有空格，一律加引號）。先讀 docs/OPENCLAW_WORK_ORDERS.md 的工作規則，再讀 docs/PRODUCTION_ROADMAP.md 的「{id}」節當規格。\n"
"開始前：在主 checkout 跑 git fetch origin，然後一律到獨立 worktree 工作：~/LTX-worktrees/wo-{lid} 不存在就 git worktree add ~/LTX-worktrees/wo-{lid} -b wo/{lid} origin/main（分支已存在就 git worktree add ~/LTX-worktrees/wo-{lid} wo/{lid}，再 rebase 到 origin/main），並 ln -s 主 checkout 的 node_modules 進 worktree。之後所有編輯、測試、commit 都在 ~/LTX-worktrees/wo-{lid} 裡做。讀 docs/work-orders/{id}.md 的進度區（沒有就建立）。\n"
"硬規則：主 checkout " + REPO + " 永遠停在 main，絕不在裡面 checkout 其他分支或改檔（正式站與自動同步都靠它）；只在 wo/{lid} 分支 commit 與 push，絕對不 push、merge 或 rebase 到 main（main 一推就自動部署正式站）；不重啟 ltx-web、ltx-api；不動 /opt/studio 的權重；系統層級動作（apt、systemctl、寫 /etc 或 unit 檔啟用）一律先發核准區塊等阿寶回覆，需要 sudo 的指令列給阿寶自己跑。\n"
"這一則的工作：\n{body}\n"
"時間紀律：15 分鐘內做不完就停在乾淨的中間狀態：commit（訊息以「{id}: 」開頭）、push wo/{lid}、更新 docs/work-orders/{id}.md 的「已完成／未完成／需要阿寶做的事」，然後回報做到哪、下一步是什麼。完成時跑自檢：{tests}；沒全過不要說完成。回報格式：改了哪些檔、跑了什麼、結果、卡點、下一步。"
)

ACC = (
"背景任務：【工單 {id} · 驗收】\n"
"專案目錄 " + REPO + "（主 checkout，只能讀、不切分支）。git fetch origin；到 worktree ~/LTX-worktrees/wo-{lid} 驗收（沒有就 git worktree add ~/LTX-worktrees/wo-{lid} wo/{lid} 並 ln -s 主 checkout 的 node_modules；分支不存在就回報並停止）。這是驗收不是開發：不修改程式與文件；只允許為了讓測試跑起來準備測試資料庫或暫存目錄，且做完要清掉。\n"
"依 docs/PRODUCTION_ROADMAP.md「{id}」節的驗收清單逐條執行，每條回報 PASS 或 FAIL 並附證據（指令、輸出摘要、數字、路徑）。另外必跑並附結果：{tests}。\n"
"{extra}"
"任何 FAIL 不要自己修：寫出重現步驟、你懷疑的檔案與行號。最後一行只能是「{id} 可合併」或「{id} 退回」。"
)

CONT = (
"背景任務：【工單 {id} · 繼續】\n"
"專案目錄 " + REPO + "（主 checkout，不切分支）。git fetch origin，到 worktree ~/LTX-worktrees/wo-{lid}（沒有就 git worktree add ~/LTX-worktrees/wo-{lid} wo/{lid} 並 ln -s 主 checkout 的 node_modules），rebase 到 origin/main，讀 docs/work-orders/{id}.md 的進度區與最近三個 commit，從第一個未完成項接著做。規則、分支紀律、15 分鐘紀律與回報格式同「{id} · 執行」那一則；規格仍是 docs/PRODUCTION_ROADMAP.md「{id}」節。"
)

JS = "node --test tests/*.test.mjs && npx --no-install tsc --noEmit -p tsconfig.json"
# The Python suite needs the LTX venv, not /usr/bin/python3: test_quality and test_mv_timeline
# import av (PyAV), which only that interpreter has. It is the same one git-sync uses for the
# suite (LTX_SYNC_PYTHON) and the one .env.local names as LTX_PYTHON.
LTX_PYTHON = "/home/kwayrdc/Documents/Codex/2026-08-28/new-chat-2/work/ltx-2.3/LTX-2/.venv/bin/python"
PY = f"PYTHONPATH=tests {LTX_PYTHON} -m unittest discover -s tests -p 'test_*.py'"
PYDB = "LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql " + PY

WO = [
 dict(id="A1", title="Bible 與繼承", phase="A", size="M", tests=JS, body=
"1. lib/production-factory.ts：工作單格式 v2 — plan.version=2、plan.bible（character／music／output／directing／lyric_offset_seconds=-0.9）、shot.pinned[]；新增 projectBible()（Bible → request 投影）、pin/unpin、reprojectShots()（只動 draft／queued／failed 且跳過 pinned）、v1→v2 匯入遷移（bible 為空、全部欄位視為釘住）。shot.request 必須仍是完整可攜的 /api/v1/jobs body。\n"
"2. components/production-factory.tsx：頂部專案面板（角色重用 CharacterLock、不限 i2v；音樂重用 MV 時間軸的音樂選擇器；輸出規格）；「新增空白鏡頭」改成從 Bible 投影的「新增鏡頭」，無 Bible 時提示先設定；每欄位籤「繼承／此鏡覆寫」可還原；每鏡「全部設定」抽屜列出 request 全部欄位與即將送出的 JSON，改動即打 /api/v1/validate。\n"
"3. app/page.tsx：「加入製片工廠」在計畫沒有 Bible 時用當下角色／音樂／規格建立 Bible，不只複製進單鏡。\n"
"4. tests/production-factory.test.mjs 新增 ≥6 個測試：投影、釘住後重新投影不覆蓋、v1 匯入、v2 匯出匯入逐 byte 相同、running／succeeded 不被重新投影、改 Bible 提示覆寫鏡數。\n"
"5. docs/PRODUCTION_FACTORY.md 更新工作單格式 v2 與 Bible 說明。",
 extra="額外檢查：用 tests/fixtures 或手寫一份 v1 工作單 JSON 匯入不報錯；匯出 JSON 每鏡 request 都能通過 curl POST http://127.0.0.1:8787/api/v1/validate（需登入 cookie 或 service key，拿不到就標為「未能執行」而非 FAIL）。\n"),
 dict(id="A2", title="階段導覽與狀態板", phase="A", size="M", tests=JS, body=
"1. components/stage-rail.tsx（新）：左側七階段 00 企劃 Bible／01 分鏡／02 關鍵格／03 拍攝／04 審片／05 後製／06 組片交付，各一顆狀態籤（未開始／進行中／待人決定／通過），狀態由計畫資料在客戶端算出；02、04、05 標「本期未啟用」而非空頁；手機寬度變 stepper。\n"
"2. components/status-board.tsx（新）：每個計畫一列 — 卡在哪個階段、上一步結論、下一步誰負責；作為首頁。\n"
"3. app/page.tsx：TabKey 改為階段；00＝A1 專案面板；01＝現有 MV 時間軸＋LRC＋cue 搬入並加鏡頭清單；03＝現有工廠佇列；06＝現有 sequence 組片＋下載；「生成」改名「沙盒」放階段列下方視覺降級，功能一個不少；「環境」改名「工站」先只顯示現有資訊。三種語系（zh-TW／en／ja）文案都要補。\n"
"4. 不做審片、關鍵格、後製的頁面內容。",
 extra="額外檢查：以 375px 寬度截圖階段列（可用 npm run dev:web -- --port 3001 起 dev server，3000 是正式站不可用）確認 stepper 可操作；沙盒頁的命令預覽、診斷資訊仍在。\n"),
 dict(id="B0", title="PostgreSQL 基礎與遷移", phase="B", size="M", tests=PYDB + " && bash tests/test_git_sync.sh", body=
"分五個子步驤，寫進 docs/work-orders/B0.md 逐項勾：\n"
"(1) 先檢查 psql -d ltx_studio -c 'select 1' 能否連線。不能 → 不要自己 apt；把 docs/PRODUCTION_ROADMAP.md B0 節「主機（由人執行）」那四行指令原封回給阿寶，附說明「peer auth、只走 unix socket」，並在這裡停下回報。能連線才往下。\n"
"(2) db/migrations/0001_baseline.sql（jobs、accounts、cloudflare_enrollments 三表，jsonb + (snapshot->>'owner_id') 等表達式索引）、schema_migrations 表、local_backend.py 啟動時套用 migration；環境變數 LTX_DATABASE_URL 與 LTX_TEST_DATABASE_URL，沒設就報錯不啟動（不要 fallback 回 sqlite）。\n"
"(3) production_store.py、user_auth.py、auth_http.py 改用 psycopg（apt 的 python3-psycopg 3.1），方法名與回傳形狀不變；tests/conftest.py 連 ltx_studio_test、每個測試在交易內並回滾；五個既有 test_*.py 全過。\n"
"(4) scripts/migrate-sqlite-to-postgres.py：只讀 sqlite → 寫 Postgres → 逐表筆數比對 → 印報告；提供 --dry-run；不刪 sqlite 檔。只在 ltx_studio_test 上實際演練一次並回報筆數；正式切換由阿寶決定時間，不在這一則做。\n"
"(5) scripts/git-sync-main.sh 的 sync_active_jobs 改打 ltx-api 的 GET http://127.0.0.1:8787/api/internal/active-jobs（新端點，只回應 127.0.0.1，回 {count}）；infra/systemd/ltx-backup.service＋.timer（每日 pg_dump 到 data/backups/）只建立檔案，enable 需核准區塊。\n"
"注意：scripts/clear-media.py 也讀 sqlite，要一起改。",
 extra="額外檢查：ss -ltn 沒有 5432；psql -d ltx_studio_test -c '\\dt' 列出三表；migrate 腳本 --dry-run 的筆數報告貼上；git-sync 的 sync_active_jobs 在 ltx-api 未啟動新端點時的行為是否安全（應視為「有任務」而拒絕重啟，不是崩掉）。\n"),
 dict(id="B1", title="主機端耐久佇列", phase="B", size="L", tests=PYDB + " && " + JS, body=
"前提：B0 已合併且 psql -d ltx_studio_test 可連；否則停下回報。\n"
"1. db/migrations/0002_factory.sql：projects／shots／takes 三表，欄位與外鍵照規格；takes.job_id 外鍵指向 jobs。\n"
"2. local_backend.py：/api/v1/factory/projects（CRUD、匯入匯出工作單 v2）、/projects/{id}/shots、/projects/{id}/run 與 /pause、/shots/{id}/takes；全部只編排 — 每鏡走既有 validate → jobs，external{project_id, asset_id, shot_id, request_id} 由 API 填；「鏡狀態＋take＋job」一個交易。排程迴圈在 ltx-api 內：一次一個 GPU job，worker_busy 保留順位重試，失敗／取消／中斷暫停整條線；API 重啟後從資料庫狀態續跑。租戶＝owner_id；管理員暫停；每帳號佇列上限可設。\n"
"3. worker_schema.py：工作單 v2 的伺服器端驗證。\n"
"4. lib/factory-client.ts（新）＋ components/production-factory.tsx 改讀寫 API；localStorage 只留 UI 偏好；首次載入若有本機 v1／v2 計畫，提供「上傳到主機」一次性搬移。\n"
"5. tests/test_factory_api.py：租戶隔離、冪等重送、暫停不殺 job、續跑。docs/PRODUCTION_FACTORY.md 與 docs/WORKER_API.md 補 API。\n"
"這張很大：優先順序 1→2→3→5→4，每個子步驤一個 commit。",
 extra="額外檢查：用兩個測試帳號各建一個專案，A 查不到 B 的（403／404）；同一鏡同一 Idempotency-Key 重送兩次只產生一個 job。\n"),
 dict(id="B2", title="音訊服務 MA／LS", phase="B", size="M", tests=PYDB, body=
"1. services/audio/server.py：跑在 /opt/studio/venvs/audio（缺 web 框架就 pip 裝進該 venv，這不是系統層級）；只 bind 127.0.0.1:8790；POST /beats {path} 回 tempo、beat 時間、段落與能量曲線；POST /align {path, lyrics, language} 回逐字時間；path 必須在 uploads/ 或 data/ 之下否則 400。\n"
"2. local_backend.py：POST /api/v1/audio/analyze {audio_id, lyrics?, language?}，檢查 asset 所有權 → 解析路徑 → 呼叫服務 → 結果快取在 asset（同檔不重算）；回傳附 lyric_offset_seconds（Bible 預設 −0.9）與說明「常數偏移，非隨機誤差」；服務不可用回 503 不影響生成。\n"
"3. infra/systemd/ltx-audio.service：只建立檔案；enable 需核准區塊，收到核准才 systemctl --user enable --now。\n"
"4. tests/test_audio_service.py：用 tests/fixtures 合成音（不下載模型也能跑的部分），與一個標記為需真模型的整合測試。",
 extra="額外檢查：用 uploads/ 裡三首沖縄 wav 之一打 /beats，BPM 與 docs/GB10_SETUP.md 記錄一致（104.2 等）；curl 從非 loopback 位址打 8790 應連不上。\n"
"對時門檻是 p50 ≤ 0.5s 且 p90 ≤ 1.5s，p90 用 nearest-rank：殘差排序後取索引 ceil(0.9n)-1。"
" 這個索引要照寫的算 —— int(0.9n) 不等於 ceil(0.9n)，在 n=40 會差一格，同一份殘差換算法"
" 差得到 0.1s 以上。門檻由來記在 docs/PRODUCTION_ROADMAP.md 的 B2 節，完整分布在"
" docs/GB10_SETUP.md。\n"),
 dict(id="B3", title="自動分鏡", phase="B", size="M", tests=JS, body=
"1. lib/breakdown.ts（純函式）：輸入 beats／sections／lyric lines／segment_seconds／Bible directing 預設，輸出鏡頭清單與 cue；規則：段落邊界 ＞ 歌詞行起點（已扣偏移）＞ 每鏡上限；切點吸附最近拍點（±1 拍）；純器樂段產生 breathing 鏡；每鏡 cue 時間＝鏡起點、主要動作留空。\n"
"2. components/breakdown-editor.tsx：01 分鏡頁 — 波形＋拍點網格＋段落色帶、歌詞行貼在對時位置、鏡頭清單可合併／拆分／改；「預覽分鏡」沿用既有。\n"
"3. tests/breakdown.test.mjs：166 秒、segment_seconds=10 → 17–24 鏡、無一鏡超上限、切點全在拍點；合併兩鏡後 cue 重算。",
 extra=""),
 dict(id="B4", title="LLM 編劇草稿", phase="B", size="S", tests=PYDB + " && " + JS, body=
"1. local_backend.py：POST /api/v1/factory/shots/{id}/draft — 主機端呼叫 OpenAI（key 讀 /opt/studio/secrets/openai，權限 0600，瀏覽器永遠拿不到）；輸入 Bible 描述、該鏡導演參數、歌詞行、前後鏡；structured output 只允許 {prompt, primary_action}；usage 寫進 project；每專案 token 上限，超過回 429。\n"
"2. UI：每鏡「起草」按鈕填進可編輯文字框；草稿不覆蓋用戶已改過（pinned）的提示詞；OpenAI 不可用時按鈕停用並說明。\n"
"3. 測試用 mock，不打真 API。",
 extra=""),
 dict(id="C1", title="裁判服務 CJ／SJ／MQ", phase="C", size="M", tests=PYDB, body=
"1. services/judge/server.py：跑在 /opt/studio/venvs/vision；只 bind 127.0.0.1:8791；POST /score {media_path, references[paths], style_anchor_path?}：抽幀每秒 1 幀；CJ 有臉用 facenet 對參照表取最大相似度、無臉退 DINOv2，回每幀與中位數；SJ 用 CLIP 對風格錨中位數；MQ 用 RAFT 光流幅度統計＋黑幀／靜止比例。只回數字，不判通過。path 必須在 uploads/、outputs/ 或 data/ 之下。\n"
"2. local_backend.py：job succeeded 後自動送判，結果寫進 take.scores（B1 的 takes 表）；判分失敗只標「未判分」不影響 job 狀態。\n"
"3. infra/systemd/ltx-judge.service 只建檔，enable 需核准。\n"
"4. tests/test_judge_service.py：合成圖（同色塊 vs 不同色塊）驗方向正確；真模型整合測試單獨標記。",
 extra="額外檢查：同一張圖對自己 CJ face 接近 1.0；nvidia-smi 顯示服務常駐記憶體約 2 GB 以內。\n"),
 dict(id="C2", title="Take 模型", phase="C", size="S", tests=PYDB + " && " + JS, body=
"1. 以 B1 的 takes 表為基礙：verdict 狀態機 pending → accepted／rejected／overridden；shot.accepted_take_id；「修改／重做」（既有 reopenFactoryShot）改為建立新 take；退回必填 reason，reason 自動以「避免：…」接到下一 take 的 prompt 末尾，累積不覆蓋，用戶可改。\n"
"2. 既有的成品刪除（回收區）→ 該 take 標 deleted，鏡與其他 take 不受影響。\n"
"3. 測試涵蓋兩次退回累積、刪除隔離、accepted_take_id 唯一。",
 extra=""),
 dict(id="C3", title="審片頁", phase="C", size="M", tests=JS, body=
"1. 04 審片頁：每鏡 take 並排；三條分數 vs Bible 門檻線（C4 前顯示「未校準」用暫定值並標示）；VLM 一句話（主機端 gpt-5.6 呼叫，走 B4 同一 key 與 usage 記帳）＋「我不同意」；接受／退回（必填原因）；紅燈下按接受 → overridden 並記錄誰、何時。\n"
"2. 抽屜：逐幀 CJ 曲線、相鄰鏡嚴格模式（fpr 1% 門檻）、本鏡門檻覆寫。\n"
"3. 否決＝take 不自動成為 accepted_take_id、不進 06；不阻止用戶接受。裁判服務關閉時頁面仍可用，分數欄顯示未判分。",
 extra="額外檢查：用兩個不同角色的參照各生成一個 take，換臉的那個是否紅燈且未自動進組片。\n"),
 dict(id="C4", title="門檻校準", phase="C", size="S", tests=JS, body=
"1. 檢查 calibration/ 是否存在且 ≥2 個角色資料夾、每個 ≥10 張；不足就列出缺什麼並停下回報，不要自己找圖湊數。\n"
"2. 足夠時：/opt/studio/venvs/vision/bin/python infra/gb10/tools/calibrate_embeddings.py --root calibration --out calibration_report.json；把 fpr 5% 門檻寫進 Bible 預設、fpr 1% 當相鄰鏡嚴格值；UI 加「匯入校準報告」讀 JSON 進 bible.thresholds；C3 門檻線不再標「未校準」；無臉圖列出並在 UI 標示。",
 extra=""),
 dict(id="D1", title="imagegen adapter 與 GPU 租約", phase="D", size="L", tests=PYDB, body=
"1. local_adapters/imagegen.py：Qwen-Image-Edit-2509、Z-Image-Turbo 註冊成 media_type image 的 adapter；參數 steps（預設 8）、seed、references（1–3 個 image_id）、lightning、size，經 model_registry.py 檢查；不接受路徑。\n"
"2. services/imagegen/server.py：跑在 /opt/studio/venvs/imagegen，只 bind 127.0.0.1:8792；模型常駐、閒置 N 分鐘釋放；infra/systemd/ltx-imagegen.service 只建檔，enable 需核准。\n"
"3. local_backend.py 大工站租約：同時只有 LTX 或 imagegen 持有 GPU；切換前必須釋放（imagegen 卸模型、LTX 無進行中 job）；裁判、音訊、後製不受限。\n"
"4. tests/test_imagegen_adapter.py、tests/test_gpu_lease.py（租約用假工站測互斥與交棒）。\n"
"絕對不要在有 LTX job 進行中時載入 Qwen（61 GB）；先查 GET /api/internal/active-jobs。",
 extra="額外檢查：LTX job 進行中送 imagegen job → 排隊不 OOM；連續 20 張只付一次載入（看服務日誌）；閒置超時後 nvidia-smi 無 imagegen 程序。\n"),
 dict(id="D2", title="關鍵格階段", phase="D", size="M", tests=JS, body=
"1. 02 關鍵格頁：鏡頭清單變縮圖格；「產生全部關鍵格」整批：每鏡依 directing.angle 選參照（既有 select_reference 邏輯）→ imagegen job → C1 判分 → 綠／黃／紅；紅自動換 seed 重生一次再請人看；核准圖成為該鏡 image_id 並在籤上標「來自關鍵格」。\n"
"2. 介面明確顯示「現在是關鍵格階段／拍攝階段」與切換代價（336 s）。",
 extra=""),
 dict(id="D3", title="後製 adapter VX", phase="D", size="M", tests=PYDB, body=
"1. 先檢查 /opt/studio/tools/rife/train_log 是否有權重；沒有就回報阿寶並跳過 RIFE、只做 ESRGAN 與 LaMa。\n"
"2. 對核准的 take 提供三個 post job：補幀（RIFE 到目標 FPS）、放大（Real-ESRGAN ×4 或沿用 LTX x2）、清理（LaMa，用戶畫遮罩）；輸入是本機 take 檔而非上傳；輸出成新 take 版本；完成後自動過 MQ。",
 extra=""),
 dict(id="D4", title="工站排程與 LP 預算", phase="D", size="M", tests=PYDB + " && " + JS, body=
"1. 排程器：待跑 job 依工站分群、同工站連續做、做完交棒（用 D1 租約）。\n"
"2. 工站頁：誰坐 GPU、佇列、切換 ETA。\n"
"3. LP 預算＝Σ 每鏡 generate 秒 + 切換次數 × 載入秒 + OpenAI usage；數字來自 docs/GB10_SETUP.md 與 jobs.runtime_seconds 滾動平均；超預算是警告不擋。",
 extra="額外檢查：混合 12 張關鍵格 + 12 鏡 LTX 的佇列恰好切換 1 次。\n"),
 dict(id="D5", title="組片與 EDL", phase="D", size="S", tests=PYDB + " && " + JS, body=
"1. 06 組片：只取每鏡 accepted_take_id，依拍點排時間軸，原曲連續鋪底（既有 sequence 組片）；任一鏡無 accepted take → 按鈕停用並列出哪幾鏡。\n"
"2. 匯出 MP4 + shot manifest／EDL JSON：每鏡 prompt、seed、參照指紋、模型版本、take 裁決；manifest 能還原每鏡完整 request（與 A1 匯出格式相容）。",
 extra=""),
]

SETUP = (
"阿寶要開一條長期工作線，請把下面寫進 USER.md（active directives）與 MEMORY.md，之後每個「工單」任務都照做：\n"
"1. 專案：LTX Local Studio，目錄 " + REPO + "（路徑有空格，一律加引號）。規格在 docs/PRODUCTION_ROADMAP.md，工作規則在 docs/OPENCLAW_WORK_ORDERS.md。\n"
"2. 分支紀律：主 checkout 永遠停在 main、不在裡面 checkout 其他分支或改檔；每張工單在自己的 worktree ~/LTX-worktrees/wo-<小寫工單號>（分支 wo/<小寫工單號>，ln -s 主 checkout 的 node_modules）工作；絕對不 push、merge、rebase 到 main — main 一推就由 ltx-git-sync 自動部署到正式站 ltx.mikamiu.studio。合併只有阿寶做。\n"
"3. 服務紀律：不重啟 ltx-web、ltx-api、ltx-cloudflared；正式站 3000 與 API 8787 不可占用，dev server 只用 3001；不動 /opt/studio 的模型權重。\n"
"4. 系統層級動作（apt、systemctl enable/start、/etc、unit 檔啟用）先發核准區塊；需要 sudo 的指令列出來給阿寶自己跑。\n"
"5. 15 分鐘紀律：每則任務在 15 分鐘內結束於乾淨狀態 — commit、push 分支、更新 docs/work-orders/<工單號>.md 的進度區（已完成／未完成／需要阿寶做的事），回報做到哪。\n"
"6. 回報格式：改了哪些檔、跑了什麼測試與結果、卡點、下一步；沒全過驗收自檢不說「完成」。\n"
"7. 兩種 runtime 不能混：前端測試用 nvm 的 node；Python 測試一律用 LTX venv 的 python\n"
"   （" + LTX_PYTHON + "），不要用 python3 — 系統 python 沒有 av，test_quality 與\n"
"   test_mv_timeline 會 import 失敗。\n"
"8. 本機 loopback 服務（ltx-audio 8790、ltx-judge 8791、ltx-imagegen 8792）先查再起：\n"
"   `ss -ltn | grep :<port>` 或打 /health，有人在聽就直接用；不要重複啟動，也不要停掉別人的。\n"
"確認寫入後，回覆你記下了哪幾條。"
)

MERGE_NOTE = (
"合併由你在主機上做（或請我做），不交給 OpenClaw：\n"
"cd \"/home/kwayrdc/LTX Local Studio\" && git fetch origin && git checkout main && git merge --ff-only origin/wo/<id> && git push origin main\n"
"push 之後 ltx-git-sync 在 5 分鐘內驗證、build、重啟對應服務。ff-only 失敗代表 main 在分支之後又動過，先 rebase 分支再合。\n"
"合併後清掉 worktree：git worktree remove ~/LTX-worktrees/wo-<id> && git branch -d wo/<id>"
)

def fill(t, w):
    return t.format(id=w["id"], lid=w["id"].lower(), body=w["body"], tests=w["tests"], extra=w.get("extra",""))

def utf16len(s): return len(s.encode("utf-16-le")) // 2

# ---------- markdown ----------
md = ["# OpenClaw 工單提示詞與工作規則", "",
"本檔與 `OPENCLAW_WORK_ORDERS.html` 由 `docs/tools/gen_openclaw_prompts.py` 產生；要改提示詞請改產生器再重跑，不要直接編輯。", "",
"這份文件是 OpenClaw（LINE 上的「老皮」）執行製片平台工單時的工作規則與提示詞正本。規格本體在 `docs/PRODUCTION_ROADMAP.md`。",
"提示詞可複製整段貼進 LINE；`背景任務：` 前綴會讓 bridge 直接放進背景（上限 15 分鐘），完成後用 `查詢 JOB-xxxx` 取結果。", "",
"## 工作規則（每張工單都適用）", "",
"0. 主 checkout `/home/kwayrdc/LTX Local Studio` **永遠停在 main**；不在裡面 checkout 其他分支或改檔 — 正式站、`ltx-git-sync`、dev preview 都靠它。每張工單在自己的 worktree `~/LTX-worktrees/wo-<工單號小寫>` 工作（`git worktree add … -b wo/<id> origin/main`，`ln -s` 主 checkout 的 `node_modules`）。",
"1. 只在 `wo/<工單號小寫>` 分支 commit 與 push；**絕不 push、merge、rebase 到 main**。main 一推就由 `ltx-git-sync` 自動部署正式站。合併只有人做。",
"2. 不重啟 `ltx-web`、`ltx-api`、`ltx-cloudflared`；正式站 3000／API 8787 不可占用，dev server 只用 3001；不動 `/opt/studio` 權重。",
"3. 系統層級動作（apt、`systemctl --user enable/start`、`/etc`、unit 檔啟用）先發核准區塊；需要 sudo 的指令列給人自己跑。",
"4. 15 分鐘紀律：每則任務結束於乾淨狀態 — commit（訊息以「<工單號>: 」開頭）、push 分支、更新 `docs/work-orders/<工單號>.md` 進度區（已完成／未完成／需要人做的事）。",
"5. 驗收是獨立的一則任務，不修改程式；每條 PASS／FAIL 附證據；最後一行「<工單號> 可合併」或「<工單號> 退回」。",
"5a. **本機服務先查再起**：工單引入的 loopback 服務（ltx-audio 8790、ltx-judge 8791、ltx-imagegen 8792）可能已由開發手動啟動。先 `ss -ltn | grep :<port>` 或打 `/health`；有人在聽就直接用，不要重複啟動，也不要停掉別人的 —— 啟停不屬於驗收動作。",
"5b. **Python 測試一律用 LTX venv 的 python**（`" + LTX_PYTHON + "`），不是 `python3`：系統 python 有 psycopg 但沒有 `av`，`test_quality` 與 `test_mv_timeline` 會 import 失敗（97 tests 而非 120）。`git-sync-main.sh` 本來就用這個直譯器跑 Python 測試。",
"6. 合併：在主 checkout `git fetch origin && git merge --ff-only origin/wo/<id> && git push origin main`；由人在主機執行。之後 `git worktree remove ~/LTX-worktrees/wo-<id> && git branch -d wo/<id>`。", "",
"## 第 0 步：開工設定（只傳一次）", "", "```text", SETUP, "```", "",
"## 繼續模板", "", "把 `{id}` 換成工單號：", "", "```text", CONT.replace("{lid}", "<id 小寫>").replace("{id}", "<id>"), "```", ""]
phase_names = {"A":"A 專案層與階段導覽（純前端）", "B":"B 主機端專案與音訊（PostgreSQL）", "C":"C 裁判與審片", "D":"D 多工站"}
cur = None
for w in WO:
    if w["phase"] != cur:
        cur = w["phase"]; md += [f"## {phase_names[cur]}", ""]
    ex, ac = fill(PRE, w), fill(ACC, w)
    md += [f"### {w['id']} {w['title']}（{w['size']}）", "", "執行：", "", "```text", ex, "```", "", "驗收：", "", "```text", ac, "```", ""]
OUT_MD = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "OPENCLAW_WORK_ORDERS.md"
OUT_MD.write_text("\n".join(md), encoding="utf-8")

# ---------- html ----------
def card(id_, title, sub, blocks):
    inner = ""
    for label, text in blocks:
        n = utf16len(text); warn = ' warn' if n > 4500 else ''
        inner += f'''<div class="blk"><div class="blk-h"><span class="lbl">{label}</span><span class="cnt{warn}">{n} 字</span><button type="button" class="copy" data-copy>複製</button></div><pre>{html.escape(text)}</pre></div>'''
    return f'''<article class="card" id="{id_}"><div class="card-h"><span class="n">{id_}</span><h3>{html.escape(title)}</h3><span class="sub">{html.escape(sub)}</span></div>{inner}</article>'''

cards = card("setup", "開工設定", "只傳一次；讓老皮把規則寫進自己的記憶", [("LINE 訊息", SETUP)])
cur = None
for w in WO:
    if w["phase"] != cur:
        cur = w["phase"]; cards += f'<h2 class="ph" id="p{cur}">{html.escape(phase_names[cur])}</h2>'
    cards += card(w["id"], w["title"], f'{w["size"]} · 分支 wo/{w["id"].lower()}', [("執行", fill(PRE, w)), ("驗收", fill(ACC, w)), ("繼續", fill(CONT, w))])
cards += card("merge", "合併（你做，不給老皮）", "驗收回「可合併」之後", [("主機指令", MERGE_NOTE)])

nav = "".join(f'<li><a href="#{w["id"]}"><span class="k">{w["id"]}</span>{html.escape(w["title"])}</a></li>' for w in WO)
page = f'''<title>工單提示詞</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{{--ground:#fbfaf7;--surface:#fff;--surface-2:#f3f1ec;--ink:#16151a;--ink-2:#4a4850;--muted:#6b6870;--line:#e4e1dc;--line-strong:#c9c5be;--accent:#e85578;--accent-soft:#fdeef2;--pass:#11786f;--pass-soft:#e6f6f3;--warn:#b7791f;--warn-soft:#fbf3e2;--code-bg:#f3f1ec;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--ground:#141318;--surface:#1c1b21;--surface-2:#232228;--ink:#ece9e3;--ink-2:#c9c5bd;--muted:#9a968f;--line:#2d2c33;--line-strong:#46444d;--accent:#ff7f9c;--accent-soft:#2e1c23;--pass:#4fc3b5;--pass-soft:#172a28;--warn:#e0a84a;--warn-soft:#2b2416;--code-bg:#232228;color-scheme:dark}}}}
:root[data-theme="dark"]{{--ground:#141318;--surface:#1c1b21;--surface-2:#232228;--ink:#ece9e3;--ink-2:#c9c5bd;--muted:#9a968f;--line:#2d2c33;--line-strong:#46444d;--accent:#ff7f9c;--accent-soft:#2e1c23;--pass:#4fc3b5;--pass-soft:#172a28;--warn:#e0a84a;--warn-soft:#2b2416;--code-bg:#232228;color-scheme:dark}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--ground);color:var(--ink);font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif;font-size:15px;line-height:1.75;-webkit-font-smoothing:antialiased}}
h1,h2,h3{{margin:0;text-wrap:balance;line-height:1.25}}p{{margin:0}}code,pre{{font-family:"IBM Plex Mono",Menlo,Consolas,monospace}}code{{background:var(--code-bg);padding:.08em .4em;font-size:.86em}}
.page{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:48px;max-width:1180px;margin:0 auto;padding:48px 32px 96px}}@media(max-width:860px){{.page{{grid-template-columns:1fr;gap:28px;padding:28px 18px 72px}}.slate{{position:static!important}}}}
.slate{{position:sticky;top:24px;align-self:start;border-top:3px solid var(--ink);padding-top:14px;font-size:13px}}.slate ol{{list-style:none;margin:0;padding:0;display:grid;gap:2px}}.slate li a{{display:grid;grid-template-columns:30px 1fr;gap:8px;align-items:baseline;padding:6px 8px 6px 6px;text-decoration:none;color:var(--ink-2)}}.slate li a:hover{{background:var(--surface-2);color:var(--ink)}}.slate .k{{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--accent);font-weight:600}}.slate .sep{{height:1px;background:var(--line);margin:10px 0}}.slate .foot{{margin-top:18px;color:var(--muted);font-size:12px;line-height:1.6}}.slate .foot a{{color:var(--ink-2)}}
.eyebrow{{font-size:11px;font-weight:700;letter-spacing:.18em;color:var(--accent);text-transform:uppercase;margin-bottom:14px}}
main{{display:grid;gap:28px;min-width:0}}header.head{{border-bottom:1px solid var(--line-strong);padding-bottom:26px;display:grid;gap:14px}}header.head h1{{font-size:clamp(30px,4.2vw,44px);font-weight:900;letter-spacing:-.01em}}header.head .sub{{font-size:16px;color:var(--ink-2);max-width:64ch}}header.head .sub a{{color:var(--ink-2)}}
.how{{border:1px solid var(--line);background:var(--surface);padding:18px 20px;display:grid;gap:8px;font-size:14px;color:var(--ink-2);max-width:78ch}}.how b{{color:var(--ink)}}.how ol{{margin:0;padding-left:1.3em;display:grid;gap:6px}}
.ph{{font-size:22px;font-weight:900;border-top:3px solid var(--ink);padding-top:14px;margin-top:12px;scroll-margin-top:24px}}
.card{{border:1px solid var(--line);background:var(--surface);scroll-margin-top:24px}}.card-h{{display:flex;flex-wrap:wrap;align-items:baseline;gap:12px;padding:14px 18px;border-bottom:1px solid var(--line);background:var(--surface-2)}}.card-h .n{{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--accent);font-weight:600}}.card-h h3{{font-size:17px;font-weight:900}}.card-h .sub{{font-size:12px;color:var(--muted)}}
.blk{{border-bottom:1px solid var(--line)}}.blk:last-child{{border-bottom:0}}.blk-h{{display:flex;align-items:center;gap:12px;padding:8px 18px;font-size:11px;letter-spacing:.1em;font-weight:700;color:var(--muted)}}.blk-h .cnt{{font-family:"IBM Plex Mono",monospace;font-weight:500;letter-spacing:0;margin-left:auto}}.blk-h .cnt.warn{{color:var(--warn)}}
.copy{{font:inherit;font-weight:700;letter-spacing:.08em;background:var(--ink);color:var(--ground);border:0;padding:5px 12px;cursor:pointer}}.copy:hover{{background:var(--accent)}}.copy:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}.copy.done{{background:var(--pass)}}
.blk pre{{margin:0;padding:14px 18px 18px;background:var(--surface);white-space:pre-wrap;word-break:break-word;font-size:12.5px;line-height:1.7;color:var(--ink-2)}}
@media (prefers-reduced-motion:no-preference){{html{{scroll-behavior:smooth}}}}
</style>
<div class="page">
<nav class="slate" aria-label="目錄"><div class="eyebrow">十六張工單 · 每張三則</div>
<ol><li><a href="#setup"><span class="k">0</span>開工設定</a></li></ol><div class="sep"></div>
<ol>{nav}</ol><div class="sep"></div><ol><li><a href="#merge"><span class="k">→</span>合併</a></li></ol>
<div class="foot">正本：<code>docs/OPENCLAW_WORK_ORDERS.md</code><br>規格：<code>docs/PRODUCTION_ROADMAP.md</code><br><a href="https://claude.ai/code/artifact/8bcb0688-59ab-45a0-84ec-430946a243a3">← 實作路線</a></div></nav>
<main>
<header class="head"><div class="eyebrow" style="margin:0">ltx.mikamiu.studio · LINE → OpenClaw</div><h1>工單提示詞</h1>
<p class="sub">每張工單三則訊息：<b>執行</b>、<b>驗收</b>、<b>繼續</b>。整段複製貼進 LINE 給老皮；<code>背景任務：</code> 前綴讓它直接進背景（上限 15 分鐘），完成後傳 <code>查詢 JOB-xxxx</code> 取結果。字數已對 LINE 上限（5000）檢查。</p></header>
<div class="how"><b>使用順序</b><ol><li>先傳一次「開工設定」，讓老皮把規則寫進自己的 USER.md／MEMORY.md。</li><li>傳某張工單的「執行」。它 15 分鐘做不完會停在乾淨狀態並回報；再傳「繼續」直到它自檢全過。</li><li>傳「驗收」— 這是獨立任務，不改程式，逐條 PASS／FAIL，最後一行「可合併」或「退回」。退回就回到步驟 2。</li><li>「可合併」後由你在主機上 ff 合併並 push main；ltx-git-sync 會自動部署。</li></ol>
<p><b>工作目錄</b>：老皮在 <code>~/LTX-worktrees/wo-&lt;id&gt;</code> 的獨立 worktree 裡做事；主 checkout 永遠停在 main。若發現主 checkout 不在 main，先 <code>git checkout main</code> 再繼續。</p>
<p>老皮遇到 apt、systemctl、sudo 會先發 <code>【需要核准：OP-xxxx】</code> 區塊 — 那是它自己的規則，回「核准 OP-xxxx」或自己跑它列出的指令。</p></div>
{cards}
</main></div>
<script>
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{{const t=b.closest('.blk').querySelector('pre').textContent;try{{await navigator.clipboard.writeText(t);b.textContent='已複製';b.classList.add('done');setTimeout(()=>{{b.textContent='複製';b.classList.remove('done')}},1600)}}catch(e){{const r=document.createRange();r.selectNodeContents(b.closest('.blk').querySelector('pre'));const s=getSelection();s.removeAllRanges();s.addRange(r);b.textContent='已選取，Ctrl+C'}}}}));
</script>'''
OUT_HTML = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "OPENCLAW_WORK_ORDERS.html"
OUT_HTML.write_text(page, encoding="utf-8")
longest = max((utf16len(fill(PRE, w)), w["id"]) for w in WO)
print("md:", OUT_MD); print("html:", OUT_HTML); print("longest 執行 prompt:", longest, "(LINE limit 5000)"); print("setup:", utf16len(SETUP))
