/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Override when the API is not same-origin, e.g. a separate Cloud Run service. */
  readonly VITE_API_BASE?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
