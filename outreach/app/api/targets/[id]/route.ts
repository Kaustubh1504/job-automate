import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

// User override: toggle whether a target is included in the campaign.
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { selected } = await req.json();
  if (typeof selected !== "boolean") {
    return NextResponse.json({ error: "selected must be a boolean" }, { status: 400 });
  }
  const { error } = await supabase().from("outreach_targets").update({ selected }).eq("id", id);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true });
}
