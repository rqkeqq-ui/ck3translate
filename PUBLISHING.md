# Публикация CK3 Localization Manager

Это руководство описывает полный выпуск приложения через GitHub Releases и companion-предмета CK3Loc Community Database через Steam Workshop. Сначала создайте GitHub-репозиторий, затем получите приватный Workshop ID, после этого зафиксируйте ссылки и выпускайте обе части публично.

## 1. Что именно публикуется

Публикация состоит из двух независимых частей:

1. **GitHub** — исходный код, документация, трекер ошибок и ZIP с готовым Windows-приложением.
2. **Steam Workshop** — только JSON-база из `workshop/ck3loc_community_database/`. Она не содержит `.exe`, ничего не меняет в игре и не включается в playset.

Переводы пользователей остаются локально в `%LOCALAPPDATA%\ck3loc`. В Workshop нельзя загружать их базу SQLite, API-ключи, логи или содержимое чужих модов.

## 2. Подготовка GitHub

Перед открытием репозитория:

- выберите и добавьте `LICENSE`; без лицензии исходный код формально остаётся «all rights reserved»;
- замените пустые значения в `ck3loc/community_db_config.json` после получения ссылок;
- проверьте, что в истории нет ключей API, персональных путей и реальных файлов модов;
- подготовьте 3–5 PNG-скриншотов: библиотека, карточка мода, редактор строк, глоссарий и настройки Community Database;
- при необходимости добавьте контакты поддержки и правила участия.

Проверка перед первым push:

```powershell
git status --short
git grep -n -I -E "(api[_-]?key|secret|password|Bearer )"
python -m unittest discover -s tests -v
python tools/validate_community_db.py
```

Создать репозиторий через GitHub CLI можно так:

```powershell
gh auth login
gh repo create OWNER/CK3-Localization-Manager --public --source . --remote origin --push
```

Если репозиторий создан через сайт:

```powershell
git remote add origin https://github.com/OWNER/CK3-Localization-Manager.git
git push -u origin master
```

Не выполняйте обе команды создания remote. Проверьте результат через `git remote -v`.

## 3. Первая приватная загрузка в Steam Workshop

1. Запустите Paradox Launcher из Steam.
2. Откройте раздел **All installed mods / Mod tools** и выберите **Create Mod**.
3. Название: `CK3Loc Community Database`; каталог: `ck3loc_community_database`; версия: `1.0.0`; тег: `Utilities` или `Translation`.
4. Закройте Launcher и найдите созданный каталог:

   ```text
   %USERPROFILE%\Documents\Paradox Interactive\Crusader Kings III\mod\ck3loc_community_database
   ```

5. Скопируйте туда содержимое `workshop/ck3loc_community_database/`. Не удаляйте внешний `.mod`-файл, созданный Launcher.
6. Добавьте квадратный `thumbnail.png`. Практичный размер — 600×600 или 1024×1024; сохраните PNG меньше 1 МБ и проверьте читаемость при уменьшении.
7. Выполните `python tools/validate_community_db.py <путь-к-каталогу-мода>`.
8. В Launcher выберите **Upload Mod**, площадку Steam и видимость **Private**.
9. Примите Steam Workshop Agreement, если Steam попросит это сделать.

После загрузки откройте приватную страницу. Число в её URL — постоянный Workshop ID:

```text
https://steamcommunity.com/sharedfiles/filedetails/?id=1234567890
                                                       ^^^^^^^^^^
```

## 4. Зафиксировать ID и ссылки

Запишите ID в два файла:

`workshop/ck3loc_community_database/ck3loc-database.json`:

```json
"workshop_id": "1234567890"
```

`ck3loc/community_db_config.json`:

```json
{
  "workshop_id": "1234567890",
  "repository_url": "https://github.com/OWNER/CK3-Localization-Manager"
}
```

В `workshop/WORKSHOP_DESCRIPTION.txt` замените:

- `REPLACE_WITH_GITHUB_URL`;
- `REPLACE_WITH_GITHUB_RELEASE_URL`;
- `REPLACE_WITH_ISSUES_URL`.

Снова скопируйте обновлённую базу в локальный каталог мода, проверьте валидатором и выполните **Upload/Update**. Не создавайте новый Workshop-предмет: обновляйте существующий с тем же `remote_file_id`.

## 5. Оформление страницы Workshop

Используйте текст из `workshop/WORKSHOP_DESCRIPTION.txt`. Первые строки должны однозначно сообщать:

> Это база данных для внешнего инструмента. Не добавляйте её в playset.

На странице обязательно должны быть:

