"""
Default settings for the literature search app.

You can change everything here, BUT you don't have to:
the web form (the page that opens in your browser) lets you
override all of these each time you run a search.

Keep this file private -- it can contain your API keys.
"""

# ---------------------------------------------------------------------------
# 1. Which databases are ticked ON by default in the web form.
#    True  = ticked on   |   False = ticked off
# ---------------------------------------------------------------------------
ENABLE_PUBMED = True
ENABLE_EMBASE = False
ENABLE_SCOPUS = False
ENABLE_SERPAPI = True   # Google Scholar via SerpAPI

# ---------------------------------------------------------------------------
# 2. API keys / logins.
#    Fill in the ones you have. Leave the others as "".
#    (You can also paste them into the web form instead.)
# ---------------------------------------------------------------------------

# PubMed: no key needed, but NCBI asks for your email. A free API key
# (from https://www.ncbi.nlm.nih.gov/account/) makes it faster.
PUBMED_EMAIL = ""
PUBMED_API_KEY = ""

# Google Scholar via SerpAPI (https://serpapi.com/manage-api-key)
SERPAPI_API_KEY = ""

# Scopus (Elsevier). Free key from https://dev.elsevier.com/ .
# IMPORTANT: Scopus only returns results when you are on your
# university/institution network, OR you have an institutional token.
SCOPUS_API_KEY = ""
SCOPUS_INST_TOKEN = ""   # optional

# Embase (Elsevier). Requires a PAID institutional Embase API entitlement.
EMBASE_API_KEY = ""
EMBASE_INST_TOKEN = ""   # optional

# ---------------------------------------------------------------------------
# 3. Default search settings (also editable in the web form).
# ---------------------------------------------------------------------------
MAX_RESULTS_PER_QUERY = 50   # per database, per search string
YEAR_LOW = None              # e.g. 2010  (None = no lower limit)
YEAR_HIGH = None             # e.g. 2025  (None = no upper limit)

# Exclusion criteria ticked ON by default (keys from search_core.EXCLUSION_CRITERIA).
# Example: ["review", "editorial", "abstract_poster"]
DEFAULT_EXCLUSIONS = []
EXCLUDE_NO_ABSTRACT = False
