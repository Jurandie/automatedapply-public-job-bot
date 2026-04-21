from __future__ import annotations


EUROPE_TERMS = (
    "europe",
    "european",
    " eu ",
    "eea",
    "emea",
    "cet",
    "cest",
    "gmt",
    "utc+0",
    "utc+1",
    "utc+2",
    "ireland",
    "dublin",
    "united kingdom",
    "uk",
    "portugal",
    "spain",
    "spanish",
    "madrid",
    "barcelona",
    "malaga",
    "mÃ¡laga",
    "valencia",
    "valÃ¨ncia",
    "sevilla",
    "seville",
    "zaragoza",
    "bilbao",
    "france",
    "germany",
    "netherlands",
    "belgium",
    "luxembourg",
    "switzerland",
    "austria",
    "denmark",
    "sweden",
    "norway",
    "finland",
    "poland",
    "czech",
    "estonia",
    "latvia",
    "lithuania",
    "italy",
    "greece",
    "malta",
    "cyprus",
    "romania",
    "bulgaria",
    "hungary",
    "croatia",
    "slovenia",
    "slovakia",
)

IRELAND_TERMS = ("ireland", "dublin", "cork", "galway", "limerick")
ITALY_TERMS = ("italy", "italia", "italian", "milan", "milano", "rome", "roma", "turin", "torino", "bologna")

TARGET_COUNTRIES = {"Ireland", "Italy"}

NON_TARGET_EUROPE_TERMS = tuple(
    term
    for term in EUROPE_TERMS
    if term
    not in {
        "ireland",
        "dublin",
        "italy",
        "milan",
        "milano",
    }
)

NON_TARGET_RESTRICTIONS = (
    "us only",
    "usa only",
    "u.s. only",
    "canada only",
    "latam only",
    "india only",
    "australia only",
    "must be based in us",
    "must be based in the us",
)


def detect_location(text: str) -> tuple[str | None, str]:
    lowered = f" {text.lower()} "

    if any(term in lowered for term in NON_TARGET_RESTRICTIONS):
        return "rejected_non_target", "location restricted outside target countries"

    if any(term in lowered for term in IRELAND_TERMS):
        return "Ireland", "Ireland detected"

    if any(term in lowered for term in ITALY_TERMS):
        return "Italy", "Italy detected"

    if any(term in lowered for term in NON_TARGET_EUROPE_TERMS):
        return "rejected_non_target", "location is European but outside target countries"

    if any(term in lowered for term in EUROPE_TERMS):
        return "rejected_non_target", "generic Europe location is not specific enough for target countries"

    return None, "location not explicit"
