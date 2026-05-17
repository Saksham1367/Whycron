import { createClient } from "@supabase/supabase-js";
import { config } from "./config";

/**
 * Singleton Supabase JS client. Handles OAuth redirects, token refresh,
 * and session persistence in localStorage. Backend verification of the
 * issued JWT is handled by `apps.api.services.auth` (CONTEXT.md §7.5).
 */
export const supabase = createClient(config.supabaseUrl, config.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    flowType: "pkce",
  },
});
