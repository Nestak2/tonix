# tonix2: your papers and their citations for Sonix

tonix2 reads your papers from ORCID, merges duplicates (for example an arXiv
preprint and its journal version), compares them with what Sonix already has,
finds who cited each paper in INSPIRE, NASA ADS and OpenAlex, and lets you
review everything with checkboxes. After you confirm, it enters the new
publications and citations in Sonix through a browser, as you would by hand.

Self-citations (citing works by you or by a co-author of the cited paper) are
left out, as Sonix asks ("Моля, не описвайте автоцитирания!"). They are listed
in `self_citations_left_out.csv` so you can check them.

## Install

1. Install Python 3.10 or newer from https://www.python.org/downloads/
   (on Windows, tick "Add python.exe to PATH" during installation). With conda:
   `conda create -n tonix python=3.12` and then `conda activate tonix`.
2. Install Firefox or Chrome if you don't have one. Selenium downloads the
   matching driver by itself the first time (this needs internet).
3. Open a terminal in this folder and run

   ```
   pip install -r requirements.txt
   ```

## Start

* Windows: double-click `start_windows.bat`
* Linux / macOS: run `./start.sh` or `python3 run.py`

A page opens in your browser at http://127.0.0.1:8765/. Any browser works.
To stop the program, click "Close tonix" on the last page, or close the terminal
window. Use `python run.py --port 8800` if port 8765 is taken.

The page is served only to your own computer (127.0.0.1); others on your
network can't open it.

## What you enter

| Field | Needed? | Notes |
|---|---|---|
| ORCID iD | yes | Only your public ORCID works are visible. Check their visibility in ORCID if papers are missing. |
| Year you joined your BAS unit | no | Papers from earlier years start with "In unit report" unticked. |
| Sonix email and password | to compare and save | Leave both empty to only review. |
| Browser for Sonix | | Firefox or Chrome. Tick "Show the browser window" to watch it work. |
| NASA ADS token | no | Without it, ADS is skipped. |
| OpenAlex API key | no | Without it OpenAlex gives only a small daily allowance, which may run out for a long publication list. A free key from https://openalex.org/settings/api gives ten times more. |
| Contact email | no | Sent to OpenAlex and in request headers, as the services ask. |

Passwords, tokens and keys are kept only in memory while the program runs. They
are never written to the cache, the log or the exported files.

### Saving tokens so you don't paste them each time (optional)

* ADS: put the token in the file `~/.ads/token` (on Windows
  `C:\Users\<you>\.ads\token`), or set the environment variable `ADS_API_TOKEN`.
* OpenAlex: put the key in `~/.openalex/key`, or set `OPENALEX_API_KEY`.

The start page tells you when a saved token or key was found.

## Checking whether citing journals are in Scopus (optional, recommended)

Sonix distinguishes "Publication in Scopus/WoS" from "International edition".
To check this, download the Scimago Journal Rank list (it covers Scopus sources):

1. Go to https://www.scimagojr.com/journalrank.php
2. Click "Download data" (top right). You get a `.csv` file.
3. Put that file in the `data` folder of tonix2 and restart.

With the list, a citing journal found in it becomes "Scopus/WoS publication";
one that isn't becomes "International edition" with a note to check. Your own
papers also show their SJR value and quartile. Without the list, refereed
journals are assumed to be indexed, and each such citation says so.

Web of Science indexing can't be checked automatically (Clarivate's data isn't
open), so a WoS-only journal shows as "International edition". Change it in the
type menu when you know better.

## The five screens

1. **Sign in.** Enter the fields above and click "Find my papers". The program
   signs in to Sonix first, so a wrong password is reported straight away.
2. **Papers.** One row per distinct paper, including papers that are in Sonix
   but not in your ORCID record. "In Sonix" shows whether Sonix already has the
   paper (matched by DOI, arXiv ID or title). For papers that aren't there:
   * *Add to Sonix* (published papers start ticked, preprints unticked),
   * *In unit report* ("Влиза в отчета на звеното"; papers from before the year
     you joined start unticked),
   * *Sonix fields*: type, journal status, JCR-IF, SJR, authors and which of
     them are people of your unit, and the rest of the Sonix form. The authors
     of your unit are matched automatically from the Sonix staff list; check them.
   * *Find citations* works for papers already in Sonix and for new ones.
