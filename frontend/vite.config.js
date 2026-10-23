import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// Keep browser requests on one origin, including HttpOnly authentication cookies.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/auth-api': { target: process.env.AUTH_API_TARGET || 'http://localhost:8080', rewrite: p => p.replace(/^\/auth-api/, '/api') },
      '/rag-api': { target: process.env.RAG_API_TARGET || 'http://localhost:8001', rewrite: p => p.replace(/^\/rag-api/, '') },
      '/voice-api': { target: process.env.VOICE_API_TARGET || 'http://localhost:8008', ws: true, rewrite: p => p.replace(/^\/voice-api/, '') },
    },
  },
});
