# Character LoRA Registry

人物與服裝 LoRA 是主機管理的模型資產。瀏覽器只能選擇 registry ID 與已驗證範圍內的 strength；不得傳入權重路徑、URL、shell 或 trigger token。

## 安裝目錄

預設目錄為 `$LTX_REPO_ROOT/models/character-loras`，可由 `LTX_CHARACTER_LORA_DIR` 覆寫。每個權重必須有同目錄 JSON metadata。大型權重與真人私密素材不得提交 Git。

```json
{
  "id": "mika.identity.v1",
  "label": "Mika Identity v1",
  "kind": "identity",
  "model_family": "ltx-2.5",
  "weight_filename": "mika.identity.v1.safetensors",
  "weight_sha256": "64-lowercase-hex",
  "trigger_token": "mikaPersonV1",
  "default_strength": 0.8,
  "validated_strength_range": { "min": 0.55, "max": 1.0 },
  "compatible_models": ["ltx25-fast"],
  "compatible_modes": ["t2v", "i2v"],
  "approval_status": "approved",
  "version": "1.0.0"
}
```

Registry 只載入 `approved`、SHA-256 相符、普通檔案且 basename 安全的 `.safetensors`。錯誤項目會出現在 `GET /api/v1/character-loras` 的 `invalid_entries`，但不向前端暴露路徑或 trigger token。

## API

```json
{
  "prompt": "walks toward camera",
  "model": "ltx25-fast",
  "identity_lora": { "id": "mika.identity.v1", "strength": 0.8 },
  "wardrobe_lora": { "id": "mika.red-coat.v1", "strength": 0.65 }
}
```

API 驗證 kind、模型、模式及 strength，再注入 metadata 的 trigger token。Job provenance 保存 ID、版本、strength 與 weight SHA-256；權重路徑只存在 GPU 子程序環境。

## UI

- 沙盒的 LTX 2.5 設定區可選 Identity／Wardrobe LoRA。
- Factory Bible 可保存兩種 LoRA，新增鏡頭與未執行鏡頭會繼承。
- Registry 為空時只顯示「不使用 LoRA」，不能手打路徑或 token。

## 上線前驗收

1. 用正式角色 metadata 與權重建立 registry entry。
2. `GET /api/v1/character-loras` 顯示 approved entry，且回應不含路徑與 token。
3. 固定 prompt、seed、參照、尺寸及 frames，比較無 LoRA、Identity、Identity＋reference、Identity＋Wardrobe。
4. 分別驗正面、3/4、側面、全身、說話、遮擋與不同背景；逐幀人工審查。
5. 只有通過的 strength 範圍才能寫入 metadata；未通過不得標 `approved`。

