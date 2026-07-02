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
    QWEN_MODEL      model slug (default qwen-flash)
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
    """Classify a batch of raw titles via the model. Returns {index: bool} for the
    indices the model answered; raises on transport/auth failure."""
    key = os.environ.get("QWEN_API_KEY")
    base = os.environ.get(
        "QWEN_API_BASE",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = os.environ.get("QWEN_MODEL", "qwen-flash")
    listing = "\n".join(f"{i}: {t}" for i, t in enumerate(titles))
    r = requests.post(
        f"{base}/chat/completions",
        json={"model": model, "temperature": 0,
              "messages": [{"role": "system", "content": _SYSTEM},
                           {"role": "user", "content": listing}]},
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", content, re.S)             # tolerate stray prose/fences
    if not m:
        raise ValueError(f"no JSON array in model reply: {content[:200]!r}")
    out = {}
    for item in json.loads(m.group(0)):
        out[int(item["i"])] = bool(item["sw"])
    return out


def classify(titles):
    """Classify raw titles. Returns {title_norm: is_software} for every title it
    could resolve (cache or model); unresolved titles are omitted. Batched; each
    distinct unseen title is asked once and cached. Never raises."""
    norms = {t: _norm(t) for t in titles}
    resolved = _cache_get(list(norms.values()))
    if not os.environ.get("QWEN_API_KEY"):
        return resolved
    model = os.environ.get("QWEN_MODEL", "qwen-flash")
    # Distinct titles still unknown (keep one representative raw title per norm).
    todo = {}
    for raw, n in norms.items():
        if n not in resolved and n not in todo:
            todo[n] = raw
    items = list(todo.items())                          # [(norm, raw), ...]
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        try:
            answered = _ask([raw for _, raw in chunk])
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
