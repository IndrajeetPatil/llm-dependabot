# hextools

This folder contains the artwork and R scripts for the hex sticker logo, the
LLM Dependabot app icon, and the GitHub social preview card.

## Generating the logo

The sticker artwork is `data.svg`, an original vector drawing in the
indrapatil.com palette: a project card whose dependency edges fan out to three
packages, one of them bumped by the agent (a teal card with an up arrow and a
sparkle). To regenerate the images:

1. **Install R dependencies**:

   ```r
   install.packages(c("hexSticker", "magick", "showtext"))
   ```

2. **Run the script** from the repository root:

   ```bash
   Rscript hextools/script.R
   ```

   The sticker is written to `docs/images/logo.png`, the same sticker on a
   square canvas to `app/icon.png`, and a small copy to
   `docs/images/favicon.ico` for the documentation site. A new icon rebuilds the app, which then
   needs Full Disk Access granted again.

## Generating the social card

`social-card.R` renders `docs/images/social-card.png`, the 1280 × 640 GitHub
social preview: the sticker on paper beside the title, tagline, and URL. It
needs the Fraunces and Hanken Grotesk fonts installed. Run it after
`script.R` so it picks up the current sticker:

```bash
Rscript hextools/social-card.R
```

Upload the image under **Settings → General → Social preview**.
