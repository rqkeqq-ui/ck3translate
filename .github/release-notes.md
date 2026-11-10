## English

### New in 0.3.1

- **Translation no longer stalls on one bad batch:** when a translator (an AI model or a service) returns fewer lines than requested — it dropped blank or code-only lines, or cut off a long answer — the app now splits that batch in half and retries it, down to a single line, instead of pausing the whole job. Finished lines are kept, and the rest can be resumed.
- **The progress bar keeps moving:** the counter now advances for every batch, including the ones that failed, so a single error no longer leaves it stuck at "Translated 0 of N".
- **Lines with nothing to translate are skipped:** empty values, whitespace and strings made only of game codes, digits or punctuation are no longer sent to the translator — these were the usual cause of a missing line in the answer. They are kept exactly as they are.
- **ChatGPT output limit:** an answer cut off by the model's output limit is now treated as an incomplete batch and retried in smaller parts, instead of stopping the job as an account or quota problem.

**Supported interface languages: English, Russian, German, French, Spanish, Simplified Chinese, and Korean.**

Download and extract the **entire archive** into a new folder. No Python installation needed. Translation data stays in your user profile (`%LOCALAPPDATA%/ck3loc` on Windows, `~/ck3loc` on Linux/macOS). On first launch the database is upgraded; a backup copy of the previous database is saved next to it. Existing translations keep their history; older machine translations without a known provider are shown as "unknown" rather than guessed.

| Platform | Archive | Open |
| --- | --- | --- |
| Windows x64 | `CK3LocalizationManager-0.3.1-windows-x86_64.zip` | `CK3LocalizationManager.exe` |
| Linux x64 | `CK3LocalizationManager-0.3.1-linux-x86_64.tar.gz` | `CK3LocalizationManager` |
| macOS Apple Silicon | `CK3LocalizationManager-0.3.1-darwin-arm64.zip` | `CK3LocalizationManager.app` |

Each archive has a matching `.sha256` file. Linux targets Ubuntu 22.04+ with a graphical desktop and system graphics libraries. macOS requires macOS 14+ on Apple Silicon; no Intel build. Binaries are not signed by a commercial publisher; macOS is ad-hoc signed and not notarized. Linux and macOS use with real game libraries remains preliminary despite native build and launch checks.

Updates are downloaded manually from GitHub, not installed automatically. Your saved translations and settings are preserved.

---

## Русский

### Новое в 0.3.1

- **Перевод больше не встаёт из-за одного неудачного батча:** если переводчик (нейросеть или сервис) вернул меньше строк, чем просили — выбросил пустые или кодовые строки либо обрезал длинный ответ — приложение делит такой батч надвое и повторяет его, вплоть до одной строки, вместо остановки всего задания. Готовые строки сохраняются, остальное можно продолжить.
- **Полоса прогресса больше не замирает:** счётчик двигается для каждой обработанной пачки, в том числе неудачной, поэтому одна ошибка больше не оставляет «Переведено 0 из N».
- **Строки, где переводить нечего, пропускаются:** пустые значения, одни пробелы, а также строки только из игровых кодов, цифр и знаков больше не отправляются переводчику — именно из-за них чаще всего не совпадало число строк в ответе. Такие строки сохраняются как есть.
- **Лимит вывода ChatGPT:** ответ, обрезанный лимитом вывода модели, теперь считается неполным батчем и повторяется меньшими частями, а не останавливает задание как проблема аккаунта или лимита.

Языки интерфейса: английский, русский, немецкий, французский, испанский, китайский (упрощённый) и корейский.

Полностью распакуйте архив своей платформы в новую папку. Python не нужен. Переводы остаются в профиле пользователя (`%LOCALAPPDATA%/ck3loc` в Windows, `~/ck3loc` в Linux/macOS). При первом запуске база обновляется, рядом сохраняется копия прежней базы. История переводов сохраняется; старые машинные переводы без известного провайдера показываются как «неизвестный источник», а не угадываются.

Загрузки: Windows x64 — `CK3LocalizationManager-0.3.1-windows-x86_64.zip` (`CK3LocalizationManager.exe`); Linux x64 — `CK3LocalizationManager-0.3.1-linux-x86_64.tar.gz` (`CK3LocalizationManager`), Ubuntu 22.04+ с графическим рабочим столом; macOS 14+ Apple Silicon — `CK3LocalizationManager-0.3.1-darwin-arm64.zip` (`CK3LocalizationManager.app`), без Intel-сборки. Рядом с каждым архивом — файл `.sha256`. Коммерческой подписи нет; macOS подписана ad-hoc и не нотарифицирована. Linux/macOS пока предварительные для реальных игровых библиотек.

Обновления скачиваются вручную с GitHub и не устанавливаются автоматически. Сохранённые переводы и настройки остаются на месте.
