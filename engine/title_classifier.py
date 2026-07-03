"""Second-stage title gate: an LLM (Qwen via an OpenAI-compatible API) judges the
titles the keyword filter can't decide.

Keyword-obvious cases never reach the model: config_store.excluded() drops
(senior/phd/...), a *domain* include term keeps (software engineer/swe/...). Only
titles matching neither -- including seniority-only matches like "Supply Chain
Intern" -- are classified here. The 7 seniority include terms (intern, new grad,
early career, ...) are deliberately NOT treated as auto-keep, so this works
whether or not they've been removed from the Supabase keywords table.

Results are cached in the Supabase `title_labels` table so each distinct title is
asked once. Any failure (no key, network/API/parse error) degrades to the keyword
decision (drop, matching the "require a software term" intent) -- the pipeline
never blocks on this.

Env (all optional; without QWEN_API_KEY the model is skipped and the gate is a
pure domain-keyword filter):
    QWEN_API_KEY    provider key (DashScope / Alibaba Model Studio, ...)
    QWEN_API_BASE   OpenAI-compatible base URL
                    (default DashScope-intl; China: dashscope.aliyuncs.com)
    QWEN_MODEL      first-choice model slug (falls back to FALLBACK_MODELS)
"""

import json
import os
import re

import requests

import config_store

# Seniority-only include terms: matching one of these is NOT enough to auto-keep
# (a "... Intern" can be any field). Titles that match only these fall through to
# the model. Kept in sync with the terms the software-domain gate wants dropped.
SENIORITY = {
    "intern", "new grad", "new graduate", "early career",
    "entry level", "university graduate", "associate engineer",
}

BATCH = 40                 # titles per model request
TABLE = "title_labels"

# Free-tier fallback chain: on DashScope each model (incl. each dated snapshot)
# has its OWN 1M-token free quota, so when one is exhausted (AllocationQuota
# error) or can't serve a plain non-streaming chat call, the next takes over.
# QWEN_MODEL (env) is tried first when set. Deliberately absent: qwen-mt-*
# (translation-only API), qwq/qvq and every *-thinking model (streaming-only
# reasoning that burns quota on thinking tokens), and the omni / livetranslate /
# tts / ocr / wan entries (not chat/completions text models). Ordered: text
# flash/plus/turbo tiers, max tier, open-weight instruct, coder, third-party,
# then the vision models as text-capable spares, character models last.
FALLBACK_MODELS = [
    "qwen-plus-latest",
    "qwen-turbo-latest",
    "qwen-flash-2025-07-28",
    "qwen-plus-2025-12-01",
    "qwen-plus-2025-09-11",
    "qwen-plus-2025-07-28",
    "qwen-plus-2025-07-14",
    "qwen-plus-2025-04-28",
    "qwen-turbo-2025-04-28",
    "qwen3.7-plus",
    "qwen3.7-plus-2026-05-26",
    "qwen3.6-plus",
    "qwen3.6-plus-2026-04-02",
    "qwen3.6-flash",
    "qwen3.6-flash-2026-04-16",
    "qwen3.5-plus",
    "qwen3.5-plus-2026-04-20",
    "qwen3.5-plus-2026-02-15",
    "qwen3.5-flash",
    "qwen3.5-flash-2026-02-23",
    "qwen3.7-max",
    "qwen3.7-max-preview",
    "qwen3.7-max-2026-06-08",
    "qwen3.7-max-2026-05-20",
    "qwen3.7-max-2026-05-17",
    "qwen3.6-max-preview",
    "qwen3-max",
    "qwen3-max-preview",
    "qwen3-max-2026-01-23",
    "qwen3-max-2025-10-30",
    "qwen3-max-2025-09-23",
    "qwen-max",
    "qwen-max-2025-01-25",
    "qwen3.5-397b-a17b",
    "qwen3.5-122b-a10b",
    "qwen3.5-35b-a3b",
    "qwen3.5-27b",
    "qwen3.6-35b-a3b",
    "qwen3.6-27b",
    "qwen3-30b-a3b-instruct-2507",
    "qwen3-235b-a22b-instruct-2507",
    "qwen3-next-80b-a3b-instruct",
    "qwen3-235b-a22b",
    "qwen3-32b",
    "qwen3-30b-a3b",
    "qwen3-14b",
    "qwen3-8b",
    "qwen3-4b",
    "qwen3-1.7b",
    "qwen3-0.6b",
    "qwen2.5-72b-instruct",
    "qwen2.5-32b-instruct",
    "qwen2.5-14b-instruct",
    "qwen2.5-14b-instruct-1m",
    "qwen2.5-7b-instruct",
    "qwen2.5-7b-instruct-1m",
    "qwen3-coder-plus",
    "qwen3-coder-plus-2025-09-23",
    "qwen3-coder-plus-2025-07-22",
    "qwen3-coder-next",
    "qwen3-coder-flash",
    "qwen3-coder-flash-2025-07-28",
    "qwen3-coder-480b-a35b-instruct",
    "qwen3-coder-30b-a3b-instruct",
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-v3.2",
    "glm-5.2",
    "glm-5.1",
    "kimi-k2.7-code",
    "qwen3-vl-flash",
    "qwen3-vl-flash-2026-01-22",
    "qwen3-vl-flash-2025-10-15",
    "qwen3-vl-plus",
    "qwen3-vl-plus-2025-12-19",
    "qwen3-vl-plus-2025-09-23",
    "qwen3-vl-235b-a22b-instruct",
    "qwen3-vl-32b-instruct",
    "qwen3-vl-30b-a3b-instruct",
    "qwen3-vl-8b-instruct",
    "qwen2.5-vl-72b-instruct",
    "qwen2.5-vl-32b-instruct",
    "qwen2.5-vl-7b-instruct",
    "qwen2.5-vl-3b-instruct",
    "qwen-vl-max-latest",
    "qwen-vl-max",
    "qwen-vl-max-2025-08-13",
    "qwen-vl-max-2025-04-08",
    "qwen-vl-plus-latest",
    "qwen-vl-plus",
    "qwen-vl-plus-2025-08-15",
    "qwen-vl-plus-2025-05-07",
    "qwen-vl-plus-2025-01-25",
    "qwen-flash-character",
    "qwen-plus-character",
]

