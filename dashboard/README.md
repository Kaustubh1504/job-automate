# Job Tracker dashboard

Next.js + Supabase dashboard for the job-automate pipeline.

- **Jobs** (`/`): every stored job, filter by recency, hide applied, show priority only; ⭐ marks priority/referral targets; tick **Applied** / **Referral** per row (writes straight to Supabase).
- **Config** (`/config`): edit the target companies, keyword include/exclude lists, and the priority allowlist + hourly threshold. The poller reads these from Supabase, so edits take effect on its next run.

## Local dev
```bash
cp .env.local.example .env.local   # fill in the two NEXT_PUBLIC_* values
npm install
npm run dev
```

## Deploy to Vercel
1. Push the repo; in Vercel "New Project", set **Root Directory** to `dashboard/`.
2. Add env vars `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (Settings → Environment Variables).
3. Deploy.

## Security
Currently "open for now": the anon key ships to the browser and RLS is disabled on
the tables, so anyone with the URL can read/edit. Before sharing the link, add
Supabase Auth + RLS policies (or a gate).
