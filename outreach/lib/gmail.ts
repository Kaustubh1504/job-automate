// TypeScript port of mailer/gmail.py: send from a Google account over SMTP
// and detect replies over IMAP. Uses a Gmail app password rather than OAuth --
// no client libraries, no token refresh, no browser flow. Create one at
// https://myaccount.google.com/apppasswords (requires 2FA) and set in .env:
//
//     GMAIL_ADDRESS=you@gmail.com
//     GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

import "server-only";
import nodemailer from "nodemailer";
import { ImapFlow } from "imapflow";

const SMTP_HOST = "smtp.gmail.com";
const SMTP_PORT = 587;
const IMAP_HOST = "imap.gmail.com";

const LINKEDIN_URL = "https://www.linkedin.com/in/kaustubh-gharat-6045b7208/";
const PORTFOLIO_URL = "https://www.kaustubhgharat.com";
const CALENDLY_URL =
  "https://calendly.com/kaustubhgharat06/introductory-call-with-kaustubh?month=2026-07";

export const FOOTER_TEXT = `
--
Kaustubh Gharat
Ex-Oracle, MS CS at Northeastern
Boston, MA | +1 (857) 379-6431
gharat.k@northeastern.edu
LinkedIn: ${LINKEDIN_URL}
Portfolio: ${PORTFOLIO_URL}
Schedule a Call: ${CALENDLY_URL}
`;

const FOOTER_HTML = `
<br>
<div style="font-family: Helvetica, Arial, sans-serif; font-size: 14px; color: #1a1a1a;">
  --<br>
  <div style="font-size: 22px; font-weight: bold; color: #7f1d1d; margin-top: 2px;">Kaustubh Gharat</div>
  <div style="font-size: 16px; color: #6b6b6b; margin-top: 2px;">Ex-Oracle, MS CS at Northeastern</div>
  <div style="border-top: 1px solid #e3a857; margin: 10px 0; width: 420px; max-width: 100%;"></div>
  <div style="font-weight: bold;">Boston, MA | +1 (857) 379-6431</div>
  <div><a href="mailto:gharat.k@northeastern.edu" style="color: #1155cc; font-weight: bold;">gharat.k@northeastern.edu</a></div>
  <div><a href="${LINKEDIN_URL}" style="color: #1155cc;">LinkedIn</a> | <a href="${PORTFOLIO_URL}" style="color: #1155cc;">Portfolio</a> | <a href="${CALENDLY_URL}" style="color: #1155cc;">Schedule a Call</a></div>
</div>
`;

function creds(): { address: string; password: string } {
  const address = process.env.GMAIL_ADDRESS;
  const password = process.env.GMAIL_APP_PASSWORD;
  if (!address || !password) {
    throw new Error("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env");
  }
  return { address, password };
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Verifies SMTP login works; returns the configured address (home-page status).
export async function connectedEmail(): Promise<string> {
  const { address, password } = creds();
  const transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port: SMTP_PORT,
    secure: false,
    requireTLS: true,
    auth: { user: address, pass: password },
  });
  await transporter.verify();
  return address;
}

// Send an email from the configured Google account. `body` is the plain-text
// content; pass `html` to supply your own HTML version (otherwise one is
// generated from `body` so the signature links render). The signature footer
// is always appended.
//
// Returns this message's Message-ID. To send a reply in the same thread, pass
// a previous message's Message-ID as `inReplyTo` (and use a "Re: ..." subject
// for clients that thread by subject).
export async function sendEmail(opts: {
  to: string;
  subject: string;
  body: string;
  html?: string;
  inReplyTo?: string;
}): Promise<string> {
  const { address, password } = creds();
  const transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port: SMTP_PORT,
    secure: false,
    requireTLS: true,
    auth: { user: address, pass: password },
  });
  const html = opts.html ?? escapeHtml(opts.body).replace(/\n/g, "<br>\n");
  const info = await transporter.sendMail({
    from: address,
    to: opts.to,
    subject: opts.subject,
    text: opts.body + "\n" + FOOTER_TEXT,
    html: html + FOOTER_HTML,
    inReplyTo: opts.inReplyTo,
    references: opts.inReplyTo,
  });
  return info.messageId;
}

// True if the mailbox contains a reply to the given Message-ID (as returned
// by sendEmail). Uses Gmail's IMAP extensions: plain HEADER searches can't
// match Message-IDs (Gmail's search index tokenizes them), so look the
// message up by rfc822msgid, take its thread id, then check whether any
// message in the thread not sent by us has In-Reply-To pointing at this one
// (that last comparison is client-side, same reason).
export async function hasReply(messageId: string): Promise<boolean> {
  const { address, password } = creds();
  const client = new ImapFlow({
    host: IMAP_HOST,
    port: 993,
    secure: true,
    auth: { user: address, pass: password },
    logger: false,
  });
  await client.connect();
  try {
    const lock = await client.getMailboxLock("[Gmail]/All Mail", { readOnly: true });
    try {
      const found = await client.search({
        gmraw: `rfc822msgid:${messageId.replace(/^<|>$/g, "")}`,
      });
      if (!found || found.length === 0) {
        throw new Error(`no message with Message-ID ${messageId} in this mailbox`);
      }
      const sent = await client.fetchOne(String(found[found.length - 1]), { threadId: true });
      if (!sent || !sent.threadId) {
        throw new Error(`could not resolve thread id for ${messageId}`);
      }
      const inThread = await client.search({
        threadId: sent.threadId,
        not: { from: address },
      });
      if (!inThread || inThread.length === 0) return false;
      for await (const msg of client.fetch(inThread.join(","), {
        headers: ["in-reply-to"],
      })) {
        if (msg.headers?.toString().includes(messageId)) return true;
      }
      return false;
    } finally {
      lock.release();
    }
  } finally {
    await client.logout();
  }
}
