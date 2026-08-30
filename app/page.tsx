"use client";
/* eslint-disable next/no-img-element, jsx-a11y/media-has-caption -- Authenticated local media uses direct URLs; generated/source videos do not yet have caption files. */

import { useEffect, useMemo, useState } from "react";
import {
  Box,
  Check,
  ChevronRight,
  CircleGauge,
  Clock3,
  Code2,
  Cpu,
  FileImage,
  FileVideo,
  FolderOpen,
  Gauge,
  HardDrive,
  Image as ImageIcon,
  Layers3,
  MemoryStick,
  Play,
  RotateCcw,
  Settings2,
  Sparkles,
  TerminalSquare,
  Video,
  WandSparkles,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { MediaLibrary, fileCopy, type Asset } from "@/components/media-library";
import { AccountGate, AccountMenu } from "@/components/account-gate";
import { serviceFetch } from "@/lib/service-session";
import { ModelComposer, type InstalledModel } from "@/components/model-composer";

const initialPrompt =
  "電影感近景，一位穿著深色外套的女性站在潮濕的台北街口。鏡頭緩慢向前推進，霓虹燈在積水中形成珊瑚紅與青綠色倒影，微風帶動髮絲，自然環境音，細緻膠片顆粒。";

const promptPresets = [
  ["CINEMATIC", "電影感廣角，一列未來列車穿越雲海，金色晨光，緩慢空拍推進，真實物理光影，空間感環境音。"],
  ["PORTRAIT", "人像近景，柔和窗光，細微呼吸與眼神變化，淺景深，手持攝影的自然晃動，細膩膚質。"],
  ["PRODUCT", "極簡產品動畫，黑色背景，輪廓光沿著金屬表面移動，鏡頭環繞，乾淨高級的棚拍質感。"],
];

type OutputItem = {
  id: string;
  name: string;
  src: string;
  poster?: string;
  meta: string;
  runtime: string;
  size: string;
  download?: string;
};

const outputItems: OutputItem[] = [];
const emptyOutput: OutputItem = {id: "empty", name: "—", src: "", meta: "—", runtime: "—", size: "—"};

type ApiJob = {
  model?: string; media_type?: string;
  id: string; filename: string; output_url: string; poster_url?: string;
  width: number; height: number; frames: number; fps: number;
  runtime_seconds?: number; elapsed_seconds?: number; size_bytes?: number;
  status: string; progress: number; message?: string; error?: string;
};
type Health = { ok: boolean; runtime?: { cuda_available?: boolean; device?: string; error?: string }; active_job?: ApiJob };

function outputFromJob(job: ApiJob): OutputItem {
  const runtime = Number(job.runtime_seconds || 0);
  const sizeBytes = Number(job.size_bytes || 0);
  return {
    id: String(job.id),
    name: String(job.filename),
    src: `${MEDIA_BASE || API_BASE}${String(job.output_url)}`,
    download: `${MEDIA_BASE || API_BASE}${String(job.output_url)}?download=1`,
    poster: job.poster_url ? `${MEDIA_BASE || API_BASE}${String(job.poster_url)}` : undefined,
    meta: `${job.width} × ${job.height} · ${job.frames} frames · ${job.fps} FPS`,
    runtime: runtime > 0 ? `${runtime} sec` : "Completed",
    size: `${Math.max(0.1, sizeBytes / 1024 / 1024).toFixed(1)} MB`,
  };
}

type TabKey = "create" | "assets" | "outputs" | "environment";
type Locale = "zh-TW" | "en" | "ja";
// Browser traffic stays same-origin. Only the server knows the worker address.
const API_BASE = "";
const MEDIA_BASE = "";

const translations = {
  "zh-TW": {
    topStrip: "本機生成 · 檔案保留在此裝置 · NVIDIA GB10",
    console: "GB10 控制台", createTab: "生成", assetsTab: "素材", outputsTab: "產出", environmentTab: "環境",
    ready: "已就緒", connecting: "連線中", generating: "生成中", complete: "已完成", failed: "失敗", offline: "離線",
    createEyebrow: "01 / 生成", createTitle: "新影片生成", createNote: "提示詞、模型、影像規格與運算策略集中在同一個工作區；設定會即時反映到本機執行命令。",
    outputPreview: "產出預覽", verifiedOutput: "已驗證產出", runtime: "執行時間", precision: "運算精度", attention: "注意力機制",
    generationSettings: "生成設定", reset: "重設", width: "寬度", height: "高度", frames: "影格數", videoDuration: "影片長度", frameRate: "影格率", inferenceSteps: "推論步數", cfgScale: "CFG 強度", seed: "隨機種子",
    seconds: "秒", actual: "實際", estimatedInference: "預估推論",
    upscaler: "x2 空間放大", upscalerNote: "二階段空間放大，提升最終解析度。", offload: "CPU 卸載", offloadNote: "記憶體吃緊時卸載部分權重。", tiling: "VAE 分塊解碼", tilingNote: "分塊解碼以降低尖峰記憶體。", audio: "音訊生成", audioNote: "同時產生 AAC 聲音軌。",
    promptAndModel: "提示詞與模型", prompt: "提示詞", negativePrompt: "負面提示詞", characters: "字元", model: "模型", mode: "生成模式",
    cinematic: "電影感", portrait: "人像", product: "產品", t2v: "文字生成影片", i2v: "圖片生成影片", v2v: "影片轉影片",
    chooseAsset: "請從素材庫選擇參照素材", openAssetLibrary: "開啟素材庫", duration: "長度", canvas: "畫布", localEngine: "本機引擎", engineConnected: "LTX-2.3 推論服務已連線", engineWaiting: "正在等待本機推論服務",
    generationFailed: "生成失敗", generateVideo: "生成影片", generatingVideo: "影片生成中…", generateNote: "會真正呼叫本機 LTX-2.3 Distilled；一次只執行一個 GPU 任務，完成後自動更新預覽。", commandPreview: "命令預覽",
    assetsEyebrow: "02 / 素材", assetsTitle: "參照素材與來源", assetsNote: "集中檢視影像、影片、模型與設定檔的來源；所有素材都保留在本機。", mediaReferences: "媒體參照 · 4 個檔案", openFolder: "開啟資料夾", video: "影片", image: "圖片", previewFrame: "PNG 預覽影格", modelSources: "模型來源", sourcePolicy: "來源與隱私", sourcePolicyNote: "所有輸入與產出留在本機。介面只引用已建立的媒體副本，不會自動上傳外部服務。",
    primaryTransformer: "主要擴散 Transformer", promptEncoder: "提示詞增強編碼器", detailRecovery: "第二階段細節恢復",
    outputsEyebrow: "03 / 產出", outputsTitle: "產出預覽與紀錄", outputsNote: "新的生成結果會自動加入這裡；可直接播放或切回生成頁作為主預覽。", runPassed: "已完成", useAsPreview: "設為主預覽", fileSize: "檔案大小", codec: "編碼", workflowConnected: "本機輸出工作流已連接", workflowNote: "模型載入、推論、VAE 解碼、空間放大、音訊與 MP4 封裝均會反映在這個頁面。", outputCount: "個產出",
    envEyebrow: "04 / 環境", envTitle: "裝置與執行環境", envNote: "以下資料來自本機實測環境，用來判斷 LTX-2 / LTX-2.3 的可執行性、記憶體餘裕與相容性。", accelerator: "加速器", unifiedMemory: "統一記憶體", peakResident: "尖峰佔用", architecture: "系統架構", runtimeStack: "執行環境", measuredPerformance: "實測效能", performanceNote: "結果取自 LTX-2.3 22B Distilled 1.1、BF16、SDPA 與 x2 空間放大。實際時間會依提示詞、幀數與背景程序變化。", localPaths: "本機路徑與檔案", currentCommand: "目前命令", compatibility: "相容性說明", compatibilityNote: "GB10 的統一記憶體足以在目前配置執行 LTX-2.3；BF16 + SDPA 是這台裝置上已驗證的穩定組合。",
    repository: "程式庫", launcher: "啟動腳本", guide: "說明文件", mainOutput: "主要產出", smokeTest: "快速測試", swap: "交換空間", output: "輸出",
    frameUnit: "影格", completedValue: "已完成", secondAbbr: "秒", restoredMessage: "已載入最近一次本機生成結果。", sendingMessage: "正在送出本機生成任務…", inferenceMessage: "LTX-2.3 正在執行推論。", completedMessage: "影片已完成並載入左側預覽，也可在產出頁簽播放。", cannotCreate: "無法建立生成任務。", cannotRead: "無法讀取任務狀態。", cannotConnect: "無法連接本機生成服務。",
    footerLeft: "LTX Studio UI/UX · 本機優先工作流", footerRight: "為 NVIDIA GB10 上的 LTX-2.3 設計",
  },
  en: {
    topStrip: "Local generation · Files stay on this device · NVIDIA GB10",
    console: "GB10 Console", createTab: "CREATE", assetsTab: "ASSETS", outputsTab: "OUTPUTS", environmentTab: "ENVIRONMENT",
    ready: "READY", connecting: "CONNECTING", generating: "GENERATING", complete: "COMPLETE", failed: "FAILED", offline: "OFFLINE",
    createEyebrow: "01 / Create", createTitle: "Create a new video", createNote: "Prompts, models, image specifications, and runtime strategy live in one workspace and update the local command instantly.",
    outputPreview: "Output preview", verifiedOutput: "Verified output", runtime: "Runtime", precision: "Precision", attention: "Attention",
    generationSettings: "Generation settings", reset: "Reset", width: "Width", height: "Height", frames: "Frames", videoDuration: "Video duration", frameRate: "Frame rate", inferenceSteps: "Inference steps", cfgScale: "CFG scale", seed: "Seed",
    seconds: "seconds", actual: "Actual", estimatedInference: "Estimated inference",
    upscaler: "x2 Spatial Upscaler", upscalerNote: "Second-stage spatial upscaling for final detail.", offload: "CPU Offload", offloadNote: "Move weights to CPU when memory is constrained.", tiling: "VAE Decode Tiling", tilingNote: "Decode in tiles to reduce peak memory.", audio: "Audio Generation", audioNote: "Generate an AAC audio track with the video.",
    promptAndModel: "Prompt & model", prompt: "Prompt", negativePrompt: "Negative prompt", characters: "characters", model: "Model", mode: "Mode",
    cinematic: "Cinematic", portrait: "Portrait", product: "Product", t2v: "Text to Video", i2v: "Image to Video", v2v: "Video to Video",
    chooseAsset: "Choose a reference from Assets", openAssetLibrary: "Open asset library", duration: "Duration", canvas: "Canvas", localEngine: "Local engine", engineConnected: "LTX-2.3 inference service connected", engineWaiting: "Waiting for local inference service",
    generationFailed: "Generation failed", generateVideo: "Generate video", generatingVideo: "Generating video…", generateNote: "Calls the local LTX-2.3 Distilled model. One GPU job runs at a time and the preview updates automatically.", commandPreview: "Command preview",
    assetsEyebrow: "02 / Assets", assetsTitle: "References & sources", assetsNote: "Review image, video, model, and configuration sources. Every asset remains on this device.", mediaReferences: "Media references · 4 files", openFolder: "Open folder", video: "Video", image: "Image", previewFrame: "PNG preview frame", modelSources: "Model sources", sourcePolicy: "Source & privacy", sourcePolicyNote: "All inputs and outputs remain local. The interface references local media copies and never uploads them automatically.",
    primaryTransformer: "Primary diffusion transformer", promptEncoder: "Prompt enhancement encoder", detailRecovery: "Second-pass detail recovery",
    outputsEyebrow: "03 / Outputs", outputsTitle: "Output previews & history", outputsNote: "New generations appear here automatically. Play them directly or set one as the main preview.", runPassed: "Passed", useAsPreview: "Use as preview", fileSize: "File size", codec: "Codec", workflowConnected: "Local output workflow connected", workflowNote: "Model loading, inference, VAE decoding, upscaling, audio, and MP4 packaging all appear in this workspace.", outputCount: "outputs",
    envEyebrow: "04 / Environment", envTitle: "Device & runtime", envNote: "Measured local data for evaluating LTX-2 / LTX-2.3 compatibility, memory headroom, and performance.", accelerator: "Accelerator", unifiedMemory: "Unified memory", peakResident: "Peak resident", architecture: "Architecture", runtimeStack: "Runtime stack", measuredPerformance: "Measured performance", performanceNote: "Measured with LTX-2.3 22B Distilled 1.1, BF16, SDPA, and x2 spatial upscaling. Runtime varies with prompt, frame count, and background processes.", localPaths: "Local paths & files", currentCommand: "Current command", compatibility: "Compatibility note", compatibilityNote: "GB10 unified memory is sufficient for this LTX-2.3 configuration; BF16 + SDPA is the verified stable combination.",
    repository: "Repository", launcher: "Launcher", guide: "Guide", mainOutput: "Main output", smokeTest: "Smoke test", swap: "Swap", output: "Output",
    frameUnit: "frames", completedValue: "Completed", secondAbbr: "sec", restoredMessage: "The latest local output has been restored.", sendingMessage: "Submitting a local generation job…", inferenceMessage: "LTX-2.3 is running inference.", completedMessage: "Video complete and loaded in the main preview. It is also available in Outputs.", cannotCreate: "Could not create the generation job.", cannotRead: "Could not read the job status.", cannotConnect: "Could not connect to the local generation service.",
    footerLeft: "LTX Studio UI/UX · local-first workflow", footerRight: "Designed for LTX-2.3 on NVIDIA GB10",
  },
  ja: {
    topStrip: "ローカル生成 · ファイルはこのデバイスに保存 · NVIDIA GB10",
    console: "GB10 コンソール", createTab: "生成", assetsTab: "素材", outputsTab: "出力", environmentTab: "環境",
    ready: "準備完了", connecting: "接続中", generating: "生成中", complete: "完了", failed: "失敗", offline: "オフライン",
    createEyebrow: "01 / 生成", createTitle: "新しい動画を生成", createNote: "プロンプト、モデル、映像仕様、実行戦略を一つのワークスペースで管理し、ローカルコマンドへ即時反映します。",
    outputPreview: "出力プレビュー", verifiedOutput: "検証済み出力", runtime: "実行時間", precision: "演算精度", attention: "Attention",
    generationSettings: "生成設定", reset: "リセット", width: "幅", height: "高さ", frames: "フレーム数", videoDuration: "動画の長さ", frameRate: "フレームレート", inferenceSteps: "推論ステップ", cfgScale: "CFG スケール", seed: "シード",
    seconds: "秒", actual: "実際", estimatedInference: "推論目安",
    upscaler: "x2 空間アップスケーラー", upscalerNote: "第2段階で解像度と細部を向上します。", offload: "CPU オフロード", offloadNote: "メモリ不足時に一部の重みをCPUへ移します。", tiling: "VAE タイルデコード", tilingNote: "分割デコードでピークメモリを抑えます。", audio: "音声生成", audioNote: "AAC音声トラックを同時生成します。",
    promptAndModel: "プロンプトとモデル", prompt: "プロンプト", negativePrompt: "ネガティブプロンプト", characters: "文字", model: "モデル", mode: "生成モード",
    cinematic: "シネマティック", portrait: "ポートレート", product: "プロダクト", t2v: "テキストから動画", i2v: "画像から動画", v2v: "動画から動画",
    chooseAsset: "素材から参照ファイルを選択", openAssetLibrary: "素材ライブラリを開く", duration: "長さ", canvas: "キャンバス", localEngine: "ローカルエンジン", engineConnected: "LTX-2.3 推論サービス接続済み", engineWaiting: "ローカル推論サービスを待機中",
    generationFailed: "生成に失敗", generateVideo: "動画を生成", generatingVideo: "動画を生成中…", generateNote: "ローカルの LTX-2.3 Distilled を実行します。GPUジョブは一度に1件で、完了後プレビューを自動更新します。", commandPreview: "コマンドプレビュー",
    assetsEyebrow: "02 / 素材", assetsTitle: "参照素材とソース", assetsNote: "画像、動画、モデル、設定ファイルのソースを確認できます。すべての素材はローカルに保存されます。", mediaReferences: "メディア参照 · 4ファイル", openFolder: "フォルダを開く", video: "動画", image: "画像", previewFrame: "PNG プレビューフレーム", modelSources: "モデルソース", sourcePolicy: "ソースとプライバシー", sourcePolicyNote: "入力と出力はすべてローカルに保持され、外部サービスへ自動アップロードされません。",
    primaryTransformer: "メイン拡散 Transformer", promptEncoder: "プロンプト拡張エンコーダー", detailRecovery: "第2段階のディテール復元",
    outputsEyebrow: "03 / 出力", outputsTitle: "出力プレビューと履歴", outputsNote: "新しい生成結果は自動的に追加され、直接再生したりメインプレビューに設定できます。", runPassed: "完了", useAsPreview: "メイン表示に設定", fileSize: "ファイルサイズ", codec: "コーデック", workflowConnected: "ローカル出力ワークフロー接続済み", workflowNote: "モデル読込、推論、VAEデコード、アップスケール、音声、MP4出力がこの画面に反映されます。", outputCount: "件の出力",
    envEyebrow: "04 / 環境", envTitle: "デバイスと実行環境", envNote: "LTX-2 / LTX-2.3 の互換性、メモリ余裕、性能を判断するためのローカル実測データです。", accelerator: "アクセラレーター", unifiedMemory: "統合メモリ", peakResident: "ピーク使用量", architecture: "アーキテクチャ", runtimeStack: "ランタイム構成", measuredPerformance: "実測パフォーマンス", performanceNote: "LTX-2.3 22B Distilled 1.1、BF16、SDPA、x2空間アップスケールで計測。時間はプロンプト、フレーム数、バックグラウンド処理で変動します。", localPaths: "ローカルパスとファイル", currentCommand: "現在のコマンド", compatibility: "互換性メモ", compatibilityNote: "GB10の統合メモリは現在のLTX-2.3構成に十分です。BF16 + SDPA は検証済みの安定した組み合わせです。",
    repository: "リポジトリ", launcher: "起動スクリプト", guide: "ガイド", mainOutput: "メイン出力", smokeTest: "スモークテスト", swap: "スワップ", output: "出力",
    frameUnit: "フレーム", completedValue: "完了", secondAbbr: "秒", restoredMessage: "最新のローカル生成結果を復元しました。", sendingMessage: "ローカル生成ジョブを送信中…", inferenceMessage: "LTX-2.3 が推論を実行中です。", completedMessage: "動画が完成し、メインプレビューに読み込まれました。出力タブでも再生できます。", cannotCreate: "生成ジョブを作成できませんでした。", cannotRead: "ジョブ状態を取得できませんでした。", cannotConnect: "ローカル生成サービスに接続できませんでした。",
    footerLeft: "LTX Studio UI/UX · ローカルファースト", footerRight: "NVIDIA GB10 上の LTX-2.3 向け",
  },
} as const;

function SectionTitle({ eyebrow, title, note }: { eyebrow: string; title: string; note: string }) {
  return (
    <div className="mb-8 flex flex-col justify-between gap-3 md:flex-row md:items-end">
      <div>
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.25em] text-[#e85578]">{eyebrow}</p>
        <h1 className="text-3xl font-extrabold tracking-[0.07em] md:text-4xl">{title}</h1>
      </div>
      <p className="max-w-lg text-sm leading-6 text-muted-foreground">{note}</p>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <span className="mb-2 block text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{children}</span>;
}

function ToggleRow({ label, note, checked, onChange, disabled }: { label: string; note: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-4 last:border-b-0">
      <div><p className="text-xs font-bold">{label}</p><p className="mt-1 text-[10px] leading-4 text-muted-foreground">{note}</p></div>
      <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} />
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-border bg-white p-5">
      <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
      <p className={`mt-2 text-xl font-extrabold tracking-tight ${accent ? "text-[#159c8f]" : ""}`}>{value}</p>
    </div>
  );
}

export default function Home() {
  return <AccountGate><Studio /></AccountGate>;
}

function Studio() {
  const [locale, setLocale] = useState<Locale>("zh-TW");
  const [tab, setTab] = useState<TabKey>("create");
  const [prompt, setPrompt] = useState(initialPrompt);
  const [model, setModel] = useState("ltx23-distilled");
  const [models, setModels] = useState<InstalledModel[]>([]);
  const [catalogError, setCatalogError] = useState(false);
  const [mode, setMode] = useState("t2v");
  const [width, setWidth] = useState(768);
  const [height, setHeight] = useState(512);
  const [frames, setFrames] = useState(49);
  const [fps, setFps] = useState("24");
  const [seed, setSeed] = useState(42);
  const precision = "bf16";
  const attention = "sdpa";
  const [upscaler, setUpscaler] = useState(true);
  const [offload, setOffload] = useState(false);
  const [tiling, setTiling] = useState(true);
  const [audio, setAudio] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [jobStatus, setJobStatus] = useState("READY");
  const [selectedOutput, setSelectedOutput] = useState<OutputItem>(emptyOutput);
  const [liveOutputs, setLiveOutputs] = useState<OutputItem[]>(outputItems);
  const [backendOnline, setBackendOnline] = useState(false);
  const [jobMessage, setJobMessage] = useState("");
  const [jobError, setJobError] = useState("");
  const [reference, setReference] = useState<Asset | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [computeDevice, setComputeDevice] = useState("");
  const transfer = fileCopy[locale];
  const ui = translations[locale];
  const visibleStatus = generating
    ? ui.generating
    : jobStatus === "COMPLETE" ? ui.complete
      : jobStatus === "FAILED" ? ui.failed
        : jobStatus === "OFFLINE" ? ui.offline
          : jobStatus === "CONNECTING" ? ui.connecting
            : backendOnline ? ui.ready : ui.offline;
  const formatMeta = (value: string) => value.replace("frames", ui.frameUnit);
  const formatRuntime = (value: string) => value === "Completed" ? ui.completedValue : value.replace("sec", ui.secondAbbr);

  const duration = useMemo(() => (frames / Number(fps)).toFixed(2), [frames, fps]);
  const durationPreset = String(Math.max(2, Math.min(10, Math.round(frames / Number(fps) / 2) * 2)));
  const setDurationSeconds = (seconds: string) => {
    const targetFrames = Math.round((Number(seconds) * Number(fps)) / 8) * 8 + 1;
    setFrames(Math.min(257, targetFrames));
  };
  const setFrameRateKeepingDuration = (nextFps: string) => {
    const seconds = frames / Number(fps);
    setFps(nextFps);
    setFrames(Math.min(257, Math.round((seconds * Number(nextFps)) / 8) * 8 + 1));
  };
  const command = useMemo(
    () => `LTX_WIDTH=${width} LTX_HEIGHT=${height} LTX_FRAMES=${frames} LTX_FPS=${fps} LTX_SEED=${seed} LTX_AUDIO=${audio ? 1 : 0}${offload ? " LTX_OFFLOAD=cpu" : ""}${mode === "i2v" && reference ? ` LTX_IMAGE="uploads/${reference.id}…"` : ""} ./scripts/run-ltx-2.3.sh "${prompt.slice(0, 42)}${prompt.length > 42 ? "…" : ""}" output.mp4`,
    [prompt, width, height, frames, fps, seed, offload, audio, mode, reference]
  );

  useEffect(() => {
    const savedLocale = window.localStorage.getItem("ltx-studio-locale");
    // eslint-disable-next-line react/react-compiler -- Read the browser-only saved preference after hydration.
    if (savedLocale === "zh-TW" || savedLocale === "en" || savedLocale === "ja") setLocale(savedLocale);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("ltx-studio-locale", locale);
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const abort = new AbortController();
    serviceFetch("/api/models", { signal: abort.signal }).then(async (response) => {
      if (!response.ok) throw new Error();
      return response.json() as Promise<{ models: InstalledModel[] }>;
    }).then((data) => { setModels(data.models); setCatalogError(false); })
      .catch(() => { if (!abort.signal.aborted) setCatalogError(true); });
    return () => abort.abort();
  }, []);

  useEffect(() => {
    let active = true;
    const checkHealth = () => serviceFetch(`${API_BASE}/api/health`)
      .then((response) => response.json() as Promise<Health>)
      .then((data) => {
        if (!active) return;
        setBackendOnline(Boolean(data.ok));
        setComputeDevice(data.runtime?.cuda_available ? data.runtime.device || "" : "");
        if (data.runtime?.error) setJobError(data.runtime.error);
        if (data.active_job && (!data.active_job.model || data.active_job.model === "ltx23-distilled")) {
          setActiveJobId(data.active_job.id);
          setGenerating(true);
        }
      })
      .catch(() => { if (active) setBackendOnline(false); });
    const loadGeneratedOutputs = () => serviceFetch(`${API_BASE}/api/outputs`)
      .then((response) => response.json() as Promise<{ outputs?: ApiJob[] }>)
      .then((data) => {
        if (!active || !Array.isArray(data.outputs) || data.outputs.length === 0) return;
        const restored = data.outputs.filter((job) => !job.media_type || job.media_type === "video").map(outputFromJob);
        if (!restored.length) return;
        setLiveOutputs([...restored, ...outputItems]);
        setSelectedOutput(restored[0]);
      })
      .catch(() => undefined);
    void checkHealth();
    void loadGeneratedOutputs();
    const timer = window.setInterval(checkHealth, 5000);
    const restoreTimer = window.setTimeout(loadGeneratedOutputs, 2500);
    return () => { active = false; window.clearInterval(timer); window.clearTimeout(restoreTimer); };
  }, [ui.restoredMessage]);

  useEffect(() => {
    if (!activeJobId) return;
    let stopped = false;
    let pending = false;
    const poll = async () => {
      if (pending) return;
      pending = true;
      try {
        const response = await serviceFetch(`${API_BASE}/api/jobs/${activeJobId}`);
        const job = await response.json() as ApiJob;
        if (stopped) return;
        if (!response.ok) {
          if (response.status === 404) { setActiveJobId(null); setGenerating(false); }
          throw new Error(job.error || ui.cannotRead);
        }
        setJobError("");
        setProgress(job.progress ?? 0);
        setElapsed(job.elapsed_seconds || job.runtime_seconds || 0);
        setJobMessage(job.message || ui.inferenceMessage);
        if (["succeeded", "failed", "cancelled", "interrupted"].includes(job.status)) {
          setActiveJobId(null);
          setGenerating(false);
          setJobStatus(job.status === "succeeded" ? "COMPLETE" : "FAILED");
          if (job.status === "succeeded") {
            const generated = outputFromJob(job);
            setLiveOutputs((current) => [generated, ...current.filter((item) => item.id !== generated.id)]);
            setSelectedOutput(generated);
            setJobMessage(ui.completedMessage);
          } else setJobError(job.message || ui.cannotRead);
        }
      } catch (error) {
        if (!stopped) setJobError(error instanceof Error ? error.message : ui.cannotConnect);
        // A temporary network failure must not abandon the GPU job.
      } finally { pending = false; }
    };
    void poll();
    const timer = window.setInterval(poll, 3000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [activeJobId, ui.cannotRead, ui.inferenceMessage, ui.completedMessage, ui.cannotConnect]);

  const simulateGeneration = async () => {
    if (generating) return;
    setJobError("");
    setJobMessage(ui.sendingMessage);
    setGenerating(true);
    setJobStatus("CONNECTING");
    setProgress(1);
    setElapsed(0);
    try {
      const response = await serviceFetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, model, mode, width, height, frames, fps: Number(fps), seed, offload, audio, image_id: mode === "i2v" ? reference?.id : undefined }),
      });
      const created = await response.json() as ApiJob;
      if (!response.ok) throw new Error(created.error || ui.cannotCreate);
      setBackendOnline(true);
      setJobStatus("GENERATING");
      setProgress(created.progress || 3);
      setJobMessage(created.message || ui.inferenceMessage);

      setActiveJobId(created.id);
    } catch (error) {
      setGenerating(false);
      setJobStatus("FAILED");
      setProgress(0);
      setJobError(error instanceof Error ? error.message : ui.cannotConnect);
    }
  };

  const navItems: [TabKey, string][] = [["create", ui.createTab], ["assets", ui.assetsTab], ["outputs", ui.outputsTab], ["environment", ui.environmentTab]];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="border-b border-border bg-[#f7f7f5] px-5 py-2 text-center text-[9px] font-semibold tracking-[0.16em] text-muted-foreground sm:text-[10px]">{ui.topStrip}</div>

      <header className="sticky top-0 z-30 border-b border-border bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1560px] items-center justify-between gap-5 px-5 py-4 lg:px-10 lg:py-5">
          <button onClick={() => setTab("create")} className="flex items-center gap-3 text-left">
            <span className="grid size-10 place-items-center rounded-full bg-foreground text-background"><Video className="size-4" /></span>
            <div><p className="text-[15px] font-extrabold tracking-[0.13em] sm:text-[17px]">LTX LOCAL STUDIO</p><p className="text-[8px] font-semibold tracking-[0.2em] text-muted-foreground sm:text-[9px]">{ui.console}</p></div>
          </button>
          <Tabs value={tab} onValueChange={(value) => setTab(value as TabKey)} className="hidden lg:block">
            <TabsList variant="line" className="h-auto gap-8 bg-transparent p-0">
              {navItems.map(([value, label]) => <TabsTrigger key={value} value={value} className="h-12 rounded-none px-1 text-[11px] font-bold tracking-[0.2em] data-[state=active]:after:bg-[#ff6f91]">{label}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          <div className="flex items-center gap-4">
            <Select value={locale} onValueChange={(value) => setLocale(value as Locale)}>
              <SelectTrigger aria-label="Language" className="h-10 w-[132px] rounded-none border-border bg-white text-[10px] font-bold tracking-[0.1em]"><SelectValue /></SelectTrigger>
              <SelectContent align="end" className="min-w-[150px]"><SelectItem value="zh-TW">繁體中文</SelectItem><SelectItem value="en">English</SelectItem><SelectItem value="ja">日本語</SelectItem></SelectContent>
            </Select>
            <AccountMenu locale={locale} />
            <div className="hidden items-center gap-2 text-[10px] font-bold tracking-[0.1em] sm:flex"><span className={`size-2 rounded-full ${generating ? "animate-pulse bg-[#ff6f91]" : backendOnline ? "bg-[#25b6a6]" : "bg-[#b8b8b2]"} shadow-[0_0_0_4px_rgba(37,182,166,.12)]`} />{visibleStatus}</div>
          </div>
        </div>
        <nav className="overflow-x-auto border-t border-border lg:hidden">
          <div className="flex min-w-max px-5">{navItems.map(([value, label]) => <button key={value} onClick={() => setTab(value)} className={`relative px-4 py-3 text-[10px] font-bold tracking-[0.18em] ${tab === value ? "text-foreground after:absolute after:inset-x-4 after:bottom-0 after:h-0.5 after:bg-[#ff6f91]" : "text-muted-foreground"}`}>{label}</button>)}</div>
        </nav>
      </header>

      <div className="mx-auto max-w-[1560px] px-5 py-8 lg:px-10 lg:py-10">
        {tab === "create" && <section className="mb-6 flex flex-wrap items-center gap-4 border border-border bg-white p-5">
          <label className="min-w-64 text-xs font-bold">{ui.model}
            <Select value={model} disabled={generating || !models.length} onValueChange={(value) => value && setModel(value)}><SelectTrigger className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent>{models.map((item) => <SelectItem key={item.id} value={item.id}>{item.label} · {item.media_type}</SelectItem>)}</SelectContent></Select>
          </label>
          <p className="text-xs text-muted-foreground">{catalogError ? (locale === "zh-TW" ? "無法讀取模型清單，請檢查服務後重新整理。" : locale === "en" ? "Model catalog unavailable. Check the service and reload." : "モデル一覧を取得できません。接続を確認して再読込してください。") : (locale === "zh-TW" ? "僅顯示主機已安裝並註冊的模型 · 帳號與 API 不隨模型更換" : locale === "en" ? "Installed host adapters only · Same account and API across models" : "導入・登録済みモデルのみ表示 · アカウントとAPIは共通")}</p>
        </section>}
        {tab === "create" && model !== "ltx23-distilled" && models.find((item) => item.id === model) && <ModelComposer key={model} model={models.find((item) => item.id === model)!} locale={locale} />}
        {tab === "create" && model === "ltx23-distilled" && (
          <section>
            <SectionTitle eyebrow={ui.createEyebrow} title={ui.createTitle} note={ui.createNote} />
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(400px,.82fr)]">
              <div className="space-y-6">
                <section className="overflow-hidden border border-border bg-[#101211] text-white">
                  <div className="flex items-center justify-between gap-4 border-b border-white/15 px-5 py-4">
                    <div className="flex flex-wrap items-center gap-3"><span className="text-[10px] font-bold tracking-[0.18em]">{ui.outputPreview}</span><span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] text-white/65">{formatMeta(selectedOutput.meta)}</span></div>
                    <span className="hidden text-[10px] text-white/50 sm:block">{selectedOutput.name}</span>
                  </div>
                  <div className="relative aspect-video bg-black">
                    {selectedOutput.src ? <><video key={selectedOutput.src} className="h-full w-full object-contain" controls preload="metadata" poster={selectedOutput.poster || undefined} src={selectedOutput.src} /><span className="pointer-events-none absolute left-4 top-4 rounded-full bg-[#25b6a6] px-3 py-1 text-[9px] font-bold tracking-[0.14em] text-white">{ui.outputPreview}</span></> : <div className="grid h-full place-items-center text-center text-white/50"><div><Video className="mx-auto mb-4 size-8" /><p className="text-xs">{locale === "zh-TW" ? "你的第一支作品將顯示在這裡" : locale === "en" ? "Your first creation will appear here" : "最初の作品がここに表示されます"}</p></div></div>}
                  </div>
                  <div className="grid grid-cols-3 divide-x divide-white/10 border-t border-white/10 bg-white/[.035] text-xs">
                    <div className="px-5 py-4"><span className="block text-[9px] tracking-[0.14em] text-white/45">{ui.runtime}</span><strong className="mt-1 block">{formatRuntime(selectedOutput.runtime)}</strong></div>
                    <div className="px-5 py-4"><span className="block text-[9px] tracking-[0.14em] text-white/45">{ui.precision}</span><strong className="mt-1 block">{precision.toUpperCase()}</strong></div>
                    <div className="px-5 py-4"><span className="block text-[9px] tracking-[0.14em] text-white/45">{ui.attention}</span><strong className="mt-1 block">{attention.toUpperCase()}</strong></div>
                  </div>
                </section>

                <section className="border border-border bg-white">
                  <div className="flex items-center justify-between border-b border-border px-5 py-4"><div className="flex items-center gap-2"><Settings2 className="size-4 text-[#e85578]"/><h2 className="text-xs font-extrabold tracking-[0.13em]">{ui.generationSettings}</h2></div><button onClick={() => { setWidth(768); setHeight(512); setFrames(49); setFps("24"); setSeed(42); }} className="flex items-center gap-2 text-[10px] font-bold tracking-[0.1em] text-muted-foreground hover:text-foreground"><RotateCcw className="size-3"/>{ui.reset}</button></div>
                  <div className="grid gap-px bg-border md:grid-cols-2 xl:grid-cols-3">
                    <label className="bg-white p-5"><Label>{ui.width}</Label><Input type="number" value={width} onChange={(e) => setWidth(Number(e.target.value))} className="rounded-none" /></label>
                    <label className="bg-white p-5"><Label>{ui.height}</Label><Input type="number" value={height} onChange={(e) => setHeight(Number(e.target.value))} className="rounded-none" /></label>
                    <label className="bg-white p-5"><Label>{ui.frames}</Label><Input type="number" value={frames} onChange={(e) => setFrames(Number(e.target.value))} className="rounded-none" /></label>
                    <label className="bg-white p-5"><Label>{ui.videoDuration}</Label><Select value={durationPreset} onValueChange={(value) => value && setDurationSeconds(value)}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent>{[2,4,6,8,10].map((value) => <SelectItem key={value} value={String(value)} disabled={value === 10 && Number(fps) === 30}>{value} {ui.seconds}</SelectItem>)}</SelectContent></Select><span className="mt-2 block text-[9px] text-muted-foreground">{ui.actual} {duration}s · {transfer.estimated}</span></label>
                    <label className="bg-white p-5"><Label>{ui.frameRate}</Label><Select value={fps} onValueChange={(value) => value && setFrameRateKeepingDuration(value)}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="16">16 FPS</SelectItem><SelectItem value="24">24 FPS</SelectItem><SelectItem value="30">30 FPS</SelectItem></SelectContent></Select></label>
                    <label className="bg-white p-5"><Label>{ui.inferenceSteps}</Label><Input value="8 + 3" disabled className="rounded-none" /></label>
                    <label className="bg-white p-5"><Label>{ui.cfgScale}</Label><Input value="—" disabled className="rounded-none" /></label>
                    <label className="bg-white p-5"><Label>{ui.seed}</Label><Input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} className="rounded-none" /></label>
                    <label className="bg-white p-5"><Label>{ui.precision}</Label><Select value={precision} disabled><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="bf16">BF16</SelectItem></SelectContent></Select></label>
                    <label className="bg-white p-5"><Label>{ui.attention}</Label><Select value={attention} disabled><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="sdpa">SDPA</SelectItem></SelectContent></Select></label>
                  </div>
                  <div className="grid gap-x-8 px-5 md:grid-cols-2">
                    <ToggleRow label={ui.upscaler} note={ui.upscalerNote} checked={upscaler} onChange={setUpscaler} disabled />
                    <ToggleRow label={ui.offload} note={ui.offloadNote} checked={offload} onChange={setOffload} />
                    <ToggleRow label={ui.tiling} note={ui.tilingNote} checked={tiling} onChange={setTiling} disabled />
                    <ToggleRow label={ui.audio} note={ui.audioNote} checked={audio} onChange={setAudio} />
                  </div>
                  <div className="border-t border-border p-5"><p className="text-[10px] leading-5 text-muted-foreground">{transfer.fixed}</p><Button variant="outline" className="mt-3 rounded-none text-[10px]" disabled={generating} onClick={() => { setWidth(384); setHeight(256); setFrames(17); setFps("24"); setOffload(false); }}><Zap className="size-3" />{transfer.draft}</Button></div>
                </section>
              </div>

              <aside className="space-y-6 xl:sticky xl:top-[122px] xl:self-start">
                <section className="border border-border bg-card">
                  <div className="border-b border-border px-6 py-5"><div className="flex items-center gap-2"><Sparkles className="size-4 text-[#e85578]"/><h2 className="text-sm font-extrabold tracking-[0.1em]">{ui.promptAndModel}</h2></div></div>
                  <div className="space-y-5 p-6">
                    <div className="flex flex-wrap gap-2">{promptPresets.map(([label, value], index) => <button key={label} onClick={() => setPrompt(value)} className="border border-border px-3 py-2 text-[9px] font-bold tracking-[0.12em] hover:border-[#ff6f91] hover:bg-[#fff5f7]">{[ui.cinematic, ui.portrait, ui.product][index]}</button>)}</div>
                    <label className="block"><Label>{ui.prompt}</Label><Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} className="min-h-40 resize-none rounded-none bg-[#fafaf8] text-sm leading-6 shadow-none focus-visible:ring-[#ff6f91]/25" /><span className="mt-2 block text-right text-[10px] text-muted-foreground">{prompt.length} {ui.characters}</span></label>
                    <label className="block"><Label>{ui.negativePrompt}</Label><Textarea value="—" disabled className="min-h-12 resize-none rounded-none bg-[#fafaf8] text-xs leading-5 shadow-none" /></label>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <label><Label>{ui.model}</Label><Input value="LTX-2.3 Distilled" readOnly className="rounded-none" /></label>
                      <label><Label>{ui.mode}</Label><Select value={mode} onValueChange={(value) => value && setMode(value)}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="t2v">{ui.t2v}</SelectItem><SelectItem value="i2v">{ui.i2v}</SelectItem><SelectItem value="v2v" disabled>{ui.v2v}</SelectItem></SelectContent></Select></label>
                    </div>
                    {mode !== "t2v" && <div className="border border-dashed border-[#b8b8b2] bg-[#fafaf8] p-5 text-center"><ImageIcon className="mx-auto size-5 text-[#25b6a6]"/><p className="mt-2 text-xs font-bold">{ui.chooseAsset}</p><button onClick={() => setTab("assets")} className="mt-2 text-[10px] font-bold text-[#e85578] underline underline-offset-4">{ui.openAssetLibrary}</button></div>}
                    {mode === "i2v" && reference && <div className="border border-[#bfe8e3] p-3"><img src={`${API_BASE}${reference.url}`} alt={reference.name} className="max-h-32 w-full object-contain" /><p className="mt-2 truncate text-[10px]">{transfer.selected}: {reference.name} · frame 0 / 0.8</p><button onClick={() => setReference(null)} className="mt-2 text-[10px] text-[#e85578] underline">{transfer.remove}</button></div>}
                    <div className="grid grid-cols-3 gap-px bg-border text-center"><div className="bg-[#fafaf8] p-3"><p className="text-[9px] text-muted-foreground">{ui.duration}</p><strong className="mt-1 block text-xs">{duration}s</strong></div><div className="bg-[#fafaf8] p-3"><p className="text-[9px] text-muted-foreground">{ui.canvas}</p><strong className="mt-1 block text-xs">{width}×{height}</strong></div><div className="bg-[#fafaf8] p-3"><p className="text-[9px] text-muted-foreground">VRAM</p><strong className="mt-1 block text-xs">~42 GiB</strong></div></div>
                    <div className={`border px-4 py-3 text-[10px] leading-5 ${backendOnline ? "border-[#bfe8e3] bg-[#f0fbf9] text-[#11786f]" : "border-[#e2e2de] bg-[#fafaf8] text-muted-foreground"}`}><span className="font-bold">{ui.localEngine} · </span>{backendOnline ? ui.engineConnected : ui.engineWaiting}</div>
                    {generating || progress > 0 ? <div className="space-y-2"><div className="flex justify-between text-[10px] font-bold tracking-[0.12em]"><span>{visibleStatus}</span><span>{progress}%</span></div><Progress value={progress} className="h-1.5 rounded-none [&>div]:bg-[#25b6a6]" />{jobMessage && <p className="text-[10px] leading-4 text-muted-foreground">{jobMessage}</p>}</div> : null}
                    <p className="text-[10px] leading-5 text-muted-foreground">{transfer.gpu}: {computeDevice || transfer.offline}{generating && <><br />{transfer.stage} · {transfer.elapsed} {Math.round(elapsed)}s</>}</p>
                    {jobError && <div role="alert" className="border border-red-200 bg-red-50 px-4 py-3 text-[10px] leading-5 text-red-700"><strong className="block">{ui.generationFailed}</strong>{jobError}</div>}
                    <Button onClick={simulateGeneration} disabled={generating || !backendOnline || (mode === "i2v" && !reference)} className="h-12 w-full rounded-none bg-foreground text-[11px] font-bold tracking-[0.16em] text-background hover:bg-[#e85578]"><Play className="size-3.5 fill-current"/>{generating ? ui.generatingVideo : ui.generateVideo}</Button>
                    {selectedOutput.src && <a href={selectedOutput.download || selectedOutput.src} download={selectedOutput.name} className="block border border-border p-3 text-center text-[11px] font-bold hover:border-[#e85578]">{transfer.download} · MP4</a>}
                    <p className="text-center text-[9px] leading-4 text-muted-foreground">{ui.generateNote}</p>
                  </div>
                </section>
                <section className="border border-border bg-[#171918] p-5 text-white"><div className="mb-3 flex items-center gap-2 text-[10px] font-bold tracking-[0.14em] text-white/65"><TerminalSquare className="size-4 text-[#25b6a6]"/>{ui.commandPreview}</div><code className="block break-words font-mono text-[10px] leading-5 text-white/75">{command}</code></section>
              </aside>
            </div>
          </section>
        )}

        {tab === "assets" && (
          <section>
            <SectionTitle eyebrow={ui.assetsEyebrow} title={ui.assetsTitle} note={ui.assetsNote} />
            <MediaLibrary locale={locale} onSelect={(asset) => { setReference(asset); setMode("i2v"); setTab("create"); }} />
            <div className="grid gap-6 lg:grid-cols-[1.35fr_.65fr]">
              <div>
                <div className="mb-4 flex items-center justify-between"><p className="text-[10px] font-bold tracking-[0.15em]">{ui.mediaReferences}</p><Button variant="outline" className="rounded-none text-[10px] font-bold tracking-[0.12em]"><FolderOpen className="size-3.5"/>{ui.openFolder}</Button></div>
                <div className="grid gap-px bg-border sm:grid-cols-2">
                  {outputItems.flatMap((item) => [
                    { id: `${item.id}-video`, type: ui.video, isVideo: true, name: item.name, src: item.poster!, meta: item.meta, path: `outputs/${item.name}` },
                    { id: `${item.id}-image`, type: ui.image, isVideo: false, name: item.poster!.split("/").pop()!, src: item.poster!, meta: ui.previewFrame, path: `outputs/${item.poster!.split("/").pop()}` },
                  ]).map((asset) => (
                    <article key={asset.id} className="group bg-white p-5">
                      <div className="relative aspect-video overflow-hidden bg-[#111]"><img src={asset.src} alt={asset.name} className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"/><span className="absolute left-3 top-3 bg-white px-2 py-1 text-[9px] font-extrabold tracking-[0.15em]">{asset.type}</span></div>
                      <div className="mt-4 flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-xs font-bold">{asset.name}</p><p className="mt-1 text-[10px] text-muted-foreground">{asset.meta}</p><code className="mt-2 block truncate text-[9px] text-[#159c8f]">{asset.path}</code></div>{asset.isVideo ? <FileVideo className="size-4 shrink-0 text-[#e85578]"/> : <FileImage className="size-4 shrink-0 text-[#25b6a6]"/>}</div>
                    </article>
                  ))}
                </div>
              </div>
              <aside className="space-y-6">
                <section className="border border-border bg-white"><div className="border-b border-border px-5 py-4"><h2 className="text-xs font-extrabold tracking-[0.13em]">{ui.modelSources}</h2></div><div className="divide-y divide-border">
                  {[
                    ["LTX-2.3 22B Distilled 1.1", "Hugging Face · Lightricks/LTX-2.3", ui.primaryTransformer],
                    ["Gemma 3 12B", "Hugging Face · google/gemma-3-12b-it", ui.promptEncoder],
                    ["x2 Spatial Upscaler", "LTX model package", ui.detailRecovery],
                  ].map(([name, source, note]) => <div key={name} className="p-5"><div className="flex gap-3"><Box className="mt-0.5 size-4 shrink-0 text-[#e85578]"/><div><p className="text-xs font-bold">{name}</p><p className="mt-1 text-[10px] text-muted-foreground">{source}</p><p className="mt-2 text-[10px] leading-4 text-[#159c8f]">{note}</p></div></div></div>)}
                </div></section>
                <section className="border border-border bg-[#f7f7f4] p-5"><div className="flex gap-3"><HardDrive className="size-4 text-[#25b6a6]"/><div><p className="text-xs font-bold">{ui.sourcePolicy}</p><p className="mt-2 text-[10px] leading-5 text-muted-foreground">{ui.sourcePolicyNote}</p></div></div></section>
              </aside>
            </div>
          </section>
        )}

        {tab === "outputs" && (
          <section>
            <SectionTitle eyebrow={ui.outputsEyebrow} title={ui.outputsTitle} note={ui.outputsNote} />
            <div className="grid gap-6 xl:grid-cols-2">
              {liveOutputs.map((item, index) => (
                <article key={item.id} className="overflow-hidden border border-border bg-white">
                  <a href={item.download || item.src} download={item.name} className="block border-b border-border px-6 py-3 text-right text-[11px] font-bold hover:text-[#e85578]">{transfer.download} · MP4</a>
                  <div className="relative aspect-video bg-black"><video className="h-full w-full object-contain" controls preload="metadata" poster={item.poster || undefined} src={item.src}/><span className="absolute left-4 top-4 bg-[#25b6a6] px-3 py-1 text-[9px] font-bold tracking-[0.12em] text-white">RUN 0{index + 1} · {ui.runPassed}</span></div>
                  <div className="p-6"><div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start"><div><p className="text-base font-extrabold tracking-[0.03em]">{item.name}</p><p className="mt-2 text-xs text-muted-foreground">{formatMeta(item.meta)}</p></div><Button onClick={() => { setSelectedOutput(item); setTab("create"); }} variant="outline" className="rounded-none text-[10px] font-bold tracking-[0.1em]">{ui.useAsPreview}<ChevronRight className="size-3.5"/></Button></div><div className="mt-6 grid grid-cols-3 gap-px bg-border"><div className="bg-[#fafaf8] p-4"><Label>{ui.runtime}</Label><strong className="text-sm">{formatRuntime(item.runtime)}</strong></div><div className="bg-[#fafaf8] p-4"><Label>{ui.fileSize}</Label><strong className="text-sm">{item.size}</strong></div><div className="bg-[#fafaf8] p-4"><Label>{ui.codec}</Label><strong className="text-sm">H.264/AAC</strong></div></div></div>
                </article>
              ))}
            </div>
            <div className="mt-6 border border-border bg-[#171918] p-6 text-white"><div className="grid gap-5 md:grid-cols-[auto_1fr_auto] md:items-center"><div className="grid size-12 place-items-center rounded-full border border-white/15"><Check className="size-5 text-[#25b6a6]"/></div><div><p className="text-sm font-bold">{ui.workflowConnected}</p><p className="mt-1 text-[11px] leading-5 text-white/55">{ui.workflowNote}</p></div><span className="text-[10px] font-bold tracking-[0.14em] text-[#76d5cb]">{liveOutputs.length} {ui.outputCount}</span></div></div>
          </section>
        )}

        {tab === "environment" && (
          <section>
            <SectionTitle eyebrow={ui.envEyebrow} title={ui.envTitle} note={ui.envNote} />
            <p className="mb-4 border border-border bg-white p-4 text-xs">{transfer.gpu}: <strong>{computeDevice || transfer.offline}</strong></p>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Stat label={ui.accelerator} value="NVIDIA GB10" accent/><Stat label={ui.unifiedMemory} value="121.69 GiB"/><Stat label={ui.peakResident} value="~42 GiB"/><Stat label={ui.architecture} value="ARM64"/></div>
            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              <section className="border border-border bg-white"><div className="border-b border-border px-5 py-4"><div className="flex items-center gap-2"><Cpu className="size-4 text-[#e85578]"/><h2 className="text-xs font-extrabold tracking-[0.13em]">{ui.runtimeStack}</h2></div></div><div className="grid gap-px bg-border sm:grid-cols-2">
                {[["CUDA", "13.0", Zap], ["PyTorch", "2.11", Layers3], [ui.precision, "BF16", CircleGauge], [ui.attention, "SDPA", Gauge], [ui.swap, "0 GiB", MemoryStick], [ui.output, "H.264 + AAC", FileVideo]].map(([label, value, Icon]) => { const I = Icon as typeof Cpu; return <div key={label as string} className="bg-white p-5"><I className="mb-4 size-4 text-[#25b6a6]"/><Label>{label as string}</Label><strong className="text-lg">{value as string}</strong></div>; })}
              </div></section>
              <section className="border border-border bg-white"><div className="border-b border-border px-5 py-4"><div className="flex items-center gap-2"><Clock3 className="size-4 text-[#e85578]"/><h2 className="text-xs font-extrabold tracking-[0.13em]">{ui.measuredPerformance}</h2></div></div><div className="p-6"><div className="space-y-6">
                <div><div className="mb-2 flex justify-between text-xs font-bold"><span>384 × 256 · 17F</span><span>33.69s</span></div><div className="h-2 bg-[#efefec]"><div className="h-full w-[73%] bg-[#25b6a6]"/></div></div>
                <div><div className="mb-2 flex justify-between text-xs font-bold"><span>768 × 512 · 49F</span><span>46.18s</span></div><div className="h-2 bg-[#efefec]"><div className="h-full w-full bg-[#ff6f91]"/></div></div>
              </div><div className="mt-8 border-t border-border pt-5 text-[10px] leading-5 text-muted-foreground">{ui.performanceNote}</div></div></section>
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
              <section className="border border-border bg-white"><div className="border-b border-border px-5 py-4"><div className="flex items-center gap-2"><FolderOpen className="size-4 text-[#e85578]"/><h2 className="text-xs font-extrabold tracking-[0.13em]">{ui.localPaths}</h2></div></div><div className="divide-y divide-border font-mono text-[10px]">
                {[
                  [ui.repository, "work/ltx-2.3/LTX-2"],
                  [ui.launcher, "outputs/run-ltx-2.3.sh"],
                  [ui.guide, "outputs/LTX-2.3-使用說明.md"],
                  [ui.mainOutput, "outputs/ltx-2.3-512x768.mp4"],
                  [ui.smokeTest, "outputs/ltx-2.3-smoke.mp4"],
                ].map(([label, path]) => <div key={label} className="grid gap-2 p-5 sm:grid-cols-[120px_1fr]"><span className="font-sans font-bold text-muted-foreground">{label}</span><span className="break-all text-[#168f84]">{path}</span></div>)}
              </div></section>
              <section className="border border-border bg-[#171918] text-white"><div className="border-b border-white/10 px-5 py-4"><div className="flex items-center gap-2"><Code2 className="size-4 text-[#25b6a6]"/><h2 className="text-xs font-extrabold tracking-[0.13em]">{ui.currentCommand}</h2></div></div><div className="p-6"><code className="block break-words font-mono text-[11px] leading-6 text-white/72">{command}</code><div className="mt-6 border-t border-white/10 pt-5"><p className="text-[9px] font-bold tracking-[0.14em] text-white/40">{ui.compatibility}</p><p className="mt-2 text-[10px] leading-5 text-white/55">{ui.compatibilityNote}</p></div></div></section>
            </div>
          </section>
        )}
      </div>

      <footer className="mt-10 border-t border-border bg-[#f7f7f4]"><div className="mx-auto flex max-w-[1560px] flex-col justify-between gap-4 px-5 py-7 text-[9px] font-bold tracking-[0.13em] text-muted-foreground sm:flex-row lg:px-10"><span>{ui.footerLeft}</span><span className="flex items-center gap-2"><WandSparkles className="size-3 text-[#e85578]"/>{ui.footerRight}</span></div></footer>
    </main>
  );
}
