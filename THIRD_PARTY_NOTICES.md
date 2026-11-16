# Third-party software notices

VRLab2GIF's own code is MIT licensed; see `LICENSE`. That license does not
replace the independent licenses, copyrights, notices, or trademarks of the
components below. The installed versions and original license texts used by a
particular Windows build are supplied with that distribution in
`third-party/generated/manifest.json` and `third-party/generated/licenses/`
(inside the frozen program), and in `docs/third-party/generated/` in both ZIPs.

| Component | Purpose | License / source |
| --- | --- | --- |
| Liberation Sans Regular 2.1.5 | Embedded GIF annotation font | SIL Open Font License 1.1; `LiberationFonts-LICENSE.txt`; https://github.com/liberationfonts/liberation-fonts |
| Pillow | PNG decoding, GIF encoding and text rasterization | MIT-CMU (older versions may identify it as HPND); https://github.com/python-pillow/Pillow |
| tkinterdnd2 | Python native drag-and-drop binding | MIT; `tkinterdnd2-LICENSE.txt`; https://github.com/Eliav2/tkinterdnd2 |
| TkDnD | Native drag-and-drop extension | Tcl/Tk-style permissive license; `TkDnD-LICENSE.txt`; https://github.com/petasis/tkdnd |
| psutil | Verify and clean up the owned Ansys process | BSD-3-Clause; https://github.com/giampaolo/psutil |
| pywin32 COM and Win32 components | Windows automation and window interfaces | BSD-style notices in `com/License.txt` and `win32/License.txt`; individual files can have their own notices; https://github.com/mhammond/pywin32 |
| Python | Interpreter and standard library | PSF License 2.0 plus historical and included-component notices in the runtime license; https://www.python.org/psf/license/ |
| Tcl / Tk | Tkinter GUI runtime | Tcl/Tk permissive license and any included-component notices; https://www.tcl-lang.org/software/tcltk/license.html |
| PyInstaller | Build tool and embedded bootloader | GPL-2.0-or-later with the bootloader exception; designated runtime files use Apache-2.0; https://pyinstaller.org/en/stable/license.html |

The build collects licenses from the actual installed distributions, preserving
original text byte-for-byte. This includes the native-library notices contained
in Pillow's wheel license and relevant package metadata; it must not be replaced
by only Pillow's top-level short permission notice. Python's Windows runtime
license also includes notices for its bundled dependencies. Build-only tools and
their dependencies are identified separately in the generated manifest.

The installed-package license collection is intentionally a conservative
superset. For example, a pywin32 wheel can carry LGPL-licensed `adodbapi` and
Pythonwin notices even though VRLab2GIF does not import those optional modules.
Their notice text alone does not mean their code is included in the EXE. The
manifest is an environment/license inventory, not a binary-level SBOM or a claim
that every optional codec in a wheel is used.

PyInstaller's bootloader exception permits bundling independently licensed
applications without applying GPL to that application's code merely because the
bootloader is present. Modifying or distributing PyInstaller itself remains
subject to its applicable license. The exception does not waive the licenses of
other bundled components.

The Liberation font may be used, embedded and redistributed with commercial
software under OFL 1.1. Preserve its copyright and full license; do not sell the
font by itself. Modified font software must retain OFL and comply with reserved
font-name restrictions. These conditions apply to font software, not to the
application code or the GIFs rendered with it. The distributed font is unchanged.
Arial is not redistributed in version 1.2.6.

Ansys VRLab is separately installed commercial software invoked through COM. It
is not included in these distributions or relicensed by this project. Repository
sample data has separate source and license documentation under `samples/` and
is not copied into the release ZIPs.

If a build uses a custom Pillow wheel, alternate Python distribution, modified
font or other native libraries, its distributor must update the corresponding
notices and check any additional source/relinking obligations. The release build
fails when required installed-component notices are missing rather than silently
shipping an incomplete collection.
