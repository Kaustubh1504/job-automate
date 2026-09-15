import { NextResponse } from "next/server";
import { listAddresses } from "@/lib/accounts";
import { requireUser, UnauthorizedError } from "@/lib/auth";
import { parseCsv } from "@/lib/csv";
import { assignSenders } from "@/lib/distribute";
import { supabase } from "@/lib/supabase";

function unauthorized(err: unknown) {
  return err instanceof UnauthorizedError
    ? NextResponse.json({ error: "Not signed in" }, { status: 401 })
    : null;
}

export async function GET() {
  let user;
  try {
    user = await requireUser();
  } catch (err) {
    return unauthorized(err) ?? NextResponse.json({ error: "Failed" }, { status: 500 });
  }

  const db = supabase();
  const { data, error } = await db
    .from("mailer_people")
    .select("id, name, email, title, company, sender_address")
    .eq("user_id", user.id)
    .order("company", { ascending: true, nullsFirst: false })
    .order("name", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ people: data });
}

// CSV intake. Dedups on linkedin_url and assigns each NEW person a sending
// account so the overall split across accounts stays even.
export async function POST(request: Request) {
  let user;
  try {
    user = await requireUser();
  } catch (err) {
    return unauthorized(err) ?? NextResponse.json({ error: "Failed" }, { status: 500 });
  }

  const { csv } = await request.json();
  if (typeof csv !== "string" || !csv.trim()) {
    return NextResponse.json({ error: "Paste or upload a CSV first" }, { status: 400 });
  }

  const { people, skipped } = parseCsv(csv);
  if (people.length === 0) {
    return NextResponse.json(
      { error: `No usable rows (${skipped.length} skipped)`, skipped },
      { status: 400 }
    );
  }

  const db = supabase();

  // Anyone already here keeps the account they were assigned -- their replies
  // are sitting in that mailbox.
  const { data: existing, error: existingError } = await db
    .from("mailer_people")
    .select("linkedin_url, sender_address")
    .eq("user_id", user.id)
    .in("linkedin_url", people.map((p) => p.linkedin_url));
  if (existingError) return NextResponse.json({ error: existingError.message }, { status: 500 });

  const keptSender = new Map(existing.map((r) => [r.linkedin_url, r.sender_address]));

  // Current load per account, so the split stays even across uploads.
  const { data: allPeople, error: countError } = await db
    .from("mailer_people")
    .select("sender_address")
    .eq("user_id", user.id);
  if (countError) return NextResponse.json({ error: countError.message }, { status: 500 });

  const counts: Record<string, number> = {};
  for (const row of allPeople) {
    if (row.sender_address) counts[row.sender_address] = (counts[row.sender_address] ?? 0) + 1;
  }

  const addresses = (await listAddresses(user.id)).map((a) => a.address);
  if (addresses.length === 0) {
    return NextResponse.json(
      { error: "Add a Gmail account before importing people" },
      { status: 400 }
    );
  }
  const newPeople = people.filter((p) => !keptSender.has(p.linkedin_url));
  const senders = assignSenders(addresses, counts, newPeople.length);
  const assignedSender = new Map(newPeople.map((p, i) => [p.linkedin_url, senders[i]]));

  const rows = people.map((p) => ({
    user_id: user.id,
    linkedin_url: p.linkedin_url,
    name: p.name,
    email: p.email,
    title: p.title,
    company: p.company,
    sender_address: keptSender.get(p.linkedin_url) ?? assignedSender.get(p.linkedin_url)!,
  }));

  const { error: upsertError } = await db
    .from("mailer_people")
    .upsert(rows, { onConflict: "user_id,linkedin_url" });
  if (upsertError) return NextResponse.json({ error: upsertError.message }, { status: 500 });

  return NextResponse.json({
    added: newPeople.length,
    updated: rows.length - newPeople.length,
    skipped,
  });
}
