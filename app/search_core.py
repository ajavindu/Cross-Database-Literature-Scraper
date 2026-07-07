"""
Database connectors + exclusion filters for the literature search app.

Every connector takes a query string and returns a list of records in ONE
shared shape (UNIFIED_FIELDS), so the rest of the app doesn't care which
database the data came from.

A connector returns: (records, message)
  records  -> list of dicts using UNIFIED_FIELDS
  message  -> short human-readable status string ("" if all good)
"""

import re
import time
from collections import Counter
from difflib import SequenceMatcher

import requests

# The columns every record has, no matter the source.
UNIFIED_FIELDS = [
    "Source", "Title", "Authors", "Year", "Venue", "PubTypes",
    "DOI", "Abstract", "URL", "Citations", "RecordID",
]

# Nice display names for each database key.
DATABASES = {
    "pubmed": "PubMed",
    "openalex": "OpenAlex",
    "crossref": "Crossref",
    "embase": "Embase",
    "scopus": "Scopus",
    "serpapi": "Google Scholar (SerpAPI)",
}

# ---------------------------------------------------------------------------
# Exclusion criteria.
# Each entry: (key, human label, [substrings to look for in a record's PubTypes]).
# Matching is case-insensitive substring matching, which works across the
# different vocabularies PubMed / Scopus / Embase use.
# ---------------------------------------------------------------------------
EXCLUSION_CRITERIA = [
    ("review",          "Reviews",                      ["review"]),
    ("meta_analysis",   "Meta-analyses",                ["meta-analysis", "meta analysis"]),
    ("editorial",       "Editorials",                   ["editorial"]),
    ("letter",          "Letters",                      ["letter"]),
    ("comment",         "Comments / notes",             ["comment", "note"]),
    ("conference",      "Conference papers / proceedings", ["conference", "congress", "proceeding", "meeting"]),
    ("abstract_poster", "Conference abstracts / posters", ["abstract", "poster"]),
    ("case_report",     "Case reports",                 ["case report"]),
    ("erratum",         "Errata / retractions",         ["erratum", "corrigendum", "correction", "retraction", "retracted"]),
    ("news",            "News items",                   ["news"]),
    ("book",            "Books / book chapters",        ["book", "chapter"]),
]

_EXCL_MAP = {key: terms for key, _label, terms in EXCLUSION_CRITERIA}
_EXCL_LABEL = {key: label for key, label, _terms in EXCLUSION_CRITERIA}
_EXCL_LABEL["_no_abstract"] = "No abstract"


def exclusion_options():
    """(key, label) pairs for building the web form."""
    return [(key, label) for key, label, _terms in EXCLUSION_CRITERIA]


def exclusion_label(key):
    return _EXCL_LABEL.get(key, key)


def apply_exclusions(records, selected_keys, exclude_no_abstract=False):
    """
    Return (kept, excluded_counter).
    A record is excluded if its PubTypes contain any term for a selected
    criterion. Records with an UNKNOWN/empty PubTypes are kept (we can't
    judge them) unless they are removed by the 'no abstract' rule.
    """
    active = [(k, _EXCL_MAP[k]) for k in selected_keys if k in _EXCL_MAP]
    kept, counts = [], Counter()
    for r in records:
        joined = (r.get("PubTypes") or "").lower()
        excluded = False
        for key, terms in active:
            if joined and any(t in joined for t in terms):
                counts[key] += 1
                excluded = True
                break
        if not excluded and exclude_no_abstract and not (r.get("Abstract") or "").strip():
            counts["_no_abstract"] += 1
            excluded = True
        if not excluded:
            kept.append(r)
    return kept, counts


def _blank_record(source):
    r = {k: "" for k in UNIFIED_FIELDS}
    r["Source"] = source
    return r


