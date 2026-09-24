export const motionCanvasDependencies = {
  '@motion-canvas/2d': '3.17.2',
  '@motion-canvas/core': '3.17.2',
  '@motion-canvas/ffmpeg': '3.17.2',
  '@motion-canvas/ui': '3.17.2',
  '@motion-canvas/vite-plugin': '3.17.2',
  vite: '5.4.21',
  typescript: '5.9.3',
} as const;

// Motion Canvas 3.17 ships CommonJS plugins. Node.js 24 exposes their default
// exports through an extra `default` layer when Vite loads an ESM config.
// Unwrapping both shapes keeps generated projects working on older Node.js
// releases and on the Node.js 24 runtime currently recommended by the studio.
export const motionCanvasViteConfig = `import {defineConfig, type PluginOption} from 'vite';
import motionCanvasModule from '@motion-canvas/vite-plugin';
import ffmpegModule from '@motion-canvas/ffmpeg';

const unwrapPlugin = (value: unknown) => {
  let candidate = value;
  while (
    typeof candidate !== 'function' &&
    candidate !== null &&
    typeof candidate === 'object' &&
    'default' in candidate
  ) {
    candidate = candidate.default;
  }
  if (typeof candidate !== 'function') {
    throw new TypeError('Unable to load a Motion Canvas Vite plugin.');
  }
  return candidate as () => PluginOption;
};

const motionCanvas = unwrapPlugin(motionCanvasModule);
const ffmpeg = unwrapPlugin(ffmpegModule);

export default defineConfig({plugins: [motionCanvas(), ffmpeg()]});
`;

export type MotionCanvasCue = {
  start: number;
  end: number;
  text: string;
};

type MotionCanvasPalette = {
  bg: string;
  ink: string;
  accent: string;
  paper: string;
};

