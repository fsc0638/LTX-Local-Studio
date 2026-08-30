import type { NextConfig } from 'next';

const apiOrigin = (process.env.LTX_INTERNAL_API_ORIGIN || 'http://127.0.0.1:8787').replace(/\/$/, '');
const nextConfig: NextConfig = {
  async rewrites() {
    // Same-origin dispatch. Private media MUST stay outside public/: some
    // static-serving layers run before application rewrites.
    return {beforeFiles: ['/api', '/generated', '/media'].map(prefix => ({
      source: `${prefix}/:path*`, destination: `${apiOrigin}${prefix}/:path*`,
    })), afterFiles: [], fallback: []};
  },
  async headers() {
    return [{source: '/:path*', headers: [
      {key: 'Referrer-Policy', value: 'no-referrer'},
      {key: 'X-Content-Type-Options', value: 'nosniff'},
      {key: 'X-Frame-Options', value: 'DENY'},
    ]}];
  },
};

export default nextConfig;
