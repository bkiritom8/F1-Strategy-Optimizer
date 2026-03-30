/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly PROD: boolean;
  readonly DEV: boolean;
  readonly GEMINI_API_KEY?: string;
  readonly VITE_ADMIN_PASSWORD?: string;
  readonly VITE_NVIDIA_API_KEY?: string;
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
