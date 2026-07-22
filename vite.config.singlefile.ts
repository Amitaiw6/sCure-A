// Builds the entire app into ONE self-contained index.html (JS, CSS, fonts and
// data all inlined) so a designer can open it by double-click — no server, no Node.
// Used for the design handoff. Run: npx vite build --config vite.config.singlefile.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { viteSingleFile } from 'vite-plugin-singlefile'
import path from 'path'

export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    outDir: 'design-handoff/_singlefile',
    emptyOutDir: true,
    assetsInlineLimit: 100000000, // inline fonts & assets as data URIs
    chunkSizeWarningLimit: 100000,
  },
})
