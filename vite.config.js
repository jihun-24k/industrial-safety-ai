import { defineConfig } from 'vite';

// Keep browser requests on one origin, including HttpOnly authentication cookies.
export default defineConfig({
  server: {
    proxy: {
      '/auth-api': { target: 'http://localhost:8080', rewrite: p => p.replace(/^\/auth-api/, '/api') },
      '/rag-api': { target: 'http://localhost:8001', rewrite: p => p.replace(/^\/rag-api/, '') },
      '/voice-api': { target: 'http://localhost:8008', rewrite: p => p.replace(/^\/voice-api/, '') },
    },
  },
});
