import { NextResponse } from "next/server";
import { listAccounts } from "@/lib/accounts";
import { requireUser, UnauthorizedError } from "@/lib/auth";
import { type Attachment, sendEmail } from "@/lib/gmail";
import { render, unknownFields } from "@/lib/template";
import { supabase } from "@/lib/supabase";

// Every refusal is logged server-side as well as returned -- a send that
// quietly does nothing is the hardest thing to diagnose after the fact.
function refuse(message: string, status: number) {
  console.error(`[send] refused (${status}): ${message}`);
  return NextResponse.json({ error: message }, { status });
}

// Sends the same template to the selected people, each from the account that
// person is assigned to. Accounts run in parallel, sequentially within
// themselves -- ten accounts means ten concurrent SMTP conversations, and no
// single mailbox firing everything at once.
export async function POST(request: Request) {
  let user;
  try {
    user = await requireUser();
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      return refuse("Not signed in", 401);
    }
    throw err;
  }

  // multipart rather than JSON so attachments ride along as binary instead of
  // base64. The files are uploaded once and reused for every recipient.
  const form = await request.formData();
  const subject = String(form.get("subject") ?? "");
  const body = String(form.get("body") ?? "");
  const personIds = JSON.parse(String(form.get("personIds") ?? "[]"));

  const attachments: Attachment[] = await Promise.all(
    form
      .getAll("attachments")
      .filter((entry): entry is File => entry instanceof File)
      .map(async (file) => ({
        filename: file.name,
        content: Buffer.from(await file.arrayBuffer()),
        contentType: file.type || "application/octet-stream",
      }))
  );

  if (!subject?.trim() || !body?.trim()) {
    return refuse("Subject and body are both required", 400);
  }
  if (!Array.isArray(personIds) || personIds.length === 0) {
    return refuse("Select at least one person", 400);
  }

  const unknown = [...new Set([...unknownFields(subject), ...unknownFields(body)])];
  if (unknown.length > 0) {
    return refuse(`Unknown merge field(s): ${unknown.map((f) => `{{${f}}}`).join(", ")}`, 400);
  }

  const db = supabase();
  const { data: people, error } = await db
    .from("mailer_people")
    .select("id, name, email, title, company, sender_address")
    .eq("user_id", user.id)
    .in("id", personIds);

  if (error) return refuse(error.message, 500);
  if (!people || people.length === 0) {
    return refuse("None of those people exist", 400);
  }

  // Credentials are decrypted once per batch, not once per message.
  const credentials = new Map((await listAccounts(user.id)).map((a) => [a.address, a]));
  const orphaned = people.filter((p) => !credentials.has(p.sender_address));
  if (orphaned.length > 0) {
    const missing = [...new Set(orphaned.map((p) => p.sender_address))];
    return refuse(`No stored credentials for ${missing.join(", ")} — re-add the account`, 400);
  }

  const byAccount = new Map<string, typeof people>();
  for (const person of people) {
    const group = byAccount.get(person.sender_address) ?? [];
    group.push(person);
    byAccount.set(person.sender_address, group);
  }

  const log: { user_id: string; person_id: string; sender_address: string; subject: string; body: string; status: string; error: string | null }[] = [];

  await Promise.all(
    [...byAccount.entries()].map(async ([address, group]) => {
      for (const person of group) {
        const renderedSubject = render(subject, person);
        const renderedBody = render(body, person);
        try {
          await sendEmail({
            account: credentials.get(address)!,
            to: person.email,
            subject: renderedSubject,
            body: renderedBody,
            attachments,
          });
          log.push({
            user_id: user.id,
            person_id: person.id,
            sender_address: address,
            subject: renderedSubject,
            body: renderedBody,
            status: "sent",
            error: null,
          });
        } catch (err) {
          log.push({
            user_id: user.id,
            person_id: person.id,
            sender_address: address,
            subject: renderedSubject,
            body: renderedBody,
            status: "failed",
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    })
  );

  const { error: logError } = await db.from("mailer_sent").insert(log);
  if (logError) console.error(`[send] could not write send log: ${logError.message}`);

  for (const row of log) {
    if (row.status === "failed") console.error(`[send] ${row.sender_address} -> failed: ${row.error}`);
  }

  const perAccount: Record<string, number> = {};
  for (const row of log) {
    if (row.status === "sent") perAccount[row.sender_address] = (perAccount[row.sender_address] ?? 0) + 1;
  }

  return NextResponse.json({
    sent: log.filter((r) => r.status === "sent").length,
    failed: log.filter((r) => r.status === "failed").length,
    errors: log.filter((r) => r.status === "failed").slice(0, 5).map((r) => r.error),
    perAccount,
  });
}
