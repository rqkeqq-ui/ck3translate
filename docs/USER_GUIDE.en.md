# CK3 Localization Manager — User guide

[Русский](https://github.com/rqkeqq-ui/ck3translate/blob/main/docs/USER_GUIDE.ru.md) · [Download](https://github.com/rqkeqq-ui/ck3translate/releases/latest) · [Community Database](https://steamcommunity.com/sharedfiles/filedetails/?id=3799038632)

## Install and start

Download the archive for your system from GitHub Releases. Extract **all files**, keeping the application and its accompanying folders together. Python is not required.

| System | Download | Open |
| --- | --- | --- |
| Windows x64 | `windows-x86_64.zip` | `CK3LocalizationManager.exe` |
| Linux x64 | `linux-x86_64.tar.gz` | `CK3LocalizationManager` |
| macOS Apple Silicon | `darwin-arm64.zip` | `CK3LocalizationManager.app` |

On macOS you can move the app to Applications. Linux requires a graphical desktop and the system graphics libraries. Check the release notes for platform requirements. Current builds have no commercial publisher signature; macOS is not notarized. Intel Macs do not have a native build in this release.

On first launch, choose the interface language and the language you want to translate mods into. You can change them independently in Settings. The interface supports English, Russian, German, French, Spanish, Simplified Chinese and Korean.

## Add the optional Community Database

1. Open [the official project database on Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3799038632).
2. Click **Subscribe** in Steam and wait for the files to download.
3. In the startup reminder, click **Check download**, or check Community Database in Settings.

**Do not enable the database in a playset.** It contains data for the application, not gameplay changes. The starter dataset contains 12 EN → RU terms; links and rules will grow with community contributions.

You can choose **Continue without the database**. To hide the reminder, select **Do not show this at startup again**; it can be re-enabled in Settings. The check looks for downloaded files, so an unfinished Steam download may still appear as missing. It does not log into or verify ownership of your Steam account.

## Find your mods

Click **Scan library**. If nothing appears, set the Steam installation folder in Settings and scan again. Steam must have finished downloading your subscriptions.

The library shows translation coverage and filters for missing or incomplete translations. Coverage is based on localization keys, not a judgment of translation quality. Double-click a mod to open its overview, strings, changes and diagnostics. Separate translation mods can supply text when they are installed and detected.

## Translate using a web chat

1. Open a mod and choose **Export a job for an AI…**.
2. Choose missing text, changed text or the complete localization. Export JSONL.
3. Open the accompanying prompt file and send it with the JSONL to your chosen chat service.
4. Save the response as JSONL and choose **Import translation from file…** in the app.
5. Review accepted strings in the editor. If a response was incomplete, import the remaining strings later.
6. Choose **Write translation to the game** when you are satisfied with the result.

This workflow needs no API key. A chat provider may impose usage limits or charge for access. XLIFF is also available for translation tools.

## Translate using an API

Select a provider in Settings and save its API key. Supported integrations include Google, DeepL, Yandex, Claude and OpenAI-compatible services. Keys use the operating system's keyring; translation providers have their own pricing and limits.

Open a mod, choose **Translate via API…**, review the estimate and start the translation. Review the result before writing it to the game. Source text and relevant context are sent to the selected provider.

## Review and write

In **Strings**, select a row to compare the source and translation. Edit the target, check the game-token indicator and save. The glossary helps keep terms consistent across mods.

Choose where to write:

- **Inside the mod:** the app adds its own localization files to the original mod's folder. Original author files are preserved.
- **Separate patch mod:** the app creates a local translation mod. Add that patch to your playset and load it after its source mod.

The separate translation patch is different from the Community Database: the patch is used in game; the database stays out of the playset. Always review machine translations and test the result in game.

## After a mod update

Scan again and open **Changes** to see new or changed source text. Translate the affected strings. If Steam removed files previously created by this app, choose **Check and restore** on the mod's overview. Recovery depends on the app's saved translation data; it cannot recover work that was never stored there.

## Update the application

Download and extract the new release into a new folder. Close the old app before starting the new one. Your translations, history and settings live separately from the program files:

- Windows: `%LOCALAPPDATA%/ck3loc`
- Linux/macOS: `~/ck3loc`

Keep a backup of this data folder. API keys remain in the system keyring. Do not share your data folder or logs publicly without reviewing their contents.

## Need help?

Report problems in [GitHub Issues](https://github.com/rqkeqq-ui/ck3translate/issues). Include your operating system, app version, what you tried and the error message. Never include API keys. If a folder cannot be detected, check the configured Steam path first.
