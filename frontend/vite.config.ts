import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
        proxy: {
          // F1 Strategy Optimizer FastAPI backend
          '/api/v1': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/token': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/health': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/metrics': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/strategy': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/models': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/data': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/users': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          '/docs': {
            target: 'http://localhost:8000',
            changeOrigin: true,
          },
          // NVIDIA proxy for AI chatbot
          '/api/nvidia': {
            target: 'https://integrate.api.nvidia.com',
            changeOrigin: true,
            rewrite: (path) => path.replace(/^\/api\/nvidia/, ''),
          },
        }
      },
      plugins: [react()],
      define: {
        'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
        'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});
