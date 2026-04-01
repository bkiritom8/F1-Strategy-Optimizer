/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly PROD: boolean;
  readonly DEV: boolean;
  readonly VITE_GEMINI_API_KEY?: string;
  readonly VITE_API_URL?: string;
  readonly VITE_API_USER?: string;
  readonly VITE_API_PASS?: string;
  readonly VITE_CLOUD_RUN_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
