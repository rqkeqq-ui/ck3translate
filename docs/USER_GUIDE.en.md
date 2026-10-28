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
2. Choose the scope and format (JSONL, XLIFF or CK3 YML). The app creates a ZIP archive and one `…_PROMPT.txt` file next to it. For a large job enable **Split into parts** and choose “into a number of archives” (lines split evenly, 5 suggested) “by lines per archive” (for example 250; the last archive is smaller) or “by text volume per archive” (for example 20,000 source characters). Text volume is the most accurate option: AI limits count text, and 250 short names differ from 250 long descriptions many times over. A line longer than the limit goes into its own archive. Archive count and sizes are shown before saving; the prompt stays a single file.
3. Send the archive(s) and the prompt text to your chat service and ask for a ZIP with the same files back.
4. Choose **Import translation from file…** and select all returned ZIPs at once (or drop them onto the mod card). Order and archive names do not matter; missing archives can be imported later — the app shows “Archives received: 2 of 5”.
5. Review the preview and choose **Apply selected**.
6. Choose **Write translation to the game** when you are satisfied with the result.

This workflow needs no API key. A chat provider may impose usage limits or charge for access.

## Translate using an API

**No key, no payment:** the "Google Translate · free" translator works right after installation. It uses Google Translate's public web gateway (the one browser extensions use), not paid Google Cloud. Lines are sent one by one with a short pause. If Google temporarily limits frequent requests (HTTP 429), the job pauses and finished lines are kept; resume later from **Action history**. The gateway is unofficial, and Google may change or close it without notice. Game codes are protected with markers, and lines with damaged codes are not saved. These translations count as a Google service and can be removed with **Remove service translations…**.

**With an API key:** select a provider in Settings and save its key. Supported integrations include Google Cloud Translation, DeepL, Yandex, Claude and OpenAI-compatible services. Keys use the operating system's keyring; translation providers have their own pricing and limits. The fields in **Extra settings for LLMs and Yandex** (Claude model, OpenAI-compatible URL and model, Yandex folder ID) apply to every translation.

**DeepSeek, Mistral, OpenRouter, your own or a local AI:** in **Settings → Extra settings for LLMs and Yandex** choose an **OpenAI-compatible API service**: OpenAI, DeepSeek, Mistral, OpenRouter, LM Studio, Ollama, llama.cpp or "Custom address". The choice fills in the URL and a default model. **Load models** asks the service for its model list; the chosen model is put into the field. Save a cloud service key under "LLM (OpenAI-compatible API)", then choose that translator in the translation window. One key is shared by all services of this translator, so replace it when you switch services. A local server (for example `http://127.0.0.1:8888/v1`) needs no key. Requests to `127.0.0.1` and `localhost` always go directly, never through a proxy. Error messages name the address the request went to. If a model returns an empty answer or refuses dark scenes (violence, intimate scenes), those are the model's safety filters: choose a model with milder filters.

**Speed and rate limits:** in the translation window, **Maximum rows per request** sets the batch size, **Parallel requests** (1–8) how many batches are sent at once, and **Pause between requests** the wait between groups of requests. For free plans keep one request and a pause of a few seconds; for a local server or a paid API you can raise the number of requests. **Stop** starts no new requests and keeps finished answers.

**ChatGPT subscription (preview):** choose "ChatGPT · subscription" and click **Sign in with ChatGPT** in the translation window or in Settings. Sign-in opens in your browser; the app never asks for your password. Pick a model from the list OpenAI returns for your account. Translation requires a paid ChatGPT plan: without one, sign-in still works but OpenAI does not allow plan usage. OpenAI currently refuses session renewal for all Sign in with ChatGPT apps, so after about an hour the app asks you to sign in again.

Open a mod, choose **Translate via API…**, review the job and start it. Results are saved as a draft: review them, apply the lines you accept, then write to the game. Source text and relevant context are sent to the selected provider.

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


## Local mods and custom folders (0.2.0)

Open Settings → **CK3 local mods folder**. Choose the `mod` directory containing your mods and launcher `.mod` files, then click **Rescan library**. **Automatic** restores the detected location. Windows uses your actual Documents location, including redirected folders. Steam is optional for local mods.

