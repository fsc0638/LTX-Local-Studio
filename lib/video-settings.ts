export type VideoCapabilities = {
  limits: { max_frames: number; fps_min: number; fps_max: number };
  aspect_ratios: Record<string, { width: number; height: number }>;
  sequence?: { supported: boolean; max_seconds: number; max_segments: number; audio_conditioning: string; precise_lip_sync: boolean };
  directing?: Record<string, Record<string, { label: Record<string, string>; prompt: string }>>;
};

// Keep duration when changing FPS. Invalid combinations block submission;
// never clamp silently or shorten playback to fit the selected FPS.
export function durationFrames(seconds: number, fps: number, maxFrames: number): number | null {
  if (!Number.isFinite(seconds) || seconds <= 0 || !Number.isInteger(fps) || fps < 8 || fps > 60 ||
      !Number.isInteger(maxFrames) || maxFrames < 9 || (maxFrames - 1) % 8 || seconds > maxFrames / fps) return null;
  const frames = Math.max(9, Math.ceil((seconds * fps - 1) / 8) * 8 + 1);
  return frames <= maxFrames ? frames : null;
}

export function maximumDurationInput(maxFrames: number, fps: number): string {
  // Floor the displayed input so its decimal rounding never exceeds the cap.
  return String(Math.floor(maxFrames / fps * 1000) / 1000);
}

export const durationPresets = [2, 4, 6, 8, 10, 12, 15, 20, 30, 45, 60, 90, 120, 180];

export function sequenceFrames(seconds: number, fps: number, maximum = 180): number | null {
  return Number.isFinite(seconds) && seconds >= 0.125 && seconds <= maximum && Number.isInteger(fps) && fps >= 8 && fps <= 60
    ? Math.ceil(seconds * fps) : null;
}

export const videoCopy = {
  "zh-TW": { ratio: "長寬比例", dimensions: "實際解析度", custom: "自訂秒數", maximum: "最長可選", ceiling: "主機上限", invalid: "秒數超出目前 FPS 的範圍。請減少秒數或降低 FPS；不會自動截短。", loading: "正在讀取主機生成限制…", resource: "時長、解析度越高，生成越慢且更耗記憶體；降低 FPS 也會降低動作流暢度。", long: "超過 20 秒屬實驗性長片，角色與動作一致性不保證。", negativeTitle: "此模型不支援負面提示詞", negative: "目前安裝的是 Distilled 快速模型（CFG=1），只使用正面提示詞。真正的負面提示詞需要 Dev 模型與 guided 執行器；本機尚未安裝，不會把未生效的欄位當作可用設定。", promptTip: "可改用正面描述，例如「清楚對焦、自然手部姿態、乾淨無字的背景」；這不是負面提示詞的等效替代。", quick: "快速測試 · 1:1 / 512 × 512 / 17 幀", memory: "依設定變動" },
  en: { ratio: "Aspect ratio", dimensions: "Output resolution", custom: "Custom seconds", maximum: "Maximum", ceiling: "Host limit", invalid: "Duration exceeds the range at this FPS. Reduce seconds or FPS; the request will not be silently shortened.", loading: "Reading host generation limits…", resource: "Longer clips and higher resolution take more time and memory. Lower FPS reduces motion smoothness.", long: "Clips beyond 20 seconds are experimental; character and motion consistency are not guaranteed.", negativeTitle: "Negative prompts unsupported by this model", negative: "The installed distilled fast model uses CFG=1 and positive conditioning only. Real negative prompts need a Dev checkpoint and guided runner, which are not installed. An inactive setting is not presented as usable.", promptTip: "Try positive descriptions such as ‘sharp focus, natural hands, a clean background without lettering’. This is not equivalent to negative conditioning.", quick: "Quick test · 1:1 / 512 × 512 / 17 frames", memory: "Depends on settings" },
  ja: { ratio: "アスペクト比", dimensions: "出力解像度", custom: "秒数を指定", maximum: "最大", ceiling: "ホストの上限", invalid: "この FPS では秒数が上限を超えます。秒数または FPS を下げてください。自動で短縮しません。", loading: "ホストの生成上限を取得中…", resource: "長い動画や高解像度ほど時間とメモリが必要です。低 FPS では動きの滑らかさが低下します。", long: "20 秒を超える動画は実験的です。人物や動きの一貫性は保証されません。", negativeTitle: "このモデルはネガティブプロンプト非対応", negative: "導入済みの Distilled 高速モデルは CFG=1 で、正のプロンプトのみ使用します。ネガティブ条件には未導入の Dev モデルと guided 実行器が必要です。機能しない入力欄は表示しません。", promptTip: "「鮮明なピント、自然な手、文字のない背景」のように正の表現で説明できますが、ネガティブ条件と同等ではありません。", quick: "クイックテスト · 1:1 / 512 × 512 / 17 フレーム", memory: "設定により変動" },
};
