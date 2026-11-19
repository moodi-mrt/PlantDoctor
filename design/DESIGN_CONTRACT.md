# PlantDoctor — Frontend Design Contract

Skills applied: `frontend-design-direction`, `make-interfaces-feel-better`, `accessibility` (WCAG 2.2 AA).

## 1. Direction

| Item | Decision |
|---|---|
| Product surface | Single-page diagnostic tool served locally (`app/static/`) |
| User's job | Photograph a leaf → get a trustworthy diagnosis → know what to do next |
| Audience | Farmers, agronomy students, extension workers; repeat use, often on a phone in the field |
| Primary action | Provide an image (drop / browse / paste / sample) |
| Scan order | 1. Verdict (disease + status badge) → 2. confidence vs. thresholds → 3. actions → 4. alternatives |
| Tone | Calm, technical, clinical-report. Neutral surfaces; colour reserved for meaning (green = confident, amber = verify, red = inconclusive) |
| Memorable detail | Confidence meter showing the 40 % / 70 % decision thresholds, plus a heatmap with opacity control — the UI exposes *why* it trusts a result |
| Constraints | No framework or build step; no new dependencies; offline-safe fallbacks for fonts; light + dark; reduced motion; WCAG 2.2 AA |
| Target viewports | `390x844` (phone), `1440x900` (desktop) |

Reference observations behind choices (local, no external research): the previous version's
coverage grid left large empty cells (→ masonry columns); confidence alone was ambiguous
without the thresholds the backend actually uses (`app/inference.py`: `UNCERTAIN = 0.40`, `CONFIDENT = 0.70`).

## 2. Content states

| State | Trigger | Visible feedback | Safe next action |
|---|---|---|---|
| Loading | Image submitted | Report skeleton + preview with scan line, `aria-busy`, SR announcement | Wait (inference < 0.5 s); cancellation not offered — request is too short to be worth it |
| Empty | First visit / "New" | Illustration + "No image analysed yet" | Upload or pick a sample |
| Error | Non-image, > 15 MB, unreadable file, server down | Inline error panel naming the failure + toast | "Try another image" button; previous report kept if one existed |
| Partial | (a) Report reopened from history — original photo not stored; (b) `/api/info` metrics missing; (c) model server offline | (a) "Original" view disabled with explanation, heatmap shown; (b) "Not available" in KPI/model card; (c) red "Model offline" pill + inline explanation in empty state | (a) re-upload for full view; (b) run `tools/eval_field.py`; (c) start server with `./run.sh` |
| Success | Prediction returned | Report with status badge, report ID, SR announcement of verdict | "New", "Print / PDF", heatmap |
| Permission | — | Not applicable | Local single-user app: no accounts, roles or protected data; camera access is not requested (file input only) |

## 3. Audit of the previous version (before this pass)

| # | Skill | Finding | Fix |
|---|---|---|---|
| A1 | accessibility | `--text-3` contrast 3.0–3.2:1 (light), 3.8–4.05:1 (dark) on labels, hints, table headers — fails 1.4.3 | Light `#696c64` (5.3:1), dark `#8a8e86` (5.5:1) |
| A2 | accessibility | Hidden file input was itself focusable → duplicate tab stop | `tabindex="-1"` on input; label is the control |
| A3 | accessibility | View switch used `role="tab"` without tabpanels / arrow keys | Toggle buttons with `aria-pressed` in a labelled group |
| A4 | accessibility | Whole report was an `aria-live` region → verbose re-reads | Dedicated visually-hidden status: "Diagnosis complete: …" |
| A5 | accessibility | Sample buttons' accessible name was "alt + Field" fragments | Explicit `aria-label` ("Try sample: Tomato late blight, field photo") |
| A6 | accessibility | Table had no caption | Visually hidden `<caption>` |
| A7 | accessibility | Theme button label static | Label reflects target ("Switch to dark theme") + `aria-pressed` |
| P1 | feel-better | `transition: .15s` shorthand (= `all`) on nav, icon buttons, segmented, toast | Explicit `transition-property` lists |
| P2 | feel-better | Icon button 34 px; "Clear" text button ~18 px tall; segmented 28 px | 40 px icon buttons; ≥ 32 px text/segmented targets |
| P3 | feel-better | No image outlines; leaf photos blur into surfaces | Neutral inset 1 px alpha outline on all content images |
| P4 | feel-better | Theme icon swapped with `display` (instant pop) | Cross-fade with opacity + scale + rotate |
| P5 | feel-better | Buttons press with `translateY` only | `scale(.97)` press; disabled under reduced motion |
| P6 | feel-better | Result appeared instantly | One-shot enter: opacity + 6 px rise + slight blur, 220 ms |
| P7 | feel-better | No `text-wrap` on body copy | `balance` on headings, `pretty` on descriptions/list items |
| D1 | design-direction | Error state only a transient toast | Inline error panel with recovery action |
| D2 | design-direction | History reopen silently showed heatmap as "Original" | Explicit partial state |
| D3 | design-direction | Header subtitle described features the controls already show | Shorter, outcome-focused copy |
| R1 | accessibility | (found in rendered review) Mobile status pill hid its text → colour-only "offline" | Short text label "Online"/"Offline" on mobile |
| R2 | design-direction | (found in rendered review) `.container` padding shorthand removed page-header bottom spacing on mobile | `padding-inline` |
| R3 | design-direction | (found in rendered review) Empty "Try a sample" heading when server offline | Block hidden until samples load |
| R4 | accessibility | (found by gate) Opacity slider 16 px tall | 32 px hit area |

## 4. Verification
`tools/ui_gate.py` (headless Chrome, CDP) → `design/evidence/` screenshots + `gate_results.json`; evidence record `design/evidence/evidence.json`.
Official checker (needs Node.js, not installed on this PC):
`node ~/.claude/skills/frontend-design-direction/scripts/check-evidence.js design/evidence/evidence.json`
