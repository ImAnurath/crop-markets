# Portfolio site (Quarto)

Published at <https://imanurath.github.io/crop-markets/> (a GitHub Pages project site, so
everything lives under `/crop-markets/`).

## Requirements

- **Quarto CLI 1.11.9** (pinned; the version the site was built and checked with).
  Windows without admin: download `quarto-1.11.9-win.zip` from
  <https://github.com/quarto-dev/quarto-cli/releases/tag/v1.11.9>, unzip it anywhere outside
  the repo (e.g. `~/tools/quarto-1.11.9`) and call `bin/quarto.exe` by its full path.
- The project venv with the site requirements (`requirements-site.txt`, includes jupyter and
  plotly) and the editable install of this repo.

## Render locally

Point Quarto's Python engine at the venv, then render from the repo root:

```bash
export QUARTO_PYTHON="$PWD/.venv/Scripts/python.exe"      # PowerShell: $env:QUARTO_PYTHON = "..."
./.venv/Scripts/python.exe scripts/build_site_data.py       # refresh site/data/ (optional)
./.venv/Scripts/python.exe scripts/build_workbook.py        # site/downloads/*.xlsx (gitignored)
quarto render site                                          # -> site/_site/ (gitignored)
quarto preview site                                         # live preview on localhost
```

Use `quarto preview` (or any local web server) rather than opening the HTML files directly:
on `file://` URLs the colour-scheme choice is not remembered and the 404 page's links point
at `/crop-markets/`.

## How it fits together

| Path | What it is |
|---|---|
| `_quarto.yml` | Site config: navbar, footer, themes (dark listed first = the default), resources copied into `_site` (`data/**`, `downloads/*.xlsx`, `assets/**`). |
| `_variables.yml` | Owner details (`author_name`, `author_bio`, `github_url`, `linkedin_url`); placeholders until the owner fills them in; `scripts/check_site_vars.py` (the workflow's first check) blocks every deploy until no value is empty, starts with `OWNER:`, says "fill in" or "placeholder", or is a `*_url` that is not a URL. Use with `{{< var author_name >}}`. |
| `theme/tokens.scss` | Shared tokens and components: fonts, 8px radius, spacing scale (`--s1`..`--s9`), 1840px content width, gutters, honeycomb background, nav, buttons, `.eyebrow`, `.panel`, `.dash` 12-column grid with `.span-1`..`.span-12`, `.strip`/`.stat`, `.explore`, `.seg`, `.pill`, chart skeleton/error states. |
| `theme/dark.scss`, `theme/light.scss` | Colour tokens per scheme, as Bootstrap variables and CSS custom properties (`--bg`, `--panel`, `--line`, `--fg`, `--muted`, `--dim`, `--accent`, `--accent-soft`). |
| `assets/icons.svg` | Line-icon sprite, inlined into every page: `<svg class="ico"><use href="#download"/></svg>` (`arrow-right`, `download`, `contrast`, `chevron-down`, `hexagon`). |
| `assets/site.js` | Adds icons to the nav, loads plotly.js once (non-blocking) and draws every chart, recolouring charts from the CSS variables when the scheme toggles. |
| `assets/CREDITS.md` | Licence and author of the hero photo (credited in the footer too). |
| `filters/main-landmark.lua` | Wraps each page's content in one `role="main"` landmark (`#quarto-document-content`, the skip link's target); the custom layout has no `<main>` of its own. |
| `404.qmd` | Not-found page. Quarto writes its links against the site path (`/crop-markets/...`) because GitHub Pages serves it at whatever URL was missing. |

Charts: build figures with `hazelnut.site.charts` and display them with
`charts.show(fig)` in a Python cell. Give each chart panel a title and a one-line takeaway in
the page; the helpers set no titles. Stat values, the as-of stamp and other page fragments come
from `hazelnut.site.page_helpers` (emit HTML with `page_helpers.raw_html(html)`, for the same reason).

Links: never write root-absolute links (`href="/..."`) in pages; use relative paths or
`.qmd` links and let Quarto resolve them. Colour scheme: the visitor's stored choice if any,
else dark.
