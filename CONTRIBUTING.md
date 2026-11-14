# Contributing

Open an issue with the problem, the expected result and steps to reproduce it.
Keep credentials, packet captures, private domain lists and runtime databases
out of issues and pull requests.

Use Python 3.12+ and Node.js 22+ for local checks:

```sh
python -m pip install -r requirements.txt
npm ci --ignore-scripts
python -m unittest discover -s tests -v
node --check gateway/web/app.js
node --check gateway/web/theme.js
node scripts/check_page_runtime.mjs
node scripts/check_login_frontend.mjs
node scripts/check_panel_frontend.mjs
node scripts/check_terminal_emulator.mjs
python scripts/check_docs.py
```

The terminal check runs the xterm parser against startup probes and fragmented
output. It checks first-screen padding, device replies and command scrollback.

On Linux with Docker Engine, build both images and run
`scripts/check_updater_integration.py --gateway-image <gateway> --updater-image <updater>`
to exercise container replacement and rollback in an isolated Compose project.
The test uses synthetic accounts and lists.

Test bootstrap changes against an empty runtime directory and preserve migrations
for existing accounts and settings. Test routing changes for per-list isolation,
LAN bypass and mixed-family exports. Keep VLESS secrets out of API responses.

The web panel supports four distinct component systems and two color modes per
system. Preserve keyboard controls, mobile reflow, readable contrast and the
identity of each style. Keep operational explanations in documentation; the
panel uses concise labels and task feedback.

NetLens has its own repository and checks. Commit its changes there before
updating this repository's submodule revision. Explain the change and relevant
validation in the pull request. Contributions use the project's Apache-2.0 license.

For version changes and tags, follow [Releases](docs/releases.md). Bump minor
for new capabilities and patch for fixes before publishing a release.
