/**
 * Frontend runtime config — sourced from Vite's `import.meta.env`.
 * Variables must use the `VITE_` prefix to be exposed to the browser.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing required env var ${name}. Copy apps/web/.env.example to apps/web/.env and fill it in.`
    );
  }
  return value;
}

export const config = {
  supabaseUrl: required("VITE_SUPABASE_URL", import.meta.env.VITE_SUPABASE_URL),
  supabaseAnonKey: required(
    "VITE_SUPABASE_ANON_KEY",
    import.meta.env.VITE_SUPABASE_ANON_KEY
  ),
  apiUrl: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
} as const;
