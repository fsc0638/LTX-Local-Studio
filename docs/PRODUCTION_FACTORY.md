# 製片工廠（Production Factory）計畫

製片工廠是通用 `/api/v1` 影片服務之上的製作控制層，不建立任何專案專用 API。角色、企劃、音樂與行銷專案可以輸出標準工作單，再由這台 GB10 主機依序生產影片。

## V1：瀏覽器製片佇列（本次完成）

- 「生成」頁的完整設定可以加入製片工廠，不立即消耗 GPU。
- 同一製片最多100個鏡頭，可改名稱、提示詞與排序。
- 開始生產後，每鏡先呼叫 `/api/v1/validate`，通過才以固定 Idempotency-Key 呼叫 `/api/v1/jobs`。
- 一次只送一個 GPU 任務；若 GPU 正忙，鏡頭保留順位並重試，不建立重複任務。
- 鏡頭失敗、取消或中斷會暫停整條生產線，需人工修正及重試。
- 暫停不強制殺掉目前 GPU 任務；當前鏡頭安全完成後，不再送下一鏡。
- 已完成鏡頭可繼續改名、改提示詞、排序、移除，或保留前次成品後重新製作，不再鎖定。
- 成品可從工廠直接刪除；檔案與預覽圖會移入本機私有回收區，鏡頭設定保留為草稿以便重做。單純移除工廠列仍不會刪除成品。
- 計畫依登入帳號隔離，保存在目前瀏覽器；重新整理可續接正在執行的 job。
- 支援匯入／匯出純 JSON 工作單。匯入內容只當資料解析，不執行程式碼；每鏡仍由 worker 做正式驗證。

瀏覽器關閉後，已經送出的單一鏡頭仍在本機 worker 繼續執行；但 V1 不會在沒有頁面的情況下自動送出下一鏡。再次開啟網站後會查詢原 job 並續跑佇列。這個限制會在 V2 移到後端排程後解除。

## 工作單格式 v2（A1）

工作單 v2 在瀏覽器計畫加入專案層 `bible`。角色、音樂、輸出規格與導演預設會投影到新鏡頭的完整 `/api/v1/jobs` `request`；每鏡自行改過的頂層 request 欄位記在 `pinned`，之後更新 Bible 時不覆蓋。`draft`、`queued`、`failed` 可重新投影，`running`、`succeeded` 永遠保持原請求。

```json
{
  "format": "ltx-production-factory",
  "version": 2,
  "title": "MV 01",
  "bible": {
    "character": {
      "name": "PERFORMER",
      "description": "Short silver hair, red coat",
      "references": [
        { "image_id": "0123456789abcdef0123456789abcdef", "view": "front" }
      ]
    },
    "music": {
      "audio_id": "abcdef0123456789abcdef0123456789",
      "audio_start_seconds": 0,
      "audio_mode": "soundtrack",
      "lrc": "[00:01.00]Opening line",
      "lrc_timebase": "music"
    },
    "output": {
      "model": "ltx23-distilled",
      "aspect_ratio": "16:9",
      "fps": 24,
      "profile": "compat-v1",
      "audio": true
    },
    "directing": { "shot_size": "wide", "camera": "static" },
    "lyric_offset_seconds": -0.9
  },
  "shots": [
    {
      "title": "OPENING",
      "request": {
        "prompt": "A cinematic wide shot of an adult performer at dawn.",
        "model": "ltx23-distilled",
        "mode": "t2v",
        "aspect_ratio": "16:9",
        "duration_seconds": 6,
        "fps": 24,
        "seed": 42,
        "audio": true,
        "character": {
          "name": "PERFORMER",
          "description": "Short silver hair, red coat",
          "references": [
            { "image_id": "0123456789abcdef0123456789abcdef", "view": "front" }
          ]
        }
      },
      "pinned": ["seed"]
    }
  ]
}
```

也可匯入 v1 工作單、單一標準 `/api/v1/jobs` request，或由多個 request 組成的 JSON array。v1 會遷移成空 Bible，既有 request 的全部欄位視為已釘住，因此不會被日後投影意外改寫。執行狀態、job ID、錯誤與成品 URL不寫入可攜工作單，避免在另一個帳號或主機錯誤重用舊任務。

## 後續路線

### V2：主機端耐久排程

- 將製片計畫與鏡頭狀態存入本機 PostgreSQL（與任務、帳號紀錄同一個資料庫；既有 SQLite 一併遷入），關閉所有瀏覽器仍可自動接續。
- 以帳號為租戶邊界，加入每帳號佇列配額、全域公平排程與管理員暫停。
- 保留現有 `/api/v1/jobs` 契約；Factory API 只負責編排，不直接碰模型命令或檔案路徑。

### V3：審片與版本管理

- 每鏡 Take A/B、接受／退回、重生原因、角色一致性與技術 QC 門檻。
- 只讓核准鏡頭進入組片；保留 prompt、seed、參照素材 fingerprint 與模型版本。
- 建立可匯出的 EDL／shot manifest，供剪輯與其他專案使用。

### V4：多模型工站

- 依已安裝 adapter 將影片、圖片、語言與後製模型視為不同工站。
- 排程器依 GPU/記憶體需求與依賴關係分派；帳號、素材權限及通用 API 不因模型更換而改變。
- 模型更新必須先經固定提示詞、效能、畫質與回歸測試，不讓「持續學習」直接改壞正式產線。

## 安全邊界

- Factory 不接受 shell、任意 URL 或本機路徑。
- 瀏覽器帳號仍受 Cloudflare Access、本機 session、CSRF 與素材所有權保護。
- Idempotency-Key 會跟著鏡頭保存；網路重試不會重複消耗 GPU。只有使用者按「修正後重試」才產生新 key。
- V1 的瀏覽器資料不是正式跨裝置資料庫；需要跨裝置共同編排時應完成 V2，不以共享 localStorage 或共用 service key 取代。
