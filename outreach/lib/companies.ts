import "server-only";
import { supabase } from "./supabase";

// Rigid find-or-create keyed on case-insensitive name. Reuses the existing
// row (so email_pattern/domain stay cached on it, per spec).
export async function findOrCreateCompany(
  name: string,
  emailDomain?: string | null
): Promise<{ id: string; name: string; email_domain: string | null; email_pattern: string | null }> {
  const db = supabase();
  const { data: existing, error: selErr } = await db
    .from("outreach_companies")
    .select("id, name, email_domain, email_pattern")
    .ilike("name", name)
    .limit(1)
    .maybeSingle();
  if (selErr) throw new Error(`company lookup failed: ${selErr.message}`);

  if (existing) {
    if (!existing.email_domain && emailDomain) {
      await db.from("outreach_companies").update({ email_domain: emailDomain }).eq("id", existing.id);
      existing.email_domain = emailDomain;
    }
    return existing;
  }

  const { data: created, error: insErr } = await db
    .from("outreach_companies")
    .insert({ name, email_domain: emailDomain ?? null })
    .select("id, name, email_domain, email_pattern")
    .single();
  if (insErr) throw new Error(`company insert failed: ${insErr.message}`);
  return created;
}
