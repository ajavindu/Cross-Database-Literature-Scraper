"""
Literature Search -- local web app.

Start it by double-clicking the launcher for your system (one folder up):
    Windows : run_windows.bat
    macOS   : run_macos.command
    Linux   : run_linux.sh

That opens a page in your browser where you type your search string(s),
tick which databases to use, choose exclusion criteria, and click Search.
CSV files are written into a 'results' folder next to the launcher -- one CSV
per search string per database, plus a merged (de-duplicated) CSV per string.
"""

import csv
import datetime
import os
import re
import threading
import webbrowser

from flask import Flask, request, send_from_directory, render_template_string

import config
from search_core import (
    UNIFIED_FIELDS, DATABASES, search_one, dedupe, DEDUPE_MODES,
    apply_exclusions, exclusion_options, exclusion_label,
)

DEFAULT_DEDUPE_MODE = getattr(config, "DEDUPE_MODE", "fuzzy")

APP_DIR = os.path.dirname(os.path.abspath(__file__))   # .../literature_search/app
ROOT_DIR = os.path.dirname(APP_DIR)                     # .../literature_search
RESULTS_DIR = os.path.join(ROOT_DIR, "results")        # where CSVs are saved
os.makedirs(RESULTS_DIR, exist_ok=True)

app = Flask(__name__)

DB_ORDER = ["pubmed", "openalex", "crossref", "embase", "scopus", "serpapi"]


def slug(text, n=30):
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return (s[:n] or "query")


