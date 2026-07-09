// Receives a Flag27 tick from the dashboard and posts it to the dedicated
// Summer 2027 Discord channel. DISCORD_FLAG27_WEBHOOK_URL is server-only (set it
// in Vercel project env / dashboard/.env.local) so the webhook never ships to
// the browser -- separate from the pipeline's DISCORD_WEBHOOK_URL.
export async function POST(request) {
  const webhook = process.env.DISCORD_FLAG27_WEBHOOK_URL;
  if (!webhook) {
    return Response.json({ error: 'DISCORD_FLAG27_WEBHOOK_URL not set' }, { status: 500 });
  }
  const { company, title, location, url } = await request.json();
  const content =
    `🚩 **Flag27** · **${company || 'Unknown'}** — ${title || 'role'}` +
    (location ? ` · ${location}` : '') +
    (url ? `\n${url}` : '');

  const res = await fetch(webhook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    return Response.json({ error: `discord ${res.status}` }, { status: 502 });
  }
  return Response.json({ ok: true });
}
