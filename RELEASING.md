# Releasing Cultivars MCP

A release puts the package on PyPI as `cultivars-mcp`, creates a GitHub release, and lists
the server in the official MCP Registry as `io.github.CopyleftCultivars/cultivars-mcp`.
Pushing a `v*` tag does the first two through `.github/workflows/release.yml`. The registry
listing is one manual command.

## One-time setup (a maintainer, once)

1. **PyPI trusted publisher.** Sign in at pypi.org, go to Your projects → Publishing → "Add a
   new pending publisher", and enter:
   - PyPI project name: `cultivars-mcp`
   - Owner: `CopyleftCultivars`
   - Repository: `cultivars-mcp`
   - Workflow name: `release.yml`
   - Environment name: `pypi`

   No API token is created or stored. The workflow proves who it is to PyPI with GitHub's
   OIDC token, and the first successful publish creates the project.
2. **GitHub environment.** In the repo's Settings → Environments, create `pypi`. Adding
   yourself as a required reviewer means every PyPI upload waits for your click.
3. **MCP Registry publisher.** Install `mcp-publisher` (see the registry's
   [publishing guide](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx)),
   then run `mcp-publisher login github` and sign in with a GitHub account that is a member of
   the CopyleftCultivars org. The `io.github.CopyleftCultivars/` namespace is granted from
   that membership.

## Each release

1. **Pick the version** (for example `0.2.0`) and set it in three places:
   - `version` in `pyproject.toml`
   - `version` in `server.json`
   - `packages[0].version` in `server.json`
2. **Write the CHANGELOG section.** Rename the `## [Unreleased] ...` heading(s) you are
   releasing to `## [0.2.0] — YYYY-MM-DD`. The workflow uses that section as the release
   notes and fails if it is missing.
3. **Check locally**:
   ```bash
   python scripts/release_check.py v0.2.0 --notes /tmp/notes.md
   pytest tests/ -q
   uv build
   ```
4. **Merge** those changes to `main` through a pull request and let CI go green.
5. **Tag and push**:
   ```bash
   git checkout main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```
   The Release workflow checks the versions, runs the tests, builds, publishes to PyPI (after
   your approval if you set a reviewer on the `pypi` environment), then creates the GitHub
   release with the wheel and sdist attached.
6. **Confirm** `uvx cultivars-mcp` starts and an MCP client lists 35 tools (or the current
   count).
7. **Registry listing**, from a clone at the tag:
   ```bash
   mcp-publisher publish
   ```
   The registry confirms PyPI ownership by finding the
   `mcp-name: io.github.CopyleftCultivars/cultivars-mcp` line in the README, which PyPI shows
   as the package description. Leave that line in place.

## If something goes wrong

- **Version mismatch or missing CHANGELOG section:** the build job stops before anything is
  published. Fix it on `main`, delete the tag (`git push --delete origin v0.2.0` and
  `git tag -d v0.2.0`), and tag again.
- **PyPI rejects the upload:** PyPI never accepts the same version twice, even after a
  deletion. Bump to the next patch version and release again.
