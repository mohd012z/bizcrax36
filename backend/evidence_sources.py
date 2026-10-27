"""Deterministic evidence sources for agentic research (no-auth by default).

Each source returns small, checkable macro/evidence facts that the research
engine attaches to a result as context. Rules:
- no-auth endpoints fetch live; key-gated endpoints (OpenSanctions,
  OpenCorporates, Bank Negara) are used only when their env key is present.
- every record is labeled: basis "evidence" (retrieved now) or
  "unavailable" (source failed / no data); failures are recorded, never fatal.
- stdlib only (urllib); a `fetch` callable may be injected for tests.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "BizCrax36ResearchV2/2.0"

COUNTRY_CODES = {
    "malaysia": "MYS", "singapore": "SGP", "indonesia": "IDN",
    "thailand": "THA", "vietnam": "VNM", "philippines": "PHL",
    "china": "CHN", "japan": "JPN", "australia": "AUS", "united states": "USA",
    "india": "IND", "uae": "ARE", "united arab emirates": "ARE",
    "nigeria": "NGA", "south africa": "ZAF", "turkey": "TUR",
}

# World Bank indicator id -> short label. Macro context for opportunity
# research; each row is a labeled fact, not an assumption.
WORLD_BANK_INDICATORS = (
    ("NY.GDP.MKTP.KD.ZG", "GDP growth (annual %)"),
    ("FP.CPI.TOTL.ZG", "Inflation, CPI (annual %)"),
    ("SL.UEM.TOTL.ZS", "Unemployment (% of labor force)"),
)


def _default_get(url, timeout=20):
    req = Request(url, headers={"User-Agent": USER_AGENT,
                                "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return response.read(1_000_000)


def _resolver(fetch, timeout):
    """Return a single-arg getter(url). Injected `fetch` takes one URL arg
    (same convention as research_v2); default uses the timeout."""
    if fetch is not None:
        return fetch
    return lambda url: _default_get(url, timeout)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _country_code(country):
    return COUNTRY_CODES.get(str(country or "").strip().lower())


def world_bank(country, fetch=None, timeout=12):
    """Latest-year macro indicators from the World Bank (no key). One query per
    indicator (the v2 API rejects comma-joined ids)."""
    code = _country_code(country)
    if not code:
        return [{"source": "world_bank", "basis": "unavailable",
                 "label": "macro",
                 "detail": "country code not known to the indicator map"}]
    getter = _resolver(fetch, timeout)

    def one(indicator_id, label):
        url = ("https://api.worldbank.org/v2/country/%s/indicator/%s"
               "?format=json&per_page=1" % (code, indicator_id))
        try:
            data = json.loads(getter(url))
        except (OSError, ValueError) as exc:
            return {"source": "world_bank", "basis": "unavailable",
                    "label": label, "country": code, "detail": type(exc).__name__}
        if not (isinstance(data, list) and len(data) == 2 and data[1]):
            return {"source": "world_bank", "basis": "unavailable",
                    "label": label, "country": code, "detail": "no data for latest year"}
        row = data[1][0]
        value = row.get("value")
        if value is None:
            return {"source": "world_bank", "basis": "unavailable",
                    "label": label, "country": code, "detail": "null latest value"}
        return {"source": "world_bank", "basis": "evidence", "label": label,
                "country": code, "year": str(row.get("date")),
                "value": round(float(value), 2), "fetched_at": _now()}

    jobs = [(i, l) for i, l in WORLD_BANK_INDICATORS]
    if len(jobs) == 1:
        return [one(*jobs[0])]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(lambda j: one(*j), jobs))


def exchange_rates(base="MYR", symbols="USD,SGD,AUD", fetch=None, timeout=12):
    """Frankfurter (ECB reference rates, no key). Fail-open to currency-api."""
    getter = _resolver(fetch, timeout)
    url = ("https://api.frankfurter.dev/v1/latest?base=%s%s%s"
           % (base.upper(), "&symbols=" if symbols and symbols != "all" else "",
              symbols.upper() if symbols and symbols != "all" else ""))
    try:
        data = json.loads(getter(url))
        rates = data.get("rates") or {}
        if not rates:
            raise ValueError("no rates")
        out = []
        for code, rate in list(rates.items())[:8]:
            out.append({"source": "frankfurter_fx", "basis": "evidence",
                        "label": "1 %s = %.4f %s" % (base.upper(), float(rate), code),
                        "date": str(data.get("date", "")), "fetched_at": _now()})
        return out
    except (OSError, ValueError):
        # Fail-open secondary: jsDelivr-hosted currency-api snapshot (MYR base).
        try:
            data = json.loads(getter(
                "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/myr.json"))
            rates = data.get(base.lower()) or {}
            out = []
            for code in ("usd", "sgd", "aud", "jpy", "cny", "eur"):
                if code in rates:
                    out.append({"source": "currency_api_fx", "basis": "evidence",
                                "label": "1 %s = %.4f %s" % (base.upper(), float(rates[code]), code),
                                "date": str(data.get("date", "")), "fetched_at": _now()})
            return out or [{"source": "fx", "basis": "unavailable", "label": "fx",
                            "detail": "no rates retrieved"}]
        except (OSError, ValueError) as exc:
            return [{"source": "fx", "basis": "unavailable", "label": "fx",
                     "detail": type(exc).__name__}]


def research_literature(query, fetch=None, timeout=12):
    """Crossref: count + top titles of peer-reviewed work matching the topic (no key)."""
    getter = _resolver(fetch, timeout)
    url = ("https://api.crossref.org/works?query=%s&rows=3&select=title,DOI,published"
           % urlencode({"query": query})[:300])
    try:
        data = json.loads(getter(url))
    except (OSError, ValueError) as exc:
        return [{"source": "crossref", "basis": "unavailable", "label": "literature",
                 "detail": type(exc).__name__}]
    message = data.get("message") or {}
    total = message.get("total-results")
    out = [{"source": "crossref", "basis": "evidence", "label": "peer-reviewed literature",
            "detail": "%d works matching topic" % (int(total) if total is not None else 0),
            "total_results": total, "fetched_at": _now()}]
    for item in (message.get("items") or [])[:3]:
        title = (item.get("title") or ["?"])[0][:160]
        out.append({"source": "crossref", "basis": "evidence", "label": "literature",
                    "detail": title, "doi": item.get("DOI")})
    return out


def open_sanctions(query, fetch=None, timeout=15):
    """OpenSanctions counterparty search. Needs OPEN_SANCTIONS_API_KEY (optional)."""
    key = os.getenv("OPEN_SANCTIONS_API_KEY", "").strip()
    if not key:
        return [{"source": "open_sanctions", "basis": "unavailable", "label": "counterparties",
                 "detail": "OPEN_SANCTIONS_API_KEY not set"}]
    getter = _resolver(fetch, timeout)
    url = "https://api.opensanctions.org/search/?%s" % urlencode({"q": query, "size": 3})
    req = Request(url, headers={"User-Agent": USER_AGENT, "Authorization": "token " + key})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read(1_000_000))
    except (OSError, ValueError) as exc:
        return [{"source": "open_sanctions", "basis": "unavailable", "label": "counterparties",
                 "detail": type(exc).__name__}]
    results = (data.get("results") or [])[:3]
    if not results:
        return [{"source": "open_sanctions", "basis": "evidence", "label": "counterparties",
                 "detail": "no entities matched '%s'" % query[:60], "fetched_at": _now()}]
    out = []
    for r in results:
        out.append({"source": "open_sanctions", "basis": "evidence", "label": "counterparties",
                    "detail": (r.get("name") or "?")[:120], "fetched_at": _now()})
    return out


def open_corporates(query, country="malaysia", fetch=None, timeout=15):
    """OpenCorporates company-registry search. Needs OPEN_CORPORATES_API_KEY (optional)."""
    key = os.getenv("OPEN_CORPORATES_API_KEY", "").strip()
    if not key:
        return [{"source": "open_corporates", "basis": "unavailable", "label": "registries",
                 "detail": "OPEN_CORPORATES_API_KEY not set"}]
    getter = _resolver(fetch, timeout)
    code = _country_code(country) or "MY"
    url = ("https://api.opencorporates.com/v0.4/companies/search?%s"
           % urlencode({"q": query, "jurisdiction_code": code}))
    req = Request(url, headers={"User-Agent": USER_AGENT, "Authorization": "Token " + key})
    try:
        with urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read(1_000_000))
    except (OSError, ValueError) as exc:
        return [{"source": "open_corporates", "basis": "unavailable", "label": "registries",
                 "detail": type(exc).__name__}]
    companies = (data.get("results") or [])[:3]
    if not companies:
        return [{"source": "open_corporates", "basis": "evidence", "label": "registries",
                 "detail": "no registry entries matched", "fetched_at": _now()}]
    out = []
    for c in companies:
        name = (c.get("name") or "?")[:120]
        status = c.get("status") or "unknown"
        out.append({"source": "open_corporates", "basis": "evidence", "label": "registries",
                    "detail": "%s (%s)" % (name, status), "fetched_at": _now()})
    return out


def fetch_all(query, country="Malaysia", fetch=None, timeout=12, workers=4):
    """Run every source in parallel. Returns (records, source_errors)."""
    jobs = (
        ("world_bank", lambda: world_bank(country, fetch=fetch, timeout=timeout)),
        ("fx", lambda: exchange_rates("MYR", fetch=fetch, timeout=timeout)),
        ("crossref", lambda: research_literature(query, fetch=fetch, timeout=timeout)),
        ("open_sanctions", lambda: open_sanctions(query, fetch=fetch, timeout=timeout + 3)),
        ("open_corporates", lambda: open_corporates(query, country, fetch=fetch, timeout=timeout + 3)),
    )
    records, errors = [], []
    if len(jobs) == 1:
        results = [jobs[0][1]()]
    else:
        def run(_name, fn):
            try:
                return fn()
            except Exception as exc:  # a source must never kill research
                return [{"source": _name, "basis": "unavailable",
                         "label": _name, "detail": type(exc).__name__}]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda j: run(j[0], j[1]), jobs))
    for (name, _), rows in zip(jobs, results):
        for row in rows:
            if row.get("basis") == "unavailable" and row.get("detail") not in (
                    "OPEN_SANCTIONS_API_KEY not set", "OPEN_CORPORATES_API_KEY not set",
                    "country code not known to the indicator map"):
                errors.append({"source": name, "error": str(row.get("detail"))[:40]})
            records.append(row)
    return records, errors
