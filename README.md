# Cross-Database Literature Search

A simple tool to search **PubMed, OpenAlex, Crossref, Embase, Scopus, and
Google Scholar** at once. You type your search string(s) into a web page, tick
the databases and any exclusion criteria you want, click **Search**, and it
saves the results as **CSV spreadsheet files** you can open in Excel. It can
also **merge and de-duplicate** results across databases.

**PubMed, OpenAlex and Crossref are free and need no API key** (just an email),
so the tool is useful straight away without any institutional access.

You do **not** need to know any programming to use it.

---

## 1. What you need

- A computer running **Windows, macOS, or Linux**.
- An internet connection.
- Nothing else. The first time you run it, it checks whether you have a
  compatible **Python (3.9 or newer)**; if not, it tries to install one. Then it
  builds its own private, self-contained environment (a "venv") inside the `app`
  folder and installs the few packages it needs there. It does **not** change
  anything else on your computer.

---

## 2. What's in this folder

You only ever need the **launcher** for your computer. Everything else lives
inside the `app` folder, which you can ignore.

```
Cross_database_Api/
├── run_windows.bat        ← double-click on Windows
├── run_macos.command      ← double-click on macOS
├── run_linux.sh           ← double-click on Linux
├── README.md              ← this file
├── app/                   ← the program (you don't need to open this)
└── results/               ← your CSV files appear here after a search
```

---

## 3. How to start it

Open the `Cross_database_Api` folder and **double-click the launcher for your system**:

| Your computer | Double-click this file |
|---------------|------------------------|
| Windows       | `run_windows.bat`      |
| macOS (Apple) | `run_macos.command`    |
| Linux         | `run_linux.sh`         |

A black text window appears and sets things up (about a minute the **first**
time only). Then your web browser opens at `http://127.0.0.1:5000`.

> **Leave the black window open** while you use the tool. Closing it stops the app.

### First-time pop-ups you might see

- **Windows:** If you see *"Windows protected your PC"*, click **More info → Run anyway**.
  If it says Python was just installed and to re-run, close the window and
  double-click `run_windows.bat` again.
- **macOS:** If macOS says the file is *"from an unidentified developer"*, do this
  once: **right-click** `run_macos.command` → **Open** → **Open**. After that,
  double-clicking works.
- **Linux:** Right-click `run_linux.sh` → *Properties* → *Permissions* → tick
  *Allow executing file as program*. Or run `bash run_linux.sh` in a terminal.

---

## 4. How to use the search page

1. **Type a search string** in the big box, e.g.
   `(couple* OR spouse*) AND counselling AND India*`
2. Need several searches? Click **“+ Add another search string.”**
   **Each search string is saved as its own separate CSV file(s).**
3. **Tick the databases** you want. (Simple on/off switches.)
4. Set a **Year range** (from / to) and **max results** if you like.
5. Tick any **exclusion criteria** — publication types to remove, such as
   Reviews, Editorials, Letters, **Conference abstracts / posters**, Case
   reports, Errata, News, Books, etc. You can also tick *“remove records with no
   abstract.”*
6. Click **“Search & save CSVs.”**
7. When it finishes, the page shows a table with **Found / Kept / Excluded**
   counts and **download links**. The same files are in the `results` folder.

### What files you get, per search string

- one CSV **per database** (e.g. `..._q1_mysearch_pubmed.csv`),
- one **MERGED** CSV combining all ticked databases with duplicates removed
  (e.g. `..._q1_mysearch_MERGED.csv`), and
- if you run several search strings, one **ALL_MERGED** CSV that is unique
  across every string and database.

Columns: Source, Title, Authors, Year, Venue, PubTypes, DOI, Abstract, URL,
Citations, RecordID.

### Removing duplicates

Merging always removes duplicates. You choose how strict via **Duplicate
matching**:

- **Fuzzy** *(default, ASySD-style)* — matches on DOI, or on very similar
  titles backed up by matching year and overlapping authors. Best for combining
  different databases, where titles vary slightly.
- **DOI + title + author**, **DOI + title**, or **DOI only** — exact-match
  options if you want tighter or looser control.

There's also a standalone **“Remove duplicates across saved CSVs”** tool on the
page: tick any result files (from any run/database) and merge them into one
de-duplicated CSV.

### A note on exclusions

Exclusions work by **publication type**, which **PubMed, OpenAlex, Crossref,
Scopus and Embase** provide. **Google Scholar does not** report publication
types, so exclusions can't filter Scholar results — those come through
unfiltered by design.

---

## 5. API keys (which databases work out of the box)

Paste keys into the **“API keys”** section on the page, or set them once in
`app/config.py`.

| Database | Key needed? | How to get it / notes |
|----------|-------------|-----------------------|
| **PubMed** | No key — just your **email**. Optional free API key = faster. | https://www.ncbi.nlm.nih.gov/account/ |
| **OpenAlex** | **No key.** Uses your email for a faster "polite pool." | https://openalex.org |
| **Crossref** | **No key.** Uses your email for a faster "polite pool." | https://www.crossref.org |
| **Google Scholar** | Yes — a **SerpAPI key**. | https://serpapi.com/manage-api-key (free tier has a monthly limit) |
| **Scopus** | Free **Elsevier key**, but **only returns results on your university network** (or with an institutional token). | https://dev.elsevier.com/ |
| **Embase** | **Paid institutional** Elsevier Embase entitlement. Most individuals don't have this. | Ask your university library |

> **Note on search syntax:** PubMed, Scopus and Embase support precise boolean
> queries (`AND`/`OR`/parentheses/field tags). **OpenAlex, Crossref and Google
> Scholar treat your query as keywords** (relevance search), so complex boolean
> logic isn't applied exactly — great for free, broad coverage, less so for a
> tightly controlled search.

If a database is ticked but has no key/access, it's **skipped with a message** —
the app never crashes.

> **Keep your keys private.** Don't share `app/config.py` publicly. The included
> `.gitignore` already excludes `results/` and the environment.

---

## 6. Troubleshooting

- **Browser didn't open.** Go to `http://127.0.0.1:5000` yourself.
- **“Port already in use.”** It's probably already running in another window.
- **macOS double-click does nothing.** Open **Terminal**, type `bash ` (with a
  space), drag `run_macos.command` into the window, press Enter.
- **“No compatible Python.”** Install Python 3.9+ from python.org and re-run.
- **Scopus returns 0 / access denied.** You're not on your institution's network
  — connect via VPN or add an institutional token.
- **Embase needs entitlement.** Expected unless your institution bought API access.
- **It's slow.** Lower “max results.” Google Scholar is paced to avoid limits.
- **Start fresh.** Delete the `app/.venv` folder and run the launcher again.