The library combines Workshop and local mods, marked `[Workshop]` or `[Local]`. Launcher `.mod` links can point to mods outside this directory. Generated translation patches and the Community Database are not treated as source mods. Separate copies keep separate translation histories. Moving a local mod creates a new library identity; the old history remains saved. This does not add automatic playset management.

## Updates and terminology (0.2.0)

The app checks GitHub for stable releases in the background. **Update** opens the release page for manual download; extract the complete archive into a new folder. **Next time** reminds you on the next launch. **Skip this version** hides only that version. Settings → **Check for updates** can show skipped releases too. Your translation data is stored separately from the executable.

Shared terminology is supplied by the optional Community Database subscription on Steam Workshop, not bundled with the application. Select your translation language in Settings to view that pair. Terms are suggestions that need context and grammatical adaptation. Only relevant terms are included in translation prompts, with a size limit. Your edits take priority over community updates. Workshop is optional; its downloaded data is refreshed when you scan.

## New in 0.3.0: drafts, undo and translation origin

**Workflow.** Select lines → review the job → start → review the result → **Apply selected** → **Write translation to the game**. Export, import and translation never change the installed mod on their own.

**Fixing a translation that already shows 100%.** On the **Strings** tab select lines with Ctrl/Shift and choose **Export selected…** or **Translate selected…**. Export scopes include missing only, missing and outdated, outdated only, selected rows and all rows; formats are JSONL, XLIFF and CK3 YML. The export is a ZIP archive plus one prompt file; **Split into parts** divides a large job into a chosen number of ZIPs or by lines per archive and shows their sizes before saving. **Import translation from file…** accepts several ZIPs or files at once or drag-and-drop; order and names do not matter, and missing archives can be imported later. The preview shows source, current and new text: additions are checked, replacements only when you check them.

**Translating in the app.** The dialog shows lines, provider, account/model and request count before anything is sent. "Reuse CK3 vanilla" and "Reuse translation memory" show what will be reused; **Translate again** sends the selected lines to the provider. **Translate 10 sample rows** gives a quick trial. Results go to a draft; **Stop** sends no new requests and keeps finished answers. Quota or charges for requests already sent are not refunded. For a ChatGPT plan choose "ChatGPT · subscription" as the translator and click **Sign in with ChatGPT** right in the window (or in Settings). Sign-in opens in your browser; the app never asks for your password. After signing in, pick a model from the list your account offers. This integration is a preview.

**Action history** on the mod card: continue a stopped job without re-requesting finished lines, **Discard task** to drop unapplied drafts, or **Undo application**. Undo restores text, status and origin; lines you edited later are kept and shown as conflicts. Write to the game again to update game files. Closing a running job offers Continue in background, Stop and save draft, or Go back; after a restart the app reminds you of unfinished jobs.

**Translation origin** is stored separately from review status: LLM, service (Google/DeepL/Yandex), manual, CK3 vanilla, mod author, other mod or unknown. See the column and filter on **Strings**, the breakdown on the mod overview and the library tooltip. "Fully filled" means every line has text, not that it is correct; reviewed lines and unreviewed service translations are counted next to it.

**Remove service translations…** removes only the unreviewed Google, DeepL and Yandex results you select. LLM, manual, reviewed, author and unknown translations are kept. Nothing is selected initially; "Also remove from manager-owned game files" rebuilds only the app's own files, with backups. The removed variant is not reused from memory in that project. Undo it in **Action history**.

**Bulk translation.** "Translate all mods with no translation…" opens immediately and reads your library in the background with a progress bar; it sends and writes nothing by itself. Choose mods (Local/Workshop) and lines, export for an LLM as ZIP archives (one folder per mod, one prompt for the whole job), translate all selected mods in one window with a common **Stop**, import many files or a whole results folder, and **Write selected translations to the game…** with the file list and the option to exclude mods. Mods whose translation is applied but not yet written stay in the list.

**Restore.** If Steam deleted files created by the app, the mod card shows "… saved in the database; translation files are missing" and **Restore translation**. Files are not recreated automatically.

**Community Database.** Settings and Glossary show its state, version, term count and terms for the current language pair. "Refresh from installed database" re-reads data Steam has already downloaded; it does not download anything. Archive-only mods are reported with a notice and do not block scanning.

**Glossary** opens immediately and loads terms in the background. **CK3 mod folders** on the library screen opens a menu with the local mods folder and every Steam Workshop folder found.
