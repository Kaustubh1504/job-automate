"""Send email from a Google account over SMTP.

Uses a Gmail app password rather than OAuth -- no client libraries, no token
refresh, no browser flow. Create one at https://myaccount.google.com/apppasswords
(requires 2FA on the account) and set in .env:

    GMAIL_ADDRESS=you@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
"""

import html as html_mod
import imaplib
import mimetypes
import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"

LINKEDIN_URL = "https://www.linkedin.com/in/kaustubh-gharat-6045b7208/"
PORTFOLIO_URL = "https://www.kaustubhgharat.com"
CALENDLY_URL = "https://calendly.com/kaustubhgharat06/introductory-call-with-kaustubh?month=2026-07"

FOOTER_TEXT = f"""
--
Kaustubh Gharat
Ex-Oracle, MS CS at Northeastern
Boston, MA | +1 (857) 379-6431
gharat.k@northeastern.edu
LinkedIn: {LINKEDIN_URL}
Portfolio: {PORTFOLIO_URL}
Schedule a Call: {CALENDLY_URL}
"""

FOOTER_HTML = f"""
<br>
<div style="font-family: Helvetica, Arial, sans-serif; font-size: 14px; color: #1a1a1a;">
  --<br>
  <div style="font-size: 22px; font-weight: bold; color: #7f1d1d; margin-top: 2px;">Kaustubh Gharat</div>
  <div style="font-size: 16px; color: #6b6b6b; margin-top: 2px;">Ex-Oracle, MS CS at Northeastern</div>
  <div style="border-top: 1px solid #e3a857; margin: 10px 0; width: 420px; max-width: 100%;"></div>
  <div style="font-weight: bold;">Boston, MA | +1 (857) 379-6431</div>
  <div><a href="mailto:gharat.k@northeastern.edu" style="color: #1155cc; font-weight: bold;">gharat.k@northeastern.edu</a></div>
  <div><a href="{LINKEDIN_URL}" style="color: #1155cc;">LinkedIn</a> | <a href="{PORTFOLIO_URL}" style="color: #1155cc;">Portfolio</a> | <a href="{CALENDLY_URL}" style="color: #1155cc;">Schedule a Call</a></div>
</div>
"""


def send_email(to, subject, body, html=None, attachments=None, in_reply_to=None):
    """Send an email from the configured Google account.

    `to` is a single address or a list of addresses. `body` is the plain-text
    content; pass `html` to supply your own HTML version (otherwise one is
    generated from `body` so the signature links render). `attachments` is a
    list of file paths to attach. The signature footer is always appended.

    Returns this message's Message-ID. To send a reply in the same thread,
    pass a previous message's Message-ID as `in_reply_to` (and use a
    "Re: ..." subject for clients that thread by subject).
    """
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to if isinstance(to, str) else ", ".join(to)
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body + "\n" + FOOTER_TEXT)
    if html is None:
        html = html_mod.escape(body).replace("\n", "<br>\n")
    msg.add_alternative(html + FOOTER_HTML, subtype="html")

    for path in attachments or []:
        path = Path(path)
        ctype, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(sender, password)
        smtp.send_message(msg)
    return msg["Message-ID"]


def has_reply(message_id):
    """True if the mailbox contains a reply to the given Message-ID (as
    returned by send_email). Uses Gmail's IMAP extensions: plain HEADER
    searches can't match Message-IDs (Gmail's search index tokenizes them),
    so look the message up by rfc822msgid, take its thread id, then check
    whether any message in the thread not sent by us has In-Reply-To pointing
    at this one (that last comparison is client-side, same reason)."""
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")

    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(sender, password)
        imap.select('"[Gmail]/All Mail"', readonly=True)
        _, data = imap.search(
            None, f'(X-GM-RAW "rfc822msgid:{message_id.strip("<>")}")'
        )
        found = data[0].split()
        if not found:
            raise LookupError(f"no message with Message-ID {message_id} in this mailbox")
        _, fetched = imap.fetch(found[-1], "(X-GM-THRID)")
        thread_id = fetched[0].decode().split("X-GM-THRID")[1].split(")")[0].strip()
        _, data = imap.search(None, f'(X-GM-THRID {thread_id} NOT FROM "{sender}")')
        for num in data[0].split():
            _, fetched = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (IN-REPLY-TO)])")
            header = fetched[0][1].decode()
            if message_id in header:
                return True
        return False


if __name__ == "__main__":
    # Smoke test: sends a message to yourself.
    send_email(
        to=os.environ["GMAIL_ADDRESS"],
        subject="mailer smoke test",
        body="If you're reading this, mailer/gmail.py works.",
    )
    print("sent")
