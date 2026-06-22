"""Pure URL canonicalizer for cross-source dedup. String parsing only, no network.

Maps an ATS job-posting URL to a stable identity "provider:tenant:id", so the
same role found via different sources collapses to one dedup key. Query string
and fragment are dropped first; the host is matched and the path is split into
segments, so locale/title differences in the path don't change the key.

Recognized shapes:
    workday          {tenant}.wdN.myworkdayjobs.com/.../{title}_{REQ}
    greenhouse       boards|job-boards.greenhouse.io/{org}/jobs/{id}
    lever            jobs.lever.co/{org}/{uuid}
    ashby            jobs.ashbyhq.com/{org}/{uuid}
    smartrecruiters  jobs.smartrecruiters.com/{org}/{id}

Unrecognized host/shape -> None (caller falls back to the listing's own key;
don't guess). Add providers as needed.
"""

import re
from urllib.parse import urlsplit

_WORKDAY_HOST = re.compile(r"^(?P<tenant>[^.]+)\.wd\d+\.myworkdayjobs\.com$")
_GREENHOUSE_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
_ORG_ID_HOSTS = {
    "jobs.lever.co": "lever",
    "jobs.ashbyhq.com": "ashby",
    "jobs.smartrecruiters.com": "smartrecruiters",
}


def canonicalize(url):
    if not url:
        return None

    parts = urlsplit(url.strip())                       # drops nothing yet, but…
    host = parts.netloc.lower().split("@")[-1].split(":")[0]   # strip creds/port
    if host.startswith("www."):
        host = host[4:]
    segments = [s for s in parts.path.split("/") if s]  # query/fragment ignored
    if not host or not segments:
        return None

    # Workday: tenant (subdomain) + requisition id, the suffix after the final
    # "_" of the last segment on a /job/ detail page.
    m = _WORKDAY_HOST.match(host)
    if m and "job" in segments:
        title, _, req = segments[-1].rpartition("_")
        return f"workday:{m['tenant']}:{req}" if title and req else None

    # Greenhouse: /{org}/jobs/{id}; both board hosts fold into one provider.
    if host in _GREENHOUSE_HOSTS and "jobs" in segments:
        i = segments.index("jobs")
        if i >= 1 and i + 1 < len(segments):
            return f"greenhouse:{segments[i - 1]}:{segments[i + 1]}"
        return None

    # Lever / Ashby / SmartRecruiters: /{org}/{id}.
    provider = _ORG_ID_HOSTS.get(host)
    if provider and len(segments) >= 2:
        return f"{provider}:{segments[0]}:{segments[1]}"

    return None
