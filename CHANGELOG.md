# Changelog

## 1.11.0

- Add a No expiry option when creating API tokens; keep revocation and 2FA confirmation.
- Represent tokens without an expiration date as `expires_at: null` in the API.

## [1.10.0](https://github.com/QueenDekim/XRay-gateway/tree/1.10.0-d87cdee)

- Authenticate API integrations with named, expiring Bearer tokens.
- Create and revoke tokens under personal settings; confirm each issue with 2FA when enabled.
- Store token hashes and display each secret once; preserve the owner’s access restrictions.
- Revoke token access after password, role or 2FA security changes.
- Document Bearer authentication and token management in the API Wiki.

## [1.9.0](https://github.com/QueenDekim/XRay-gateway/tree/1.9.0-25aa28a)

- Serve login, overview, profiles, lists, RouterOS and settings as separate pages; retain the current page and settings tab on reload.
- Restore encrypted sessions after panel restarts without flashing the login screen.
- Check published releases and show an update notification above the version link.
- Install updates through a separate Compose worker with a private backup, health checks and rollback; add optional automatic updates.
- Publish the updater image alongside the gateway for Linux amd64 and arm64.
- Add API Wiki navigation with separate reference pages in the panel and documentation.
- Correct the README logo for GitHub light mode and refresh theme screenshots.
- Document source builds, GHCR deployment, updates and recovery.

## [1.8.2](https://github.com/QueenDekim/XRay-gateway/tree/1.8.2-b1979d9)

- Publish tested Linux amd64/arm64 gateway images to GitHub Container Registry.
- Include version aliases, source labels and license notices in published images.

## [1.8.1](https://github.com/QueenDekim/XRay-gateway/tree/1.8.1-ec9bd89)

- Use feature-based minor versions and patch versions for fixes.
- Validate release tags against VERSION and the source revision.
- Reclassify historical tags without rewriting source commits.

## [1.8.0](https://github.com/QueenDekim/XRay-gateway/tree/1.8.0-e1b40c6)

- Select, rename and prioritize subscription profiles in a modal; group profiles by subscription.

## [1.7.0](https://github.com/QueenDekim/XRay-gateway/tree/1.7.0-68e7383)

- Review and import multiple VLESS subscription profiles in one update.

## [1.6.1](https://github.com/QueenDekim/XRay-gateway/tree/1.6.1-209592d)

- Hide RouterOS from regular users and avoid misleading perfect success rates.

## [1.6.0](https://github.com/QueenDekim/XRay-gateway/tree/1.6.0-353eef5)

- Give regular users read-only shared data and full-list viewing.

## [1.5.2](https://github.com/QueenDekim/XRay-gateway/tree/1.5.2-f0ce224)

- Preserve terminal probes and visible banner rows while removing blank scrollback.

## [1.5.1](https://github.com/QueenDekim/XRay-gateway/tree/1.5.1-9d0f94c)

- Trim excess blank rows during RouterOS terminal startup.

## [1.5.0](https://github.com/QueenDekim/XRay-gateway/tree/1.5.0-c0f5100)

- Accept domains in mixed lists and connect the RouterOS terminal on page entry.

## [1.4.5](https://github.com/QueenDekim/XRay-gateway/tree/1.4.5-ffed7bf)

- Polish account controls and show masked placeholders for saved RouterOS credentials.

## [1.4.4](https://github.com/QueenDekim/XRay-gateway/tree/1.4.4-6ed8370)

- Request two-factor codes in a separate login dialog.

## [1.4.3](https://github.com/QueenDekim/XRay-gateway/tree/1.4.3-b51060a)

- Preserve login credentials while requesting a two-factor code.

## [1.4.2](https://github.com/QueenDekim/XRay-gateway/tree/1.4.2-333ce0f)

- Keep login fields editable during two-factor authentication.

## [1.4.1](https://github.com/QueenDekim/XRay-gateway/tree/1.4.1-0f7922c)

- Use themed confirmation dialogs for panel operations.

## [1.4.0](https://github.com/QueenDekim/XRay-gateway/tree/1.4.0-b657483)

- Managed RouterOS SSH, direct list operations, personal accounts, avatars and TOTP 2FA.

## [1.3.0](https://github.com/QueenDekim/XRay-gateway/tree/1.3.0-a118b51)

- Support VLESS transports with TLS, REALITY and no transport encryption.

## [1.2.0](https://github.com/QueenDekim/XRay-gateway/tree/1.2.0-aa72ba3)

- Import subscription URLs and reset profile check counters; fix VLESS validation.

## [1.1.1](https://github.com/QueenDekim/XRay-gateway/tree/1.1.1-4c5ba97)

- Update the NetLens submodule with the portable Tcl/Tk fix.

## [1.1.0](https://github.com/QueenDekim/XRay-gateway/tree/1.1.0-6744ab8)

- Russian and English interfaces, language selection and linked build versions.

## [1.0.0](https://github.com/QueenDekim/XRay-gateway/tree/1.0.0-c657815)

- Configurable deployment, dashboard, RouterOS scripts and NetLens submodule.
