import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // The root-level app imports frontend/src, so load the same production API
  // configuration used by the frontend workspace build.
  envDir: './frontend',
});
