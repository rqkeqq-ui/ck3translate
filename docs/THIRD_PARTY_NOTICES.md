# Third-party software

CK3 Localization Manager is licensed under the GNU General Public License v3 (see LICENSE).
Versions up to 0.2.0 were released under MIT. Bundled dependencies retain their own
licenses; all of them are compatible with GPLv3.

- PySide6 / Qt: LGPLv3, GPLv3 or commercial terms. https://doc.qt.io/qtforpython-6/licenses.html
- Shiboken6: LGPLv3/GPLv3. https://code.qt.io/cgit/pyside/pyside-setup.git/tree/LICENSES
- HTTPX: BSD-3-Clause. https://github.com/encode/httpx/blob/master/LICENSE.md
- keyring: MIT. https://github.com/jaraco/keyring
- watchdog: Apache-2.0. https://github.com/gorakhargosh/watchdog
- PyJWT: MIT. https://github.com/jpadilla/pyjwt
- cryptography: Apache-2.0 or BSD-3-Clause. https://github.com/pyca/cryptography
- filelock: Unlicense. https://github.com/tox-dev/filelock
- PyInstaller: GPL with a bootloader exception permitting distribution of bundled applications. https://pyinstaller.org/en/stable/license.html
- translators: GPL-3.0. https://github.com/UlionTse/translators — free web translators (Bing, Google web, Yandex, Alibaba).
  Its dependencies: requests, requests-toolbelt, niquests, urllib3, urllib3-future, jh2, qh3, wassima: Apache-2.0/MIT/BSD;
  lxml, pathos, dill, multiprocess, pox, ppft, psutil, colorama: BSD; pycryptodome: BSD-2-Clause, Unlicense and MIT;
  exejs: Apache-2.0; Js2Py, pyjsparser, ai-cloudscraper, ai-urllib4, tzlocal, six, pyparsing: MIT; tqdm: MPL-2.0 and MIT;
  aiohttp, aiosignal, frozenlist, multidict, propcache, yarl, tzdata: Apache-2.0 (aiohttp also MIT); certifi: MPL-2.0;
  cffi: MIT-0; pycparser: BSD-3-Clause; typing_extensions, aiohappyeyeballs: PSF.

The portable directory keeps Qt shared libraries separate. You may replace compatible
libraries and debug modifications as permitted by their licenses. Corresponding Qt
and PySide source versions are available at https://download.qt.io/official_releases/
and https://code.qt.io/cgit/pyside/pyside-setup.git/ . Installed package license files
are included under THIRD_PARTY_LICENSES in release bundles.

Crusader Kings III and its assets belong to their respective rights holders.
Game localization files, terminology datasets and third-party mods are not distributed with this application.
This project is not affiliated with Paradox Interactive or Valve.