# ===========================================================================
# PubMed  (NCBI E-utilities -- free)
# ===========================================================================
def search_pubmed(query, max_results, year_low, year_high, creds):
    from Bio import Entrez

    email = creds.get("pubmed_email") or ""
    api_key = creds.get("pubmed_api_key") or ""
    if not email:
        return [], "PubMed needs an email address (set it in config or the form)."

    Entrez.email = email
    if api_key:
        Entrez.api_key = api_key

    term = query
    if year_low or year_high:
        lo = year_low or 1800
        hi = year_high or 3000
        term = f"({query}) AND ({lo}:{hi}[dp])"

    try:
        with Entrez.esearch(db="pubmed", term=term, retmax=max_results,
                            usehistory="y") as h:
            res = Entrez.read(h)
    except Exception as e:
        return [], f"PubMed search error: {e}"

    total = min(int(res["Count"]), max_results)
    if total == 0:
        return [], "PubMed: 0 results."

    webenv, qk = res["WebEnv"], res["QueryKey"]
    records = []
    for start in range(0, total, 100):
        try:
            with Entrez.efetch(db="pubmed", retstart=start, retmax=100,
                               webenv=webenv, query_key=qk, retmode="xml") as h:
                parsed = Entrez.read(h)
        except Exception as e:
            return records, f"PubMed fetch error after {len(records)}: {e}"

        for art in parsed.get("PubmedArticle", []):
            citation = art["MedlineCitation"]
            article = citation["Article"]
            rec = _blank_record("PubMed")

            pmid = str(citation["PMID"])
            rec["RecordID"] = pmid
            rec["Title"] = str(article.get("ArticleTitle", ""))
            rec["Venue"] = str(article.get("Journal", {}).get("Title", ""))
            rec["URL"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            rec["PubTypes"] = "; ".join(str(pt) for pt in
                                        article.get("PublicationTypeList", []))

            pub_date = (article.get("Journal", {})
                        .get("JournalIssue", {}).get("PubDate", {}))
            rec["Year"] = pub_date.get("Year", "") or pub_date.get("MedlineDate", "")[:4]

            for eid in article.get("ELocationID", []):
                if eid.attributes.get("EIdType") == "doi":
                    rec["DOI"] = str(eid)
                    break

            abs_block = article.get("Abstract", {}).get("AbstractText", [])
            if abs_block:
                rec["Abstract"] = " ".join(str(seg) for seg in abs_block)

            authors = []
            for a in article.get("AuthorList", []):
                name = (f"{a.get('ForeName', '') or a.get('Initials', '')} "
                        f"{a.get('LastName', '')}").strip()
                name = name or str(a.get("CollectiveName", ""))
                if name:
                    authors.append(name)
            rec["Authors"] = "; ".join(authors)

            records.append(rec)

        time.sleep(0.34 if not api_key else 0.11)

    return records, f"PubMed: {len(records)} results."


# ===========================================================================
# Scopus  (Elsevier Search API)
# ===========================================================================
def search_scopus(query, max_results, year_low, year_high, creds):
    api_key = creds.get("scopus_api_key") or ""
    inst_token = creds.get("scopus_inst_token") or ""
    if not api_key:
        return [], "Scopus skipped: no Scopus API key set."

    q = query
    if year_low:
        q += f" AND PUBYEAR AFT {int(year_low) - 1}"
    if year_high:
        q += f" AND PUBYEAR BEF {int(year_high) + 1}"

    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    if inst_token:
        headers["X-ELS-Insttoken"] = inst_token

    records, start, count = [], 0, 25
    while len(records) < max_results:
        params = {"query": q, "count": count, "start": start}
        try:
            resp = requests.get("https://api.elsevier.com/content/search/scopus",
                                headers=headers, params=params, timeout=60)
            data = resp.json()
        except Exception as e:
            return records, f"Scopus error: {e}"

        sr = data.get("search-results")
        if not sr:
            svc = data.get("service-error") or data.get("error-response") or data
            return records, f"Scopus error: {str(svc)[:200]}"

        entries = sr.get("entry", [])
        if entries and "error" in entries[0]:
            return records, "Scopus: 0 results (or access denied on this network)."

        for e in entries:
            rec = _blank_record("Scopus")
            rec["Title"] = e.get("dc:title", "")
            rec["Authors"] = e.get("dc:creator", "")   # first author (standard view)
            rec["Venue"] = e.get("prism:publicationName", "")
            rec["Year"] = (e.get("prism:coverDate", "") or "")[:4]
            rec["DOI"] = e.get("prism:doi", "")
            rec["Abstract"] = e.get("dc:description", "")
            rec["Citations"] = e.get("citedby-count", "")
            rec["RecordID"] = e.get("dc:identifier", "")
            rec["PubTypes"] = (e.get("subtypeDescription", "") or
                               e.get("prism:aggregationType", "") or "")
            for link in e.get("link", []):
                if link.get("@ref") == "scopus":
                    rec["URL"] = link.get("@href", "")
                    break
            records.append(rec)

        try:
            total = int(sr.get("opensearch:totalResults", 0))
        except (TypeError, ValueError):
            total = len(records)

        start += count
        if not entries or start >= total:
            break
        time.sleep(0.3)

    return records[:max_results], f"Scopus: {len(records[:max_results])} results."


# ===========================================================================
# Embase  (Elsevier -- requires paid institutional entitlement)
# ===========================================================================
def search_embase(query, max_results, year_low, year_high, creds):
    api_key = creds.get("embase_api_key") or ""
    inst_token = creds.get("embase_inst_token") or ""
    if not api_key:
        return [], ("Embase skipped: no Embase API key set. Embase has no "
                    "free/self-serve API -- it needs a paid institutional "
                    "Embase API entitlement from Elsevier.")

    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    if inst_token:
        headers["X-ELS-Insttoken"] = inst_token

    q = query
    if year_low:
        q += f" AND [{int(year_low)}-{int(year_high) if year_high else 3000}]/py"

    records, start, count = [], 0, 25
    while len(records) < max_results:
        params = {"query": q, "count": count, "start": start}
        try:
            resp = requests.get("https://api.elsevier.com/content/search/embase",
                                headers=headers, params=params, timeout=60)
            if resp.status_code != 200:
                return records, (f"Embase error {resp.status_code}: "
                                 f"{resp.text[:200]} (endpoint/entitlement may "
                                 f"need adjusting for your institution).")
            data = resp.json()
        except Exception as e:
            return records, f"Embase error: {e} (endpoint may need customising)."

        sr = data.get("results") or data.get("search-results") or {}
        entries = sr.get("entry", []) if isinstance(sr, dict) else []
        if not entries:
            break

        for e in entries:
            rec = _blank_record("Embase")
            rec["Title"] = e.get("dc:title", "") or e.get("title", "")
            rec["Authors"] = e.get("dc:creator", "") or e.get("authors", "")
            rec["Venue"] = e.get("prism:publicationName", "")
            rec["Year"] = (e.get("prism:coverDate", "") or "")[:4]
            rec["DOI"] = e.get("prism:doi", "")
            rec["Abstract"] = e.get("dc:description", "")
            rec["RecordID"] = e.get("dc:identifier", "")
            rec["PubTypes"] = (e.get("subtypeDescription", "") or
                               e.get("itemtype", "") or "")
            records.append(rec)

        start += count
        time.sleep(0.3)

    return records[:max_results], f"Embase: {len(records[:max_results])} results."


# ===========================================================================
# Google Scholar via SerpAPI
# ===========================================================================
def search_serpapi(query, max_results, year_low, year_high, creds):
    api_key = creds.get("serpapi_api_key") or ""
    if not api_key:
        return [], "Google Scholar skipped: no SerpAPI key set."

    records, start, per_page = [], 0, 20
    while len(records) < max_results:
        params = {
            "engine": "google_scholar", "q": query, "api_key": api_key,
            "start": start, "num": per_page, "hl": "en",
        }
        if year_low:
            params["as_ylo"] = year_low
        if year_high:
            params["as_yhi"] = year_high

        try:
            resp = requests.get("https://serpapi.com/search", params=params, timeout=60)
            data = resp.json()
        except Exception as e:
            return records, f"Google Scholar error: {e}"

        if "error" in data:
            return records, f"Google Scholar: {data['error']}"

        organic = data.get("organic_results", [])
        if not organic:
            break

        for r in organic:
            pub_info = r.get("publication_info", {})
            summary = pub_info.get("summary", "")
            authors_list = pub_info.get("authors", [])
            authors = ("; ".join(a.get("name", "") for a in authors_list)
                       if authors_list else (summary.split(" - ")[0] if summary else ""))
            parts = summary.split(" - ")
            venue = parts[1] if len(parts) >= 2 else ""
            ym = re.search(r"\b(19|20)\d{2}\b", summary)

            rec = _blank_record("Google Scholar")
            rec["Title"] = r.get("title", "")
            rec["Authors"] = authors
            rec["Venue"] = venue
            rec["Year"] = ym.group(0) if ym else ""
            rec["Abstract"] = r.get("snippet", "")
            rec["Citations"] = (r.get("inline_links", {})
                                .get("cited_by", {}).get("total", ""))
            rec["URL"] = r.get("link", "")
            rec["RecordID"] = r.get("result_id", "")
            # Google Scholar has no publication-type metadata, so PubTypes stays "".
            records.append(rec)

        if "next" not in data.get("serpapi_pagination", {}):
            break
        start += per_page
        time.sleep(1)

    return records[:max_results], f"Google Scholar: {len(records[:max_results])} results."


# ===========================================================================
# OpenAlex  (free, no key -- ~250M works)
# ===========================================================================
def _openalex_abstract(inverted_index):
    """OpenAlex stores abstracts as an inverted index; rebuild the text."""
    if not inverted_index:
        return ""
    positions = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def search_openalex(query, max_results, year_low, year_high, creds):
    email = creds.get("pubmed_email") or ""   # used only for the "polite pool"
    per_page = max(1, min(200, max_results))

    filters = []
    if year_low:
        filters.append(f"from_publication_date:{int(year_low)}-01-01")
    if year_high:
        filters.append(f"to_publication_date:{int(year_high)}-12-31")

    records, cursor = [], "*"
    while len(records) < max_results and cursor:
        params = {"search": query, "per-page": per_page, "cursor": cursor}
        if filters:
            params["filter"] = ",".join(filters)
        if email:
            params["mailto"] = email
        try:
            resp = requests.get("https://api.openalex.org/works",
                                params=params, timeout=60)
            data = resp.json()
        except Exception as e:
            return records, f"OpenAlex error: {e}"

        if "results" not in data:
            return records, f"OpenAlex error: {str(data)[:200]}"

        for w in data["results"]:
            rec = _blank_record("OpenAlex")
            rec["Title"] = w.get("display_name") or ""
            rec["Authors"] = "; ".join(
                a.get("author", {}).get("display_name", "")
                for a in w.get("authorships", []) if a.get("author"))
            rec["Year"] = str(w.get("publication_year") or "")
            src = (w.get("primary_location") or {}).get("source") or {}
            rec["Venue"] = src.get("display_name", "") or ""
            doi = w.get("doi") or ""
            rec["DOI"] = doi.replace("https://doi.org/", "") if doi else ""
            rec["Abstract"] = _openalex_abstract(w.get("abstract_inverted_index"))
            rec["URL"] = w.get("id", "") or doi
            rec["Citations"] = w.get("cited_by_count", "")
            rec["RecordID"] = w.get("id", "")
            rec["PubTypes"] = w.get("type", "") or ""   # article, review, editorial...
            records.append(rec)

        if not data["results"]:
            break
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)

    return records[:max_results], f"OpenAlex: {len(records[:max_results])} results."


