---
name: documentation-illustrations
description: >
  Create or revise informative diagrams and illustrations for llm-dependabot's
  documentation. Use when a user asks for generated docs artwork or diagrams.
---

# Documentation illustrations

Everything this skill needs is in this repository: the design rules in
`DESIGN.md`, the guides in `docs/`, and figures in `docs/images/`. Do not look
for external references or prompts.

## Inputs

- **Design rules:** read the documentation-illustration section and the colour
  and typography tokens in `DESIGN.md`.
- **Visual references:** open existing raster figures in `docs/images/` (other
  than the hex sticker) and match the one closest to the new subject.
- **Prior prompts:** reuse the structure of prompts recorded in
  `docs/images/README.md` and the adjacent `.prompt.txt` files.
- **Facts:** the guide the figure illustrates is the only source of labels,
  components, values, and flows. For how a run works, that is
  `docs/architecture.md`.

## When to illustrate

Prefer a Mermaid diagram in the guide for flows and process trees; GitHub
renders it, it follows the reader's theme, and it stays editable text. Generate
an illustration only for an overview that Mermaid cannot lay out legibly.

## House style

Map the `DESIGN.md` tokens into the prompt by value, reading them fresh each
time rather than copying them from an older prompt:

| Element | Token |
| --- | --- |
| Canvas | `bg` |
| Title, headings, icons, primary labels | `text` |
| Explanatory labels, arrows | `text-muted` |
| Separators and hairlines | `border` |
| The path being explained (sparingly) | `accent` |
| Failures and denials | `chip-rust` |

- Landscape 3:2, with a large Fraunces-like serif title and headings and
  Hanken-like sans labels.
- Horizontal bands separated by hairlines, each with a heading and a one-line
  muted summary on the left and its flow on the right.
- Flat outline icons in ink; service marks (such as GitHub or Apple) only where
  they identify a real actor, kept accurate and secondary to the labels.
- Thin orthogonal arrows; branches split cleanly and never cross.
- None of: shadows, gradients, texture, 3D, cards, emoji, decorative footers,
  ordinal numbering, invented statistics, hostnames, credentials, private
  repository names, or account values.

## Prompt template

Fill every bracket from the guide and `DESIGN.md`; drop lines that do not
apply.

```text
Use case: infographic-diagram. Asset type: documentation diagram for
llm-dependabot, a macOS tool that runs an AI coding agent weekly to update
dependencies. Landscape 3:2, flat canvas [bg], ink [text], muted ink
[text-muted], fine hairlines [border], sparse accent [accent] for [the path
being explained], muted rust [chip-rust] only for [failures]. Fraunces-like
serif title and band headings, Hanken-like sans labels, generous whitespace,
outline icons, thin orthogonal arrows. No shadows, gradients, texture, 3D,
cards, emoji, ordinal numbering, or invented values. Title exactly '[title]'.
Band '[heading]' with summary '[summary]': '[node]' → '[node]' → '[node]';
under '[node]', note '[label]'. [Repeat per band.] [Branches and boundaries
that must stay distinct.] Use the exact wording given; verify arrow directions
and spelling.
```

For a follow-up edit, state what to preserve (every element, position, arrow,
icon, colour, and other label) and the single change to make.

## Check the result

- View the image at documentation width. Verify every label, arrow direction,
  branch, and boundary against the guide; regenerate or edit if text is
  misspelled, icons mislead, labels are cramped, or the hierarchy departs from
  the references.
- Keep caveats and detail in the Markdown; the image summarises, it does not
  replace searchable text.

## Asset and documentation

- Use the agent's image generation tool. Without one, draw simple diagrams as
  hand-written SVG using the same tokens, or stop and ask.
- Save raster output as WebP in `docs/images/` with a kebab-case name, and
  embed it with alt text that states what the diagram shows.
- Record the final prompt and any edit prompts in `docs/images/README.md` and
  the adjacent `.prompt.txt` files, so the next figure can start from them.
- Change `DESIGN.md` only when the illustration rules change.
