## English

The first public release of CK3 Localization Manager.

- Scan Steam Workshop mods and find missing translations.
- Export and import JSONL/XLIFF, translate through APIs, and review text in the editor.
- Keep terminology consistent with a glossary and validate game tokens before writing.
- Track changes and restore app-generated translations.
- Optional Community Database support; its Workshop page is coming later.

### Download and launch

Download the archive for your platform and **extract it completely**:

| Archive suffix | Platform | Launch |
| --- | --- | --- |
| `windows-x86_64.zip` | Windows x64 | `CK3LocalizationManager.exe` |
| `linux-x86_64.tar.gz` | Linux x64 | `CK3LocalizationManager` (use `chmod +x` if needed) |
| `darwin-arm64.zip` | macOS Apple Silicon | The `.app` bundle |

No Python installation is required. SHA-256 checksum files are provided alongside the archives.

### Platform notes

- **Linux:** built on Ubuntu 22.04. Requires a graphical session and system Qt/XCB/OpenGL dependencies.
- **macOS:** built on macOS 14 for Apple Silicon. Not notarized by Apple; an Intel build is not included.
- The binaries do not have a commercial publisher signature. Treat the initial Linux/macOS builds as preliminary until tested with a real game library.

**Do not enable the Community Database in a playset.** The application works without it.

---

## Русский

Первый публичный выпуск CK3 Localization Manager.

- Сканирование Steam Workshop и поиск недостающего перевода.
- JSONL/XLIFF, перевод через API, редактор строк и глоссарий.
- Проверка игровых токенов, история и восстановление переводов.
- Необязательная Community Database: страница Workshop ещё готовится.

Скачайте архив своей платформы и распакуйте его целиком:

- windows-x86_64.zip — Windows x64, запуск CK3LocalizationManager.exe.
- linux-x86_64.tar.gz — Linux x64, запуск CK3LocalizationManager (при необходимости chmod +x).
- darwin-arm64.zip — macOS Apple Silicon, приложение .app.

Python не требуется. SHA-256 лежат рядом с архивами.
Linux: сборка на Ubuntu 22.04, требуется графический сеанс и системные Qt/XCB/OpenGL-зависимости.
macOS: сборка на macOS 14, Apple Silicon; не нотарифицирована Apple. Intel-сборка в этот выпуск не входит.
Бинарники не имеют коммерческой подписи издателя. Первые Linux/macOS сборки следует считать предварительными до проверки на реальной игровой библиотеке.

Community Database не нужно включать в playset. Приложение работает без неё.