# Matches DashScope's quota-exhaustion error bodies (e.g. code
# "AllocationQuota.FreeTierOnly", "the free quota has been exhausted").
_QUOTA_ERR = re.compile(r"allocationquota|free quota|insufficient_quota", re.I)

# A model that can't serve this call shape at all (doesn't exist, needs
# streaming, rejects the params) -- skip it like an exhausted one instead of
# retrying it forever and wedging the chain on a permanently-broken entry.
_SKIP_ERR = re.compile(
    r"model.{0,60}(not exist|not found|unsupport)|only support.{0,30}stream"
    r"|enable_thinking|invalidparameter|access denied", re.I)

_model_idx = 0             # first not-yet-exhausted model this process has seen


def _models():
    env = os.environ.get("QWEN_MODEL")
    return ([env] if env else []) + [m for m in FALLBACK_MODELS if m != env]

_SYSTEM = (
    "You classify job titles for a software-engineering job board aimed at CS "
    "students and new grads. For each title decide if it is a software/CS "
    "engineering role: software engineering, web/backend/frontend/full-stack, "
    "data/ML/AI engineering or data science, systems/platform/infrastructure/"
    "security/DevOps/SRE, embedded/firmware, or mobile. Roles that are NOT "
    "software: sales, marketing, finance/analyst, operations, supply chain, "
    "mechanical/electrical/civil engineering, hardware-only, healthcare/nursing, "
    "admin, support, recruiting, content, design. Reply with ONLY a compact JSON "
    'array like [{"i":0,"sw":true},{"i":1,"sw":false}] -- no prose.'
)


def _norm(title):
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def _domain_include(include):
    """Include terms that count as a definite software keep (seniority stripped)."""
    return [i for i in include if i.lower() not in SENIORITY]


def _cache_get(norms):
    """{title_norm: is_software} for the norms already classified."""
    if not norms:
        return {}
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        return {}
    out = {}
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    uniq = sorted(set(norms))
    for i in range(0, len(uniq), 100):                 # PostgREST `in.()` URL length
        chunk = uniq[i:i + 100]
        quoted = ",".join('"' + n.replace('"', '""') + '"' for n in chunk)
        try:
            r = requests.get(f"{url.rstrip('/')}/rest/v1/{TABLE}",
                             params={"select": "title_norm,is_software",
                                     "title_norm": f"in.({quoted})"},
                             headers=h, timeout=30)
            r.raise_for_status()
            for row in r.json():
                out[row["title_norm"]] = row["is_software"]
        except Exception as e:
            print(f"[classifier] cache read failed: {e}")
            return out
    return out