def write_csv(path, records):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=UNIFIED_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def read_csv(path):
    """Read a saved results CSV back into a list of record dicts."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def list_result_csvs():
    """Names of CSV files currently in the results folder (newest first)."""
    if not os.path.isdir(RESULTS_DIR):
        return []
    files = [f for f in os.listdir(RESULTS_DIR) if f.lower().endswith(".csv")]
    return sorted(files, reverse=True)


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Literature Search</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         max-width: 880px; margin: 0 auto; padding: 24px; color: #1a1a1a; background: #f6f7f9; }
  h1 { margin-bottom: 4px; } .sub { color: #666; margin-top: 0; }
  .card { background: #fff; border: 1px solid #e2e5ea; border-radius: 10px; padding: 18px; margin: 16px 0; }
  label { font-weight: 600; display: block; margin-bottom: 6px; }
  textarea { width: 100%; min-height: 90px; font-family: ui-monospace, Menlo, Consolas, monospace;
             font-size: 13px; padding: 10px; border: 1px solid #ccd; border-radius: 8px; }
  .qname { width: 100%; padding: 8px; margin-bottom: 6px; border: 1px solid #ccd; border-radius: 8px; }
  .row { display: flex; gap: 14px; flex-wrap: wrap; }
  .row > div { flex: 1; min-width: 150px; }
  input[type=number], input[type=text], input[type=password] {
     width: 100%; padding: 8px; border: 1px solid #ccd; border-radius: 8px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 18px; }
  .grid label, .dbs label { font-weight: 500; display: flex; align-items: center; gap: 8px; margin: 5px 0; cursor: pointer; }
  .queryblock { border: 1px dashed #cfd4dc; border-radius: 10px; padding: 12px; margin-bottom: 12px; }
  button { background: #2563eb; color: #fff; border: 0; padding: 11px 18px; font-size: 15px; border-radius: 8px; cursor: pointer; }
  button.secondary { background: #e5e7eb; color: #111; padding: 7px 12px; font-size: 13px; }
  .remove { background: #fde2e2; color: #b42318; }
  details summary { cursor: pointer; font-weight: 600; }
  .hint { color: #777; font-size: 13px; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #eee; font-size: 14px; }
  a.dl { color: #2563eb; } .msg { color: #555; font-size: 13px; }
  .dash { color: #999; }
</style>
</head>
<body>
  <h1>Literature Search</h1>
  <p class="sub">Search PubMed, Embase, Scopus and Google Scholar. CSVs are saved to the <code>results</code> folder.</p>

  <form method="post" action="/search">
    <div class="card">
      <label>Search string(s)</label>
      <p class="hint">Each search string is saved as its own set of CSV files. Add as many as you like.</p>
      <div id="queries">
        <div class="queryblock">
          <input class="qname" name="qname" placeholder="Optional short name (e.g. couples_help_seeking)">
          <textarea name="queries" placeholder="Type your search string here..."></textarea>
        </div>
      </div>
      <button type="button" class="secondary" onclick="addQuery()">+ Add another search string</button>
    </div>

    <div class="card dbs">
      <label>Databases to search</label>
      <p class="hint">PubMed, OpenAlex and Crossref are free and need no key (just an email). Scopus/Embase need
         institutional access; Google Scholar needs a SerpAPI key.</p>
      {% for key, name in dbs %}
        <label><input type="checkbox" name="db" value="{{key}}" {{ 'checked' if defaults[key] else '' }}> {{name}}</label>
      {% endfor %}
    </div>

    <div class="card">
      <label>Year range</label>
      <div class="row">
        <div><span class="hint">From (optional)</span>
          <input type="number" name="year_low" value="{{year_low or ''}}" placeholder="e.g. 2010"></div>
        <div style="flex:0 0 auto; align-self:end; padding-bottom:8px" class="dash">—</div>
        <div><span class="hint">To (optional)</span>
          <input type="number" name="year_high" value="{{year_high or ''}}" placeholder="e.g. 2025"></div>
        <div><span class="hint">Max results / database / string</span>
          <input type="number" name="max_results" value="{{max_results}}" min="1" max="2000"></div>
      </div>
    </div>

    <div class="card">
      <label>Exclusion criteria</label>
      <p class="hint">Tick things to REMOVE from the results (by publication type). Applied to databases that
         report a type (PubMed, OpenAlex, Crossref, Scopus, Embase). Google Scholar carries no type
         information, so these can't filter it.</p>
      <div class="grid">
        {% for key, label in exclusions %}
          <label><input type="checkbox" name="exclude" value="{{key}}" {{ 'checked' if key in default_exclusions else '' }}> {{label}}</label>
        {% endfor %}
      </div>
      <label style="margin-top:10px; font-weight:500;">
        <input type="checkbox" name="exclude_no_abstract" value="1" {{ 'checked' if exclude_no_abstract else '' }}>
        Also remove records that have no abstract
      </label>
    </div>

    <div class="card">
      <label>Duplicate matching</label>
      <p class="hint">How strictly to treat two records as the same paper when merging.
         "DOI + title + author" avoids removing different papers that happen to share a title.</p>
      <select name="dedupe_mode" style="width:100%; padding:8px; border:1px solid #ccd; border-radius:8px;">
        {% for value, label in dedupe_modes.items() %}
          <option value="{{value}}" {{ 'selected' if value == dedupe_mode else '' }}>{{label}}</option>
        {% endfor %}
      </select>
    </div>

    <div class="card">
      <details>
        <summary>API keys (optional — pre-filled from config.py)</summary>
        <div style="margin-top:12px">
          <div class="row">
            <div><span class="hint">PubMed email</span><input type="text" name="pubmed_email" value="{{creds.pubmed_email}}"></div>
            <div><span class="hint">PubMed API key</span><input type="password" name="pubmed_api_key" value="{{creds.pubmed_api_key}}"></div>
          </div>
          <div class="row" style="margin-top:10px">
            <div><span class="hint">SerpAPI key (Google Scholar)</span><input type="password" name="serpapi_api_key" value="{{creds.serpapi_api_key}}"></div>
          </div>
          <div class="row" style="margin-top:10px">
            <div><span class="hint">Scopus key</span><input type="password" name="scopus_api_key" value="{{creds.scopus_api_key}}"></div>
            <div><span class="hint">Scopus inst. token</span><input type="password" name="scopus_inst_token" value="{{creds.scopus_inst_token}}"></div>
          </div>
          <div class="row" style="margin-top:10px">
            <div><span class="hint">Embase key</span><input type="password" name="embase_api_key" value="{{creds.embase_api_key}}"></div>
            <div><span class="hint">Embase inst. token</span><input type="password" name="embase_inst_token" value="{{creds.embase_inst_token}}"></div>
          </div>
        </div>
      </details>
    </div>

    <button type="submit">Search &amp; save CSVs</button>
    <p class="hint">Searching can take a little while for large limits — please wait after clicking.</p>
  </form>

  <div class="card">
    <h2>Remove duplicates across saved CSVs</h2>
    <p class="hint">Tick any result files below and merge them into one de-duplicated CSV
       (matched by DOI, or by title when there's no DOI). Useful for combining results
       from different databases or different runs.</p>
    {% if result_files %}
    <form method="post" action="/dedupe">
      <div class="grid">
        {% for fn in result_files %}
          <label><input type="checkbox" name="dedupe_files" value="{{fn}}"> {{fn}}</label>
        {% endfor %}
      </div>
      <div style="margin-top:12px; max-width:420px;">
        <span class="hint">Duplicate matching</span>
        <select name="dedupe_mode" style="width:100%; padding:8px; border:1px solid #ccd; border-radius:8px;">
          {% for value, label in dedupe_modes.items() %}
            <option value="{{value}}" {{ 'selected' if value == dedupe_mode else '' }}>{{label}}</option>
          {% endfor %}
        </select>
      </div>
      <button type="submit" class="secondary" style="margin-top:12px">Merge &amp; remove duplicates</button>
    </form>
    {% else %}
      <p class="msg">No result files yet — run a search first.</p>
    {% endif %}

    {% if dedupe_result is not none %}
      <table style="margin-top:14px">
        <tr><td>Files combined</td><td>{{ dedupe_result.files }}</td></tr>
        <tr><td>Total records read</td><td>{{ dedupe_result.total }}</td></tr>
        <tr><td>Duplicates removed</td><td>{{ dedupe_result.duplicates }}</td></tr>
        <tr><td><strong>Unique records</strong></td><td><strong>{{ dedupe_result.unique }}</strong></td></tr>
        <tr><td>Saved file</td>
            <td>{% if dedupe_result.file %}<a class="dl" href="/download/{{dedupe_result.file}}">{{ dedupe_result.file }}</a>{% else %}—{% endif %}</td></tr>
      </table>
    {% endif %}
  </div>

  {% if results is not none %}
  <div class="card">
    <h2>Results</h2>
    {% for block in results %}
      <h3>{{ block.name }}</h3>
      <p class="msg" style="white-space:pre-line">{{ block.query }}</p>
      <table>
        <tr><th>Database</th><th>Found</th><th>Kept</th><th>Excluded</th><th>Status</th><th>File</th></tr>
        {% for row in block.rows %}
          <tr>
            <td>{{ row.db }}</td>
            <td>{{ row.found }}</td>
            <td>{{ row.kept }}</td>
            <td>{{ row.excluded }}{% if row.breakdown %} <span class="hint">({{ row.breakdown }})</span>{% endif %}</td>
            <td class="msg">{{ row.message }}</td>
            <td>{% if row.file %}<a class="dl" href="/download/{{row.file}}">{{ row.file }}</a>{% endif %}</td>
          </tr>
        {% endfor %}
        <tr>
          <td><strong>Merged (deduped)</strong></td>
          <td colspan="3"><strong>{{ block.merged_count }}</strong> unique kept records</td>
          <td class="msg">across ticked databases</td>
          <td><a class="dl" href="/download/{{block.merged_file}}">{{ block.merged_file }}</a></td>
        </tr>
      </table>
    {% endfor %}
    {% if grand is not none %}
      <h3>All search strings combined</h3>
      <table>
        <tr>
          <td><strong>Unique across every string &amp; database</strong></td>
          <td><strong>{{ grand.count }}</strong> records</td>
          <td class="msg">{{ grand.duplicates }} duplicates removed</td>
          <td><a class="dl" href="/download/{{grand.file}}">{{ grand.file }}</a></td>
        </tr>
      </table>
    {% endif %}
    <p class="hint">Saved into: <code>{{ results_dir }}</code></p>
  </div>
  {% endif %}

<script>
function addQuery() {
  const wrap = document.getElementById('queries');
  const div = document.createElement('div');
  div.className = 'queryblock';
  div.innerHTML =
    '<input class="qname" name="qname" placeholder="Optional short name">' +
    '<textarea name="queries" placeholder="Type your search string here..."></textarea>' +
    '<button type="button" class="secondary remove" onclick="this.parentNode.remove()">Remove</button>';
  wrap.appendChild(div);
}
</script>
</body>
</html>
"""


