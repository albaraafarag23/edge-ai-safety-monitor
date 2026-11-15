# Regulation clauses in incident reports

Every incident report quotes the code-of-practice clause that its rule enforces, in a `## Regulation` section
between Violations and Findings (Arabic report: `## اللائحة`). The clauses come from **SiteSentry Regs**
(github.com/albaraafarag23/sitesentry-regs), the team's companion assistant for construction-safety
regulations: SiteSentry detects the violation, SiteSentry Regs says which rule it breaks.

## How it works

- Each plugin rule has a `regulations` list (docs/plugins.md): document, title, clause, heading, page, the
  clause's words (`text`, verbatim, `…` where parts are left out), and the official PDF's address. Arabic
  reports use `heading_ar`/`text_ar` where given.
- `ai_reporting/report.py` (`with_regulations`) adds the section **in code, after** the report is written, for
  Claude and template reports alike. The LLM is told not to cite regulations itself, so a clause number or a
  quotation can never be made up.
- No live dependency: the clauses are stored in the plugin, so reports cite them offline on the Jetson, at no
  cost, and nothing breaks if the SiteSentry Regs server is asleep or down.

## Which clause for which rule (looked up 2026-11-15)

Documents: Sharjah Prevention and Safety Authority codes of practice **OSHJ-CoP-02** (OSH Management in
Construction) and **OSHJ-CoP-04** (Working at Height Safety), Version 1 Rev 0, Sep 2021.

| Rule | Clause | Why |
|---|---|---|
| RULE_PPE_01 hard hat | CoP-02 5.13 Personal Protective Equipment | Safety helmets are a minimum requirement |
| RULE_PPE_02 vest | CoP-02 5.13 Personal Protective Equipment | High-visibility vests "to be worn by employees working on construction sites" |
| RULE_ZONE_01 excavation edge (construction_safety) | CoP-02 5.9 Securing the Construction Site | "Barrier off or cover over excavations or pits", keep unauthorised people out |
| RULE_ZONE_01 no-entry area (construction_demo) | CoP-02 5.7 Site Rules | Site rules must cover restricted areas |
| RULE_ZONE_02 under the crane | CoP-04 5.5.1 Falling Objects | Protect people below from falling objects |
| RULE_ZONE_03 scaffold capacity | CoP-04 5.3 Selecting the Right Work at Height Equipment | The platform must not be overloaded |
| RULE_PROX_01 near machinery | CoP-02 5.7 Site Rules | Site rules must cover traffic management and pedestrian routes |
| RULE_SMOKE_01 / _02 smoking, vaping | CoP-02 5.7 Site Rules | Site rules must cover smoking |
| RULE_FOOD_01 food in a restricted zone | CoP-02 5.7 Site Rules | Site rules must cover food and rest areas, and restricted areas |
| RULE_POSE_01 person down | CoP-02 7.2 First Aid | First aid and an appointed person who calls the ambulance |
| RULE_POSE_02 sleeping on site | none | Neither code covers it; better no citation than a far-fetched one |

How: the SiteSentry Regs search (`app.retrieval.retrieve`, same as its `/search` endpoint) was asked one plain
question per rule; every candidate clause was then read in full, and only clauses that really cover the rule
were kept. Every quoted piece was checked to appear word for word in the clause as stored.

Note on smoking: CoP-02 doesn't ban smoking outright; it requires the site rules to address it. The report
quotes exactly that, so it says what the code says.

Arabic: OSHJ-CoP-04 has an Arabic edition, but its extracted text has letters in the wrong order (a known
limit, see the SiteSentry Regs README), so Arabic reports use its clean Arabic headings with the English
wording. CoP-02 has no Arabic edition.

## Refreshing the clauses

When SiteSentry Regs gets new documents, or a rule changes, run its search locally and update `regulations`:

```bash
# in a clone of sitesentry-regs, with its database filled (README: download + ingest)
python -c "from app.retrieval import retrieve; [print(c['document'], c['clause'], c['heading'], c['page'])
           for c in retrieve('Must workers on a construction site wear a safety helmet?', top_k=5)]"
```

Read the clause in full before citing it, and quote it word for word.