- понятная обложка с надписями `CK3Loc` и `Community Database`;
- ссылка на конкретный GitHub Release, а не на случайный файлообменник;
- четыре шага установки;
- объяснение, какие данные скачивает подписка;
- ссылка на Issues;
- отметка, что проект не связан с Paradox Interactive или Valve;
- разделы Discussions: «Ошибки», «Предложения», «Добавить русификатор в реестр».

Не обещайте, что подписка устанавливает само приложение. Не кладите `.exe` в Workshop и не используйте чужие логотипы или изображения без разрешения.

## 6. Сборка Windows-релиза

Обновите версию в `ck3loc/__init__.py`, например:

```python
__version__ = "0.2.0"
```

Затем:

```bat
install.bat
build_release.bat
```

Скрипт устанавливает PyInstaller, запускает все тесты и валидатор, собирает приложение в режиме `onedir` и создаёт:

```text
dist/CK3LocalizationManager-0.2.0-win64.zip
```

Перед выпуском распакуйте ZIP в новый каталог и проверьте на машине без Python:

1. запуск GUI;
2. поиск Steam-библиотеки;
3. обнаружение Community Database;
4. сканирование модов;
5. экспорт задания;
6. запись тестового перевода и восстановление после удаления созданного файла;
7. отсутствие консольного окна и ошибок Credential Manager.

Посчитайте контрольную сумму:

```powershell
Get-FileHash dist\CK3LocalizationManager-0.2.0-win64.zip -Algorithm SHA256
```

Опубликуйте SHA-256 в описании GitHub Release. Для нового неподписанного `.exe` предупреждения SmartScreen ожидаемы; не советуйте пользователям отключать антивирус. При возможности подпишите приложение сертификатом code signing.

## 7. GitHub Release

Сделайте отдельный коммит выпуска и аннотированный тег:

```powershell
git add .
git commit -m "release: версия 0.2.0"
git push origin master
git tag -a v0.2.0 -m "CK3 Localization Manager 0.2.0"
git push origin v0.2.0
gh release create v0.2.0 `
  "dist/CK3LocalizationManager-0.2.0-win64.zip" `
  --title "CK3 Localization Manager 0.2.0" `
  --generate-notes
```

В описание релиза добавьте требования Windows, SHA-256, список изменений, известные ограничения и ссылку на Workshop Database.

## 8. Сделать Workshop публичным

Только после появления рабочего GitHub Release:

1. установите подписку на приватный предмет своим аккаунтом;
2. дождитесь загрузки в `steamapps/workshop/content/1158310/<ID>/`;
3. запустите приложение и убедитесь, что в Настройках показаны версия базы, число терминов и связей;
4. убедитесь, что предмет не отображается среди переводимых модов;
5. проверьте все ссылки и изображения;
6. смените видимость Workshop с **Private** на **Public**.

## 9. Обновление Community Database

Для обычного обновления данных:

1. редактируйте только JSON в staging-каталоге репозитория;
2. повышайте `database_version`, используя дату `YYYY.MM.DD`;
3. не меняйте `schema_version`, пока старое приложение может прочитать формат;
4. запустите валидатор и тесты;
5. обновите существующий Workshop-предмет;
6. заполните вкладку **Change Notes**.

Формат связи русификатора:

```json
{
  "source_mod_id": "1111111111",
  "provider_mod_id": "2222222222",
  "source_lang": "english",
  "target_lang": "russian"
}
```

Приложение не доверяет записи вслепую: оба предмета должны быть установлены, а их ключи должны реально пересекаться.

Формат правила:

```json
"1111111111": {
  "source_language": "english",
  "exclude_globs": ["localization/english/debug/**"],
  "protected_key_prefixes": ["DEBUG_", "DEV_"]
}
```

Пути задаются относительно корня мода, с `/`. Добавляйте правило только после воспроизводимого теста на конкретном Workshop ID.

## 10. Контрольный список выпуска

- [ ] Выбрана лицензия и проверена история Git.
- [ ] Нет API-ключей, персональных путей и чужих файлов.
- [ ] Версии приложения и базы обновлены.
- [ ] Workshop ID и GitHub URL записаны в config/marker.
- [ ] Все тесты и валидатор проходят.
- [ ] ZIP проверен после чистой распаковки.
- [ ] SHA-256 опубликован.
- [ ] GitHub Release доступен без авторизации.
- [ ] Workshop-ссылки и изображения работают.
- [ ] База обнаруживается приложением и не попадает в список модов.
- [ ] Workshop-предмет опубликован как обновление существующего ID.
