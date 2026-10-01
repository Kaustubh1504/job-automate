"""Does this JD explicitly refuse visa sponsorship?

Only an EXPLICIT refusal counts, matching how jobright treats H1B: an outright
"No" is dropped, while "Not Sure" and silence pass. Most postings say nothing
about sponsorship, and treating silence as a refusal would throw away most of
the board.

Deterministic, and it runs before the model: a role that won't sponsor is not
worth a call, whatever its seniority.
"""

import re

# Explicit refusals. Each pattern carries its own negation so "we are happy to
# sponsor visas" cannot match -- the word "sponsor" alone is not a signal.
_BLOCKED = re.compile(
    r"(?:"
    r"(?:do|does|can|will|are|is)\s*(?:not|n't)\s*(?:be\s+)?(?:able\s+to\s+)?(?:offer|provide|support)?\s*"
    r"(?:visa\s+|employment\s+|immigration\s+)?sponsor(?:ship|ing)?"
    r"|unable\s+to\s+(?:offer|provide|support)?\s*(?:visa\s+)?sponsor(?:ship|ing)?"
    r"|no\s+(?:visa\s+|employment\s+)?sponsorship"
    r"|without\s+(?:the\s+need\s+for\s+)?(?:visa\s+|employment\s+)?sponsorship"
    r"|sponsorship\s+is\s+not\s+(?:available|offered|provided)"
    r"|not\s+(?:offer|provide|consider)\s+(?:visa\s+)?sponsorship"
    r"|must\s+be\s+a\s+(?:u\.?s\.?|united\s+states)\s+citizen"
    r"|u\.?s\.?\s+citizenship\s+(?:is\s+)?required"
    r"|requires?\s+u\.?s\.?\s+citizenship"
    r"|(?:active\s+)?(?:security\s+)?clearance\s+requires?\s+u\.?s\.?\s+citizenship"
    r")",
    re.I,
)


def blocks_sponsorship(text):
    """True only when the posting states it will not sponsor.

    Silence returns False -- the vast majority of JDs never mention it, and the
    point is to drop the explicit no's, not to guess.
    """
    if not text:
        return False
    return bool(_BLOCKED.search(text))
