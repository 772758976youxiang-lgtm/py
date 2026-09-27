import { defineConfig } from 'vite';
const proxy = { '/api': { target: process.env.LAB_API_URL || 'http://127.0.0.1:8000', changeOrigin: true } };
export default defineConfig({
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
});