def current_creds(form=None):
    form = form or {}

    def pick(field, default):
        v = form.get(field)
        return v if v not in (None, "") else default

    return {
        "pubmed_email": pick("pubmed_email", config.PUBMED_EMAIL),
        "pubmed_api_key": pick("pubmed_api_key", config.PUBMED_API_KEY),
        "serpapi_api_key": pick("serpapi_api_key", config.SERPAPI_API_KEY),
        "scopus_api_key": pick("scopus_api_key", config.SCOPUS_API_KEY),
        "scopus_inst_token": pick("scopus_inst_token", config.SCOPUS_INST_TOKEN),
        "embase_api_key": pick("embase_api_key", config.EMBASE_API_KEY),
        "embase_inst_token": pick("embase_inst_token", config.EMBASE_INST_TOKEN),
    }


def render(**kw):
    base = dict(
        dbs=[(k, DATABASES[k]) for k in DB_ORDER],
        defaults={"pubmed": config.ENABLE_PUBMED,
                  "openalex": getattr(config, "ENABLE_OPENALEX", True),
                  "crossref": getattr(config, "ENABLE_CROSSREF", False),
                  "embase": config.ENABLE_EMBASE,
                  "scopus": config.ENABLE_SCOPUS, "serpapi": config.ENABLE_SERPAPI},
        exclusions=exclusion_options(),
        max_results=config.MAX_RESULTS_PER_QUERY,
        year_low=config.YEAR_LOW, year_high=config.YEAR_HIGH,
        default_exclusions=config.DEFAULT_EXCLUSIONS,
        exclude_no_abstract=config.EXCLUDE_NO_ABSTRACT,
        creds=current_creds(), results=None, results_dir=RESULTS_DIR,
        result_files=list_result_csvs(), dedupe_result=None, grand=None,
        dedupe_modes=DEDUPE_MODES, dedupe_mode=DEFAULT_DEDUPE_MODE,
    )
    base.update(kw)
    return render_template_string(PAGE, **base)


