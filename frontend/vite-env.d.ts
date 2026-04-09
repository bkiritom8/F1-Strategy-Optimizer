/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly PROD: boolean;
  readonly DEV: boolean;
  /** Gemini API key for the AI Strategist chat. */
  readonly VITE_GEMINI_API_KEY?: string;
  /** Legacy API base URL (overridden by VITE_CLOUD_RUN_URL if set). */
  readonly VITE_API_URL?: string;
  /** GCP Cloud Run backend URL. Leave empty to use Vite proxy in dev. */
  readonly VITE_CLOUD_RUN_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
