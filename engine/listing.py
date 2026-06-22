"""The common format every source converges to.

Content fields (key, company, title, locations, url, live) are filled by each
parser. Provenance fields (source, role_type) are stamped on by the engine from
the source config, so parsers don't need to know which repo they're reading.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Listing:
    key: str                    # stable unique id within its own source
    company: str
    title: str
    locations: tuple = ()
    url: str = ""
    live: bool = True
    source: str = ""            # e.g. "simplify-intern"  (stamped by engine)
    role_type: str = ""         # "intern" | "newgrad"     (stamped by engine)
    annual_salary: float | None = None   # USD/yr when a source exposes pay (jobhive)
    priority: bool = False                # referral/priority tag (classify.is_priority)

    def display(self):
        loc = ", ".join(self.locations) or "\u2014"
        return f"{self.company} | {self.title} | {loc} | {self.url}"