@app.route("/")
def index():
    defaults = {
        "pubmed": config.ENABLE_PUBMED,
        "openalex": getattr(config, "ENABLE_OPENALEX", True),
        "crossref": getattr(config, "ENABLE_CROSSREF", False),
        "embase": config.ENABLE_EMBASE,
        "scopus": config.ENABLE_SCOPUS, "serpapi": config.ENABLE_SERPAPI,
    }
    return render(defaults=defaults)


@app.route("/search", methods=["POST"])
def search():
    f = request.form
    creds = current_creds(f)

    queries = [q.strip() for q in f.getlist("queries")]
    names = f.getlist("qname")
    selected_dbs = [d for d in f.getlist("db") if d in DATABASES]
    selected_excl = f.getlist("exclude")
    exclude_no_abstract = bool(f.get("exclude_no_abstract"))
    dedupe_mode = f.get("dedupe_mode") or DEFAULT_DEDUPE_MODE

    def as_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    max_results = as_int(f.get("max_results")) or config.MAX_RESULTS_PER_QUERY
    year_low = as_int(f.get("year_low"))
    year_high = as_int(f.get("year_high"))

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []
    all_kept = []   # every kept record, to build one run-wide deduped file

    for i, query in enumerate(queries):
        if not query:
            continue
        name = (names[i].strip() if i < len(names) and names[i].strip()
                else f"query{i + 1}")
        label = f"q{i + 1}_{slug(name)}"

        rows, merged = [], []
        for db in selected_dbs:
            records, message = search_one(db, query, max_results,
                                          year_low, year_high, creds)
            kept, counts = apply_exclusions(records, selected_excl, exclude_no_abstract)
            breakdown = ", ".join(f"{exclusion_label(k)}: {c}"
                                  for k, c in counts.most_common())

            fname = ""
            if kept:
                fname = f"{stamp}_{label}_{db}.csv"
                write_csv(os.path.join(RESULTS_DIR, fname), kept)
                merged.extend(kept)

            rows.append({
                "db": DATABASES[db], "found": len(records), "kept": len(kept),
                "excluded": sum(counts.values()), "breakdown": breakdown,
                "message": message, "file": fname,
            })

        merged, _dups = dedupe(merged, dedupe_mode)
        merged_file = f"{stamp}_{label}_MERGED.csv"
        write_csv(os.path.join(RESULTS_DIR, merged_file), merged)
        all_kept.extend(merged)

        results.append({
            "name": name, "query": query, "rows": rows,
            "merged_count": len(merged), "merged_file": merged_file,
        })

    # Run-wide file: unique records across ALL search strings AND databases.
    grand = None
    if len(results) > 1:
        grand_records, grand_dups = dedupe(all_kept, dedupe_mode)
        grand_file = f"{stamp}_ALL_MERGED.csv"
        write_csv(os.path.join(RESULTS_DIR, grand_file), grand_records)
        grand = {"count": len(grand_records), "duplicates": grand_dups,
                 "file": grand_file}

    defaults = {d: (d in selected_dbs) for d in DB_ORDER}
    return render(
        defaults=defaults, max_results=max_results,
        year_low=year_low, year_high=year_high,
        default_exclusions=selected_excl, exclude_no_abstract=exclude_no_abstract,
        creds=creds, results=results, grand=grand, dedupe_mode=dedupe_mode,
    )


