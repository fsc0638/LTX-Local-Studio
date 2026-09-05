'use client';
/* eslint-disable next/no-img-element, jsx-a11y/media-has-caption -- Authenticated local media uses direct URLs; generated/source videos do not yet have caption files. */

import { useEffect, useRef, useState } from 'react';
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
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { MediaLibrary, fileCopy, type Asset } from '@/components/media-library';
import { AccountGate, AccountMenu } from '@/components/account-gate';
import { serviceFetch } from '@/lib/service-session';
import {
  ModelComposer,
  type InstalledModel,
} from '@/components/model-composer';
import { DeleteMediaButton } from '@/components/delete-media-button';
import {
  durationFrames,
  durationPresets,
  sequenceFrames,
  videoCopy,
  type VideoCapabilities,
} from '@/lib/video-settings';
import {
  DirectingControls,
  TimelineControls,
  emptyTimeline,
  mvCopy,
  type Directing,
  type TimelineDraft,
} from '@/components/mv-controls';
import {
  CharacterLock,
  emptyCharacter,
  type CharacterDraft,
} from '@/components/character-lock';
import {
  ProductionFactory,
  type FactoryIncoming,
} from '@/components/production-factory';
import { StageRail, stageCopy, type RailKey } from '@/components/stage-rail';
import { StatusBoard, progressOf } from '@/components/status-board';
import { restoreFactoryPlan, type FactoryPlan } from '@/lib/production-factory';
import { STAGE_KEYS, UNAVAILABLE_STAGES, type StageKey } from '@/lib/stages';
import { bibleFromRequest } from '@/lib/production-factory';

const initialPrompt =
  '電影感近景，一位穿著深色外套的女性站在潮濕的台北街口。鏡頭緩慢向前推進，霓虹燈在積水中形成珊瑚紅與青綠色倒影，微風帶動髮絲，自然環境音，細緻膠片顆粒。';

