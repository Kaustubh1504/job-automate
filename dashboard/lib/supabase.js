import { createClient } from '@supabase/supabase-js';

// Anon key, exposed to the browser. "Open for now" -- lock down with RLS/Auth
// before sharing the URL.
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
);
