import "server-only";
import { createClient, SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

// Service-role client — server-side only (RLS is disabled on this project).
export function supabase(): SupabaseClient {
  if (!client) {
    const url = process.env.SUPABASE_URL;
    // Anon key works too: RLS is disabled on this project.
    const key = process.env.SUPABASE_SERVICE_ROLE_KEY ?? process.env.SUPABASE_KEY;
    if (!url || !key) {
      throw new Error("SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) must be set");
    }
    client = createClient(url, key, { auth: { persistSession: false } });
  }
  return client;
}
