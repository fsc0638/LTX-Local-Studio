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
