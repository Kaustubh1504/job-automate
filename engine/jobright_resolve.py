"""Resolve jobright jobs to their underlying ATS / original-posting URL.

jobright's public feed only exposes the jobright.ai redirect. An *authenticated*
jobright job page (/jobs/info/<id>) renders the original posting link (the
`originalUrl` / "Original Job Post" field). We drive a cloakbrowser stealth
browser on a persistent profile -- logging in with JOBRIGHT_EMAIL /
JOBRIGHT_PASSWORD only when the saved session has lapsed -- and READ that link
per job. We never click "Apply with Autofill" (that could submit a real
application); reading `originalUrl` yields the identical destination safely.

Returns {id: original_url} for the ids it could resolve. Never raises -- any
failure (no creds, login/Cloudflare/page error) yields a partial/empty map so
the scraper stores what it has and retries the rest next run.

Env: JOBRIGHT_EMAIL, JOBRIGHT_PASSWORD (without them, resolution is skipped).
"""

import os
import re
import sys
from pathlib import Path

import authsession

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "jobright_profile"
AGENT_URL = "https://jobright.ai/ai-agent?from=agent"
JOB_URL = "https://jobright.ai/jobs/info/{}"
FEED_URL = "https://jobright.ai/jobs/recommend"

# The original posting URL is server-rendered into the authed page as a JSON
# field; read it out of the HTML (read-only -- no Apply click).
_ORIGINAL = re.compile(r'"originalUrl"\s*:\s*"([^"]+)"')
_APPLY_LINK = re.compile(r'"applyLink"\s*:\s*"([^"]+)"')


def _logged_in(page):
    # Logged out, jobright sets JR_userid to the sentinel string "not logined";
    # a real login makes it a numeric id. Guard against the sentinel/empty.
    try:
        uid = page.evaluate("() => localStorage.getItem('JR_userid')")
        return bool(uid) and uid not in ("not logined", "not logged in", "null", "undefined")
    except Exception:
        return False


def _login(page, email, password):
    """Open the sign-in modal and submit email/password. Returns True on success."""
    page.goto(AGENT_URL, wait_until="networkidle", timeout=60000)
    authsession.clear_cloudflare(page, 20)
    page.wait_for_timeout(3000)
    page.evaluate("""() => {
      const el=[...document.querySelectorAll('button,a,span,div')]
        .find(e=>(e.textContent||'').trim().toUpperCase()==='SIGN IN');
      if (el) el.click();
    }""")
    page.wait_for_timeout(2500)
    page.fill("#basic_email", email)
    page.fill("#basic_password", password)
    page.click(".index_sign-in-button__ZXtP1")
    page.wait_for_timeout(7000)
    return _logged_in(page)


def _read_original(page, job_id):
    page.goto(JOB_URL.format(job_id), wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3500)
    html = page.content()
    m = _ORIGINAL.search(html) or _APPLY_LINK.search(html)
    return m.group(1) if m else None


def resolve(ids, limit=60, headless=True):
    """{id: original_url} for as many of `ids` as we can resolve (capped at
    `limit` per run to bound runtime). Never raises."""
    email = os.environ.get("JOBRIGHT_EMAIL")
    password = os.environ.get("JOBRIGHT_PASSWORD")
    ids = list(ids)[:limit]
    if not (email and password):
        print("[jobright] JOBRIGHT_EMAIL/PASSWORD not set; skipping ATS resolution",
              file=sys.stderr)
        return {}
    if not ids:
        return {}
    out, ctx = {}, None
    try:
        ctx = authsession.launch(PROFILE_DIR, headless=headless)
        page = ctx.new_page()
        page.set_viewport_size({"width": 1280, "height": 900})
        page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        if not _logged_in(page) and not _login(page, email, password):
            print("[jobright] login failed; skipping ATS resolution", file=sys.stderr)
            return {}
        for jid in ids:
            try:
                url = _read_original(page, jid)
                if url:
                    out[jid] = url
            except Exception as e:
                print(f"[jobright] resolve {jid} failed: {type(e).__name__}: {e}",
                      file=sys.stderr)
        print(f"[jobright] resolved {len(out)}/{len(ids)} ATS urls", file=sys.stderr)
    except Exception as e:
        print(f"[jobright] resolver error: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        if ctx:
            try:
                ctx.close()
            except Exception:
                pass
    return out


if __name__ == "__main__":                              # quick manual test
    print(resolve(sys.argv[1:], headless=True))
