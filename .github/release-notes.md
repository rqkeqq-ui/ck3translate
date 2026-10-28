## English

### New in 0.3.0

- **Fix translations even at 100%:** on the **Strings** tab select lines with Ctrl/Shift, then **Export selected…** or **Translate selected…**. Export, import and writing are available at any coverage. Scopes: missing only, missing and outdated, outdated only, selected rows, all rows.
- **Review before anything changes:** imports and in-app translations go to a draft. The preview shows source, current and new text; additions are checked, replacements only when you check them. **Apply selected** updates the project; **Write translation to the game** is always a separate step.
- **One archive for the AI:** export creates a ZIP (JSONL, XLIFF or CK3 YML inside) and a single prompt file with the relevant glossary. **Split into parts** divides a large job into a chosen number of ZIPs or by a number of lines per archive. **Import translation from file…** accepts the returned ZIPs in any order and shows how many archives are still missing.
- **Bulk wizard:** "Translate all mods with no translation…" opens immediately and reads the library in the background; it sends and writes nothing on its own. Choose mods (Local/Workshop) and lines, export for an LLM as ZIP archives, translate all selected mods in one window with a common Stop, import many results with one combined preview, then **Write selected translations to the game…** with the file list and backups.
- **Stop, resume and undo:** **Stop** keeps finished answers; **Action history** resumes jobs without re-requesting finished lines, discards drafts or undoes an application while keeping your later edits. Quota or charges for requests already sent are not refunded. After a restart the app reminds you of unfinished jobs.
- **Translation origin:** LLM, service (Google/DeepL/Yandex), manual, CK3 vanilla, mod author, other mod and unknown are shown separately from review status, with filters and mixed-translation counts. The "Done" tile is now "Fully filled", with reviewed and unreviewed service counts.
- **Remove service translations…:** removes only the unreviewed Google/DeepL/Yandex lines you select, optionally from the app's own game files (with backups). LLM, manual, reviewed, author and unknown translations stay. Undo is available.
- **Free machine translation without a key:** choose "Google Translate · free" in the translation window. It is the default for new installations and needs no account or API key. It uses Google Translate's public web gateway, so lines go one by one with a pause; if Google limits requests (HTTP 429) the job pauses with finished lines kept and can be resumed later. The gateway is unofficial and may change. Results count as a Google service translation.
- **Local and custom AI servers:** the **OpenAI-compatible API URL** and **model** from Settings are now actually used (before, requests still went to api.openai.com — GitHub issue #1). A local server such as LM Studio, llama.cpp or Ollama at `http://127.0.0.1:…/v1` works without a key and never goes through the proxy. The Claude model and Yandex folder ID fields from Settings are applied too. Error messages show the address the request went to.
- **ChatGPT subscription (preview):** choose "ChatGPT · subscription" and click **Sign in with ChatGPT** in the translation window or Settings. Sign-in opens in your browser; the app never asks for your password. Pick a model from the list your account offers. Tokens are kept in the system keyring. No automatic switch to paid API use. Translation needs a paid ChatGPT plan. OpenAI currently refuses session renewal for Sign in with ChatGPT apps, so you sign in again about every hour.
- **System proxy:** translation services, ChatGPT sign-in, covers and Workshop requests now use the Windows system proxy, the same way your browser does (for example a VPN client's system proxy).
- **Rescan and restore:** **Scan library** now really forgets deleted translation mods, including local mods that a `.mod` file pointed to outside the mod folder; they stop counting as coverage. A temporarily unplugged drive is not treated as a deletion. Deleted app files show **Restore translation** instead of being recreated automatically. Archive-only mods no longer appear as broken descriptors.
- **Community Database status:** Settings and Glossary show version, total terms and terms for your language pair. "Refresh from installed database" re-reads data Steam already downloaded. Re-importing with no changes says so instead of suggesting a missing subscription.
- **Faster on large libraries:** opening mods, translation previews and the glossary no longer re-read CK3 vanilla files or re-import the Community Database on every click; localization parsing is faster. **CK3 mod folders** lists the local folder and every Steam Workshop library.

**Supported interface languages: English, Russian, German, French, Spanish, Simplified Chinese, and Korean.**

Download and extract the **entire archive** into a new folder. No Python installation needed. Translation data stays in your user profile (`%LOCALAPPDATA%/ck3loc` on Windows, `~/ck3loc` on Linux/macOS). On first launch the database is upgraded; a backup copy of the previous database is saved next to it. Existing translations keep their history; older machine translations without a known provider are shown as "unknown" rather than guessed.

**Behaviour change:** bulk and in-app translation no longer write to mods automatically. Review the draft, apply it, then write.

| Platform | Archive | Open |
| --- | --- | --- |
| Windows x64 | `CK3LocalizationManager-0.3.0-windows-x86_64.zip` | `CK3LocalizationManager.exe` |
| Linux x64 | `CK3LocalizationManager-0.3.0-linux-x86_64.tar.gz` | `CK3LocalizationManager` |
| macOS Apple Silicon | `CK3LocalizationManager-0.3.0-darwin-arm64.zip` | `CK3LocalizationManager.app` |

Each archive has a matching `.sha256` file. Linux targets Ubuntu 22.04+ with a graphical desktop and system graphics libraries. macOS requires macOS 14+ on Apple Silicon; no Intel build. Binaries are not signed by a commercial publisher; macOS is ad-hoc signed and not notarized. Linux and macOS use with real game libraries remains preliminary despite native build and launch checks.

[Optional Community Database](https://steamcommunity.com/sharedfiles/filedetails/?id=3799038632) is downloaded separately through Steam Workshop: do not enable it in a playset. Updates are downloaded manually from GitHub, not installed automatically.

---

## Русский

### Новое в 0.3.0

- **Исправление перевода даже при 100%:** на вкладке **Строки** выделите строки (Ctrl/Shift) и нажмите **Выгрузить выбранные…** или **Перевести выбранные…**. Выгрузка, загрузка и запись доступны при любом проценте. Объём: только недостающие, недостающие и устаревшие, только устаревшие, выбранные строки, все строки.
- **Проверка до изменений:** импорт и перевод внутри приложения попадают в черновик. Предпросмотр показывает исходник, текущий и новый текст; добавления отмечены, замены — только по вашему выбору. **Применить выбранное** меняет проект; **Записать перевод в игру** — всегда отдельный шаг.
- **Один архив для нейросети:** выгрузка создаёт ZIP (внутри JSONL, XLIFF или CK3 YML) и один файл с промптом и подходящим глоссарием. **Разделить на части** делит большое задание на заданное число ZIP или по заданному числу строк в архиве. **Загрузить перевод из файла…** принимает возвращённые ZIP в любом порядке и показывает, сколько архивов ещё не вернулось.
- **Массовый мастер:** «Перевести все моды, где перевода нет…» открывается сразу и читает библиотеку в фоне; сам ничего не отправляет и не записывает. Выберите моды (Local/Workshop) и строки, выгрузите для LLM в ZIP-архивы, переведите все выбранные моды в одном окне с общей остановкой, загрузите результаты с одним общим предпросмотром, затем **Записать выбранные переводы в игру…** со списком файлов и резервными копиями.
- **Остановка, продолжение и отмена:** **Остановить** сохраняет готовые ответы; **История действий** продолжает задание без повторных запросов готовых строк, отменяет черновики или отменяет применение, не затирая ваши поздние правки. Использованный лимит или оплата отправленных запросов не возвращается. После перезапуска приложение напоминает о незавершённых заданиях.
- **Источник перевода:** LLM, сервис (Google/DeepL/Яндекс), ручной, ваниль CK3, автор мода, другой мод и неизвестный — отдельно от проверки, с фильтрами и составом смешанного перевода. Плитка «Готово» стала «Полностью заполнено», рядом — число проверенных строк и непроверенных переводов сервисов.
- **Убрать перевод сервисов…:** убирает только выбранные вами непроверенные строки Google/DeepL/Яндекса, при желании и из собственных файлов приложения (с резервными копиями). LLM, ручные, проверенные, авторские и неизвестные переводы остаются. Действие можно отменить.
- **Бесплатный машинный перевод без ключа:** выберите «Google Translate · бесплатно» в окне перевода. Для новых установок он выбран по умолчанию, аккаунт и API-ключ не нужны. Используется публичный веб-шлюз Google Translate, поэтому строки идут по одной с паузой. Если Google ограничит запросы (HTTP 429), задание встанет на паузу, готовые строки сохранятся, и его можно продолжить позже. Шлюз неофициальный и может измениться. Такой перевод учитывается как перевод сервиса Google.
- **Локальные и свои ИИ-серверы:** **Адрес** и **Модель OpenAI-совместимого API** из Настроек теперь действительно используются (раньше запрос всё равно уходил на api.openai.com — GitHub issue #1). Локальный сервер LM Studio, llama.cpp или Ollama на `http://127.0.0.1:…/v1` работает без ключа и никогда не идёт через прокси. Модель Claude и Yandex folder ID из Настроек тоже применяются. В тексте ошибки виден адрес, куда ушёл запрос.
- **Подписка ChatGPT (предварительно):** выберите «ChatGPT · подписка» и нажмите **Войти через ChatGPT** в окне перевода или в Настройках. Вход открывается в браузере, пароль приложение не запрашивает. Модель выбирается из списка, доступного вашему аккаунту. Токены хранятся в системном keyring. Автоматического перехода на платный API нет. Для перевода нужен платный план ChatGPT. Сейчас OpenAI отклоняет продление сессий Sign in with ChatGPT, поэтому входить придётся примерно раз в час.
- **Системный прокси:** запросы к сервисам перевода, вход в ChatGPT, обложки и Workshop теперь идут через системный прокси Windows — так же, как в браузере (например, через системный прокси VPN-клиента).
- **Пересканирование и восстановление:** **Сканировать библиотеку** теперь действительно забывает удалённые русификаторы, в том числе локальные моды, на которые `.mod`-файл ссылался вне папки модов; они перестают давать покрытие. Временно отключённый диск удалением не считается. При удалённых файлах приложения появляется **Восстановить перевод** вместо автоматического пересоздания. Архивные моды больше не считаются повреждёнными дескрипторами.
- **Состояние Community Database:** Настройки и Глоссарий показывают версию, число терминов и число для вашей языковой пары. «Обновить из установленной базы» перечитывает уже скачанные Steam данные. Повторный импорт без изменений так и сообщает, не предлагая проверить подписку.
- **Быстрее на больших библиотеках:** открытие модов, предпросмотр перевода и глоссарий больше не перечитывают ванильные файлы CK3 и не импортируют Community Database при каждом действии; разбор локализации ускорен. **Папки модов CK3** показывает локальную папку и все библиотеки Steam Workshop.

Языки интерфейса: английский, русский, немецкий, французский, испанский, китайский (упрощённый) и корейский.

Полностью распакуйте архив своей платформы в новую папку. Python не нужен. Переводы остаются в профиле пользователя (`%LOCALAPPDATA%/ck3loc` в Windows, `~/ck3loc` в Linux/macOS). При первом запуске база обновляется, рядом сохраняется копия прежней базы. История переводов сохраняется; старые машинные переводы без известного провайдера показываются как «неизвестный источник», а не угадываются.

**Изменение поведения:** массовый перевод и перевод в приложении больше не записывают моды автоматически. Проверьте черновик, примените его и затем запишите.

Загрузки: Windows x64 — `CK3LocalizationManager-0.3.0-windows-x86_64.zip` (`CK3LocalizationManager.exe`); Linux x64 — `CK3LocalizationManager-0.3.0-linux-x86_64.tar.gz` (`CK3LocalizationManager`), Ubuntu 22.04+ с графическим рабочим столом; macOS 14+ Apple Silicon — `CK3LocalizationManager-0.3.0-darwin-arm64.zip` (`CK3LocalizationManager.app`), без Intel-сборки. Рядом с каждым архивом — файл `.sha256`. Коммерческой подписи нет; macOS подписана ad-hoc и не нотарифицирована. Linux/macOS пока предварительные для реальных игровых библиотек.

[Community Database](https://steamcommunity.com/sharedfiles/filedetails/?id=3799038632) необязательна, скачивается отдельно через Steam Workshop и не включается в playset. Обновления скачиваются вручную с GitHub и не устанавливаются автоматически.
