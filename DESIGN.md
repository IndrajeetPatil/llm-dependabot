---
version: alpha
name: llm-dependabot
description: >-
  llm-dependabot in the indrapatil.com identity — warm paper, ink, one teal
  accent, Fraunces headings, and flat hairline drawing — applied to the only
  visual surfaces a command-line tool has: its hex sticker, its macOS app
  icon, and its documentation figures.
colors:
  primary: "{colors.accent}"
  bg: "#faf8f4"
  bg-alt: "#f2efe8"
  surface: "#fdfcf9"
  text: "#201d18"
  text-muted: "#5d574c"
  accent: "#14584d"
  accent-light: "#0e7466"
  border: "#e3ded2"
  chip-rust: "#9a3d2e"
typography:
  title:
    fontFamily: Fraunces Variable
    fontWeight: 600
  body:
    fontFamily: Hanken Grotesk Variable
    fontWeight: 400
  sticker:
    fontFamily: Rubik
    fontWeight: 400
rounded:
  sm: 4px
  md: 6px
  lg: 8px
---

# DESIGN.md

The visual design of llm-dependabot. It follows the visual identity of
[indrapatil.com](https://www.indrapatil.com/) (the base), last reconciled on
2026-11-18. Everything in that identity applies here unless this file records
a choice or an addition below.

The tokens above are the base values unchanged. They live in
[`hextools/data.svg`](hextools/data.svg), the social card script
[`hextools/social-card.R`](hextools/social-card.R), and the prompts in
[`docs/images/README.md`](docs/images/README.md), so update those when a token
changes.

## Overview

llm-dependabot has no interface of its own. Its visual surfaces are:

| Surface | Where |
| --- | --- |
| Hex sticker | `docs/images/logo.png`, shown in the README |
| Social card | `docs/images/social-card.png`, the repository's GitHub social preview |
| Documentation site | The theme shared with the owner's other documentation sites; only the logo and favicon come from here |
| App icon | `app/icon.png`, shown for LLM Dependabot in System Settings |
| Diagrams | Generated figures in `docs/images/`, embedded in `docs/` |
| Illustration prompts | `docs/images/README.md` |

All of them should read as part of the indrapatil.com family at a glance:
paper, ink, hairlines, and one accent.

## Choices

| Base parameter | Choice here | Why |
| --- | --- | --- |
| Accent | Teal-green, the base default | Nothing about the subject calls for another accent. |
| Paper and ink | The base values, unchanged | — |
| Chip hues | Rust only, for failures in figures | There is no taxonomy to colour. |
| Dark mode | Not applicable | The sticker and icon are fixed artwork; GitHub themes the Mermaid diagrams. |

## Additions

### Hex sticker and app icon

- **Artwork:** an original vector drawing in `hextools/data.svg` — a project
  card in ink whose dependency edges, in muted ink, fan out to three packages.
  Two stay on `bg-alt` with muted outlines; the one the agent bumps is filled
  with the accent and carries an up arrow in `surface`, with two sparkles in
  `accent-light` beside it for the language model.
- **Frame:** white fill and an accent border, as on the other project stickers.
- **Type:** the package name in Rubik, ink, centred above the artwork; the
  documentation site URL in small grey type along the lower-right edge.
- **Icon:** the same sticker centred on a transparent square, so the app is
  recognisable in Full Disk Access next to the sticker in the README.
- Keep the drawing flat: no shadows, gradients, texture, or emoji.

### Social card

- **Layout:** 1280 × 640 on `bg` with a `border` hairline frame; the sticker
  on the right, and on the left the name in Fraunces (`text`), a short accent
  rule, the tagline in Hanken Grotesk (`text-muted`), and the documentation site URL
  in the accent.
- **Source:** `hextools/social-card.R`, which reuses the rendered sticker.

### Documentation diagrams

Generated diagrams use this file's palette and typography. Keep one idea per
figure, labels in sentence case, and the same wording as the surrounding text.
Record the prompts in [`docs/images/README.md`](docs/images/README.md), and
preserve explanatory detail in searchable Markdown.

## Documentation illustrations

Generated figures use the palette and typography above: warm paper
(`#faf8f4`), ink (`#201d18`), muted ink (`#5d574c`), hairlines (`#e3ded2`),
sparse teal accent (`#14584d`) for the path being explained, and muted rust
(`#9a3d2e`) only for failures. Use Fraunces-like serif titles and Hanken-like
sans labels, flat outline icons in ink, and thin orthogonal arrows. Preserve
explanatory detail in searchable Markdown. Avoid shadows, gradients, texture,
3D, cards, decorative footers, emoji, ordinal numbering, and invented facts.
The [documentation-illustrations skill](.agents/skills/documentation-illustrations/SKILL.md)
turns these rules into a prompt.
