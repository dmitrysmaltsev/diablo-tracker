# Diablo 4 Gear Tracker

A fast, mobile-first reference for **per-slot gear stat priorities** from Diablo 4 build
guides (e.g. [maxroll.gg](https://maxroll.gg/d4)). It strips a long guide down to the part you
check constantly while playing: *"I just got a new helm — which stats matter?"*

It deliberately leaves out skill trees and paragon boards (you set those up once).

- **Static site** — plain HTML/CSS/JS, no build step.
- **Installable PWA** — add to your phone's home screen, works offline.
- **Multiple builds** — pick from a dropdown; each build is one small JSON file.

## Run locally

```sh
python -m http.server 8000
# then open http://localhost:8000
```

(A static server is required — opening `index.html` via `file://` blocks `fetch()` of the
JSON files.)

## Adding / editing a build

1. Copy `builds/shield-of-retribution-paladin.json` to `builds/<your-build-id>.json`.
2. Fill in the fields (see schema below). Set `"verify": false` once a slot is confirmed.
3. Add one line to `builds/index.json` so it shows in the picker:

   ```json
   { "id": "<your-build-id>", "name": "Display Name", "class": "Class", "updated": "YYYY-MM-DD" }
   ```

### Slot schema

```json
{
  "slot": "Helm",
  "item": "Godslayer Crown",   // unique/legendary item name, or "" for a rare
  "type": "unique",            // "unique" | "legendary" | "rare"
  "aspect": "",                // aspect name when type is "legendary"
  "affixes": ["Maximum Life", "Cooldown Reduction"],  // ordered priority, top = most important
  "tempering": ["..."],        // temper recipes/affixes
  "masterwork": ["..."],       // masterwork stat priorities
  "gem": "Ruby",               // socketed gem
  "verify": true               // shows a ⚠ flag until you confirm against the guide
}
```

> **Note:** maxroll renders the detailed affix priorities inside an embedded planner widget,
> not as page text, so this data is curated by hand rather than scraped. The seeded Paladin
> build has item assignments filled in; affix/tempering/masterwork/gem fields are marked
> `"verify": true` and need to be completed from the guide's planner.

## Deploy to GitHub Pages

`gh` CLI is optional. Either way:

**A. With the `gh` CLI** (`winget install GitHub.cli` then `gh auth login`):

```sh
gh repo create diablo-tracker --public --source=. --remote=origin --push
```

**B. Manually:** create an empty repo named `diablo-tracker` on github.com, then:

```sh
git remote add origin https://github.com/<you>/diablo-tracker.git
git push -u origin main
```

Then in the repo: **Settings → Pages → Source: `main` / `/ (root)`**. The site goes live at
`https://<you>.github.io/diablo-tracker/`. Open it on your phone and **Add to Home Screen**.
