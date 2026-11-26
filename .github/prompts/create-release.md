---
name: create-release
description: Create and publish a patch, minor, or major release of llm-dependabot
---

# Create a Release

Ask the user exactly one question before doing anything else:

> Which release type should I create: patch, minor, or major?

Accept only `patch`, `minor`, or `major` (case-insensitive), and ask again
until the answer is one of them; never infer the type from the repository.
Then carry out the rest of the release, following `AGENTS.md` throughout.

A release is a Git tag and a GitHub release. llm-dependabot runs from its
checkout, which holds `config.yaml` and the app's sources, so it is never
published to PyPI: do not run `uv publish` or upload the built distributions.

## Prepare the release pull request

1. Verify `gh` authentication, fetch and prune `origin`, and work in a new
   worktree off the latest `origin/main`, never in the owner's checkout (see
   "The live checkout" in `AGENTS.md`).

2. Confirm that the version in `pyproject.toml` matches the latest GitHub
   release (`gh release list`), if there is one. Versions and tags use the
   bare `x.y.z` form, without a `v` prefix.

3. Preview the bump with `uv version --bump <type> --dry-run`, create a
   `release-x.y.z` branch for the computed version, and apply it with
   `uv version --bump <type>`, which also updates `uv.lock`. Never edit the
   lockfile by hand.

4. For a release that reaches 1.0.0, set the `Development Status` classifier
   in `pyproject.toml` to `5 - Production/Stable`.

5. Turn the `Unreleased` section of `CHANGELOG.md` into a section headed
   `## [x.y.z] - YYYY-MM-DD`, with today's date, and start a new empty
   `## Unreleased` section above it. Review the pull requests merged since
   the latest release (`gh pr list --state merged`), and make sure the
   section lists every user-facing change under the Keep a Changelog
   categories, without inventing entries.

6. Check the open security alerts with
   `gh api "repos/{owner}/{repo}/<kind>/alerts?state=open"`, where `<kind>`
   is `code-scanning`, `dependabot`, and `secret-scanning` in turn. Where
   code scanning is not set up, the first returns a 404 with "no analysis
   found" (add `-i` to see it), which `gh` misreports as a missing
   `admin:repo_hook` scope; that means there is nothing to check, so do not
   request more scopes. Fix legitimate findings first; dismiss an alert only when the
   repository proves the dismissal reason.

7. Run `make check`, `make hooks`, and `make docs`, and confirm that the
   built files in `dist/` carry the new version.

8. Commit only the version, lockfile, classifier, and changelog changes as
   `chore(release): x.y.z`, and open a ready-for-review pull request with
   that title whose body holds the new changelog section and the validation.
   Take it through CI and review to a squash-merge, as `AGENTS.md` describes.

## Publish

1. Find the squash-merge commit on `main` and confirm that its
   `pyproject.toml` holds the new version.

2. Write the new changelog section, without its heading, to a notes file
   outside the repository, and create the release at that commit:

   ```sh
   gh release create x.y.z --target <merge-commit> --title "llm-dependabot x.y.z" --notes-file <notes-file>
   ```

3. Verify with `gh release view x.y.z` that the tag points at the merge
   commit and the notes match `CHANGELOG.md`.

4. Remove the release worktree, and tell the owner to run
   `make self-update` so the scheduled jobs run the released version.

Report the pull request, merge commit, release URL, and every validation.
Do not claim the release succeeded until the GitHub release is verified.