# ===========================================================================
# Crossref  (free, no key -- scholarly metadata registry)
# ===========================================================================
def search_crossref(query, max_results, year_low, year_high, creds):
    email = creds.get("pubmed_email") or ""
    rows = max(1, min(100, max_results))

    filters = []
    if year_low:
        filters.append(f"from-pub-date:{int(year_low)}-01-01")
    if year_high:
        filters.append(f"until-pub-date:{int(year_high)}-12-31")

    headers = {"User-Agent": f"CrossDatabaseApp/1.0 (mailto:{email})"} if email else {}
    records, cursor = [], "*"
    while len(records) < max_results and cursor:
        params = {"query": query, "rows": rows, "cursor": cursor}
        if filters:
            params["filter"] = ",".join(filters)
        if email:
            params["mailto"] = email
        try:
            resp = requests.get("https://api.crossref.org/works",
                                params=params, headers=headers, timeout=60)
            data = resp.json()
        except Exception as e:
            return records, f"Crossref error: {e}"

        message = data.get("message", {})
        items = message.get("items", [])
        if not items:
            break

        for it in items:
            rec = _blank_record("Crossref")
            title = it.get("title") or []
            rec["Title"] = title[0] if title else ""
            authors = []
            for a in it.get("author", []):
                nm = (f"{a.get('given', '')} {a.get('family', '')}").strip() or a.get("name", "")
                if nm:
                    authors.append(nm)
            rec["Authors"] = "; ".join(authors)
            dp = (it.get("issued", {}) or {}).get("date-parts", [[None]])
            rec["Year"] = str(dp[0][0]) if dp and dp[0] and dp[0][0] else ""
            ct = it.get("container-title") or []
            rec["Venue"] = ct[0] if ct else ""
            rec["DOI"] = it.get("DOI", "") or ""
            abstract = it.get("abstract", "") or ""
            rec["Abstract"] = re.sub(r"<[^>]+>", "", abstract).strip()  # strip JATS tags
            rec["URL"] = it.get("URL", "") or ""
            rec["Citations"] = it.get("is-referenced-by-count", "")
            rec["RecordID"] = it.get("DOI", "")
            rec["PubTypes"] = it.get("type", "") or ""   # journal-article, proceedings-article...
            records.append(rec)

        cursor = message.get("next-cursor")
        time.sleep(0.2)

    return records[:max_results], f"Crossref: {len(records[:max_results])} results."


