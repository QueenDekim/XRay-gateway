# Third-party notices

Xray Gateway code uses Apache-2.0. This license does not replace the licenses of
the software used by the deployment.

| Component             | License and source                                                                                                     |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Xray-core             | [MPL-2.0](https://github.com/XTLS/Xray-core/blob/main/LICENSE), used as a separate container and validation executable |
| Python                | [Python Software Foundation License](https://docs.python.org/3/license.html), supplied by the base image               |
| Alpine Linux packages | Package-specific licenses; consult the base image and its package metadata                                             |

Interface design reference: Damir Sokolovsky,
[Unslop](https://heydamir.design/unslop), CC BY 4.0. The project retains its own
application code, name and user-provided logo.

The gateway image installs these Python libraries and their dependencies:

- [Paramiko](https://github.com/paramiko/paramiko), LGPL-2.1, for SSH/SFTP.
- [cryptography](https://github.com/pyca/cryptography), Apache-2.0 OR BSD-3-Clause,
  for encrypted runtime secrets and SSH cryptography.
- [Pillow](https://github.com/python-pillow/Pillow), MIT-CMU, for avatar processing.
- [qrcode](https://github.com/lincolnloop/python-qrcode), BSD-3-Clause, for local
  authenticator QR codes.

Python package distributions include their license texts. Installed SSH
dependencies include bcrypt (Apache-2.0), PyNaCl (Apache-2.0), cffi (MIT-0),
pycparser (BSD-3-Clause), and Invoke (BSD-2-Clause).

The web panel bundles xterm.js 6.0.0 and its fit addon 0.11.0 under the MIT
license. The files, license texts and package integrity values are in
`gateway/web/vendor/`. Source: [xterm.js](https://github.com/xtermjs/xterm.js).