def _cache_put(labels, model):
    """Upsert {title_norm: is_software} into the cache."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key) or not labels:
        return
    rows = [{"title_norm": n, "is_software": sw, "model": model} for n, sw in labels.items()]
    try:
        r = requests.post(f"{url.rstrip('/')}/rest/v1/{TABLE}",
                          params={"on_conflict": "title_norm"},
                          json=rows,
                          headers={"apikey": key, "Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json",
                                   "Prefer": "resolution=merge-duplicates,return=minimal"},
                          timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[classifier] cache write failed: {e}")


def _ask(titles):
    """Classify a batch of raw titles via the first model in the fallback chain
    that still has quota. Returns ({index: bool}, model_used) for the indices the
    model answered; raises on transport/auth failure or when every model's quota
    is exhausted. The chain position sticks for the process, so an exhausted
    model costs one wasted request per run, not per batch."""
    global _model_idx
    key = os.environ.get("QWEN_API_KEY")
    base = os.environ.get(
        "QWEN_API_BASE",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1").rstrip("/")
    listing = "\n".join(f"{i}: {t}" for i, t in enumerate(titles))
    models = _models()
    while _model_idx < len(models):
        model = models[_model_idx]
        r = requests.post(
            f"{base}/chat/completions",
            # enable_thinking=False: required by the open-weight qwen3 hybrids
            # for non-streaming calls; accepted (or ignored) by the rest.
            json={"model": model, "temperature": 0, "enable_thinking": False,
                  "messages": [{"role": "system", "content": _SYSTEM},
                               {"role": "user", "content": listing}]},
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=60,
        )
        if r.status_code != 200 and _QUOTA_ERR.search(r.text or ""):
            print(f"[classifier] {model} quota exhausted; falling back", flush=True)
            _model_idx += 1
            continue
        if r.status_code != 200 and _SKIP_ERR.search(r.text or ""):
            print(f"[classifier] {model} can't serve this call "
                  f"({r.text[:120]!r}); skipping", flush=True)
            _model_idx += 1
            continue
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", content, re.S)         # tolerate stray prose/fences
        if not m:
            raise ValueError(f"no JSON array in model reply: {content[:200]!r}")
        out = {}
        for item in json.loads(m.group(0)):
            out[int(item["i"])] = bool(item["sw"])
        return out, model
    raise RuntimeError("every fallback model's free quota is exhausted")


def classify(titles):
    """Classify raw titles. Returns {title_norm: is_software} for every title it
    could resolve (cache or model); unresolved titles are omitted. Batched; each
    distinct unseen title is asked once and cached. Never raises."""
    norms = {t: _norm(t) for t in titles}
    resolved = _cache_get(list(norms.values()))
    if not os.environ.get("QWEN_API_KEY"):
        return resolved
    # Distinct titles still unknown (keep one representative raw title per norm).
    todo = {}
    for raw, n in norms.items():
        if n not in resolved and n not in todo:
            todo[n] = raw
    items = list(todo.items())                          # [(norm, raw), ...]
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        try:
            answered, model = _ask([raw for _, raw in chunk])
        except Exception as e:
            print(f"[classifier] model call failed ({len(chunk)} titles): {e}")
            continue
        fresh = {chunk[idx][0]: sw for idx, sw in answered.items() if idx < len(chunk)}
        resolved.update(fresh)
        _cache_put(fresh, model)
    return resolved


def ambiguous(title, include, exclude):
    """True if neither an exclude term nor a domain include term decides `title`,
    so it needs the model. Use to pick which titles to classify() up front."""
    if config_store.excluded(title, exclude):
        return False
    t = (title or "").lower()
    domain = _domain_include(include)
    return not (domain and any(re.search(rf"\b{re.escape(i.lower())}", t) for i in domain))


def keep(title, include, exclude, labels=None):
    """The gate. exclude term -> drop; domain include term -> keep; otherwise use
    the classifier label (from a preloaded `labels` map, else a live lookup).
    Unknown/unavailable label -> drop (the safe, keyword-consistent default).

    Pass `labels` (from a prior classify() over the run's titles) to keep this
    synchronous and network-free in hot loops."""
    if config_store.excluded(title, exclude):
        return False
    t = (title or "").lower()
    domain = _domain_include(include)
    if domain and any(re.search(rf"\b{re.escape(i.lower())}", t) for i in domain):
        return True
    if labels is None:
        labels = classify([title])
    return bool(labels.get(_norm(title), False))


if __name__ == "__main__":                              # quick manual test
    import sys
    inc, exc = config_store.keywords()
    for ti in sys.argv[1:]:
        print(f"{keep(ti, inc, exc)}\t{ti}")
