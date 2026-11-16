'use client';

import { useEffect, useMemo, useState } from 'react';
import JSZip from 'jszip';
import { Download, ImagePlus, Mic2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  buildMotionCanvasScene,
  buildMotionCanvasReadme,
  motionCanvasDependencies,
  motionCanvasMacLauncher,
  motionCanvasViteConfig,
  parseMotionCanvasTimeline,
} from '@/lib/motion-canvas-project';
import { serviceFetch } from '@/lib/service-session';
import type { Asset } from '@/components/media-library';
import type { InstalledModel } from '@/components/model-composer';

type Locale = 'zh-TW' | 'en' | 'ja';
type ToolResult = {
  beats?: { duration_seconds?: number; beats?: number[]; sections?: number[] };
  alignment?: unknown;
  cached?: boolean;
};

const copy = {
  'zh-TW': {
    title: 'Motion Canvas 工作台',
    note: '建立可在 Motion Canvas Editor 預覽與渲染的 TypeScript 專案。這是動畫工具，不是 AI 模型。',
    project: '專案與腳本',
    projectName: '專案名稱',
    headline: '片頭標題',
    script: '旁白／畫面腳本',
    canvas: '畫布與時間',
    width: '寬度',
    height: '高度',
    fps: '幀率',
    duration: '秒數',
    language: '內容語言',
    theme: '視覺主題',
    captions: '建立字幕層',
    lipsync: '保留角色嘴型軌',
    assets: '素材',
    voice: '旁白音訊',
    character: '角色／主視覺',
    none: '未選擇',
    tools: '模型與工具',
    analyze: 'Whisper 對時／節拍分析',
    analyzing: '分析中…',
    analyzed: '分析完成',
    imageTool: '前往圖片模型',
    imageNote:
      '使用 Z-Image 產生素材，或以 Qwen 編修角色與插圖。返回 Motion Canvas 前請先下載目前專案草稿。',
    export: '下載 Motion Canvas 專案',
    exporting: '打包中…',
    exportNote:
      'macOS 解壓後請按住 Control 點擊（或右鍵點擊）start-mac.command，選「打開」；首次不要直接雙擊。',
    failed: '操作失敗，請檢查素材與服務。',
    editorLimit: '第一階段採互動式 Editor；背景一鍵 MP4 會在第二階段加入。',
  },
  en: {
    title: 'Motion Canvas workspace',
    note: 'Build a TypeScript project for preview and rendering in Motion Canvas Editor. This is an animation tool, not an AI model.',
    project: 'Project and script',
    projectName: 'Project name',
    headline: 'Opening title',
    script: 'Narration / visual script',
    canvas: 'Canvas and timing',
    width: 'Width',
    height: 'Height',
    fps: 'Frame rate',
    duration: 'Seconds',
    language: 'Content language',
    theme: 'Visual theme',
    captions: 'Create caption layer',
    lipsync: 'Reserve character lip-sync track',
    assets: 'Assets',
    voice: 'Voice-over audio',
    character: 'Character / key visual',
    none: 'None',
    tools: 'Models and tools',
    analyze: 'Whisper alignment / beat analysis',
    analyzing: 'Analyzing…',
    analyzed: 'Analysis complete',
    imageTool: 'Open image model',
    imageNote:
      'Generate assets with Z-Image or edit characters and illustrations with Qwen. Download the current project draft before leaving Motion Canvas.',
    export: 'Download Motion Canvas project',
    exporting: 'Packaging…',
    exportNote:
      'On macOS, unzip, Control-click or right-click start-mac.command, then choose Open. Do not double-click it the first time.',
    failed: 'Operation failed. Check the asset and service.',
    editorLimit:
      'Phase one uses the interactive Editor; background one-click MP4 rendering arrives in phase two.',
  },
  ja: {
    title: 'Motion Canvas ワークスペース',
    note: 'Motion Canvas Editor でプレビュー・書き出しできる TypeScript プロジェクトを作成します。AIモデルではなくアニメーションツールです。',
    project: 'プロジェクトと台本',
    projectName: 'プロジェクト名',
    headline: '冒頭タイトル',
    script: 'ナレーション／映像台本',
    canvas: 'キャンバスと時間',
    width: '幅',
    height: '高さ',
    fps: 'フレームレート',
    duration: '秒数',
    language: '言語',
    theme: 'テーマ',
    captions: '字幕レイヤーを作成',
    lipsync: '口パク用トラックを予約',
    assets: '素材',
    voice: 'ナレーション音声',
    character: 'キャラクター／メイン画像',
    none: '未選択',
    tools: 'モデルとツール',
    analyze: 'Whisper同期／ビート解析',
    analyzing: '解析中…',
    analyzed: '解析完了',
    imageTool: '画像モデルを開く',
    imageNote:
      'Z-Imageで素材を生成、Qwenでキャラクターやイラストを編集できます。移動前に現在のプロジェクト草稿を保存してください。',
    export: 'Motion Canvas プロジェクトをダウンロード',
    exporting: '作成中…',
    exportNote:
      'macOSでは展開後、start-mac.commandをControlクリック（または右クリック）して「開く」を選択してください。初回はダブルクリックしないでください。',
    failed: '操作に失敗しました。素材とサービスを確認してください。',
    editorLimit:
      '第1段階は対話型Editorです。バックグラウンドのワンクリックMP4は第2段階で追加します。',
  },
} as const;