# ===========================================================================
# Dispatcher
# ===========================================================================
_CONNECTORS = {
    "pubmed": search_pubmed,
    "openalex": search_openalex,
    "crossref": search_crossref,
    "scopus": search_scopus,
    "embase": search_embase,
    "serpapi": search_serpapi,
}


def search_one(db_key, query, max_results, year_low, year_high, creds):
    """Run a single database. Never raises -- returns (records, message)."""
    fn = _CONNECTORS.get(db_key)
    if not fn:
        return [], f"Unknown database '{db_key}'."
    try:
        return fn(query, max_results, year_low, year_high, creds)
    except Exception as e:  # last-resort safety net
        return [], f"{DATABASES.get(db_key, db_key)} crashed: {e}"


def _norm_title(title):
    """Normalise a title for matching: lowercase, strip punctuation/extra spaces."""
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _surnames(authors):
    """
    Pull comparable surname tokens out of an author string, regardless of how
    a database formats it ("John Smith", "Smith J.", "J Smith, A Roy" all give
    {'smith', ...}). Single letters/initials and digits are ignored.
    """
    return {w.lower() for w in re.findall(r"[^\W\d_]{2,}", authors or "", re.UNICODE)}


def _authors_conflict(a, b):
    """True only when BOTH records list authors AND they share no surname."""
    return bool(a) and bool(b) and a.isdisjoint(b)


