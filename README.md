<div align="center">

# CK3 Localization Manager

### More stories in your language.

Translate Crusader Kings III mods, keep up with changes and restore your work after updates.

[**Download the app**](https://github.com/rqkeqq-ui/ck3translate/releases) · [Get started](#get-started-in-minutes) · [Report an issue](https://github.com/rqkeqq-ui/ck3translate/issues) · [Русский](docs/README.ru.md)

</div>

![Mod library](docs/images/01-library.png)

## Your favorite mod just updated. Keep its translation up to date, too.

CK3 Localization Manager brings mod translation into one place: find missing text, translate what you need and restore files created by the app. For players who want to understand every event, and translators who want to keep their progress through every update.

### Your whole library at a glance

Scan installed Steam Workshop subscriptions. Find untranslated mods, incomplete localizations and separate translation mods. Coverage measures matching localization keys; translation quality still needs a human review.

### Translate your way

Export a JSONL task with a ready-to-use prompt, send it to ChatGPT, Claude, DeepSeek or another chat, then import the result. No API key is needed for this workflow; free access depends on the chat service. Or connect Google, DeepL, Yandex, Claude and OpenAI-compatible APIs directly in the app. Provider pricing and limits apply. XLIFF exchange is available for translation tools.

### Keep the work you have already done

The app writes its own translation files while preserving the mod author's original files. Write into the mod directory or create a separate patch mod. Local history, backups and change tracking help restore app-generated translations after Steam updates. Translate new or changed source text separately.

### Consistent terms. Game syntax under control.

Review the original and translated text side by side. A glossary and translation memory help keep your terminology consistent; vanilla references can be extracted from your installed CK3. Token validation detects missing variables, formatting tags and commands before writing. Always review the text and test it in game.

## See it in action

| Mod overview | Translation editor |
| --- | --- |
| ![Mod overview](docs/images/02-mod.png) | ![Translation editor](docs/images/03-editor.png) |
| **Glossary** | **Export for an AI chat** |
| ![Glossary](docs/images/04-glossary.png) | ![Export dialog](docs/images/05-export.png) |

Actual application screens, shown in English with fictional demonstration mods. [Gallery and publishing captions](docs/GALLERY.md).

## Get started in minutes

1. Open [Releases](https://github.com/rqkeqq-ui/ck3translate/releases) and download the archive for your operating system.
2. Extract the **entire archive**. Run `CK3LocalizationManager.exe` on Windows, `CK3LocalizationManager` on Linux, or the `.app` on macOS. No Python installation required.
3. Choose your languages and scan your library. If Steam is not detected, set its folder in Settings.
4. Open a mod, translate missing text, review the result and write your translation.

Windows x64, Linux x64 and macOS Apple Silicon are built separately. Check the release notes for available downloads and platform limitations. [Detailed user guide (Russian)](README-запуск.md).

## Community Database — growing with the community

An optional dataset for links between mods and their translations, shared terminology and processing rules. The first release includes 12 EN → RU glossary terms; translation links and mod rules are currently empty. Share verifiable suggestions through Issues.

**The Steam Workshop page is coming later.** The app works without a subscription. Once published, the link will appear in Settings in a new build; an installed database can already be discovered through its marker file.

Subscribing downloads data, not the desktop application. **Do not enable the database in a playset.**

## Free and open source

The app is free and licensed under [MIT](LICENSE). Translation services may charge separately. This project is not affiliated with Paradox Interactive or Valve. Dependencies retain their [own licenses](THIRD_PARTY_NOTICES.md).

[Support development](docs/SUPPORT.md) · [Publishing guide for the author (Russian)](PUBLISHING.md) · [Build from source (Russian)](docs/DEVELOPMENT.md) · [Описание на русском](docs/README.ru.md)