const safeName = (value: string, fallback: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '') || fallback;
const safeFile = (value: string, fallback: string) =>
  value.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^[-.]+/, '') || fallback;

export function MotionCanvasComposer({
  locale,
  models,
  onSelectModel,
}: {
  locale: Locale;
  models: InstalledModel[];
  onSelectModel: (id: string) => void;
}) {
  const t = copy[locale];
  const [assets, setAssets] = useState<Asset[]>([]);
  const [name, setName] = useState('ai-teaching-video');
  const [headline, setHeadline] = useState(
    locale === 'zh-TW' ? '建立你的 AI 員工' : 'Build your AI employee',
  );
  const [script, setScript] = useState('');
  const [width, setWidth] = useState(1080);
  const [height, setHeight] = useState(1080);
  const [fps, setFps] = useState(30);
  const [duration, setDuration] = useState(60);
  const [language, setLanguage] = useState(locale);
  const [theme, setTheme] = useState('paper');
  const [captions, setCaptions] = useState(true);
  const [lipsync, setLipsync] = useState(true);
  const [audioId, setAudioId] = useState('');
  const [characterId, setCharacterId] = useState('');
  const [analysis, setAnalysis] = useState<ToolResult | null>(null);
  const [busy, setBusy] = useState<'analyze' | 'export' | ''>('');
  const [error, setError] = useState('');
  const imageModels = useMemo(
    () =>
      models.filter((item) => item.media_type === 'image' && item.available),
    [models],
  );
  const audioAssets = assets.filter((item) => item.kind === 'audio');
  const imageAssets = assets.filter((item) => item.kind === 'image');

  useEffect(() => {
    const abort = new AbortController();
    serviceFetch('/api/assets', { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const data = (await response.json()) as { assets?: Asset[] };
        if (!abort.signal.aborted) setAssets(data.assets || []);
      })
      .catch(() => {
        if (!abort.signal.aborted) setError(t.failed);
      });
    return () => abort.abort();
  }, [t.failed]);

  const analyze = async () => {
    if (!audioId) return;
    setBusy('analyze');
    setError('');
    try {
      const response = await serviceFetch('/api/v1/audio/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_id: audioId,
          lyrics: script || undefined,
          language,
        }),
      });
      const result = (await response.json()) as ToolResult & { error?: string };
      if (!response.ok) throw new Error(result.error || t.failed);
      setAnalysis(result);
      const measured = Number(result.beats?.duration_seconds);
      if (Number.isFinite(measured) && measured > 0)
        setDuration(Math.ceil(measured));
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : t.failed);
    } finally {
      setBusy('');
    }
  };

  const addAsset = async (
    zip: JSZip,
    asset: Asset | undefined,
    preferred: string,
  ) => {
    if (!asset) return null;
    const response = await serviceFetch(asset.url);
    if (!response.ok) throw new Error(t.failed);
    const extension = asset.name.includes('.')
      ? asset.name.split('.').pop()!
      : preferred.split('.').pop()!;
    const filename = safeFile(
      `${preferred.replace(/\.[^.]+$/, '')}.${extension}`,
      preferred,
    );
    zip.file(`src/assets/${filename}`, await response.blob());
    return filename;
  };

  const exportProject = async () => {
    setBusy('export');
    setError('');
    try {
      const projectName = safeName(name, 'motion-canvas-video');
      const zip = new JSZip();
      const audioAsset = assets.find((item) => item.id === audioId);
      const characterAsset = assets.find((item) => item.id === characterId);
      const audioFile = await addAsset(zip, audioAsset, 'voice.wav');
      const characterFile = await addAsset(
        zip,
        characterAsset,
        'character.png',
      );
      const palette =
        theme === 'dark'
          ? {
              bg: '#101211',
              ink: '#f7f2e8',
              accent: '#ff6f91',
              paper: '#242826',
            }
          : theme === 'minimal'
            ? {
                bg: '#ffffff',
                ink: '#171918',
                accent: '#159c8f',
                paper: '#f3f4f2',
              }
            : {
                bg: '#f6f1e6',
                ink: '#171918',
                accent: '#b85c3d',
                paper: '#eadfc9',
              };
      const timeline = parseMotionCanvasTimeline(script, duration, headline);
      const manifest = {
        schema: 'ltx-motion-canvas-v1',
        projectName,
        headline,
        script,
        width,
        height,
        fps,
        duration,
        language,
        theme,
        captions,
        lipsync,
        timeline,
        assets: {
          audio: audioAsset?.id || null,
          character: characterAsset?.id || null,
        },
        tools: {
          audioAnalysis: analysis,
          imageModels: imageModels.map((item) => item.id),
        },
      };
      zip.file(
        'package.json',
        JSON.stringify(
          {
            name: projectName,
            private: true,
            type: 'module',
            scripts: {
              start: 'vite --host 127.0.0.1 --port 9000 --strictPort',
              build: 'vite build',
            },
            dependencies: motionCanvasDependencies,
          },
          null,
          2,
        ),
      );
      zip.file('vite.config.ts', motionCanvasViteConfig);
      zip.file(
        'tsconfig.json',
        JSON.stringify(
          {
            compilerOptions: {
              target: 'ES2022',
              module: 'ESNext',
              moduleResolution: 'Bundler',
              strict: true,
              jsx: 'react-jsx',
              jsxImportSource: '@motion-canvas/2d/lib',
            },
            include: ['src'],
          },
          null,
          2,
        ),
      );
      const audioImport = audioFile
        ? `import voice from './assets/${audioFile}';\n`
        : '';
      zip.file(
        'src/project.ts',
        `import {makeProject} from '@motion-canvas/core';\nimport main from './scenes/main?scene';\n${audioImport}export default makeProject({scenes: [main]${audioFile ? ', audio: voice' : ''}});\n`,
      );
      zip.file(
        'src/scenes/main.tsx',
        buildMotionCanvasScene({
          headline,
          width,
          height,
          duration,
          palette,
          cues: timeline,
          characterFile,
        }),
      );
      zip.file('project.manifest.json', JSON.stringify(manifest, null, 2));
      zip.file('start-mac.command', motionCanvasMacLauncher, {
        unixPermissions: 0o755,
      });
      zip.file(
        'README.md',
        buildMotionCanvasReadme(headline),
      );
      const blob = await zip.generateAsync({
        type: 'blob',
        compression: 'DEFLATE',
        platform: 'UNIX',
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${projectName}.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (issue) {
      setError(issue instanceof Error ? issue.message : t.failed);
    } finally {
      setBusy('');
    }
  };

  return (
    <section className="space-y-6">
      <div className="border border-border bg-white p-6">
        <div className="flex items-start gap-3">
          <Sparkles className="mt-1 size-5 text-[#e85578]" />
          <div>
            <h2 className="text-xl font-extrabold">{t.title}</h2>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-muted-foreground">
              {t.note}
            </p>
            <p className="mt-2 text-xs text-amber-800">{t.editorLimit}</p>
          </div>
        </div>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1.25fr_.75fr]">
        <div className="space-y-6">
          <section className="border border-border bg-white p-6">
            <h3 className="mb-5 text-sm font-extrabold">{t.project}</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-xs font-bold">
                {t.projectName}
                <Input
                  className="mt-2 rounded-none"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label className="text-xs font-bold">
                {t.headline}
                <Input
                  className="mt-2 rounded-none"
                  value={headline}
                  onChange={(e) => setHeadline(e.target.value)}
                />
              </label>
            </div>
            <label className="mt-4 block text-xs font-bold">
              {t.script}
              <Textarea
                className="mt-2 min-h-56 rounded-none"
                maxLength={12000}
                value={script}
                onChange={(e) => setScript(e.target.value)}
              />
            </label>
          </section>
          <section className="border border-border bg-white p-6">
            <h3 className="mb-5 text-sm font-extrabold">{t.canvas}</h3>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="text-xs font-bold">
                {t.width}
                <Input
                  type="number"
                  min={320}
                  max={3840}
                  className="mt-2 rounded-none"
                  value={width}
                  onChange={(e) => setWidth(Number(e.target.value))}
                />
              </label>
              <label className="text-xs font-bold">
                {t.height}
                <Input
                  type="number"
                  min={320}
                  max={3840}
                  className="mt-2 rounded-none"
                  value={height}
                  onChange={(e) => setHeight(Number(e.target.value))}
                />
              </label>
              <label className="text-xs font-bold">
                {t.fps}
                <Select
                  value={String(fps)}
                  onValueChange={(value) => value && setFps(Number(value))}
                >
                  <SelectTrigger className="mt-2 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[24, 25, 30, 50, 60].map((value) => (
                      <SelectItem key={value} value={String(value)}>
                        {value}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label className="text-xs font-bold">
                {t.duration}
                <Input
                  type="number"
                  min={1}
                  max={1800}
                  className="mt-2 rounded-none"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                />
              </label>
              <label className="text-xs font-bold">
                {t.language}
                <Select
                  value={language}
                  onValueChange={(value) => value && setLanguage(value)}
                >
                  <SelectTrigger className="mt-2 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="zh-TW">繁體中文</SelectItem>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="ja">日本語</SelectItem>
                  </SelectContent>
                </Select>
              </label>
              <label className="text-xs font-bold">
                {t.theme}
                <Select
                  value={theme}
                  onValueChange={(value) => value && setTheme(value)}
                >
                  <SelectTrigger className="mt-2 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="paper">Paper</SelectItem>
                    <SelectItem value="minimal">Minimal</SelectItem>
                    <SelectItem value="dark">Dark</SelectItem>
                  </SelectContent>
                </Select>
              </label>
            </div>
            <div className="mt-5 flex flex-wrap gap-6 text-xs font-bold">
              <label>
                {t.captions}
                <Switch
                  className="ml-3"
                  checked={captions}
                  onCheckedChange={setCaptions}
                />
              </label>
              <label>
                {t.lipsync}
                <Switch
                  className="ml-3"
                  checked={lipsync}
                  onCheckedChange={setLipsync}
                />
              </label>
            </div>
          </section>
        </div>
        <aside className="space-y-6">
          <section className="border border-border bg-white p-6">
            <h3 className="mb-5 text-sm font-extrabold">{t.assets}</h3>
            <label className="block text-xs font-bold">
              {t.voice}
              <Select
                value={audioId || 'none'}
                onValueChange={(value) =>
                  setAudioId(value === 'none' ? '' : value!)
                }
              >
                <SelectTrigger className="mt-2 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t.none}</SelectItem>
                  {audioAssets.map((asset) => (
                    <SelectItem key={asset.id} value={asset.id}>
                      {asset.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="mt-4 block text-xs font-bold">
              {t.character}
              <Select
                value={characterId || 'none'}
                onValueChange={(value) =>
                  setCharacterId(value === 'none' ? '' : value!)
                }
              >
                <SelectTrigger className="mt-2 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">{t.none}</SelectItem>
                  {imageAssets.map((asset) => (
                    <SelectItem key={asset.id} value={asset.id}>
                      {asset.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
          </section>
          <section className="border border-border bg-white p-6">
            <h3 className="mb-4 text-sm font-extrabold">{t.tools}</h3>
            <Button
              type="button"
              variant="outline"
              disabled={!audioId || busy === 'analyze'}
              onClick={() => void analyze()}
              className="w-full rounded-none"
            >
              <Mic2 className="size-4" />
              {busy === 'analyze'
                ? t.analyzing
                : analysis
                  ? t.analyzed
                  : t.analyze}
            </Button>
            <p className="mt-3 text-[10px] leading-5 text-muted-foreground">
              {analysis
                ? `${Math.round(analysis.beats?.duration_seconds || duration)}s · ${analysis.beats?.beats?.length || 0} beats · ${analysis.beats?.sections?.length || 0} sections`
                : 'Whisper large-v3 / stable-ts / librosa'}
            </p>
            <div className="my-5 border-t border-border" />
            <p className="text-[10px] leading-5 text-muted-foreground">
              {t.imageNote}
            </p>
            <div className="mt-3 grid gap-2">
              {imageModels.map((item) => (
                <Button
                  key={item.id}
                  type="button"
                  variant="outline"
                  onClick={() => onSelectModel(item.id)}
                  className="justify-start rounded-none"
                >
                  <ImagePlus className="size-4" />
                  {t.imageTool} · {item.label}
                </Button>
              ))}
            </div>
          </section>
          <section className="border border-[#e85578] bg-white p-6">
            <Button
              type="button"
              disabled={busy === 'export' || !headline.trim()}
              onClick={() => void exportProject()}
              className="h-12 w-full rounded-none"
            >
              <Download className="size-4" />
              {busy === 'export' ? t.exporting : t.export}
            </Button>
            <p className="mt-3 text-[10px] leading-5 text-muted-foreground">
              {t.exportNote}
            </p>
            {error && (
              <p role="alert" className="mt-3 text-xs text-red-700">
                {error}
              </p>
            )}
          </section>
        </aside>
      </div>
    </section>
  );
}
