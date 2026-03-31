import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react-swc';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  return {
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/api/v1': { target: 'http://localhost:8000', changeOrigin: true },
        '/token':  { target: 'http://localhost:8000', changeOrigin: true },
        '/health': { target: 'http://localhost:8000', changeOrigin: true },
        '/metrics':{ target: 'http://localhost:8000', changeOrigin: true },
        '/strategy':{ target: 'http://localhost:8000', changeOrigin: true },
        '/models': { target: 'http://localhost:8000', changeOrigin: true },
        '/users':  { target: 'http://localhost:8000', changeOrigin: true },
        // NOTE: Do NOT proxy /data here. Static files in public/data/ (drivers.json,
        // circuits.json, etc.) are served by Vite's built-in static file server.
        // Proxying /data would redirect those requests to the backend, which
        // doesn't serve them, breaking the second tier of the fallback chain.
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    build: {
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-charts': ['recharts'],
            'vendor-motion': ['framer-motion'],
          },
        },
      },
    },
  };
});
