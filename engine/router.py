"""Routing stage for platform-sourced listings (the cards the browser extension
POSTs in from LinkedIn / Indeed / Handshake / NUworks).

Each platform listing is routed to exactly one action:
  KEEP         -> unique inventory; emit as a listing.
  DROP         -> a monitored company's offsite job; jobhive already has it.
  NEW_COMPANY  -> an unmonitored company's offsite job; surface "add to monitoring?".

The critical fork is `easy_apply`: an in-platform (Easy Apply) job has no ATS
equivalent, so it is ALWAYS kept and NEVER routed toward jobhive. Only OFFSITE
jobs (apply on the company's own site) are jobhive's territory.

Per-platform behavior is a one-line table entry, not a branch:
  "company-discovery" -> has the easy-apply fork; offsite -> monitored check.
  "keep-direct"       -> employer-direct postings (university/co-op); always KEEP.
Adding a platform later means adding one row to PLATFORM_BEHAVIOR.
"""

from dataclasses import dataclass

import company_resolver
import config_store
from company_norm import canon_company

PLATFORM_BEHAVIOR = {
    "linkedin": "company-discovery",
    "indeed": "company-discovery",
    "handshake": "keep-direct",
    "nuworks": "keep-direct",
}

KEEP, DROP, NEW_COMPANY = "KEEP", "DROP", "NEW_COMPANY"


@dataclass(frozen=True)
class PlatformListing:
    platform: str
    company: str
    title: str
    location: str
    platform_job_id: str
    url: str
    posted: str
    easy_apply: bool


@dataclass(frozen=True)
class Decision:
    action: str          # KEEP | DROP | NEW_COMPANY
    reason: str
    suggested_ats: str | None = None   # set on NEW_COMPANY when it resolves
    suggested_slug: str | None = None


_monitored = None  # (set of (ats, slug), set of canonical names)


def _monitored_companies():
    """Monitored targets as both (ats, slug) pairs and canonical names.

    Names are derived from the non-URL slugs (workday slugs are full URLs and
    aren't name-like, so those rely on the (ats, slug) match instead).
    """
    global _monitored
    if _monitored is None:
        targets = config_store.targets()
        pairs = {(t["ats"], t["slug"]) for t in targets}
        names = {canon_company(t["slug"]) for t in targets if "://" not in t["slug"]}
        _monitored = (pairs, names - {""})
    return _monitored


def route(listing):
    behavior = PLATFORM_BEHAVIOR.get(listing.platform.lower())

    if behavior is None:
        return Decision(KEEP, f"unknown platform '{listing.platform}' -- keep by default")

    if behavior == "keep-direct":
        return Decision(KEEP, f"{listing.platform}: employer-direct posting, no ATS equivalent")

    # company-discovery platform (LinkedIn / Indeed) below.
    if listing.easy_apply:
        return Decision(KEEP, f"{listing.platform} Easy Apply: in-platform inventory, not on any ATS")

    # Offsite apply -> jobhive's territory. Is the company already monitored?
    pairs, names = _monitored_companies()
    if canon_company(listing.company) in names:
        return Decision(DROP, f"'{listing.company}' is monitored -- jobhive already scrapes it every cycle")

    resolved = company_resolver.resolve(listing.company)
    if resolved and resolved in pairs:
        return Decision(DROP, f"'{listing.company}' is monitored ({resolved[0]}:{resolved[1]}) -- jobhive covers it")

    if resolved:
        ats, slug = resolved
        return Decision(
            NEW_COMPANY,
            f"'{listing.company}' not monitored -- add to monitoring? resolves to {ats}:{slug}\n"
            f"             {listing.url}",
            ats,
            slug,
        )

    return Decision(
        KEEP,
        f"'{listing.company}' not monitored and not on any supported ATS -- keep directly (likely a startup/unique role)",
    )


def _samples():
    """One listing per routing path. The monitored sample is pulled from the
    live config so the DROP demo is deterministic regardless of targets.json."""
    pairs, names = _monitored_companies()
    monitored_name = next(iter(names), "stripe")

    def L(platform, company, easy_apply, jid="0", url="https://example.com/job"):
        return PlatformListing(platform, company, "Software Engineer Intern",
                               "Boston, MA", jid, url, "2h ago", easy_apply)

    return [
        L("linkedin", "Some Startup", easy_apply=True, jid="111", url="https://www.linkedin.com/jobs/view/111/"),
        L("linkedin", monitored_name, easy_apply=False, jid="222"),
        L("indeed", "Linear", easy_apply=False, jid="333", url="https://linear.app/careers/333"),
        L("indeed", "Totally Fake Garage Startup", easy_apply=False, jid="444"),
        L("handshake", "Northeastern Co-op Employer", easy_apply=False, jid="555"),
        L("nuworks", "Local Research Lab", easy_apply=False, jid="666"),
    ]


def main():
    for listing in _samples():
        d = route(listing)
        ea = "easy-apply" if listing.easy_apply else "offsite   "
        print(f"[{d.action:<11}] {listing.platform:<9} {ea} {listing.company:<28} -> {d.reason}")


if __name__ == "__main__":
    main()
