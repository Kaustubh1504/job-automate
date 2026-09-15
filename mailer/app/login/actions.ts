"use server";

import { redirect } from "next/navigation";
import { authClient } from "@/lib/auth";

export async function signIn(_prev: string | null, formData: FormData): Promise<string | null> {
  const supabase = await authClient();
  const { error } = await supabase.auth.signInWithPassword({
    email: String(formData.get("email") ?? ""),
    password: String(formData.get("password") ?? ""),
  });
  if (error) return error.message;
  redirect("/");
}

export async function signUp(_prev: string | null, formData: FormData): Promise<string | null> {
  const supabase = await authClient();
  const { data, error } = await supabase.auth.signUp({
    email: String(formData.get("email") ?? ""),
    password: String(formData.get("password") ?? ""),
  });
  if (error) return error.message;

  // With "Confirm email" off, signUp returns a session and the cookies are
  // already set -- go straight in. If it comes back without one, confirmation
  // is still enabled on the Supabase project and no amount of retrying here
  // will help, so say exactly what to change.
  if (data.session) redirect("/");

  return "Supabase still has email confirmation on. Turn off Authentication → Sign In / Providers → Email → Confirm email, then try again.";
}

export async function signOut() {
  const supabase = await authClient();
  await supabase.auth.signOut();
  redirect("/login");
}
