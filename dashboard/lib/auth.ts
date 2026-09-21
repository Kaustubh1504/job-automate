// Supabase Auth session, read from cookies. This client is only used for
// authentication -- all data access goes through lib/supabase.ts (service
// client, RLS disabled) with an explicit user_id filter.

import "server-only";
import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";
import type { User } from "@supabase/supabase-js";

function anonKey(): { url: string; key: string } {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL and SUPABASE_KEY must be set");
  return { url, key };
}

export async function authClient() {
  const { url, key } = anonKey();
  const store = await cookies();
  return createServerClient(url, key, {
    cookies: {
      getAll: () => store.getAll(),
      setAll: (cookiesToSet) => {
        try {
          for (const { name, value, options } of cookiesToSet) {
            store.set(name, value, options);
          }
        } catch {
          // Called from a Server Component, where cookies are read-only.
          // proxy.ts refreshes the session, so this is safe to ignore.
        }
      },
    },
  });
}

export async function currentUser(): Promise<User | null> {
  const supabase = await authClient();
  const { data } = await supabase.auth.getUser();
  return data.user;
}

// For API routes: the caller must be signed in.
export async function requireUser(): Promise<User> {
  const user = await currentUser();
  if (!user) throw new UnauthorizedError();
  return user;
}

export class UnauthorizedError extends Error {
  constructor() {
    super("Not signed in");
    this.name = "UnauthorizedError";
  }
}
