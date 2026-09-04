import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { extractPeople } from "@/lib/llm";
import { normalizeLinkedinUrl } from "@/lib/linkedin";
import { findOrCreateCompany } from "@/lib/companies";

export async function GET() {
  const { data, error } = await supabase()
    .from("outreach_people")
    .select("id, name, title, linkedin_url, email, email_status, company:outreach_companies(name)")
    .order("created_at", { ascending: false });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ people: data });
}

// Paste a freeform block of LinkedIn people. LLM extracts (intelligent);
// dedup/upsert on linkedin_url is rigid — duplicates are silently skipped.
export async function POST(req: NextRequest) {
  const { text } = await req.json();
  if (!text?.trim()) return NextResponse.json({ error: "text is required" }, { status: 400 });

  let extracted;
  try {
    extracted = await extractPeople(text);
  } catch (err) {
    return NextResponse.json(
      { error: `extraction failed: ${err instanceof Error ? err.message : err}` },
      { status: 502 }
    );
  }

  const db = supabase();
  let inserted = 0;
  let skipped = 0;
  try {
    for (const person of extracted) {
      const linkedinUrl = normalizeLinkedinUrl(person.linkedin_url);
      if (!linkedinUrl) {
        skipped++;
        continue;
      }
      let companyId: string | null = null;
      if (person.company) {
        companyId = (await findOrCreateCompany(person.company)).id;
      }
      const { error, data } = await db
        .from("outreach_people")
        .upsert(
          { linkedin_url: linkedinUrl, name: person.name, title: person.title, company_id: companyId },
          { onConflict: "linkedin_url", ignoreDuplicates: true }
        )
        .select("id");
      if (error) throw new Error(error.message);
      if (data && data.length > 0) inserted++;
      else skipped++; // already saved — silent skip so sloppy pastes are fine
    }
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "save failed" }, { status: 500 });
  }

  return NextResponse.json({ extracted: extracted.length, inserted, skipped });
}
