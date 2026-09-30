"""What counts as New Grad, for the Discord digest.

Mirrors dashboard/lib/newgrad.js so the notification and the /newgrad page agree
on the same roles. **Change one, change the other** -- they are two runtimes, so
the rule cannot be shared as code. (The durable fix is persisting the verdict as
a column and having the dashboard read it; not done yet.)

    GitHub repos  -- the two new-grad listing repos (the intern repos are not)
    Built In      -- its search URL is filtered to internship + entry-level, so
                     a non-intern title from it is entry-level by construction
    jobhive       -- Claude's 0-3yrs verdict (engine/llm_fit.py), falling back to
                     the years engine/yoe.py read out of the JD when unjudged

An intern title is excluded first, whatever the source said: internships have
their own digest and their own tab.

LinkedIn is in the dashboard's version but not here on purpose -- those rows come
from jobspy, which runs in a different service and notifies separately.
"""

import re

MAX_YEARS_EXP = 3

NEWGRAD_REPOS = {"simplify-newgrad", "vansh-newgrad"}

INTERN_RE = re.compile(r"\bintern(ship)?\b", re.I)


def is_newgrad(listing):
    if INTERN_RE.search(listing.title or ""):
        return False

    source = (listing.source or "").lower()

    if source in NEWGRAD_REPOS:
        return True
    if source.startswith("builtin"):
        return True
    if source == "jobhive":
        # A null verdict means NOT JUDGED (no login, call failed, over the run's
        # ceiling), not "no" -- fall back to the number read out of the text.
        if listing.llm_junior_ok is not None:
            return listing.llm_junior_ok
        return (listing.min_years_exp is not None
                and listing.min_years_exp <= MAX_YEARS_EXP)

    return False
