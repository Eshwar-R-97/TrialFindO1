/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** When set (e.g. http://127.0.0.1:5050), API calls skip Vite proxy and hit Flask directly. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
