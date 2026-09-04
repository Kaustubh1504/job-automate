import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { parseJd } from "@/lib/llm";
import { findOrCreateCompany } from "@/lib/companies";

const PURPOSES = ["referral", "recruiter_followup", "hiring_manager_intro"] as const;

// Paste a JD + purpose. LLM parses company/role/domain/requirements
// (intelligent, all stored as proposals); campaign + company rows are created
// rigidly. Company is reused if it already exists.
export async function POST(req: NextRequest) {
  const { jd_text, purpose } = await req.json();
  if (!jd_text?.trim()) return NextResponse.json({ error: "jd_text is required" }, { status: 400 });
  if (!PURPOSES.includes(purpose)) {
    return NextResponse.json({ error: `purpose must be one of ${PURPOSES.join(", ")}` }, { status: 400 });
  }

  let parsed;
  try {
    parsed = await parseJd(jd_text);
  } catch (err) {
    return NextResponse.json(
      { error: `JD parsing failed: ${err instanceof Error ? err.message : err}` },
      { status: 502 }
    );
  }

  const company = await findOrCreateCompany(parsed.company_name, parsed.email_domain);

  const { data: campaign, error } = await supabase()
    .from("outreach_campaigns")
    .insert({
      jd_text,
      company_id: company.id,
      role_title: parsed.role_title,
      purpose,
      parsed_requirements: parsed.requirements,
    })
    .select("id")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ campaign_id: campaign.id, company: company.name, parsed });
}
