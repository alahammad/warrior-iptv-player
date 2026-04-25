# Third-Party Notices

This project bundles or depends on the following third-party components at
runtime. Each component retains its own license; the relevant texts are
either linked below or included in this directory.

## libmpv (mpv-2.dll)

- **Upstream:** https://mpv.io / https://github.com/mpv-player/mpv
- **License:** GNU LGPL-2.1-or-later
- **License text:** [`LGPL-2.1.txt`](./LGPL-2.1.txt) (see also https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt)
- **Use:** Dynamically linked via `python-mpv` through `mpv-2.dll`.
- **Obtaining sources:** The corresponding source code is available from the
  upstream mpv project at https://github.com/mpv-player/mpv. Windows builds
  we link against are commonly provided by
  https://sourceforge.net/projects/mpv-player-windows/files/libmpv/ and
  https://github.com/shinchiro/mpv-winbuild-cmake.

libmpv in turn bundles **FFmpeg** (LGPL-2.1-or-later or GPL-2.0-or-later
depending on build configuration), plus other components. See the mpv and
FFmpeg projects for the full list.

> LGPL note: if you redistribute a binary that links against libmpv, you
> must (a) include this notice and the LGPL text, (b) preserve the ability
> for end users to replace the library (which is satisfied here because
> `mpv-2.dll` is a separate DLL next to the executable), and (c) provide a
> way to obtain the corresponding source — the upstream links above
> satisfy this for unmodified builds.

## Python runtime dependencies

See [`requirements.txt`](../requirements.txt) for the full list. Summary:

| Package      | License        | Home                                          |
|--------------|----------------|-----------------------------------------------|
| PySide6      | LGPL-3.0       | https://doc.qt.io/qtforpython/                |
| requests     | Apache-2.0     | https://requests.readthedocs.io/              |
| python-mpv   | AGPLv3 *(see note below)* | https://github.com/jaseg/python-mpv |
| keyring      | MIT            | https://github.com/jaredks/keyring            |

> python-mpv is distributed under the GNU AGPLv3. Depending on how this
> project is distributed, that may impose additional obligations; consult
> an attorney if you intend to ship a closed-source binary.

## Icons and assets

Icons under `resources/assets/` — check individual files or the project
README for attribution.
