"""Is this role realistic for 0-3 years of experience? Judged by Claude.

Runs on the NEW jobhive rows of a poll, after the keyword gate and after the
state-file dedup -- never on the raw scrape. That placement is the whole cost
story: the gate+dedup set is ~150 rows/day, while the raw scrape is ~3,300
companies' full boards (hundreds of roles each).

engine/yoe.py runs first and is a free prefilter: a JD that states "8+ years"
never reaches the model. Only the candidates (no number stated, or <= 3) are
sent, which is ~45% of jobs.

Transport is the **Claude Code CLI** (`claude -p`), not the Anthropic SDK, so
this runs on the subscription rather than a per-token API key. Consequences
worth knowing:

  * ~16s per call (a Node process start plus a tool-call round trip), against
    ~2s for a direct API call. Concurrency in run.py covers it.
  * Each call is its own session -- no shared context, no conversation state.
  * `--json-schema` enforces the output shape; the parsed object comes back on
    the envelope's `structured_output`.
  * It counts against Claude Code usage limits, not a dollar balance.

FAILS OPEN, deliberately. The previous title classifier was a hard dependency
and the pipeline lost its gate when the quota died. Here every failure path --
CLI missing, not logged in, timeout, malformed output, over the call ceiling --
returns None, the row still stores with its regex `min_years_exp`, and the poll
completes. The model never decides whether a job is stored or notified.

Env:
    JOBFIT_MAX_CALLS    per-run ceiling on calls (default 400)
    JOBFIT_MODEL        model alias passed to --model (default "haiku")
    JOBFIT_TIMEOUT      per-call seconds (default 120)
    JOBFIT_CLI          path to the claude binary (default "claude")
"""

import json
import os
import subprocess
import sys
import tempfile
import threading

CLI = os.environ.get("JOBFIT_CLI", "claude")
MODEL = os.environ.get("JOBFIT_MODEL", "haiku")

# The requirements section is what decides this, and it is sent on every call.
MAX_JD_CHARS = 4000

# Consecutive failures after which the rest of the run is skipped. Not logged in
# and CLI-missing both fail every time; 150 sequential 120s timeouts would stall
# the poll far past its systemd timeout.
MAX_CONSECUTIVE_FAILURES = 3

SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "junior_ok": {"type": "boolean"},
        "min_years": {"type": ["integer", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["junior_ok", "min_years", "reason"],
    "additionalProperties": False,
}, sort_keys=True)

# Spelled out because the first version of this prompt marked a "2+ years" role
# junior_ok=false -- the model read "0-3 years" as "no experience at all" unless
# the boundary is stated as an explicit rule.
SYSTEM = (
    "You screen software job postings for a candidate with 0-3 years of professional "
    "experience (recent graduate or early career).\n\n"
    "Decide junior_ok by this rule, in order:\n"
    "1. If the posting requires MORE than 3 years of experience, junior_ok is false.\n"
    "2. If the title is senior, staff, principal, lead, architect, director, or a "
    "management role, junior_ok is false.\n"
    "3. If it requires a PhD or deep specialisation a recent graduate could not have, "
    "junior_ok is false.\n"
    "4. Otherwise junior_ok is TRUE. This includes postings requiring 1, 2, or 3 years, "
    "and postings that state no experience requirement at all. A role asking for 2 or 3 "
    "years IS acceptable -- do not reject it for not being zero.\n\n"
    "min_years is the lowest number of years the posting requires, or null if it never "
    "states one. Do not infer a number that is not written down.\n\n"
    "Judge only what the posting says. reason must be at most 100 characters."
)

# Reentrant: the ceiling check calls _disable() while holding the lock, and a
# plain Lock deadlocks there -- which froze the poll precisely when the call
# ceiling was reached, until systemd's timeout killed the run.
_lock = threading.RLock()
_calls = 0
_failures = 0
_disabled_reason = None


def _limit():
    try:
        return int(os.environ.get("JOBFIT_MAX_CALLS", "400"))
    except ValueError:
        return 400


def _timeout():
    try:
        return float(os.environ.get("JOBFIT_TIMEOUT", "120"))
    except ValueError:
        return 120.0


def _disable(reason):
    global _disabled_reason
    with _lock:
        if _disabled_reason is None:
            _disabled_reason = reason
            print(f"[jobfit] disabled for this run: {reason}", file=sys.stderr)


def _note_failure(detail):
    global _failures
    with _lock:
        _failures += 1
        count = _failures
    print(f"[jobfit] {detail}", file=sys.stderr)
    if count >= MAX_CONSECUTIVE_FAILURES:
        _disable(f"{count} consecutive failures; last: {detail}")


def _note_success():
    global _failures
    with _lock:
        _failures = 0


def judge(title, company, description):
    """{"junior_ok": bool, "min_years": int|None, "reason": str} or None.

    None means "not judged" -- it never means "not a fit"; callers must treat it
    as unknown.
    """
    global _calls

    if _disabled_reason or not description:
        return None

    with _lock:
        if _calls >= _limit():
            _disable(f"hit JOBFIT_MAX_CALLS ({_limit()})")
            return None
        _calls += 1

    prompt = (
        f"Title: {title}\n"
        f"Company: {company}\n\n"
        f"Job description:\n{description[:MAX_JD_CHARS]}"
    )

    argv = [
        CLI, "-p",
        "--model", MODEL,
        "--output-format", "json",
        "--json-schema", SCHEMA,
        # No tools, no MCP servers, no skills: this is a text judgement, and a
        # tool call here would mean filesystem access from the poll path.
        "--tools", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--system-prompt", SYSTEM,
    ]

    try:
        # cwd is a neutral directory so no project CLAUDE.md, settings, or
        # workspace-trust state leaks into the judgement.
        proc = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=_timeout(),
            cwd=tempfile.gettempdir(),
        )
    except FileNotFoundError:
        _disable(f"{CLI} not found on PATH")
        return None
    except subprocess.TimeoutExpired:
        _note_failure(f"{title[:40]!r}: timed out after {_timeout():.0f}s")
        return None
    except Exception as e:                                   # pragma: no cover
        _note_failure(f"{title[:40]!r}: {type(e).__name__}: {e}")
        return None

    if proc.returncode != 0:
        _note_failure(f"{title[:40]!r}: exit {proc.returncode}: "
                      f"{(proc.stderr or proc.stdout or '').strip()[:200]}")
        return None

    try:
        envelope = json.loads(proc.stdout)
    except (ValueError, TypeError):
        _note_failure(f"{title[:40]!r}: unparseable CLI output")
        return None

    if envelope.get("is_error"):
        _note_failure(f"{title[:40]!r}: {str(envelope.get('result'))[:200]}")
        return None

    # --json-schema puts the validated object here; `result` is the same thing as
    # a JSON string, so prefer the parsed field and fall back to the string.
    fit = envelope.get("structured_output")
    if not isinstance(fit, dict):
        try:
            fit = json.loads(envelope.get("result") or "")
        except (ValueError, TypeError):
            fit = None
    if not isinstance(fit, dict) or "junior_ok" not in fit:
        _note_failure(f"{title[:40]!r}: no structured output in envelope")
        return None

    _note_success()
    years = fit.get("min_years")
    return {
        "junior_ok": bool(fit["junior_ok"]),
        "min_years": years if isinstance(years, int) else None,
        "reason": str(fit.get("reason") or "")[:200],
    }


def calls_made():
    return _calls
