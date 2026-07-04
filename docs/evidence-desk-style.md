# Handoff prompt — "Evidence Desk" visual style for rebuild/eval reports

Paste this whole block into a new thread when you want its charts, figures, and
banners to match our house style. It is self-contained: every color, font, and
layout rule is here, so you do not need to fetch any external repo.

---

You are producing the visuals for a technical write-up (a codebase rebuild, a
model eval, or a benchmark comparison). Render them in the **"Evidence Desk"**
style described below — an editorial-broadsheet aesthetic on newsprint, crossed
with a terminal's monospace precision. Do not invent a different look; match this
one exactly. It exists so a reader recognizes the series across articles.

## The one aesthetic rule that matters most

**Honesty is the design.** This style is for reports where the interesting
finding is often the un-flattering one (a flat wall-clock, a metric that didn't
move, a file we failed to improve). Never let the visuals oversell. The accent
color points at the thing being measured, not at "the win." If a result is a
non-win, style it in ink/grey, label it plainly ("honest miss", "already
minimal", "end-to-end: no"), and give it equal space. A skeptical engineer
should trust the chart *because* it shows the misses.

## Palette (exact hex — use as CSS custom properties)

```
--paper:     #F9F8F6   /* page/card background — warm newsprint */
--paper-2:   #F3F1EC   /* secondary surface */
--ink:       #1A1A1A   /* primary text, masthead rules */
--ink-2:     #2A2A2A   /* body text */
--fg-3:      #6E6A61   /* secondary/muted text, kickers */
--fg-4:      #9E988C   /* tertiary, "from" annotations, legacy dots */
--muted:     #B7B2A8   /* faintest labels */
--border:    rgba(26,26,26,0.18)   /* hairline card & rule borders */
--baseline:  rgba(26,26,26,0.22)   /* axis baseline / dashed floor */
--accent:    #E05A47   /* vermilion — the SINGLE accent, "the thing measured" */
--accent-2:  #C84A38   /* darker vermilion for accent TEXT (contrast) */
--base-bar:  #E4E0D8   /* warm grey — the comparison/"before"/legacy series */
--floor:     rgba(26,26,26,0.055)  /* the pale "essential/unavoidable" portion of a bar */
--success:   #4ADE80   /* used sparingly, only for literal pass/green states */
```

Page background behind cards is a slightly darker paper (`#EBE8E1`) so white-ish
cards lift off it. There is exactly **one** accent (vermilion). Everything else
is ink and warm greys. Never introduce a second saturated hue.

**Encoding convention:** accent (vermilion) = the new/rebuilt/winning series;
warm grey (`--base-bar`) = the old/baseline/legacy series; `--floor` = the
unavoidable/essential portion of any measured quantity. Identity must never rest
on color alone — every mark also carries a direct text label.

## Typography (three families; inline as @font-face data URIs — CSP blocks CDNs)

- **Headings & big stat figures:** `Newsreader`, italic, weight 500 (fallback
  `Charter, Georgia, serif`). Used italic for figure titles (~27–31px), section
  h2 (~40px), masthead h1 (~58px), and the giant callout numbers (44–76px).
  This serif italic IS the personality — use it for every title and every hero
  number.
- **Body & captions:** `DM Sans`, weight 400/500 (fallback `Inter, system-ui,
  sans-serif`). Caption size ~14.5px, line-height ~1.55.
- **Everything structural/mono:** `IBM Plex Mono`, weight 400/500 (fallback
  `ui-monospace, monospace`). Used for: kickers/eyebrows, axis ticks, category
  labels, legends, stat-labels, footer colophons. Always UPPERCASE with wide
  tracking for these roles.

Letter-spacing values (use verbatim):
```
kicker/eyebrow:   0.3em, uppercase
category labels:  0.16em, uppercase
tick labels:      0.04em
colophon/footer:  0.18em, uppercase
serif headings:   -0.01em to -0.03em (tighter as they get bigger)
```

Download the three faces locally (Google Fonts CSS2 API → grab the woff2 files →
rewrite the @font-face src to local paths or data URIs) so renders are faithful,
not fallback approximations. Do NOT rely on a CDN link.

## Layout grammar

- **Figure card:** `--paper` background, `1px solid --border`, **square corners
  (no border-radius)**, ~40px padding. Each card is one figure.
- **Masthead of each card, top to bottom:** (1) mono kicker in `--fg-3`
  ("EVIDENCE · DETERMINISTIC CALL COUNTS"); (2) a full-width **1px solid --ink**
  rule; (3) the serif-italic title; (4) a DM Sans caption with the key number
  **bolded in `--accent-2`**.
- **Footer colophon** on every card: `1px solid --border` top rule, then a mono
  uppercase row, space-between: left = the series name (e.g. `RAC-CORE — THE
  EVIDENCE DESK`), right = the method note (e.g. `SYS.SETPROFILE BY CODE-OBJECT
  IDENTITY · IDENTICAL EXIT CODES`). This colophon is the signature of the style
  — always include it.
- **Stat grid** (for headline-figure cards): 4 equal columns, `1px --border`
  outer box with vertical `1px --border` dividers between columns, no
  horizontal dividers. Each cell: a **3px-tall accent bar** at top (use an *ink*
  bar instead when the stat is a non-win), then the giant Newsreader-italic
  figure with a smaller "from X" in `--fg-4`, then a mono uppercase label, then
  a one-line DM Sans note. This is the newsjack signature block.

## Chart specs (all inline SVG — `<rect>`/`<line>`/`<text>`/`<circle>`)

- **Bars:** solid fill, square corners, thin. Stack the pale `--floor` portion
  first, then the series color, with the value label as mono text just past the
  bar end (accent-2 text for the rebuilt/winning row, ink for the baseline row).
- **Dumbbell/comparison rows:** a `--baseline` connector line with a `--fg-4`
  dot (baseline) and an `--accent` dot (new) at each end; ratio/delta label
  right-aligned in mono.
- **Grid:** faint `rgba(26,26,26,0.10)` vertical gridlines; a solid `--baseline`
  axis at the bottom; a **dashed** `--baseline` line to mark a floor/threshold.
- **Category labels:** mono, UPPERCASE, 0.16em tracking, `--ink-2`, right-aligned
  to the left of each row.
- **No chart junk:** no 3D, no gradients, no drop shadows, no rounded bar caps,
  no dual axes. One measure per axis.

## Banner (for X / OpenGraph / article header)

Newsprint masthead treatment: `#F9F8F6` ground, mono uppercase kicker, a
full-width `--ink` rule under it, then a two-line Newsreader-italic headline
with the **second line in `--accent-2`**. Below: a mono sub-line of run stats
(`60 agents · 8M tokens · 1,747/1,747 — twice`), then the hero comparison motif
(the two-bar "less work, same answer" graphic) bottom-left with a mono
pass-checklist bottom-right. Render three geometries from ONE viewport-relative
HTML file (`body { width:100vw; height:100vh }`): **1500×600 (5:2, X's
recommended article header)**, 1200×675 (16:9 card), 1200×630 (OG link preview).
Add a `@media (min-aspect-ratio: 2/1)` block that widens the bars and padding so
the 5:2 crop reads as composition, not stretched 16:9.

## Copy / tone

- Titles are a claim, lowercase-ish and plain: "The engine does less work for
  the same answer", "End-to-end it is not faster today — the profile shows why".
- Captions state the method in the first clause, then the finding, then bold the
  number: "Median of five interleaved runs... **0.96–1.05× everywhere**".
- Prefer real domain nouns and exact figures over adjectives. Never "blazing
  fast" / "dramatically better". The numbers carry it.
- Kickers name the evidence type: `EVIDENCE · WALL-CLOCK, INTERLEAVED MEDIANS`.

## Production mechanics (what actually worked)

- Build ONE `*-export.html` holding all figure cards (each an `id`'d `<div>`),
  and ONE `*-banner.html`. Screenshot with headless Chromium via Playwright at
  `device_scale_factor=2` (`el.screenshot()` per card id; full-page for
  banners). On this environment Chromium is at
  `/opt/pw-browsers/chromium-<ver>/chrome-linux/chrome` — do NOT run `playwright
  install`.
- After every render, **open the PNG and eyeball it** for label collisions and
  overflow before delivering — the palette validator checks color, not layout.
- Verify each PNG by full decode (Pillow `Image.verify()`), and emit a **JPEG
  twin** (quality ~92) — some upload paths reject large PNGs, and a decode check
  catches the "file won't open" failure before the user hits it.
- Keep visible text free of raw HTML entities (`&nbsp;`, `&lt;`) — use plain
  characters (` `, `·`, `under 50%`) so nothing renders literally.
- Two aesthetics can coexist in one export dir — namespace files by style
  (`nj-*` for this Evidence Desk look) so you never clobber the other.

Attribution note: this style is adapted from the public "newsjack.sh eval desk"
design system (elvisun/newsjack). Match the *grammar* (newsprint + serif italic
+ mono + single vermilion accent + honest framing); write your own copy and data.
