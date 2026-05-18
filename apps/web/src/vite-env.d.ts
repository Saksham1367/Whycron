/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL: string;
  readonly VITE_SUPABASE_ANON_KEY: string;
  readonly VITE_API_URL?: string;
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_SENTRY_ENVIRONMENT?: string;
  readonly VITE_POSTHOG_KEY?: string;
  readonly VITE_POSTHOG_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Vite supports importing files as raw strings with the ``?raw`` suffix.
// Used for our Markdown legal pages so the source-of-truth lives in
// PRIVACY.md / TERMS.md and is rendered at runtime by react-markdown.
declare module "*.md?raw" {
  const content: string;
  export default content;
}
