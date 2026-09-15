// Sending accounts, per user, stored in Supabase. App passwords are encrypted
// at rest (lib/crypto.ts) and only decrypted here, on the server, at send time.

import "server-only";
import { decrypt, encrypt } from "@/lib/crypto";
import { supabase } from "@/lib/supabase";

export type Account = {
  id: string;
  address: string;
  appPassword: string;
};

export async function listAccounts(userId: string): Promise<Account[]> {
  const { data, error } = await supabase()
    .from("mailer_accounts")
    .select("id, address, app_password")
    .eq("user_id", userId)
    .order("created_at", { ascending: true });

  if (error) throw new Error(error.message);
  return data.map((row) => ({
    id: row.id,
    address: row.address,
    appPassword: decrypt(row.app_password),
  }));
}

// Addresses only -- for the UI, which must never see the passwords.
export async function listAddresses(userId: string): Promise<{ id: string; address: string }[]> {
  const { data, error } = await supabase()
    .from("mailer_accounts")
    .select("id, address")
    .eq("user_id", userId)
    .order("created_at", { ascending: true });

  if (error) throw new Error(error.message);
  return data;
}

export async function addAccount(userId: string, address: string, appPassword: string) {
  const { error } = await supabase()
    .from("mailer_accounts")
    .upsert(
      { user_id: userId, address, app_password: encrypt(appPassword) },
      { onConflict: "user_id,address" }
    );
  if (error) throw new Error(error.message);
}

export async function removeAccount(userId: string, id: string) {
  const { error } = await supabase()
    .from("mailer_accounts")
    .delete()
    .eq("user_id", userId)
    .eq("id", id);
  if (error) throw new Error(error.message);
}