3. **Citations.** Only citations that are new to Sonix are shown; ones Sonix
   already has, and self-citations, are left out (the counts are at the top).
   The text is in the MLA format the Sonix form asks for, and the DOI goes into
   Sonix's link field. Untick anything you don't want and check each type.

   If Sonix has a citation entered as its arXiv preprint and the work has since
   appeared in a journal, it is shown with "Update in Sonix", the current Sonix
   text above the new one. Saving edits that Sonix entry in place (text, type,
   year and link) instead of adding a second one. Before changing it, the
   program checks that the edit page shows the entry it expects; if not, the
   entry is left alone and reported.
4. **Save.** Shows exactly what will be entered or updated and anything that must be fixed
   first (for example a journal status that hasn't been chosen). "Save to Sonix"
   enters the publications first, then the citations, one by one with a short
   pause so the Sonix server isn't overloaded. If Sonix refuses three entries in
   a row, the program stops; what was saved stays saved. "Finish without saving"
   skips this.
5. **Summary.** What was saved, what Sonix refused and why, counts and
   warnings. The files are also saved in `output/run-<date>-<time>/`:
   * `papers.csv`, `citations.csv` and `self_citations_left_out.csv`
     (open in Excel or LibreOffice),
   * `summary.json`,
   * `log.txt`, the activity log.

### Your first save

Before saving many entries, try it once with a single citation: untick
everything except one, save, and look at the result in Sonix. Tick "Show the
browser window" on the start page to watch what the program types.

Running the program again is safe: what is already in Sonix is recognised and
not entered twice.

### What can't be filled in automatically

* **JCR-IF and the WoS quartile.** Clarivate's data isn't open. With the
  Scimago list (below), the SJR value and a status based on the Scimago
  quartile are suggested; if your unit uses the JCR quartile, check the status.
* **Publisher and issue number** are left empty when the databases don't give
  them; add them in Sonix if you want.
* For long author lists (more than 25), the first 10 authors plus your unit's
  authors are entered, and "Общ брой автори" gets the full number.

## Good to know

* Results are cached for 24 hours in the `.cache` folder, so running again is
  fast and gentle on the services. Tick "Download everything again" to refresh,
  or delete `.cache`.
* Google Scholar isn't used: it has no API and blocks automated access. Scopus
  isn't used as a citation source: its API needs an institutional licence.
* INSPIRE returns at most 10,000 citations per paper. A note appears if a paper
  goes beyond that.
* The self-citation check compares surnames and first initials, so it can
  occasionally flag someone with the same name. For papers with more than 50
  authors the co-author check is skipped, since it would flag almost everything.
* If a source fails repeatedly or refuses the token, it is switched off for the
  rest of the run and the summary says so. The other sources carry on.

## If something goes wrong

* **Firefox doesn't start on Ubuntu** (Firefox installed as a snap): choose
  Chrome on the start page, or install Firefox from Mozilla's own package.
* **"Sonix did not answer"**: the server is busy. Try again later; entries that
  were saved are recognised next time.


Open "Activity log" at the bottom of the page, or `log.txt` in the run folder.
Send that log (it contains no passwords or tokens) along with a description of
what you expected.

## For developers

```
pip install -r requirements-dev.txt
python -m pytest
```

The tests use offline stand-ins for all four APIs (`tests/fake_api.py`) and a
fake Sonix built from saved Sonix pages (`tests/fake_sonix.py`). The saved pages
hold personal data and are not in the repository, so the tests that need them are
skipped unless you add your own (see `tests/fixtures/README.md`). The browser
test runs the real form-filling code with Playwright, if it is installed.

| File | Role |
|---|---|
| `run.py` | starts the local server and opens the browser |
| `tonix2/web.py` | the page and its JSON endpoints |
| `tonix2/pipeline.py` | the steps: papers, citations, summary |
| `tonix2/sources/` | ORCID, INSPIRE, ADS, OpenAlex |
| `tonix2/merge.py` | duplicate detection and picking the best version |
| `tonix2/classify.py` | Sonix citation type, optional Scimago list |
| `tonix2/fmt.py` | citation text in the MLA format the Sonix form asks for |
| `tonix2/http.py` | retries, throttling, cache |
| `tonix2/sonix/` | Sonix pages: reading (`parse.py`), matching (`match.py`), browser (`browser.py`), filling forms (`client.py`) |
