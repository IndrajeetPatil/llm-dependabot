# hextools

This folder contains the artwork and R script for the hex sticker logo and the
LLM Dependabot app icon.

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

   The sticker is written to `docs/images/logo.png`, and the same sticker on a
   square canvas to `app/icon.png`. A new icon rebuilds the app, which then
   needs Full Disk Access granted again.
