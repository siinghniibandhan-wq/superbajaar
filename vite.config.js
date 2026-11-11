import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const candidateRelease = process.env.AWS_COMMIT_ID || process.env.GITHUB_SHA || 'local';
const releaseId = /^[0-9a-f]{7,64}$/i.test(candidateRelease) ? candidateRelease : 'unknown';

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'super-bajaar-release-marker',
      transformIndexHtml(html) {
        return html.replace(
          '</head>',
          `<meta name="sb-release" content="${releaseId}" />\n  </head>`,
        );
      },
    },
  ],
  // The root-level app imports frontend/src, so load the same production API
  // configuration used by the frontend workspace build.
  envDir: './frontend',
});
