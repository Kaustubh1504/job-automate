"""Parser for the Pitt CSC / Simplify listings.json schema.

Shared by Simplify and vansh; their internship and new-grad repos all use this
identical schema, so each is just a source-config entry pointing here.
"""

from listing import Listing
from registry import register


@register("simplify_schema")
def parse(resp):
    out = []
    for j in resp.json():
        out.append(Listing(
            key=j["id"],
            company=j["company_name"],
            title=j["title"],
            locations=tuple(j.get("locations", [])),
            url=j["url"],
            live=bool(j.get("active") and j.get("is_visible")),
        ))
    return out