const promptPresets = [
  [
    'CINEMATIC',
    '電影感廣角，一列未來列車穿越雲海，金色晨光，緩慢空拍推進，真實物理光影，空間感環境音。',
  ],
  [
    'PORTRAIT',
    '人像近景，柔和窗光，細微呼吸與眼神變化，淺景深，手持攝影的自然晃動，細膩膚質。',
  ],
  [
    'PRODUCT',
    '極簡產品動畫，黑色背景，輪廓光沿著金屬表面移動，鏡頭環繞，乾淨高級的棚拍質感。',
  ],
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
const emptyOutput: OutputItem = {
  id: 'empty',
  name: '—',
  src: '',
  meta: '—',
  runtime: '—',
  size: '—',
};

type ApiJob = {
  model?: string;
  media_type?: string;
  id: string;
  filename: string;
  output_url: string;
  poster_url?: string;
  width: number;
  height: number;
  frames: number;
  fps: number;
  runtime_seconds?: number;
  elapsed_seconds?: number;
  size_bytes?: number;
  status: string;
  progress: number;
  message?: string;
  error?: string;
};
type Health = {
  ok: boolean;
  runtime?: { cuda_available?: boolean; device?: string; error?: string };
  active_job?: ApiJob;
};

function outputFromJob(job: ApiJob): OutputItem {
  const runtime = Number(job.runtime_seconds || 0);
  const sizeBytes = Number(job.size_bytes || 0);
  return {
    id: String(job.id),
    name: String(job.filename),
    src: `${MEDIA_BASE || API_BASE}${String(job.output_url)}`,
    download: `${MEDIA_BASE || API_BASE}${String(job.output_url)}?download=1`,
    poster: job.poster_url
      ? `${MEDIA_BASE || API_BASE}${String(job.poster_url)}`
      : undefined,
    meta: `${job.width} × ${job.height} · ${job.frames} frames · ${job.fps} FPS`,
    runtime: runtime > 0 ? `${runtime} sec` : 'Completed',
    size: `${Math.max(0.1, sizeBytes / 1024 / 1024).toFixed(1)} MB`,
  };
}

type TabKey = RailKey;
type Locale = 'zh-TW' | 'en' | 'ja';
// Browser traffic stays same-origin. Only the server knows the worker address.
const API_BASE = '';
const MEDIA_BASE = '';

const translations = {
  'zh-TW': {
    topStrip: '本機生成 · 檔案保留在此裝置 · NVIDIA GB10',
    console: 'GB10 控制台',
    createTab: '沙盒',
    factoryTab: '拍攝',
    assetsTab: '素材庫',
    outputsTab: '產出',
    environmentTab: '工站',
    bibleEyebrow: '00 / 企劃 BIBLE',
    bibleTitle: '固定角色、音樂與輸出規格',
    bibleNote: '這裡設定一次，之後每一鏡都繼承。改這裡會套用到所有還沒生產的鏡頭；你手動改過的欄位會保留。',
    breakdownEyebrow: '01 / 分鏡',
    breakdownTitle: '把歌切成鏡頭',
    breakdownNote: '上傳音樂與歌詞，設定每一鏡的主要動作與運鏡。拍點與逐字對時的自動分鏡在 B 期接上。',
    shootEyebrow: '03 / 拍攝',
    shootTitle: '製片工廠佇列',
    shootNote: '一次送一個 GPU 任務；失敗會暫停整條線等人處理。',
    assemblyEyebrow: '06 / 組片交付',
    assemblyTitle: '產出與組片',
    assemblyNote: '已完成的鏡頭與歷史產出。跨 take 選片與 EDL 匯出在 D 期接上。',
    unavailableTitle: '這個階段本期未啟用',
    unavailableNote: '模型都已安裝，但還沒接上介面。實作進度見 docs/PRODUCTION_ROADMAP.md。',
    unavailableKeyframes: '需要把 Qwen-Image-Edit 註冊成 adapter，並接上一致性裁判（D 期）。',
    unavailableReview: '需要裁判服務與 take 概念（C 期）。',
    unavailablePost: '需要後製 adapter：補幀、放大、清理（D 期）。',
    backToBoard: '回狀態板',
    ready: '已就緒',
    connecting: '連線中',
    generating: '生成中',
    complete: '已完成',
    failed: '失敗',
    offline: '離線',
    createEyebrow: '01 / 生成',
    createTitle: '新影片生成',
    createNote:
      '提示詞、模型、影像規格與運算策略集中在同一個工作區；設定會即時反映到本機執行命令。',
    outputPreview: '產出預覽',
    verifiedOutput: '已驗證產出',
    runtime: '執行時間',
    precision: '運算精度',
    attention: '注意力機制',
    generationSettings: '生成設定',
    reset: '重設',
    width: '寬度',
    height: '高度',
    frames: '影格數',
    videoDuration: '影片長度',
    frameRate: '影格率',
    inferenceSteps: '推論步數',
    cfgScale: 'CFG 強度',
    seed: '隨機種子',
    seconds: '秒',
    actual: '實際',
    estimatedInference: '預估推論',
    upscaler: 'x2 空間放大',
    upscalerNote: '二階段空間放大，提升最終解析度。',
    offload: 'CPU 卸載',
    offloadNote: '記憶體吃緊時卸載部分權重。',
    tiling: 'VAE 分塊解碼',
    tilingNote: '分塊解碼以降低尖峰記憶體。',
    audio: '音訊生成',
    audioNote: '同時產生 AAC 聲音軌。',
    promptAndModel: '提示詞與模型',
    prompt: '提示詞',
    negativePrompt: '負面提示詞',
    characters: '字元',
    model: '模型',
    mode: '生成模式',
    cinematic: '電影感',
    portrait: '人像',
    product: '產品',
    t2v: '文字生成影片',
    i2v: '圖片生成影片',
    v2v: '影片轉影片',
    chooseAsset: '請從素材庫選擇參照素材',
    openAssetLibrary: '開啟素材庫',
    duration: '長度',
    canvas: '畫布',
    localEngine: '本機引擎',
    engineConnected: 'LTX-2.3 推論服務已連線',
    engineWaiting: '正在等待本機推論服務',
    generationFailed: '生成失敗',
    generateVideo: '生成影片',
    generatingVideo: '影片生成中…',
    addToFactory: '加入製片工廠',
    generateNote:
      '會真正呼叫本機 LTX-2.3 Distilled；一次只執行一個 GPU 任務，完成後自動更新預覽。',
    commandPreview: '命令預覽',
    assetsEyebrow: '03 / 素材',
    assetsTitle: '參照素材與來源',
    assetsNote:
      '集中檢視影像、影片、模型與設定檔的來源；所有素材都保留在本機。',
    mediaReferences: '媒體參照 · 4 個檔案',
    openFolder: '開啟資料夾',
    video: '影片',
    image: '圖片',
    previewFrame: 'PNG 預覽影格',
    modelSources: '模型來源',
    sourcePolicy: '來源與隱私',
    sourcePolicyNote:
      '所有輸入與產出留在本機。介面只引用已建立的媒體副本，不會自動上傳外部服務。',
    primaryTransformer: '主要擴散 Transformer',
    promptEncoder: '提示詞增強編碼器',
    detailRecovery: '第二階段細節恢復',
    outputsEyebrow: '04 / 產出',
    outputsTitle: '產出預覽與紀錄',
    outputsNote:
      '新的生成結果會自動加入這裡；可直接播放或切回生成頁作為主預覽。',
    runPassed: '已完成',
    useAsPreview: '設為主預覽',
    fileSize: '檔案大小',
    codec: '編碼',
    workflowConnected: '本機輸出工作流已連接',
    workflowNote:
      '模型載入、推論、VAE 解碼、空間放大、音訊與 MP4 封裝均會反映在這個頁面。',
    outputCount: '個產出',
    envEyebrow: '05 / 環境',
    envTitle: '裝置與執行環境',
    envNote:
      '以下資料來自本機實測環境，用來判斷 LTX-2 / LTX-2.3 的可執行性、記憶體餘裕與相容性。',
    accelerator: '加速器',
    unifiedMemory: '統一記憶體',
    peakResident: '尖峰佔用',
    architecture: '系統架構',
    runtimeStack: '執行環境',
    measuredPerformance: '實測效能',
    performanceNote:
      '結果取自 LTX-2.3 22B Distilled 1.1、BF16、SDPA 與 x2 空間放大。實際時間會依提示詞、幀數與背景程序變化。',
    localPaths: '本機路徑與檔案',
    currentCommand: '目前命令',
    compatibility: '相容性說明',
    compatibilityNote:
      'GB10 的統一記憶體足以在目前配置執行 LTX-2.3；BF16 + SDPA 是這台裝置上已驗證的穩定組合。',
    repository: '程式庫',
    launcher: '啟動腳本',
    guide: '說明文件',
    mainOutput: '主要產出',
    smokeTest: '快速測試',
    swap: '交換空間',
    output: '輸出',
    frameUnit: '影格',
    completedValue: '已完成',
    secondAbbr: '秒',
    restoredMessage: '已載入最近一次本機生成結果。',
    sendingMessage: '正在送出本機生成任務…',
    inferenceMessage: 'LTX-2.3 正在執行推論。',
    completedMessage: '影片已完成並載入左側預覽，也可在產出頁簽播放。',
    cannotCreate: '無法建立生成任務。',
    cannotRead: '無法讀取任務狀態。',
    cannotConnect: '無法連接本機生成服務。',
    footerLeft: 'LTX Studio UI/UX · 本機優先工作流',
    footerRight: '為 NVIDIA GB10 上的 LTX-2.3 設計',
  },
  en: {
    topStrip: 'Local generation · Files stay on this device · NVIDIA GB10',
    console: 'GB10 Console',
    createTab: 'SANDBOX',
    factoryTab: 'GENERATION',
    assetsTab: 'MEDIA',
    outputsTab: 'OUTPUTS',
    environmentTab: 'WORKSTATION',
    bibleEyebrow: '00 / PROJECT BIBLE',
    bibleTitle: 'Fix the character, music and output format',
    bibleNote: 'Set once here and every shot inherits it. Changes apply to shots that have not run yet; fields you edited by hand keep their values.',
    breakdownEyebrow: '01 / BREAKDOWN',
    breakdownTitle: 'Cut the song into shots',
    breakdownNote: 'Load the music and lyrics, then set each shot\u2019s main action and camera. Beat-aligned automatic breakdown arrives in phase B.',
    shootEyebrow: '03 / GENERATION',
    shootTitle: 'Production factory queue',
    shootNote: 'One GPU job at a time; a failure pauses the whole line for a person.',
    assemblyEyebrow: '06 / ASSEMBLY',
    assemblyTitle: 'Outputs and assembly',
    assemblyNote: 'Finished shots and past outputs. Take selection and EDL export arrive in phase D.',
    unavailableTitle: 'This stage is not enabled yet',
    unavailableNote: 'The models are installed; nothing is wired to the interface yet. See docs/PRODUCTION_ROADMAP.md.',
    unavailableKeyframes: 'Needs Qwen-Image-Edit registered as an adapter and the consistency judge (phase D).',
    unavailableReview: 'Needs the judge service and the take model (phase C).',
    unavailablePost: 'Needs the post adapters: interpolation, upscaling, cleanup (phase D).',
    backToBoard: 'Back to the board',
    ready: 'READY',
    connecting: 'CONNECTING',
    generating: 'GENERATING',
    complete: 'COMPLETE',
    failed: 'FAILED',
    offline: 'OFFLINE',
    createEyebrow: '01 / Create',
    createTitle: 'Create a new video',
    createNote:
      'Prompts, models, image specifications, and runtime strategy live in one workspace and update the local command instantly.',
    outputPreview: 'Output preview',
    verifiedOutput: 'Verified output',
    runtime: 'Runtime',
    precision: 'Precision',
    attention: 'Attention',
    generationSettings: 'Generation settings',
    reset: 'Reset',
    width: 'Width',
    height: 'Height',
    frames: 'Frames',
    videoDuration: 'Video duration',
    frameRate: 'Frame rate',
    inferenceSteps: 'Inference steps',
    cfgScale: 'CFG scale',
    seed: 'Seed',
    seconds: 'seconds',
    actual: 'Actual',
    estimatedInference: 'Estimated inference',
    upscaler: 'x2 Spatial Upscaler',
    upscalerNote: 'Second-stage spatial upscaling for final detail.',
    offload: 'CPU Offload',
    offloadNote: 'Move weights to CPU when memory is constrained.',
    tiling: 'VAE Decode Tiling',
    tilingNote: 'Decode in tiles to reduce peak memory.',
    audio: 'Audio Generation',
    audioNote: 'Generate an AAC audio track with the video.',
    promptAndModel: 'Prompt & model',
    prompt: 'Prompt',
    negativePrompt: 'Negative prompt',
    characters: 'characters',
    model: 'Model',
    mode: 'Mode',
    cinematic: 'Cinematic',
    portrait: 'Portrait',
    product: 'Product',
    t2v: 'Text to Video',
    i2v: 'Image to Video',
    v2v: 'Video to Video',
    chooseAsset: 'Choose a reference from Assets',
    openAssetLibrary: 'Open asset library',
    duration: 'Duration',
    canvas: 'Canvas',
    localEngine: 'Local engine',
    engineConnected: 'LTX-2.3 inference service connected',
    engineWaiting: 'Waiting for local inference service',
    generationFailed: 'Generation failed',
    generateVideo: 'Generate video',
    generatingVideo: 'Generating video…',
    addToFactory: 'Add to production factory',
    generateNote:
      'Calls the local LTX-2.3 Distilled model. One GPU job runs at a time and the preview updates automatically.',
    commandPreview: 'Command preview',
    assetsEyebrow: '03 / Assets',
    assetsTitle: 'References & sources',
    assetsNote:
      'Review image, video, model, and configuration sources. Every asset remains on this device.',
    mediaReferences: 'Media references · 4 files',
    openFolder: 'Open folder',
    video: 'Video',
    image: 'Image',
    previewFrame: 'PNG preview frame',
    modelSources: 'Model sources',
    sourcePolicy: 'Source & privacy',
    sourcePolicyNote:
      'All inputs and outputs remain local. The interface references local media copies and never uploads them automatically.',
    primaryTransformer: 'Primary diffusion transformer',
    promptEncoder: 'Prompt enhancement encoder',
    detailRecovery: 'Second-pass detail recovery',
    outputsEyebrow: '04 / Outputs',
    outputsTitle: 'Output previews & history',
    outputsNote:
      'New generations appear here automatically. Play them directly or set one as the main preview.',
    runPassed: 'Passed',
    useAsPreview: 'Use as preview',
    fileSize: 'File size',
    codec: 'Codec',
    workflowConnected: 'Local output workflow connected',
    workflowNote:
      'Model loading, inference, VAE decoding, upscaling, audio, and MP4 packaging all appear in this workspace.',
    outputCount: 'outputs',
    envEyebrow: '05 / Environment',
    envTitle: 'Device & runtime',
    envNote:
      'Measured local data for evaluating LTX-2 / LTX-2.3 compatibility, memory headroom, and performance.',
    accelerator: 'Accelerator',
    unifiedMemory: 'Unified memory',
    peakResident: 'Peak resident',
    architecture: 'Architecture',
    runtimeStack: 'Runtime stack',
    measuredPerformance: 'Measured performance',
    performanceNote:
      'Measured with LTX-2.3 22B Distilled 1.1, BF16, SDPA, and x2 spatial upscaling. Runtime varies with prompt, frame count, and background processes.',
    localPaths: 'Local paths & files',
    currentCommand: 'Current command',
    compatibility: 'Compatibility note',
    compatibilityNote:
      'GB10 unified memory is sufficient for this LTX-2.3 configuration; BF16 + SDPA is the verified stable combination.',
    repository: 'Repository',
    launcher: 'Launcher',
    guide: 'Guide',
    mainOutput: 'Main output',
    smokeTest: 'Smoke test',
    swap: 'Swap',
    output: 'Output',
    frameUnit: 'frames',
    completedValue: 'Completed',
    secondAbbr: 'sec',
    restoredMessage: 'The latest local output has been restored.',
    sendingMessage: 'Submitting a local generation job…',
    inferenceMessage: 'LTX-2.3 is running inference.',
    completedMessage:
      'Video complete and loaded in the main preview. It is also available in Outputs.',
    cannotCreate: 'Could not create the generation job.',
    cannotRead: 'Could not read the job status.',
    cannotConnect: 'Could not connect to the local generation service.',
    footerLeft: 'LTX Studio UI/UX · local-first workflow',
    footerRight: 'Designed for LTX-2.3 on NVIDIA GB10',
  },
  ja: {
    topStrip: 'ローカル生成 · ファイルはこのデバイスに保存 · NVIDIA GB10',
    console: 'GB10 コンソール',
    createTab: 'サンドボックス',
    factoryTab: '生成',
    assetsTab: '素材ライブラリ',
    outputsTab: '出力',
    environmentTab: 'ワークステーション',
    bibleEyebrow: '00 / 企画 BIBLE',
    bibleTitle: '人物・音楽・出力設定を固定する',
    bibleNote: 'ここで一度決めれば各ショットが継承します。未生成のショットに反映され、手動で変更した項目はそのまま残ります。',
    breakdownEyebrow: '01 / 絵コンテ',
    breakdownTitle: '曲をショットに割る',
    breakdownNote: '音楽と歌詞を読み込み、各ショットの主要アクションとカメラを設定します。拍に合わせた自動分割はフェーズBで対応します。',
    shootEyebrow: '03 / 生成',
    shootTitle: '制作工場キュー',
    shootNote: 'GPUジョブは一度に1件。失敗するとライン全体が停止し、人の判断を待ちます。',
    assemblyEyebrow: '06 / 編集・納品',
    assemblyTitle: '出力と編集',
    assemblyNote: '完了したショットと過去の出力。テイク選択とEDL書き出しはフェーズDで対応します。',
    unavailableTitle: 'この段階は今期未対応です',
    unavailableNote: 'モデルは導入済みですが、まだ画面につながっていません。docs/PRODUCTION_ROADMAP.md を参照してください。',
    unavailableKeyframes: 'Qwen-Image-Edit のアダプター登録と一貫性判定が必要です（フェーズD）。',
    unavailableReview: '判定サービスとテイク概念が必要です（フェーズC）。',
    unavailablePost: '仕上げアダプター（補間・拡大・除去）が必要です（フェーズD）。',
    backToBoard: 'ボードに戻る',
    ready: '準備完了',
    connecting: '接続中',
    generating: '生成中',
    complete: '完了',
    failed: '失敗',
    offline: 'オフライン',
    createEyebrow: '01 / 生成',
    createTitle: '新しい動画を生成',
    createNote:
      'プロンプト、モデル、映像仕様、実行戦略を一つのワークスペースで管理し、ローカルコマンドへ即時反映します。',
    outputPreview: '出力プレビュー',
    verifiedOutput: '検証済み出力',
    runtime: '実行時間',
    precision: '演算精度',
    attention: 'Attention',
    generationSettings: '生成設定',
    reset: 'リセット',
    width: '幅',
    height: '高さ',
    frames: 'フレーム数',
    videoDuration: '動画の長さ',
    frameRate: 'フレームレート',
    inferenceSteps: '推論ステップ',
    cfgScale: 'CFG スケール',
    seed: 'シード',
    seconds: '秒',
    actual: '実際',
    estimatedInference: '推論目安',
    upscaler: 'x2 空間アップスケーラー',
    upscalerNote: '第2段階で解像度と細部を向上します。',
    offload: 'CPU オフロード',
    offloadNote: 'メモリ不足時に一部の重みをCPUへ移します。',
    tiling: 'VAE タイルデコード',
    tilingNote: '分割デコードでピークメモリを抑えます。',
    audio: '音声生成',
    audioNote: 'AAC音声トラックを同時生成します。',
    promptAndModel: 'プロンプトとモデル',
    prompt: 'プロンプト',
    negativePrompt: 'ネガティブプロンプト',
    characters: '文字',
    model: 'モデル',
    mode: '生成モード',
    cinematic: 'シネマティック',
    portrait: 'ポートレート',
    product: 'プロダクト',
    t2v: 'テキストから動画',
    i2v: '画像から動画',
    v2v: '動画から動画',
    chooseAsset: '素材から参照ファイルを選択',
    openAssetLibrary: '素材ライブラリを開く',
    duration: '長さ',
    canvas: 'キャンバス',
    localEngine: 'ローカルエンジン',
    engineConnected: 'LTX-2.3 推論サービス接続済み',
    engineWaiting: 'ローカル推論サービスを待機中',
    generationFailed: '生成に失敗',
    generateVideo: '動画を生成',
    generatingVideo: '動画を生成中…',
    addToFactory: '制作工場に追加',
    generateNote:
      'ローカルの LTX-2.3 Distilled を実行します。GPUジョブは一度に1件で、完了後プレビューを自動更新します。',
    commandPreview: 'コマンドプレビュー',
    assetsEyebrow: '03 / 素材',
    assetsTitle: '参照素材とソース',
    assetsNote:
      '画像、動画、モデル、設定ファイルのソースを確認できます。すべての素材はローカルに保存されます。',
    mediaReferences: 'メディア参照 · 4ファイル',
    openFolder: 'フォルダを開く',
    video: '動画',
    image: '画像',
    previewFrame: 'PNG プレビューフレーム',
    modelSources: 'モデルソース',
    sourcePolicy: 'ソースとプライバシー',
    sourcePolicyNote:
      '入力と出力はすべてローカルに保持され、外部サービスへ自動アップロードされません。',
    primaryTransformer: 'メイン拡散 Transformer',
    promptEncoder: 'プロンプト拡張エンコーダー',
    detailRecovery: '第2段階のディテール復元',
    outputsEyebrow: '04 / 出力',
    outputsTitle: '出力プレビューと履歴',
    outputsNote:
      '新しい生成結果は自動的に追加され、直接再生したりメインプレビューに設定できます。',
    runPassed: '完了',
    useAsPreview: 'メイン表示に設定',
    fileSize: 'ファイルサイズ',
    codec: 'コーデック',
    workflowConnected: 'ローカル出力ワークフロー接続済み',
    workflowNote:
      'モデル読込、推論、VAEデコード、アップスケール、音声、MP4出力がこの画面に反映されます。',
    outputCount: '件の出力',
    envEyebrow: '05 / 環境',
    envTitle: 'デバイスと実行環境',
    envNote:
      'LTX-2 / LTX-2.3 の互換性、メモリ余裕、性能を判断するためのローカル実測データです。',
    accelerator: 'アクセラレーター',
    unifiedMemory: '統合メモリ',
    peakResident: 'ピーク使用量',
    architecture: 'アーキテクチャ',
    runtimeStack: 'ランタイム構成',
    measuredPerformance: '実測パフォーマンス',
    performanceNote:
      'LTX-2.3 22B Distilled 1.1、BF16、SDPA、x2空間アップスケールで計測。時間はプロンプト、フレーム数、バックグラウンド処理で変動します。',
    localPaths: 'ローカルパスとファイル',
    currentCommand: '現在のコマンド',
    compatibility: '互換性メモ',
    compatibilityNote:
      'GB10の統合メモリは現在のLTX-2.3構成に十分です。BF16 + SDPA は検証済みの安定した組み合わせです。',
    repository: 'リポジトリ',
    launcher: '起動スクリプト',
    guide: 'ガイド',
    mainOutput: 'メイン出力',
    smokeTest: 'スモークテスト',
    swap: 'スワップ',
    output: '出力',
    frameUnit: 'フレーム',
    completedValue: '完了',
    secondAbbr: '秒',
    restoredMessage: '最新のローカル生成結果を復元しました。',
    sendingMessage: 'ローカル生成ジョブを送信中…',
    inferenceMessage: 'LTX-2.3 が推論を実行中です。',
    completedMessage:
      '動画が完成し、メインプレビューに読み込まれました。出力タブでも再生できます。',
    cannotCreate: '生成ジョブを作成できませんでした。',
    cannotRead: 'ジョブ状態を取得できませんでした。',
    cannotConnect: 'ローカル生成サービスに接続できませんでした。',
    footerLeft: 'LTX Studio UI/UX · ローカルファースト',
    footerRight: 'NVIDIA GB10 上の LTX-2.3 向け',
  },
} as const;

function SectionTitle({
  eyebrow,
  title,
  note,
}: {
  eyebrow: string;
  title: string;
  note: string;
}) {
  return (
    <div className="mb-8 flex flex-col justify-between gap-3 md:flex-row md:items-end">
      <div>
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.25em] text-[#e85578]">
          {eyebrow}
        </p>
        <h1 className="text-3xl font-extrabold tracking-[0.07em] md:text-4xl">
          {title}
        </h1>
      </div>
      <p className="max-w-lg text-sm leading-6 text-muted-foreground">{note}</p>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-2 block text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
      {children}
    </span>
  );
}

function ToggleRow({
  label,
  note,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  note: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border py-4 last:border-b-0">
      <div>
        <p className="text-xs font-bold">{label}</p>
        <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
          {note}
        </p>
      </div>
      <Switch
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
      />
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="border border-border bg-white p-5">
      <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <p
        className={`mt-2 text-xl font-extrabold tracking-tight ${accent ? 'text-[#159c8f]' : ''}`}
      >
        {value}
      </p>
    </div>
  );
}

export default function Home() {
  return (
    <AccountGate>
      <Studio />
    </AccountGate>
  );
}

function Studio() {
  const [locale, setLocale] = useState<Locale>('zh-TW');
  const [tab, setTab] = useState<TabKey>('board');
  // The factory owns the plan; the page keeps a mirror so the rail and the board can read it.
  const [plan, setPlan] = useState<FactoryPlan | null>(null);
  const [prompt, setPrompt] = useState(initialPrompt);
  const [model, setModel] = useState('ltx23-distilled');
  const [models, setModels] = useState<InstalledModel[]>([]);
  const [catalogError, setCatalogError] = useState(false);
  const [mode, setMode] = useState('t2v');
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [seconds, setSeconds] = useState('2');
  const [capabilities, setCapabilities] = useState<VideoCapabilities | null>(
    null,
  );
  const [capabilitiesFailed, setCapabilitiesFailed] = useState(false);
  const [fps, setFps] = useState('24');
  const [seed, setSeed] = useState(42);
  const precision = 'bf16';
  const attention = 'sdpa';
  const [upscaler, setUpscaler] = useState(true);
  const [offload, setOffload] = useState(false);
  const [tiling, setTiling] = useState(true);
  const [audio, setAudio] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [jobStatus, setJobStatus] = useState('READY');
  const [selectedOutput, setSelectedOutput] = useState<OutputItem>(emptyOutput);
  const [liveOutputs, setLiveOutputs] = useState<OutputItem[]>(outputItems);
  const [backendOnline, setBackendOnline] = useState(false);
  const [jobMessage, setJobMessage] = useState('');
  const [jobError, setJobError] = useState('');
  const [reference, setReference] = useState<Asset | null>(null);
  const [imageStrength, setImageStrength] = useState(0.72);
  const [referenceBackground, setReferenceBackground] = useState<
    'source' | 'alpha_neutral'
  >('source');
  const [character, setCharacter] = useState<CharacterDraft>({
    ...emptyCharacter,
  });
  const [directing, setDirecting] = useState<Directing>({});
  const [timeline, setTimeline] = useState<TimelineDraft>({ ...emptyTimeline });
  const [factoryIncoming, setFactoryIncoming] =
    useState<FactoryIncoming | null>(null);
  const [referenceUploading, setReferenceUploading] = useState(false);
  const referenceInput = useRef<HTMLInputElement>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [computeDevice, setComputeDevice] = useState('');
  const deletedOutputs = useRef(new Set<string>());
  const transfer = fileCopy[locale];
  const videoText = videoCopy[locale];
  const mvText = mvCopy[locale];
  const maxFrames = capabilities?.limits.max_frames || 481;
  const dimensions =
    aspectRatio === 'source'
      ? reference?.suggested_dimensions
      : capabilities?.aspect_ratios[aspectRatio];
  const { width, height } = dimensions || { width: 1024, height: 576 };
  const isSequence =
    timeline.enabled || Number(seconds) > maxFrames / Number(fps);
  const validFrames = isSequence
    ? sequenceFrames(
        Number(seconds),
        Number(fps),
        capabilities?.sequence?.max_seconds || 180,
      )
    : durationFrames(Number(seconds), Number(fps), maxFrames);
  const frames = validFrames || 0;
  const maximumSeconds =
    capabilities?.sequence?.max_seconds || maxFrames / Number(fps);
  const settingsReady = Boolean(
    capabilities &&
    dimensions &&
    validFrames &&
    (!isSequence || capabilities.sequence?.supported),
  );
  const characterReady =
    !character.enabled ||
    Boolean(
      character.name.trim() &&
      character.description.trim() &&
      reference &&
      character.references.some((item) => item.asset.id === reference.id),
    );
  const canSubmit =
    !generating &&
    backendOnline &&
    Boolean(prompt.trim()) &&
    (mode !== 'i2v' || Boolean(reference));
  const selectReference = (asset: Asset) => {
    setReference(asset);
    setMode('i2v');
    setAspectRatio(asset.suggested_aspect_ratio || 'source');
    setTab('sandbox');
  };
  const uploadReference = async (file?: File) => {
    if (!file) return;
    setReferenceUploading(true);
    setJobError('');
    try {
      if (file.size > 50 * 1024 * 1024) throw new Error(transfer.tooLarge);
      const mime =
        file.type ||
        (
          {
            png: 'image/png',
            jpg: 'image/jpeg',
            jpeg: 'image/jpeg',
            webp: 'image/webp',
          } as Record<string, string>
        )[file.name.split('.').pop()?.toLowerCase() || ''];
      if (!mime?.startsWith('image/')) throw new Error('PNG / JPEG / WebP');
      const response = await serviceFetch(
        `/api/v1/assets?name=${encodeURIComponent(file.name)}`,
        { method: 'POST', headers: { 'Content-Type': mime }, body: file },
      );
      const result = (await response.json()) as Asset & { error?: string };
      if (!response.ok) throw new Error(result.error || transfer.failed);
      selectReference(result);
    } catch (issue) {
      setJobError(issue instanceof Error ? issue.message : transfer.failed);
    } finally {
      setReferenceUploading(false);
    }
  };
  const removeOutput = (id: string) => {
    deletedOutputs.current.add(id);
    setLiveOutputs((current) => current.filter((item) => item.id !== id));
    setSelectedOutput((current) => (current.id === id ? emptyOutput : current));
  };
  const ui = translations[locale];
  const visibleStatus = generating
    ? ui.generating
    : jobStatus === 'COMPLETE'
      ? ui.complete
      : jobStatus === 'FAILED'
        ? ui.failed
        : jobStatus === 'OFFLINE'
          ? ui.offline
          : jobStatus === 'CONNECTING'
            ? ui.connecting
            : backendOnline
              ? ui.ready
              : ui.offline;
  const formatMeta = (value: string) => value.replace('frames', ui.frameUnit);
  const formatRuntime = (value: string) =>
    value === 'Completed'
      ? ui.completedValue
      : value.replace('sec', ui.secondAbbr);

  const duration = validFrames ? (frames / Number(fps)).toFixed(3) : '—';
  const durationPreset =
    durationPresets.includes(Number(seconds)) &&
    Number(seconds) <= maximumSeconds
      ? String(Number(seconds))
      : 'custom';
  const generationRequest = {
    prompt,
    model,
    mode,
    aspect_ratio: aspectRatio,
    duration_seconds: Number(seconds),
    fps: Number(fps),
    seed,
    offload,
    audio: isSequence && timeline.music ? true : audio,
    image_id: mode === 'i2v' ? reference?.id : undefined,
    image_strength: mode === 'i2v' ? imageStrength : undefined,
    reference_background: mode === 'i2v' ? referenceBackground : undefined,
    directing,
    ...(mode === 'i2v' && character.enabled
      ? {
          character: {
            name: character.name.trim(),
            description: character.description.trim(),
            references: character.references.map((item) => ({
              image_id: item.asset.id,
              view: item.view,
            })),
          },
        }
      : {}),
    ...(isSequence
      ? {
          render_mode: 'sequence',
          segment_seconds: timeline.segmentSeconds,
          timeline: {
            audio_id: timeline.music?.id,
            audio_start_seconds: timeline.audioStart,
            audio_mode: timeline.music ? timeline.audioMode : 'soundtrack',
            lrc: timeline.lrc,
            lrc_timebase: timeline.lrcTimebase,
            cues: timeline.cues,
          },
        }
      : {}),
  };
  const command = `POST /api/v1/jobs\n${JSON.stringify(generationRequest, null, 2)}`;

  useEffect(() => {
    const savedLocale = window.localStorage.getItem('ltx-studio-locale');
    if (savedLocale === 'zh-TW' || savedLocale === 'en' || savedLocale === 'ja') {
      // eslint-disable-next-line react/react-compiler -- Read the browser-only saved preference after hydration.
      setLocale(savedLocale);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem('ltx-studio-locale', locale);
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    const abort = new AbortController();
    serviceFetch('/api/v1/capabilities', { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const data = (await response.json()) as VideoCapabilities;
        if (!data.aspect_ratios || !data.limits?.max_frames) throw new Error();
        if (!abort.signal.aborted) setCapabilities(data);
      })
      .catch(() => {
        if (!abort.signal.aborted) setCapabilitiesFailed(true);
      });
    serviceFetch('/api/models', { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        return response.json() as Promise<{ models: InstalledModel[] }>;
      })
      .then((data) => {
        setModels(data.models);
        setCatalogError(false);
      })
      .catch(() => {
        if (!abort.signal.aborted) setCatalogError(true);
      });
    return () => abort.abort();
  }, []);

  useEffect(() => {
    let active = true;
    const checkHealth = () =>
      serviceFetch(`${API_BASE}/api/health`)
        .then((response) => response.json() as Promise<Health>)
        .then((data) => {
          if (!active) return;
          setBackendOnline(Boolean(data.ok));
          setComputeDevice(
            data.runtime?.cuda_available ? data.runtime.device || '' : '',
          );
          if (data.runtime?.error) setJobError(data.runtime.error);
          if (
            data.active_job &&
            (!data.active_job.model ||
              data.active_job.model === 'ltx23-distilled')
          ) {
            setActiveJobId(data.active_job.id);
            setGenerating(true);
          }
        })
        .catch(() => {
          if (active) setBackendOnline(false);
        });
    const loadGeneratedOutputs = () =>
      serviceFetch(`${API_BASE}/api/outputs`)
        .then((response) => response.json() as Promise<{ outputs?: ApiJob[] }>)
        .then((data) => {
          if (!active || !Array.isArray(data.outputs)) return;
          const restored = data.outputs
            .filter(
              (job) =>
                (!job.media_type || job.media_type === 'video') &&
                !deletedOutputs.current.has(job.id),
            )
            .map(outputFromJob);
          setLiveOutputs([...restored, ...outputItems]);
          setSelectedOutput(
            (current) =>
              restored.find((item) => item.id === current.id) ||
              restored[0] ||
              emptyOutput,
          );
        })
        .catch(() => undefined);
    void checkHealth();
    void loadGeneratedOutputs();
    const timer = window.setInterval(checkHealth, 5000);
    const restoreTimer = window.setTimeout(loadGeneratedOutputs, 2500);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.clearTimeout(restoreTimer);
    };
  }, [ui.restoredMessage]);

  useEffect(() => {
    if (!activeJobId) return;
    let stopped = false;
    let pending = false;
    const poll = async () => {
      if (pending) return;
      pending = true;
      try {
        const response = await serviceFetch(
          `${API_BASE}/api/jobs/${activeJobId}`,
        );
        const job = (await response.json()) as ApiJob;
        if (stopped) return;
        if (!response.ok) {
          if (response.status === 404) {
            setActiveJobId(null);
            setGenerating(false);
          }
          throw new Error(job.error || ui.cannotRead);
        }
        setJobError('');
        setProgress(job.progress ?? 0);
        setElapsed(job.elapsed_seconds || job.runtime_seconds || 0);
        setJobMessage(job.message || ui.inferenceMessage);
        if (
          ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(
            job.status,
          )
        ) {
          setActiveJobId(null);
          setGenerating(false);
          setJobStatus(job.status === 'succeeded' ? 'COMPLETE' : 'FAILED');
          if (job.status === 'succeeded') {
            const generated = outputFromJob(job);
            setLiveOutputs((current) => [
              generated,
              ...current.filter((item) => item.id !== generated.id),
            ]);
            setSelectedOutput(generated);
            setJobMessage(ui.completedMessage);
          } else setJobError(job.message || ui.cannotRead);
        }
      } catch (error) {
        if (!stopped)
          setJobError(
            error instanceof Error ? error.message : ui.cannotConnect,
          );
        // A temporary network failure must not abandon the GPU job.
      } finally {
        pending = false;
      }
    };
    void poll();
    const timer = window.setInterval(poll, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [
    activeJobId,
    ui.cannotRead,
    ui.inferenceMessage,
    ui.completedMessage,
    ui.cannotConnect,
  ]);

  const simulateGeneration = async () => {
    if (!canSubmit) return;
    setJobError('');
    setJobMessage(ui.sendingMessage);
    setGenerating(true);
    setJobStatus('CONNECTING');
    setProgress(1);
    setElapsed(0);
    try {
      const response = await serviceFetch(`${API_BASE}/api/v1/jobs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': crypto.randomUUID(),
        },
        body: JSON.stringify(generationRequest),
      });
      const created = (await response.json()) as ApiJob;
      if (!response.ok) throw new Error(created.error || ui.cannotCreate);
      setBackendOnline(true);
      setJobStatus('GENERATING');
      setProgress(created.progress || 3);
      setJobMessage(created.message || ui.inferenceMessage);

      setActiveJobId(created.id);
    } catch (error) {
      setGenerating(false);
      setJobStatus('FAILED');
      setProgress(0);
      setJobError(error instanceof Error ? error.message : ui.cannotConnect);
    }
  };

  const emptyPlan = restoreFactoryPlan(null);
  const stageProgress = progressOf(plan || emptyPlan);
  const stageNames = stageCopy[locale].stages;
  const stageIndexOf = (key: TabKey) =>
    String(STAGE_KEYS.indexOf(key as StageKey)).padStart(2, '0');

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="border-b border-border bg-[#f7f7f5] px-5 py-2 text-center text-[9px] font-semibold tracking-[0.16em] text-muted-foreground sm:text-[10px]">
        {ui.topStrip}
      </div>

      <header className="sticky top-0 z-30 border-b border-border bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1560px] items-center justify-between gap-5 px-5 py-4 lg:px-10 lg:py-5">
          <button
            onClick={() => setTab('sandbox')}
            className="flex items-center gap-3 text-left"
          >
            <span className="grid size-10 place-items-center rounded-full bg-foreground text-background">
              <Video className="size-4" />
            </span>
            <div>
              <p className="text-[15px] font-extrabold tracking-[0.13em] sm:text-[17px]">
                LTX LOCAL STUDIO
              </p>
              <p className="text-[8px] font-semibold tracking-[0.2em] text-muted-foreground sm:text-[9px]">
                {ui.console}
              </p>
            </div>
          </button>
          <div className="flex items-center gap-4">
            <Select
              value={locale}
              onValueChange={(value) => setLocale(value as Locale)}
            >
              <SelectTrigger
                aria-label="Language"
                className="h-10 w-[132px] rounded-none border-border bg-white text-[10px] font-bold tracking-[0.1em]"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="end" className="min-w-[150px]">
                <SelectItem value="zh-TW">繁體中文</SelectItem>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="ja">日本語</SelectItem>
              </SelectContent>
            </Select>
            <AccountMenu locale={locale} />
            <div className="hidden items-center gap-2 text-[10px] font-bold tracking-[0.1em] sm:flex">
              <span
                className={`size-2 rounded-full ${generating ? 'animate-pulse bg-[#ff6f91]' : backendOnline ? 'bg-[#25b6a6]' : 'bg-[#b8b8b2]'} shadow-[0_0_0_4px_rgba(37,182,166,.12)]`}
              />
              {visibleStatus}
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1560px] gap-6 px-5 py-6 lg:grid-cols-[210px_minmax(0,1fr)] lg:gap-10 lg:px-10 lg:py-10">
        <div className="-mx-5 lg:mx-0">
          <StageRail
            active={tab}
            statuses={stageProgress.statuses}
            locale={locale}
            onSelect={setTab}
          />
        </div>

        <div className="min-w-0">
        {tab === 'board' && (
          <StatusBoard
            plans={plan ? [plan] : []}
            locale={locale}
            onOpenStage={setTab}
          />
        )}

        {UNAVAILABLE_STAGES.includes(tab as StageKey) && (
          <section>
            <SectionTitle
              eyebrow={`${stageIndexOf(tab)} / ${stageNames[tab as StageKey]}`}
              title={ui.unavailableTitle}
              note={ui.unavailableNote}
            />
            <div className="grid min-h-64 place-items-center border border-dashed border-border bg-[#fafaf8] p-8 text-center">
              <div className="max-w-md space-y-4">
                <p className="text-sm text-muted-foreground">
                  {tab === 'keyframes'
                    ? ui.unavailableKeyframes
                    : tab === 'review'
                      ? ui.unavailableReview
                      : ui.unavailablePost}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-none"
                  onClick={() => setTab('board')}
                >
                  {ui.backToBoard}
                </Button>
              </div>
            </div>
          </section>
        )}

        {tab === 'breakdown' && (
          <section>
            <SectionTitle
              eyebrow={ui.breakdownEyebrow}
              title={ui.breakdownTitle}
              note={ui.breakdownNote}
            />
            <TimelineControls
              locale={locale}
              catalog={capabilities?.directing}
              value={timeline}
              onChange={setTimeline}
              request={generationRequest}
              onDuration={(value) => setSeconds(String(value))}
            />
          </section>
        )}

        {tab === 'sandbox' && (
          <section className="mb-6 flex flex-wrap items-center gap-4 border border-border bg-white p-5">
            <label className="min-w-64 text-xs font-bold">
              {ui.model}
              <Select
                value={model}
                disabled={generating || !models.length}
                onValueChange={(value) => value && setModel(value)}
              >
                <SelectTrigger className="mt-2 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {models.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.label} · {item.media_type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <p className="text-xs text-muted-foreground">
              {catalogError
                ? locale === 'zh-TW'
                  ? '無法讀取模型清單，請檢查服務後重新整理。'
                  : locale === 'en'
                    ? 'Model catalog unavailable. Check the service and reload.'
                    : 'モデル一覧を取得できません。接続を確認して再読込してください。'
                : locale === 'zh-TW'
                  ? '僅顯示主機已安裝並註冊的模型 · 帳號與 API 不隨模型更換'
                  : locale === 'en'
                    ? 'Installed host adapters only · Same account and API across models'
                    : '導入・登録済みモデルのみ表示 · アカウントとAPIは共通'}
            </p>
          </section>
        )}
        {tab === 'sandbox' &&
          model !== 'ltx23-distilled' &&
          models.find((item) => item.id === model) && (
            <ModelComposer
              key={model}
              model={models.find((item) => item.id === model)!}
              locale={locale}
            />
          )}
        {tab === 'sandbox' && model === 'ltx23-distilled' && (
          <section>
            <SectionTitle
              eyebrow={ui.createEyebrow}
              title={ui.createTitle}
              note={ui.createNote}
            />
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(400px,.82fr)]">
              <div className="space-y-6">
                <section className="overflow-hidden border border-border bg-[#101211] text-white">
                  <div className="flex items-center justify-between gap-4 border-b border-white/15 px-5 py-4">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="text-[10px] font-bold tracking-[0.18em]">
                        {ui.outputPreview}
                      </span>
                      <span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] text-white/65">
                        {formatMeta(selectedOutput.meta)}
                      </span>
                    </div>
                    <span className="hidden text-[10px] text-white/50 sm:block">
                      {selectedOutput.name}
                    </span>
                  </div>
                  <div className="relative aspect-video bg-black">
                    {selectedOutput.src ? (
                      <>
                        <video
                          key={selectedOutput.src}
                          className="h-full w-full object-contain"
                          controls
                          preload="metadata"
                          poster={selectedOutput.poster || undefined}
                          src={selectedOutput.src}
                        />
                        <span className="pointer-events-none absolute left-4 top-4 rounded-full bg-[#25b6a6] px-3 py-1 text-[9px] font-bold tracking-[0.14em] text-white">
                          {ui.outputPreview}
                        </span>
                      </>
                    ) : (
                      <div className="grid h-full place-items-center text-center text-white/50">
                        <div>
                          <Video className="mx-auto mb-4 size-8" />
                          <p className="text-xs">
                            {locale === 'zh-TW'
                              ? '你的第一支作品將顯示在這裡'
                              : locale === 'en'
                                ? 'Your first creation will appear here'
                                : '最初の作品がここに表示されます'}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-3 divide-x divide-white/10 border-t border-white/10 bg-white/[.035] text-xs">
                    <div className="px-5 py-4">
                      <span className="block text-[9px] tracking-[0.14em] text-white/45">
                        {ui.runtime}
                      </span>
                      <strong className="mt-1 block">
                        {formatRuntime(selectedOutput.runtime)}
                      </strong>
                    </div>
                    <div className="px-5 py-4">
                      <span className="block text-[9px] tracking-[0.14em] text-white/45">
                        {ui.precision}
                      </span>
                      <strong className="mt-1 block">
                        {precision.toUpperCase()}
                      </strong>
                    </div>
                    <div className="px-5 py-4">
                      <span className="block text-[9px] tracking-[0.14em] text-white/45">
                        {ui.attention}
                      </span>
                      <strong className="mt-1 block">
                        {attention.toUpperCase()}
                      </strong>
                    </div>
                  </div>
                </section>

                <section className="border border-border bg-white">
                  <div className="flex items-center justify-between border-b border-border px-5 py-4">
                    <div className="flex items-center gap-2">
                      <Settings2 className="size-4 text-[#e85578]" />
                      <h2 className="text-xs font-extrabold tracking-[0.13em]">
                        {ui.generationSettings}
                      </h2>
                    </div>
                    <button
                      onClick={() => {
                        setAspectRatio('16:9');
                        setSeconds('2');
                        setFps('24');
                        setSeed(42);
                      }}
                      className="flex items-center gap-2 text-[10px] font-bold tracking-[0.1em] text-muted-foreground hover:text-foreground"
                    >
                      <RotateCcw className="size-3" />
                      {ui.reset}
                    </button>
                  </div>
                  <div className="grid gap-px bg-border md:grid-cols-2 xl:grid-cols-3">
                    <label className="bg-white p-5">
                      <Label>{videoText.ratio}</Label>
                      <Select
                        value={aspectRatio}
                        onValueChange={(value) =>
                          value && setAspectRatio(value)
                        }
                        disabled={!capabilities}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.keys(
                            capabilities?.aspect_ratios || { '16:9': {} },
                          ).map((ratio) => (
                            <SelectItem key={ratio} value={ratio}>
                              {ratio}
                            </SelectItem>
                          ))}
                          {mode === 'i2v' && reference && (
                            <SelectItem value="source">
                              {mvText.source} · {reference.source_ratio}
                            </SelectItem>
                          )}
                        </SelectContent>
                      </Select>
                      <span className="mt-2 block text-[10px] text-muted-foreground">
                        {videoText.dimensions} · {width} × {height}
                      </span>
                    </label>
                    <div className="bg-white p-5">
                      <Label>{ui.videoDuration}</Label>
                      <Select
                        value={durationPreset}
                        onValueChange={(value) =>
                          value && setSeconds(value === 'custom' ? '' : value)
                        }
                      >
                        <SelectTrigger
                          aria-label={ui.videoDuration}
                          className="w-full"
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {durationPresets
                            .filter((value) => value <= maximumSeconds)
                            .map((value) => (
                              <SelectItem key={value} value={String(value)}>
                                {value} {ui.seconds}
                              </SelectItem>
                            ))}
                          <SelectItem value="custom">
                            {videoText.custom}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        aria-label={videoText.custom}
                        type="number"
                        min="0.125"
                        max={maximumSeconds}
                        step="any"
                        value={seconds}
                        onChange={(event) => setSeconds(event.target.value)}
                        className="mt-2 rounded-none"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        disabled={!capabilities}
                        className="mt-2 w-full rounded-none text-[10px]"
                        onClick={() => setSeconds(String(maximumSeconds))}
                      >
                        {videoText.maximum} · {maximumSeconds.toFixed(3)}s
                      </Button>
                      <span className="mt-2 block text-[10px] text-muted-foreground">
                        {ui.actual} {duration}s · {validFrames ? frames : '—'}{' '}
                        {ui.frameUnit}
                      </span>
                      <span className="mt-2 block text-[10px] text-[#a32e4a]">
                        {isSequence ? mvText.sequence : mvText.single}
                      </span>
                    </div>
                    <label className="bg-white p-5">
                      <Label>{ui.frameRate}</Label>
                      <Select
                        value={fps}
                        onValueChange={(value) => value && setFps(value)}
                      >
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {[8, 16, 24, 25, 30, 50, 60]
                            .filter(
                              (value) =>
                                !capabilities ||
                                (value >= capabilities.limits.fps_min &&
                                  value <= capabilities.limits.fps_max),
                            )
                            .map((value) => (
                              <SelectItem key={value} value={String(value)}>
                                {value} FPS
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                      <span className="mt-2 block text-[10px] text-muted-foreground">
                        {videoText.ceiling} · {maxFrames} {ui.frameUnit}
                      </span>
                    </label>
                    <label className="bg-white p-5">
                      <Label>{ui.inferenceSteps}</Label>
                      <Input value="8 + 3" disabled className="rounded-none" />
                    </label>
                    <label className="bg-white p-5">
                      <Label>{ui.cfgScale}</Label>
                      <Input
                        value="1 · Distilled"
                        readOnly
                        className="rounded-none"
                      />
                    </label>
                    <label className="bg-white p-5">
                      <Label>{ui.seed}</Label>
                      <Input
                        type="number"
                        value={seed}
                        onChange={(e) => setSeed(Number(e.target.value))}
                        className="rounded-none"
                      />
                    </label>
                    <label className="bg-white p-5">
                      <Label>{ui.precision}</Label>
                      <Select value={precision} disabled>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="bf16">BF16</SelectItem>
                        </SelectContent>
                      </Select>
                    </label>
                    <label className="bg-white p-5">
                      <Label>{ui.attention}</Label>
                      <Select value={attention} disabled>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="sdpa">SDPA</SelectItem>
                        </SelectContent>
                      </Select>
                    </label>
                  </div>
                  <div className="grid gap-x-8 px-5 md:grid-cols-2">
                    <ToggleRow
                      label={ui.upscaler}
                      note={ui.upscalerNote}
                      checked={upscaler}
                      onChange={setUpscaler}
                      disabled
                    />
                    <ToggleRow
                      label={ui.offload}
                      note={ui.offloadNote}
                      checked={offload}
                      onChange={setOffload}
                    />
                    <ToggleRow
                      label={ui.tiling}
                      note={ui.tilingNote}
                      checked={tiling}
                      onChange={setTiling}
                      disabled
                    />
                    <ToggleRow
                      label={
                        isSequence && timeline.music ? mvText.music : ui.audio
                      }
                      note={
                        isSequence && timeline.music
                          ? mvText.soundtrack
                          : ui.audioNote
                      }
                      checked={isSequence && timeline.music ? true : audio}
                      onChange={setAudio}
                      disabled={Boolean(isSequence && timeline.music)}
                    />
                  </div>
                  <div className="border-t border-border p-5">
                    <p className="text-[10px] leading-5 text-muted-foreground">
                      {transfer.fixed}
                    </p>
                    <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                      {videoText.resource}
                    </p>
                    {!capabilities && (
                      <output className="mt-2 block text-xs">
                        {videoText.loading}
                      </output>
                    )}
                    {capabilities && !validFrames && (
                      <p role="alert" className="mt-2 text-xs text-red-700">
                        {isSequence ? '0.125–180s' : videoText.invalid}
                      </p>
                    )}
                    {isSequence && (
                      <p className="mt-2 text-xs text-amber-800">
                        {mvText.note}
                      </p>
                    )}
                    <Button
                      variant="outline"
                      className="mt-3 rounded-none text-[10px]"
                      disabled={generating}
                      onClick={() => {
                        setTimeline({ ...emptyTimeline });
                        setAspectRatio('1:1');
                        setSeconds('0.667');
                        setFps('24');
                        setOffload(false);
                      }}
                    >
                      <Zap className="size-3" />
                      {videoText.quick}
                    </Button>
                  </div>
                </section>
                <TimelineControls
                  locale={locale}
                  catalog={capabilities?.directing}
                  value={timeline}
                  onChange={setTimeline}
                  request={generationRequest}
                  onDuration={(value) => setSeconds(String(value))}
                />
              </div>

              <aside className="space-y-6 xl:sticky xl:top-[122px] xl:self-start">
                <section className="border border-border bg-card">
                  <div className="border-b border-border px-6 py-5">
                    <div className="flex items-center gap-2">
                      <Sparkles className="size-4 text-[#e85578]" />
                      <h2 className="text-sm font-extrabold tracking-[0.1em]">
                        {ui.promptAndModel}
                      </h2>
                    </div>
                  </div>
                  <div className="space-y-5 p-6">
                    <div className="flex flex-wrap gap-2">
                      {promptPresets.map(([label, value], index) => (
                        <button
                          key={label}
                          onClick={() => setPrompt(value)}
                          className="border border-border px-3 py-2 text-[9px] font-bold tracking-[0.12em] hover:border-[#ff6f91] hover:bg-[#fff5f7]"
                        >
                          {[ui.cinematic, ui.portrait, ui.product][index]}
                        </button>
                      ))}
                    </div>
                    <label className="block">
                      <Label>{ui.prompt}</Label>
                      <Textarea
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        className="min-h-40 resize-none rounded-none bg-[#fafaf8] text-sm leading-6 shadow-none focus-visible:ring-[#ff6f91]/25"
                      />
                      <span className="mt-2 block text-right text-[10px] text-muted-foreground">
                        {prompt.length} {ui.characters}
                      </span>
                    </label>
                    <section className="space-y-3 border-t border-border pt-4">
                      <h3 className="text-xs font-bold">{mvText.director}</h3>
                      <DirectingControls
                        locale={locale}
                        catalog={capabilities?.directing}
                        value={directing}
                        onChange={setDirecting}
                      />
                    </section>
                    <section
                      aria-label={ui.negativePrompt}
                      className="border border-[#efc4d0] bg-[#fff8fa] p-4 text-[11px] leading-6"
                    >
                      <h3 className="font-bold text-[#a32e4a]">
                        {videoText.negativeTitle}
                      </h3>
                      <p className="mt-1">{videoText.negative}</p>
                      <p className="mt-2 text-muted-foreground">
                        {videoText.promptTip}
                      </p>
                    </section>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <label>
                        <Label>{ui.model}</Label>
                        <Input
                          value="LTX-2.3 Distilled"
                          readOnly
                          className="rounded-none"
                        />
                      </label>
                      <label>
                        <Label>{ui.mode}</Label>
                        <Select
                          value={mode}
                          onValueChange={(value) => {
                            if (!value) return;
                            setMode(value);
                            if (value === 't2v' && aspectRatio === 'source')
                              setAspectRatio('16:9');
                          }}
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="t2v">{ui.t2v}</SelectItem>
                            <SelectItem value="i2v">{ui.i2v}</SelectItem>
                            <SelectItem value="v2v" disabled>
                              {ui.v2v}
                            </SelectItem>
                          </SelectContent>
                        </Select>
                      </label>
                    </div>
                    {mode !== 't2v' && (
                      <div className="border border-dashed border-[#b8b8b2] bg-[#fafaf8] p-5 text-center">
                        <ImageIcon className="mx-auto size-5 text-[#25b6a6]" />
                        <p className="mt-2 text-xs font-bold">
                          {ui.chooseAsset}
                        </p>
                        <button
                          onClick={() => setTab('bible')}
                          className="mt-2 text-[10px] font-bold text-[#e85578] underline underline-offset-4"
                        >
                          {ui.openAssetLibrary}
                        </button>
                      </div>
                    )}
                    <input
                      ref={referenceInput}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      aria-label={mvText.imageImport}
                      onChange={(event) => {
                        void uploadReference(event.target.files?.[0]);
                        event.target.value = '';
                      }}
                    />
                    <Button
                      variant="outline"
                      className="w-full rounded-none text-xs"
                      disabled={referenceUploading || generating}
                      onClick={() => referenceInput.current?.click()}
                    >
                      <ImageIcon />
                      {referenceUploading ? mvText.loading : mvText.imageImport}
                    </Button>
                    {mode === 'i2v' && reference && (
                      <div className="border border-[#bfe8e3] p-3">
                        <img
                          src={`${API_BASE}${reference.url}`}
                          alt={reference.name}
                          className="max-h-32 w-full object-contain"
                        />
                        <p className="mt-2 truncate text-[10px]">
                          {transfer.selected}: {reference.name} ·{' '}
                          {reference.source_ratio}
                        </p>
                        <p className="mt-2 text-[10px] leading-5">
                          {mvText.aligned}{' '}
                          {reference.ratio_error_percent
                            ? `Δ ${reference.ratio_error_percent}%`
                            : ''}
                        </p>
                        <button
                          onClick={() => {
                            setReference(null);
                            if (aspectRatio === 'source')
                              setAspectRatio('16:9');
                          }}
                          className="mt-2 text-[10px] text-[#e85578] underline"
                        >
                          {transfer.remove}
                        </button>
                      </div>
                    )}
                    {mode === 'i2v' && (
                      <section className="grid gap-3 border border-border bg-[#fafaf8] p-4 sm:grid-cols-2">
                        <label className="text-[10px] font-bold">
                          {locale === 'zh-TW'
                            ? '圖片約束強度'
                            : locale === 'en'
                              ? 'Image conditioning strength'
                              : '画像条件の強さ'}
                          <Input
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={imageStrength}
                            onChange={(event) =>
                              setImageStrength(Number(event.target.value))
                            }
                            className="mt-2 rounded-none bg-white"
                          />
                          <span className="mt-1 block font-normal leading-5 text-muted-foreground">
                            {locale === 'zh-TW'
                              ? '建議 0.65–0.8；越低越能改背景，但人物也可能較鬆。'
                              : locale === 'en'
                                ? 'Try 0.65–0.8. Lower values free the background but may loosen identity.'
                                : '0.65～0.8推奨。低いほど背景は変わりやすく、人物も緩くなります。'}
                          </span>
                        </label>
                        <label className="text-[10px] font-bold">
                          {locale === 'zh-TW'
                            ? '參照背景處理'
                            : locale === 'en'
                              ? 'Reference background'
                              : '参照背景処理'}
                          <Select
                            value={referenceBackground}
                            onValueChange={(value) =>
                              value &&
                              setReferenceBackground(
                                value as 'source' | 'alpha_neutral',
                              )
                            }
                          >
                            <SelectTrigger className="mt-2 w-full bg-white">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="source">
                                {locale === 'zh-TW'
                                  ? '保留原圖'
                                  : locale === 'en'
                                    ? 'Keep source'
                                    : '元画像を保持'}
                              </SelectItem>
                              <SelectItem value="alpha_neutral">
                                {locale === 'zh-TW'
                                  ? '透明人物 PNG → 中性背景'
                                  : locale === 'en'
                                    ? 'Transparent subject PNG → neutral'
                                    : '透過人物PNG → 中立背景'}
                              </SelectItem>
                            </SelectContent>
                          </Select>
                          <span className="mt-1 block font-normal leading-5 text-muted-foreground">
                            {locale === 'zh-TW'
                              ? '中性模式只接受已去背的透明 PNG，避免把原照片背景一起鎖進影片。'
                              : locale === 'en'
                                ? 'Neutral mode requires transparent cutout PNGs so the source background is not locked into the video.'
                                : '中立モードには背景を除去した透過PNGが必要です。'}
                          </span>
                        </label>
                      </section>
                    )}
                    {mode === 'i2v' && (
                      <CharacterLock
                        locale={locale}
                        value={character}
                        current={reference}
                        primaryId={reference?.id}
                        onChange={setCharacter}
                        onPrimary={setReference}
                      />
                    )}
                    <div className="grid grid-cols-3 gap-px bg-border text-center">
                      <div className="bg-[#fafaf8] p-3">
                        <p className="text-[9px] text-muted-foreground">
                          {ui.duration}
                        </p>
                        <strong className="mt-1 block text-xs">
                          {duration}s
                        </strong>
                      </div>
                      <div className="bg-[#fafaf8] p-3">
                        <p className="text-[9px] text-muted-foreground">
                          {ui.canvas}
                        </p>
                        <strong className="mt-1 block text-xs">
                          {aspectRatio} · {width}×{height}
                        </strong>
                      </div>
                      <div className="bg-[#fafaf8] p-3">
                        <p className="text-[9px] text-muted-foreground">VRAM</p>
                        <strong className="mt-1 block text-xs">
                          {videoText.memory}
                        </strong>
                      </div>
                    </div>
                    <div
                      className={`border px-4 py-3 text-[10px] leading-5 ${backendOnline ? 'border-[#bfe8e3] bg-[#f0fbf9] text-[#11786f]' : 'border-[#e2e2de] bg-[#fafaf8] text-muted-foreground'}`}
                    >
                      <span className="font-bold">{ui.localEngine} · </span>
                      {backendOnline ? ui.engineConnected : ui.engineWaiting}
                    </div>
                    {generating || progress > 0 ? (
                      <div className="space-y-2">
                        <div className="flex justify-between text-[10px] font-bold tracking-[0.12em]">
                          <span>{visibleStatus}</span>
                          <span>{progress}%</span>
                        </div>
                        <Progress
                          value={progress}
                          className="h-1.5 rounded-none [&>div]:bg-[#25b6a6]"
                        />
                        {jobMessage && (
                          <p className="text-[10px] leading-4 text-muted-foreground">
                            {jobMessage}
                          </p>
                        )}
                      </div>
                    ) : null}
                    <p className="text-[10px] leading-5 text-muted-foreground">
                      {transfer.gpu}: {computeDevice || transfer.offline}
                      {generating && (
                        <>
                          <br />
                          {transfer.stage} · {transfer.elapsed}{' '}
                          {Math.round(elapsed)}s
                        </>
                      )}
                    </p>
                    {jobError && (
                      <div
                        role="alert"
                        className="border border-red-200 bg-red-50 px-4 py-3 text-[10px] leading-5 text-red-700"
                      >
                        <strong className="block">{ui.generationFailed}</strong>
                        {jobError}
                      </div>
                    )}
                    {capabilitiesFailed && (
                      <div
                        role="alert"
                        className="border border-red-200 p-3 text-xs text-red-700"
                      >
                        {ui.cannotConnect}
                        <Button
                          variant="outline"
                          onClick={() => location.reload()}
                          className="ml-2 rounded-none"
                        >
                          {locale === 'zh-TW'
                            ? '重新載入'
                            : locale === 'en'
                              ? 'Reload'
                              : '再読み込み'}
                        </Button>
                      </div>
                    )}
                    <Button
                      onClick={simulateGeneration}
                      disabled={!canSubmit}
                      className="h-12 w-full rounded-none bg-foreground text-[11px] font-bold tracking-[0.16em] text-background hover:bg-[#e85578]"
                    >
                      <Play className="size-3.5 fill-current" />
                      {generating ? ui.generatingVideo : ui.generateVideo}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={
                        !prompt.trim() ||
                        !settingsReady ||
                        !characterReady ||
                        (mode === 'i2v' && !reference)
                      }
                      onClick={() => {
                        setFactoryIncoming({
                          token: crypto.randomUUID(),
                          request: generationRequest,
                          bible: bibleFromRequest(generationRequest),
                        });
                        setTab('shoot');
                      }}
                      className="h-12 w-full rounded-none text-[11px] font-bold tracking-[0.12em]"
                    >
                      <Layers3 className="size-3.5" />
                      {ui.addToFactory}
                    </Button>
                    {canSubmit && (!settingsReady || !characterReady) && (
                      <p className="border-l-2 border-amber-500 pl-3 text-[10px] leading-5 text-amber-800">
                        {locale === 'zh-TW'
                          ? '可送出；若設定仍有衝突，後端會回傳明確欄位錯誤，不再無提示地鎖住按鈕。'
                          : locale === 'en'
                            ? 'Submission is enabled. Any remaining conflict will return an explicit server validation error instead of silently disabling the button.'
                            : '送信できます。残る設定エラーはボタンを無言で無効化せず、サーバーが明示します。'}
                      </p>
                    )}
                    {selectedOutput.src && (
                      <>
                        <a
                          href={selectedOutput.download || selectedOutput.src}
                          download={selectedOutput.name}
                          className="block border border-border p-3 text-center text-[11px] font-bold hover:border-[#e85578]"
                        >
                          {transfer.download} · MP4
                        </a>
                        <DeleteMediaButton
                          locale={locale}
                          kind="jobs"
                          id={selectedOutput.id}
                          name={selectedOutput.name}
                          onDeleted={() => removeOutput(selectedOutput.id)}
                        />
                      </>
                    )}
                    <p className="text-center text-[9px] leading-4 text-muted-foreground">
                      {ui.generateNote}
                    </p>
                  </div>
                </section>
                <section className="border border-border bg-[#171918] p-5 text-white">
                  <div className="mb-3 flex items-center gap-2 text-[10px] font-bold tracking-[0.14em] text-white/65">
                    <TerminalSquare className="size-4 text-[#25b6a6]" />
                    {ui.commandPreview}
                  </div>
                  <code className="block break-words font-mono text-[10px] leading-5 text-white/75">
                    {command}
                  </code>
                </section>
              </aside>
            </div>
          </section>
        )}

        {/* One mounted factory serves stage 00 and stage 03; two mounts would mean two plans. */}
        <div hidden={tab !== 'bible' && tab !== 'shoot'}>
          <SectionTitle
            eyebrow={tab === 'shoot' ? ui.shootEyebrow : ui.bibleEyebrow}
            title={tab === 'shoot' ? ui.shootTitle : ui.bibleTitle}
            note={tab === 'shoot' ? ui.shootNote : ui.bibleNote}
          />
          <ProductionFactory
            locale={locale}
            online={backendOnline}
            incoming={factoryIncoming}
            onIncomingConsumed={() => setFactoryIncoming(null)}
            onPlanChange={setPlan}
            section={tab === 'shoot' ? 'queue' : 'bible'}
          />
        </div>

        {tab === 'bible' && (
          <section>
            <SectionTitle
              eyebrow={ui.assetsEyebrow}
              title={ui.assetsTitle}
              note={ui.assetsNote}
            />
            <MediaLibrary
              locale={locale}
              onSelect={selectReference}
              onDelete={(id) => {
                if (reference?.id === id) {
                  setReference(null);
                  if (aspectRatio === 'source') setAspectRatio('16:9');
                }
                setCharacter((current) => ({
                  ...current,
                  references: current.references.filter(
                    (item) => item.asset.id !== id,
                  ),
                }));
                if (timeline.music?.id === id)
                  setTimeline((current) => ({
                    ...current,
                    music: null,
                    audioStart: 0,
                  }));
              }}
            />
            <div className="grid gap-6 lg:grid-cols-[1.35fr_.65fr]">
              <div>
                <div className="mb-4 flex items-center justify-between">
                  <p className="text-[10px] font-bold tracking-[0.15em]">
                    {ui.mediaReferences}
                  </p>
                  <Button
                    variant="outline"
                    className="rounded-none text-[10px] font-bold tracking-[0.12em]"
                  >
                    <FolderOpen className="size-3.5" />
                    {ui.openFolder}
                  </Button>
                </div>
                <div className="grid gap-px bg-border sm:grid-cols-2">
                  {outputItems
                    .flatMap((item) => [
                      {
                        id: `${item.id}-video`,
                        type: ui.video,
                        isVideo: true,
                        name: item.name,
                        src: item.poster!,
                        meta: item.meta,
                        path: `outputs/${item.name}`,
                      },
                      {
                        id: `${item.id}-image`,
                        type: ui.image,
                        isVideo: false,
                        name: item.poster!.split('/').pop()!,
                        src: item.poster!,
                        meta: ui.previewFrame,
                        path: `outputs/${item.poster!.split('/').pop()}`,
                      },
                    ])
                    .map((asset) => (
                      <article key={asset.id} className="group bg-white p-5">
                        <div className="relative aspect-video overflow-hidden bg-[#111]">
                          <img
                            src={asset.src}
                            alt={asset.name}
                            className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
                          />
                          <span className="absolute left-3 top-3 bg-white px-2 py-1 text-[9px] font-extrabold tracking-[0.15em]">
                            {asset.type}
                          </span>
                        </div>
                        <div className="mt-4 flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-xs font-bold">
                              {asset.name}
                            </p>
                            <p className="mt-1 text-[10px] text-muted-foreground">
                              {asset.meta}
                            </p>
                            <code className="mt-2 block truncate text-[9px] text-[#159c8f]">
                              {asset.path}
                            </code>
                          </div>
                          {asset.isVideo ? (
                            <FileVideo className="size-4 shrink-0 text-[#e85578]" />
                          ) : (
                            <FileImage className="size-4 shrink-0 text-[#25b6a6]" />
                          )}
                        </div>
                      </article>
                    ))}
                </div>
              </div>
              <aside className="space-y-6">
                <section className="border border-border bg-white">
                  <div className="border-b border-border px-5 py-4">
                    <h2 className="text-xs font-extrabold tracking-[0.13em]">
                      {ui.modelSources}
                    </h2>
                  </div>
                  <div className="divide-y divide-border">
                    {[
                      [
                        'LTX-2.3 22B Distilled 1.1',
                        'Hugging Face · Lightricks/LTX-2.3',
                        ui.primaryTransformer,
                      ],
                      [
                        'Gemma 3 12B',
                        'Hugging Face · google/gemma-3-12b-it',
                        ui.promptEncoder,
                      ],
                      [
                        'x2 Spatial Upscaler',
                        'LTX model package',
                        ui.detailRecovery,
                      ],
                    ].map(([name, source, note]) => (
                      <div key={name} className="p-5">
                        <div className="flex gap-3">
                          <Box className="mt-0.5 size-4 shrink-0 text-[#e85578]" />
                          <div>
                            <p className="text-xs font-bold">{name}</p>
                            <p className="mt-1 text-[10px] text-muted-foreground">
                              {source}
                            </p>
                            <p className="mt-2 text-[10px] leading-4 text-[#159c8f]">
                              {note}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
                <section className="border border-border bg-[#f7f7f4] p-5">
                  <div className="flex gap-3">
                    <HardDrive className="size-4 text-[#25b6a6]" />
                    <div>
                      <p className="text-xs font-bold">{ui.sourcePolicy}</p>
                      <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
                        {ui.sourcePolicyNote}
                      </p>
                    </div>
                  </div>
                </section>
              </aside>
            </div>
          </section>
        )}

        {tab === 'assembly' && (
          <section>
            <SectionTitle
              eyebrow={ui.outputsEyebrow}
              title={ui.outputsTitle}
              note={ui.outputsNote}
            />
            <div className="grid gap-6 xl:grid-cols-2">
              {liveOutputs.map((item, index) => (
                <article
                  key={item.id}
                  className="overflow-hidden border border-border bg-white"
                >
                  <div className="flex flex-wrap items-center justify-end gap-3 border-b border-border px-6 py-3">
                    <a
                      href={item.download || item.src}
                      download={item.name}
                      className="text-[11px] font-bold hover:text-[#e85578]"
                    >
                      {transfer.download} · MP4
                    </a>
                    <DeleteMediaButton
                      locale={locale}
                      kind="jobs"
                      id={item.id}
                      name={item.name}
                      onDeleted={() => removeOutput(item.id)}
                    />
                  </div>
                  <div className="relative aspect-video bg-black">
                    <video
                      className="h-full w-full object-contain"
                      controls
                      preload="metadata"
                      poster={item.poster || undefined}
                      src={item.src}
                    />
                    <span className="absolute left-4 top-4 bg-[#25b6a6] px-3 py-1 text-[9px] font-bold tracking-[0.12em] text-white">
                      RUN 0{index + 1} · {ui.runPassed}
                    </span>
                  </div>
                  <div className="p-6">
                    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                      <div>
                        <p className="text-base font-extrabold tracking-[0.03em]">
                          {item.name}
                        </p>
                        <p className="mt-2 text-xs text-muted-foreground">
                          {formatMeta(item.meta)}
                        </p>
                      </div>
                      <Button
                        onClick={() => {
                          setSelectedOutput(item);
                          setTab('sandbox');
                        }}
                        variant="outline"
                        className="rounded-none text-[10px] font-bold tracking-[0.1em]"
                      >
                        {ui.useAsPreview}
                        <ChevronRight className="size-3.5" />
                      </Button>
                    </div>
                    <div className="mt-6 grid grid-cols-3 gap-px bg-border">
                      <div className="bg-[#fafaf8] p-4">
                        <Label>{ui.runtime}</Label>
                        <strong className="text-sm">
                          {formatRuntime(item.runtime)}
                        </strong>
                      </div>
                      <div className="bg-[#fafaf8] p-4">
                        <Label>{ui.fileSize}</Label>
                        <strong className="text-sm">{item.size}</strong>
                      </div>
                      <div className="bg-[#fafaf8] p-4">
                        <Label>{ui.codec}</Label>
                        <strong className="text-sm">H.264/AAC</strong>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            {liveOutputs.length === 0 && (
              <p className="border border-dashed border-border bg-white p-12 text-center text-sm text-muted-foreground">
                {locale === 'zh-TW'
                  ? '尚無產出，完成生成後會顯示於此。'
                  : locale === 'en'
                    ? 'No outputs yet. Completed generations will appear here.'
                    : '作品はありません。生成が完了するとここに表示されます。'}
              </p>
            )}
            <div className="mt-6 border border-border bg-[#171918] p-6 text-white">
              <div className="grid gap-5 md:grid-cols-[auto_1fr_auto] md:items-center">
                <div className="grid size-12 place-items-center rounded-full border border-white/15">
                  <Check className="size-5 text-[#25b6a6]" />
                </div>
                <div>
                  <p className="text-sm font-bold">{ui.workflowConnected}</p>
                  <p className="mt-1 text-[11px] leading-5 text-white/55">
                    {ui.workflowNote}
                  </p>
                </div>
                <span className="text-[10px] font-bold tracking-[0.14em] text-[#76d5cb]">
                  {liveOutputs.length} {ui.outputCount}
                </span>
              </div>
            </div>
          </section>
        )}

        {tab === 'workstation' && (
          <section>
            <SectionTitle
              eyebrow={ui.envEyebrow}
              title={ui.envTitle}
              note={ui.envNote}
            />
            <p className="mb-4 border border-border bg-white p-4 text-xs">
              {transfer.gpu}:{' '}
              <strong>{computeDevice || transfer.offline}</strong>
            </p>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat label={ui.accelerator} value="NVIDIA GB10" accent />
              <Stat label={ui.unifiedMemory} value="121.69 GiB" />
              <Stat label={ui.peakResident} value="~42 GiB" />
              <Stat label={ui.architecture} value="ARM64" />
            </div>
            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              <section className="border border-border bg-white">
                <div className="border-b border-border px-5 py-4">
                  <div className="flex items-center gap-2">
                    <Cpu className="size-4 text-[#e85578]" />
                    <h2 className="text-xs font-extrabold tracking-[0.13em]">
                      {ui.runtimeStack}
                    </h2>
                  </div>
                </div>
                <div className="grid gap-px bg-border sm:grid-cols-2">
                  {[
                    ['CUDA', '13.0', Zap],
                    ['PyTorch', '2.11', Layers3],
                    [ui.precision, 'BF16', CircleGauge],
                    [ui.attention, 'SDPA', Gauge],
                    [ui.swap, '0 GiB', MemoryStick],
                    [ui.output, 'H.264 + AAC', FileVideo],
                  ].map(([label, value, Icon]) => {
                    const I = Icon as typeof Cpu;
                    return (
                      <div key={label as string} className="bg-white p-5">
                        <I className="mb-4 size-4 text-[#25b6a6]" />
                        <Label>{label as string}</Label>
                        <strong className="text-lg">{value as string}</strong>
                      </div>
                    );
                  })}
                </div>
              </section>
              <section className="border border-border bg-white">
                <div className="border-b border-border px-5 py-4">
                  <div className="flex items-center gap-2">
                    <Clock3 className="size-4 text-[#e85578]" />
                    <h2 className="text-xs font-extrabold tracking-[0.13em]">
                      {ui.measuredPerformance}
                    </h2>
                  </div>
                </div>
                <div className="p-6">
                  <div className="space-y-6">
                    <div>
                      <div className="mb-2 flex justify-between text-xs font-bold">
                        <span>384 × 256 · 17F</span>
                        <span>33.69s</span>
                      </div>
                      <div className="h-2 bg-[#efefec]">
                        <div className="h-full w-[73%] bg-[#25b6a6]" />
                      </div>
                    </div>
                    <div>
                      <div className="mb-2 flex justify-between text-xs font-bold">
                        <span>768 × 512 · 49F</span>
                        <span>46.18s</span>
                      </div>
                      <div className="h-2 bg-[#efefec]">
                        <div className="h-full w-full bg-[#ff6f91]" />
                      </div>
                    </div>
                  </div>
                  <div className="mt-8 border-t border-border pt-5 text-[10px] leading-5 text-muted-foreground">
                    {ui.performanceNote}
                  </div>
                </div>
              </section>
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
              <section className="border border-border bg-white">
                <div className="border-b border-border px-5 py-4">
                  <div className="flex items-center gap-2">
                    <FolderOpen className="size-4 text-[#e85578]" />
                    <h2 className="text-xs font-extrabold tracking-[0.13em]">
                      {ui.localPaths}
                    </h2>
                  </div>
                </div>
                <div className="divide-y divide-border font-mono text-[10px]">
                  {[
                    [ui.repository, 'work/ltx-2.3/LTX-2'],
                    [ui.launcher, 'outputs/run-ltx-2.3.sh'],
                    [ui.guide, 'outputs/LTX-2.3-使用說明.md'],
                    [ui.mainOutput, 'outputs/ltx-2.3-512x768.mp4'],
                    [ui.smokeTest, 'outputs/ltx-2.3-smoke.mp4'],
                  ].map(([label, path]) => (
                    <div
                      key={label}
                      className="grid gap-2 p-5 sm:grid-cols-[120px_1fr]"
                    >
                      <span className="font-sans font-bold text-muted-foreground">
                        {label}
                      </span>
                      <span className="break-all text-[#168f84]">{path}</span>
                    </div>
                  ))}
                </div>
              </section>
              <section className="border border-border bg-[#171918] text-white">
                <div className="border-b border-white/10 px-5 py-4">
                  <div className="flex items-center gap-2">
                    <Code2 className="size-4 text-[#25b6a6]" />
                    <h2 className="text-xs font-extrabold tracking-[0.13em]">
                      {ui.currentCommand}
                    </h2>
                  </div>
                </div>
                <div className="p-6">
                  <code className="block break-words font-mono text-[11px] leading-6 text-white/72">
                    {command}
                  </code>
                  <div className="mt-6 border-t border-white/10 pt-5">
                    <p className="text-[9px] font-bold tracking-[0.14em] text-white/40">
                      {ui.compatibility}
                    </p>
                    <p className="mt-2 text-[10px] leading-5 text-white/55">
                      {ui.compatibilityNote}
                    </p>
                  </div>
                </div>
              </section>
            </div>
          </section>
        )}
        </div>
      </div>

      <footer className="mt-10 border-t border-border bg-[#f7f7f4]">
        <div className="mx-auto flex max-w-[1560px] flex-col justify-between gap-4 px-5 py-7 text-[9px] font-bold tracking-[0.13em] text-muted-foreground sm:flex-row lg:px-10">
          <span>{ui.footerLeft}</span>
          <span className="flex items-center gap-2">
            <WandSparkles className="size-3 text-[#e85578]" />
            {ui.footerRight}
          </span>
        </div>
      </footer>
    </main>
  );
}