# How strictly two records count as the same paper:
DEDUPE_MODES = {
    "fuzzy": "Fuzzy — title similarity + year/author (recommended, ASySD-style)",
    "doi_title_author": "Exact: DOI + title + author",
    "doi_title": "Exact: DOI + title (aggressive)",
    "doi_only": "DOI only (safest — keeps near-duplicates)",
}

# Fuzzy matching thresholds (0–1 title similarity).
_FUZZY_AUTO = 0.97    # this similar -> duplicate outright
_FUZZY_MIN = 0.90     # this similar -> duplicate only if year/author agree


def _year_int(value):
    m = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(m.group(0)) if m else None


def _title_sim(a, b):
    """Order-independent title similarity in [0, 1] (token-sorted ratio)."""
    a2 = " ".join(sorted(a.split()))
    b2 = " ".join(sorted(b.split()))
    return SequenceMatcher(None, a2, b2).ratio()


def _dedupe_fuzzy(records):
    """
    ASySD-style fuzzy dedup with no external dependencies:
      * exact DOI match  -> duplicate
      * near-identical title (>= _FUZZY_AUTO) -> duplicate
      * similar title (>= _FUZZY_MIN) AND publication years within 1 year AND
        (authors overlap or one side has no authors) -> duplicate
    Years are compared as a cheap gate before the expensive string compare.
    """
    seen_doi = set()
    kept_meta = []   # dicts: {title, year, auth}
    out = []
    for r in records:
        doi = (r.get("DOI") or "").strip().lower()
        title = _norm_title(r.get("Title"))
        year = _year_int(r.get("Year"))
        auth = _surnames(r.get("Authors"))

        if doi and doi in seen_doi:
            continue

        is_dup = False
        if title:
            for m in kept_meta:
                if not m["title"]:
                    continue
                if year and m["year"] and abs(year - m["year"]) > 1:
                    continue  # different year -> skip pricey compare
                sim = _title_sim(title, m["title"])
                if sim >= _FUZZY_AUTO:
                    is_dup = True
                    break
                if sim >= _FUZZY_MIN and not _authors_conflict(auth, m["auth"]):
                    is_dup = True
                    break
        if is_dup:
            continue

        if doi:
            seen_doi.add(doi)
        kept_meta.append({"title": title, "year": year, "auth": auth})
        out.append(r)
    return out, len(records) - len(out)


def dedupe(records, mode="fuzzy"):
    """
    Remove duplicates across databases. Returns (unique_records, num_removed).

    Modes:
      - fuzzy            : title-similarity matching (ASySD-style, default).
      - doi_only         : never merge on title alone (only DOI).
      - doi_title        : merge whenever normalised titles match.
      - doi_title_author : merge on exact title UNLESS both records list authors
                           and those authors don't overlap at all.
    The first occurrence is kept; later duplicates are dropped.
    """
    if mode not in DEDUPE_MODES:
        mode = "fuzzy"
    if mode == "fuzzy":
        return _dedupe_fuzzy(records)

    seen_doi = set()
    title_map = {}   # normalised title -> list of surname-sets of kept records
    out = []
    for r in records:
        doi = (r.get("DOI") or "").strip().lower()
        title = _norm_title(r.get("Title"))
        auth = _surnames(r.get("Authors"))

        if doi and doi in seen_doi:
            continue

        is_dup = False
        if mode != "doi_only" and title and title in title_map:
            for kept_auth in title_map[title]:
                if mode == "doi_title" or not _authors_conflict(auth, kept_auth):
                    is_dup = True
                    break
        if is_dup:
            continue

        if doi:
            seen_doi.add(doi)
        if title:
            title_map.setdefault(title, []).append(auth)
        out.append(r)
    return out, len(records) - len(out)
