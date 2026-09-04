import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";
import { selectTargets } from "@/lib/llm";
import { normalizeLinkedinUrl } from "@/lib/linkedin";

type CampaignRow = {
  id: string;
  role_title: string | null;
  purpose: string;
  parsed_requirements: string[] | null;
  company: { id: string; name: string } | null;
};

async function loadCampaign(id: string): Promise<CampaignRow> {
  const { data, error } = await supabase()
    .from("outreach_campaigns")
    .select("id, role_title, purpose, parsed_requirements, company:outreach_companies(id, name)")
    .eq("id", id)
    .single();
  if (error) throw new Error(`campaign not found: ${error.message}`);
  // supabase-js types to-one joins as arrays without generated DB types
  return data as unknown as CampaignRow;
}

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let campaign;
  try {
    campaign = await loadCampaign(id);
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "not found" }, { status: 404 });
  }

  const { data: targets, error } = await supabase()
    .from("outreach_targets")
    .select(
      "id, selected, relevance_score, relevance_reason, person:outreach_people(id, name, title, linkedin_url, email, email_status)"
    )
    .eq("campaign_id", id)
    .order("relevance_score", { ascending: false });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ campaign, targets });
}

// LLM ranks the saved people for this campaign (intelligent); rows are
// upserted rigidly on (campaign_id, person_id). The user toggles `selected`
// afterwards — the LLM never has the final word on who gets contacted.
export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let campaign;
  try {
    campaign = await loadCampaign(id);
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "not found" }, { status: 404 });
  }

  const db = supabase();
  const { data: peopleRaw, error: pplErr } = await db
    .from("outreach_people")
    .select("id, name, title, linkedin_url, company:outreach_companies(name)")
    .order("created_at", { ascending: false });
  if (pplErr) return NextResponse.json({ error: pplErr.message }, { status: 500 });
  const people = peopleRaw as unknown as
    | { id: string; name: string; title: string | null; linkedin_url: string; company: { name: string } | null }[]
    | null;
  if (!people || people.length === 0) {
    return NextResponse.json({ error: "no saved people — add some on the People screen first" }, { status: 400 });
  }

  let ranked;
  try {
    ranked = await selectTargets({
      company: campaign.company?.name ?? "",
      roleTitle: campaign.role_title ?? "",
      purpose: campaign.purpose,
      requirements: (campaign.parsed_requirements as string[]) ?? [],
      people: people.map((p) => ({
        name: p.name,
        title: p.title,
        company: p.company?.name ?? null,
        linkedin_url: p.linkedin_url,
      })),
    });
  } catch (err) {
    return NextResponse.json(
      { error: `target selection failed: ${err instanceof Error ? err.message : err}` },
      { status: 502 }
    );
  }

  const byUrl = new Map(people.map((p) => [p.linkedin_url, p.id]));
  let saved = 0;
  for (const target of ranked) {
    const url = normalizeLinkedinUrl(target.linkedin_url);
    const personId = url ? byUrl.get(url) : undefined;
    if (!personId) continue; // LLM proposed someone not in our list — drop it
    const { error } = await db.from("outreach_targets").upsert(
      {
        campaign_id: id,
        person_id: personId,
        relevance_score: target.relevance_score,
        relevance_reason: target.relevance_reason,
      },
      { onConflict: "campaign_id,person_id" }
    );
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    saved++;
  }

  return NextResponse.json({ proposed: ranked.length, saved });
}
