"""Years-of-experience requirement, read out of a job description.

Only jobhive exposes description text (the repo parsers are link aggregators),
so this runs in that collector and the extracted number is what gets stored --
never the 5KB description itself.

Deliberately a regex, not a model: the Qwen title classifier was removed once
its quota died, and a silent per-row model dependency in the scrape path is the
same trap. What is stored is the *minimum* year count the posting asks for, so
the "how junior is this" threshold stays a query-time decision (<=3, <=2, ...)
instead of being baked in at scrape time.

Measured on 2,401 live JDs (greenhouse:stripe, ashby:openai, greenhouse:databricks):
a number is found for ~71%. The rest genuinely never state one -- common for
new-grad and intern postings -- which is why None means "unstated", not "zero".
"""

import re

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
          "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

_NUM = r"(\d{1,2}|" + "|".join(_WORDS) + r")"

# "2+ years", "1-3 years", "5–8 yrs", "two years", "two (2) years". The optional
# second number covers ranges; only the low end is taken, since that's the actual
# bar. `_PAREN` absorbs the numeral legal-style JDs repeat after the word.
_PAREN = r"(?:\s*\(\s*\d{1,2}\s*\))?"
_SPAN = re.compile(
    _NUM + _PAREN + r"\s*(?:\+|plus)?\s*(?:(?:-|–|—|to|or)\s*" + _NUM + r"\s*(?:\+|plus)?\s*)?"
    r"(?:\+)?\s*(?:year|yr)s?\b",
    re.I,
)

# A year count only counts as a requirement if the surrounding text is talking
# about experience -- otherwise "3 years" out of a tenure or vesting sentence
# would read as a bar.
_CUE = re.compile(r"experience|exp\.|background|working|industry|professional", re.I)

# Phrases that mention years but are never an experience bar.
_VETO = re.compile(
    r"\d\s*-?\s*year\s+(?:degree|program|college|university|school)"
    r"|year[- ]over[- ]year|years old|per year|/year|a year",
    re.I,
)

_WINDOW = 90   # chars of context each side that _CUE / _VETO judge


def _to_int(token):
    token = token.lower()
    return _WORDS.get(token, int(token) if token.isdigit() else None)


def min_years(text):
    """Lowest year count `text` asks for as experience, or None if it states none.

    None is "unstated", not 0: a posting with no years mentioned is usually
    intern/new-grad, but it may also just be a terse JD, so callers decide how
    to treat the difference.
    """
    if not text:
        return None

    lowest = None
    for match in _SPAN.finditer(text):
        context = text[max(0, match.start() - _WINDOW): match.end() + _WINDOW]
        if not _CUE.search(context) or _VETO.search(context):
            continue
        value = _to_int(match.group(1))
        if value is None or value > 50:      # guards a stray 4-digit-ish match
            continue
        if lowest is None or value < lowest:
            lowest = value
    return lowest
