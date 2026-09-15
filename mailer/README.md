# mailer

One page. Write a template, pick people, send — each email goes out from a
different Gmail account so the volume spreads evenly across all of them.

Multi-tenant: each user signs in, and their people, send history and Gmail
accounts are theirs alone. Every query filters on `user_id`.

## Setup

1. **Apply the schema.** Paste `supabase/schema.sql` into the Supabase SQL
   editor. Three tables: `mailer_people`, `mailer_sent`, `mailer_accounts`.
   It is safe to re-run, and it migrates a pre-multi-tenant install in place.

2. **Set the env.** Copy `.env.example` to `.env`. You need `SUPABASE_URL`,
   `SUPABASE_KEY` (anon) and `ENCRYPTION_KEY`:

   ```
   node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
   ```

   `ENCRYPTION_KEY` encrypts the stored Gmail app passwords. **Changing or
   losing it makes every saved account unreadable** until re-entered.

3. **Turn off email confirmation** (one time, in the Supabase dashboard):
   **Authentication → Sign In / Providers → Email → Confirm email → off.**

   This cannot be changed from code — it is project configuration, not an API
   setting. With it off, "Create account" on the login page creates the user
   and signs them straight in, no email involved.

   Leave it on and Supabase returns no session at signup; the login page will
   tell you so rather than appearing to hang. (The built-in confirmation mailer
   is also rate-limited and spam-prone, which is why off is the better default
   for a two-person tool.)

4. **Create the accounts.** Each person opens the app and clicks *Create
   account* once. There is no invite gate, so don't expose this to the open
   internet as-is.

5. `npm run dev`

## Gmail accounts

Each user adds their own, in-app: click the account count in the top bar, enter
the address and a Gmail app password from
https://myaccount.google.com/apppasswords (needs 2FA on that account).

The password is verified against Gmail's SMTP server before it is saved — a bad
one is rejected on the spot rather than failing partway through a batch. It is
then stored AES-256-GCM encrypted, and only decrypted server-side at send time.
The browser never receives it; the accounts API returns addresses only.

## The two flows

**New people** — the CSV button. Needs `name`, `email` and `linkedin_url`;
`company` and `title` optional. Headers are case-insensitive and accept common
aliases (`LinkedIn URL`, `Full Name`, `Job Title`). Bad rows are skipped and
counted, not fatal.

```csv
Name,Email,LinkedIn URL,Company,Title
Jane Doe,jane@acme.com,https://linkedin.com/in/janedoe,Acme Corp,Recruiter
```

**One person at a time** — the **Add** button opens a small inline form (name,
email, LinkedIn URL required; company and title optional). It goes through the
same import path as a CSV, so a manual entry gets identical dedup and
sending-account assignment.

**Existing people** — the list is grouped by company, with a header checkbox
per company so you can take a whole org in one click (it shows a dash when only
some of that company is picked). Each row carries name, title, email and the
account that will send to them. The filter box matches on any of those, and
All/None operate on whatever the filter is currently showing. People with no
company land in a "No company" group.

Then write the subject and body and hit Send. The button arms on first click
and sends on the second: this fires real mail with no undo.

## Attachments

The **Attach** button takes any number of files; they ride along on every
message in the batch. They're uploaded once as multipart and reused per
recipient, not re-encoded each time.

Total size is capped at 20MB client-side, short of Gmail's 25MB limit, so an
oversized batch fails as one clear message instead of an SMTP error per
recipient.

## How the even split works

Each person is assigned a sending account **once, when their CSV row is first
imported**, and keeps it. Assignment goes to whichever account currently owns
the fewest people, so the split stays even across repeated uploads rather than
only within one CSV. The rightmost column in the list shows who sends to whom.

It's sticky rather than round-robin-per-send because a reply lands in whichever
mailbox sent the message — a follow-up from a different account would start a
new thread and lose the conversation.

Re-importing a CSV updates people in place (`linkedin_url` is the dedup key)
and never reshuffles an existing assignment.

At send time accounts run in parallel, sequentially within themselves: ten
accounts means ten concurrent SMTP conversations, not one mailbox firing 100
messages back to back.

## Merge fields

`{{first_name}}`, `{{name}}`, `{{email}}`, `{{title}}`, `{{company}}`.

Plain string substitution — no model in the send path, so what you type is what
goes out. An unrecognised placeholder (a typo like `{{firstname}}`) is rejected
before anything sends rather than shipping as literal text.