const metadataLine = /^\[(?:ar|al|ti|au|by|re|ve|length):/i;
const timestamp = /\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/g;

const fractionSeconds = (value = '') =>
  value ? Number(value.padEnd(3, '0').slice(0, 3)) / 1000 : 0;

export function parseMotionCanvasTimeline(
  script: string,
  duration: number,
  fallback: string,
): MotionCanvasCue[] {
  const safeDuration = Math.max(1, duration);
  const offsetMatch = script.match(/^\[offset:([+-]?\d+)\]/im);
  const offset = offsetMatch ? Number(offsetMatch[1]) / 1000 : 0;
  const timed: Array<{ start: number; text: string }> = [];
  const untimed: string[] = [];

  for (const rawLine of script.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || metadataLine.test(line) || /^\[offset:/i.test(line)) continue;
    const matches = [...line.matchAll(timestamp)];
    const text = line.replace(timestamp, '').trim();
    if (matches.length && text) {
      for (const match of matches) {
        const start =
          Number(match[1]) * 60 +
          Number(match[2]) +
          fractionSeconds(match[3]) +
          offset;
        if (Number.isFinite(start) && start >= 0 && start < safeDuration) {
          timed.push({ start, text });
        }
      }
    } else if (text) {
      untimed.push(text);
    }
  }

  if (timed.length) {
    timed.sort((a, b) => a.start - b.start);
    return timed.map((cue, index) => ({
      start: cue.start,
      end: Math.max(
        cue.start + 0.1,
        Math.min(safeDuration, timed[index + 1]?.start ?? safeDuration),
      ),
      text: cue.text,
    }));
  }

  const lines = untimed.length ? untimed : [fallback];
  const span = safeDuration / lines.length;
  return lines.map((text, index) => ({
    start: index * span,
    end: index === lines.length - 1 ? safeDuration : (index + 1) * span,
    text,
  }));
}

export function buildMotionCanvasScene({
  headline,
  width,
  height,
  duration,
  palette,
  cues,
  characterFile,
}: {
  headline: string;
  width: number;
  height: number;
  duration: number;
  palette: MotionCanvasPalette;
  cues: MotionCanvasCue[];
  characterFile: string | null;
}) {
  const characterImport = characterFile
    ? `import character from '../assets/${characterFile}';\n`
    : '';
  const characterRef = characterFile
    ? `  const characterImage = createRef<Img>();\n`
    : '';
  const characterNode = characterFile
    ? `<Rect width={${Math.round(width * 0.3)}} height={${Math.round(height * 0.5)}} x={-${Math.round(width * 0.3)}} y={${Math.round(height * 0.08)}} radius={28} clip fill="${palette.paper}" shadowColor="${palette.ink}33" shadowBlur={24}>
        <Img ref={characterImage} src={character} width="100%" />
      </Rect>`
    : `<Circle width={${Math.round(width * 0.22)}} height={${Math.round(width * 0.22)}} x={-${Math.round(width * 0.3)}} y={${Math.round(height * 0.08)}} fill="${palette.accent}" opacity={0.82} />`;
  const characterEnter = characterFile
    ? `,
      characterImage().position.x(side * ${Math.round(width * 0.018)}, enter),
      characterImage().rotation(side * 2.4, enter),
      characterImage().scale(1.04, enter)`
    : '';
  const characterHold = characterFile
    ? `,
      characterImage().position.y(side * -${Math.round(height * 0.012)}, remain),
      characterImage().rotation(side * -1.4, remain),
      characterImage().scale(1, remain)`
    : '';

  return `import {Circle, Img, Layout, Rect, Txt, makeScene2D} from '@motion-canvas/2d';
import {all, createRef, waitFor} from '@motion-canvas/core';
${characterImport}
const cues = ${JSON.stringify(cues)};
const totalDuration = ${Math.max(1, duration)};

export default makeScene2D(function* (view) {
  view.fill('${palette.bg}');
  const title = createRef<Txt>();
  const caption = createRef<Txt>();
  const counter = createRef<Txt>();
  const card = createRef<Rect>();
  const progress = createRef<Rect>();
  const orbTop = createRef<Circle>();
  const orbBottom = createRef<Circle>();
${characterRef}
  view.add(
    <Layout width="100%" height="100%">
      <Circle ref={orbTop} width={${Math.round(width * 0.42)}} height={${Math.round(width * 0.42)}} x={${Math.round(width * 0.44)}} y={-${Math.round(height * 0.42)}} fill="${palette.accent}" opacity={0.16} />
      <Circle ref={orbBottom} width={${Math.round(width * 0.3)}} height={${Math.round(width * 0.3)}} x={-${Math.round(width * 0.46)}} y={${Math.round(height * 0.44)}} fill="${palette.accent}" opacity={0.1} />
      <Txt ref={title} text={${JSON.stringify(headline)}} x={-${Math.round(width * 0.3)}} y={-${Math.round(height * 0.39)}} width={${Math.round(width * 0.78)}} fontFamily="Arial" fontWeight={900} fontSize={${Math.max(32, Math.round(width * 0.055))}} fill="${palette.ink}" opacity={0} />
      <Txt text="MOTION CANVAS · LTX" x={${Math.round(width * 0.34)}} y={-${Math.round(height * 0.41)}} fontFamily="Arial" fontWeight={700} fontSize={${Math.max(16, Math.round(width * 0.015))}} fill="${palette.accent}" letterSpacing={3} />
      ${characterNode}
      <Rect ref={card} x={${Math.round(width * 0.17)}} y={${Math.round(height * 0.07)}} width={${Math.round(width * 0.56)}} minHeight={${Math.round(height * 0.34)}} padding={${Math.max(32, Math.round(width * 0.04))}} radius={28} fill="${palette.paper}" stroke="${palette.ink}" lineWidth={3} opacity={0} scale={0.94} shadowColor="${palette.ink}22" shadowBlur={28}>
        <Txt ref={counter} y={-${Math.round(height * 0.13)}} width="100%" text="01 / ${String(cues.length).padStart(2, '0')}" fontFamily="Arial" fontWeight={800} fontSize={${Math.max(18, Math.round(width * 0.018))}} fill="${palette.accent}" />
        <Txt ref={caption} width="100%" text="" fontFamily="Arial" fontWeight={700} fontSize={${Math.max(30, Math.round(width * 0.035))}} lineHeight={${Math.max(42, Math.round(width * 0.049))}} fill="${palette.ink}" textWrap />
      </Rect>
      <Rect y={${Math.round(height * 0.43)}} width={${Math.round(width * 0.82)}} height={10} radius={5} fill="${palette.ink}18">
        <Rect ref={progress} width="100%" height="100%" radius={5} fill="${palette.accent}" scaleX={0} />
      </Rect>
    </Layout>,
  );

  const introDuration = Math.min(0.5, cues[0]?.start ?? 0.5);
  if (introDuration > 0) {
    yield* all(
      title().opacity(1, introDuration),
      title().position.x(-${Math.round(width * 0.27)}, introDuration),
      card().opacity(1, introDuration),
      card().scale(1, introDuration),
    );
  } else {
    title().opacity(1);
    card().opacity(1);
    card().scale(1);
  }

  let playhead = introDuration;
  for (let index = 0; index < cues.length; index += 1) {
    const cue = cues[index];
    if (cue.start > playhead) {
      yield* waitFor(cue.start - playhead);
      playhead = cue.start;
    }
    const available = Math.max(0.1, cue.end - playhead);
    const enter = Math.min(0.32, available * 0.3);
    const remain = Math.max(0, available - enter);
    const side = index % 2 === 0 ? -1 : 1;

    caption().text(cue.text);
    caption().opacity(0);
    caption().position.y(24);
    counter().text(String(index + 1).padStart(2, '0') + ' / ' + String(cues.length).padStart(2, '0'));
    card().rotation(side * 1.1);

    yield* all(
      caption().opacity(1, enter),
      caption().position.y(0, enter),
      card().rotation(0, enter),
      orbTop().position.x(${Math.round(width * 0.44)} + side * ${Math.round(width * 0.025)}, enter),
      orbBottom().position.x(-${Math.round(width * 0.46)} - side * ${Math.round(width * 0.02)}, enter)${characterEnter}
    );
    if (remain > 0) {
      yield* all(
        progress().scale.x(Math.min(1, cue.end / totalDuration), remain),
        orbTop().rotation(orbTop().rotation() + side * 8, remain),
        orbBottom().rotation(orbBottom().rotation() - side * 10, remain)${characterHold},
        waitFor(remain),
      );
    }
    playhead = cue.end;
  }

  if (playhead < totalDuration) {
    yield* waitFor(totalDuration - playhead);
  }
});
`;
}

export const motionCanvasMacLauncher = `#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  osascript -e 'display alert "需要 Node.js" message "請先安裝 Node.js 22 或 24，再重新雙擊此檔案。"'
  exit 1
fi

if [ ! -d node_modules ]; then
  npm install
fi

npm start &
server_pid=$!
trap 'kill "$server_pid" >/dev/null 2>&1 || true' EXIT INT TERM

for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:9000/ >/dev/null 2>&1; then
    open http://127.0.0.1:9000/
    wait "$server_pid"
    exit $?
  fi
  if ! kill -0 "$server_pid" >/dev/null 2>&1; then
    wait "$server_pid"
    exit $?
  fi
  sleep 1
done

echo "Motion Canvas 未能在 60 秒內啟動。"
exit 1
`;