@app.route("/dedupe", methods=["POST"])
def dedupe_tool():
    """Merge selected CSVs from the results folder and remove duplicates."""
    selected = request.form.getlist("dedupe_files")
    dedupe_mode = request.form.get("dedupe_mode") or DEFAULT_DEDUPE_MODE
    records = []
    for name in selected:
        safe = os.path.basename(name)  # never leave the results folder
        path = os.path.join(RESULTS_DIR, safe)
        if os.path.isfile(path):
            records.extend(read_csv(path))

    unique, dups = dedupe(records, dedupe_mode)
    out_file = ""
    if unique:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = f"{stamp}_DEDUPED_{len(selected)}files.csv"
        write_csv(os.path.join(RESULTS_DIR, out_file), unique)

    dedupe_result = {
        "files": len(selected), "total": len(records),
        "unique": len(unique), "duplicates": dups, "file": out_file,
    }
    return render(dedupe_result=dedupe_result, dedupe_mode=dedupe_mode)


@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(RESULTS_DIR, filename, as_attachment=True)


def open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.2, open_browser).start()
    print("\n  Literature Search is running.")
    print("  If your browser didn't open, go to:  http://127.0.0.1:5000")
    print(f"  CSVs will be saved in: {RESULTS_DIR}")
    print("  To stop it, close this window (or press Ctrl+C).\n")
    app.run(host="127.0.0.1", port=5000, threaded=True)
