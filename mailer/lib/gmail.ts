// SMTP send, one transporter per sending account. Ported from
// outreach/lib/gmail.ts, with the account passed in rather than read from a
// single env pair -- this app sends from many mailboxes, not one.
//
// Credentials are handed in by the caller (lib/accounts.ts decrypts them);
// this module never looks them up itself.

import "server-only";
import nodemailer, { type Transporter } from "nodemailer";
import type { Account } from "@/lib/accounts";

const SMTP_HOST = "smtp.gmail.com";
const SMTP_PORT = 587;

const transporters = new Map<string, Transporter>();

function transporter(account: Account): Transporter {
  let existing = transporters.get(account.id);
  if (!existing) {
    existing = nodemailer.createTransport({
      host: SMTP_HOST,
      port: SMTP_PORT,
      secure: false,
      requireTLS: true,
      auth: { user: account.address, pass: account.appPassword },
    });
    transporters.set(account.id, existing);
  }
  return existing;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Verifies SMTP login without sending anything -- used when an account is
// added, so a bad app password fails there rather than mid-batch.
export async function verifyAccount(account: Account): Promise<string | null> {
  try {
    await transporter(account).verify();
    return null;
  } catch (err) {
    transporters.delete(account.id);
    return err instanceof Error ? err.message : String(err);
  }
}

export type Attachment = {
  filename: string;
  content: Buffer;
  contentType: string;
};

export async function sendEmail(opts: {
  account: Account;
  to: string;
  subject: string;
  body: string;
  attachments?: Attachment[];
}): Promise<string> {
  const info = await transporter(opts.account).sendMail({
    from: opts.account.address,
    to: opts.to,
    subject: opts.subject,
    text: opts.body,
    html: escapeHtml(opts.body).replace(/\n/g, "<br>\n"),
    attachments: opts.attachments,
  });
  return info.messageId;
}
