# CK3 Localization Manager

Windows-приложение для поиска, перевода и восстановления локализаций модов Crusader Kings III. Оно сканирует подписки Steam Workshop, сравнивает языки по ключам, защищает игровые коды CK3 и добавляет перевод, не перезаписывая файлы автора.

## Возможности

- GUI на PySide6 и полноценный CLI;
- автоматический поиск Steam и всех библиотек Workshop;
- перевод через Google, Yandex, DeepL, Claude и OpenAI-совместимые API;
- экспорт и импорт заданий JSONL/XLIFF для работы через нейросетевой чат;
- память переводов, редактируемый глоссарий и официальная локализация CK3;
- обнаружение отдельных модов-русификаторов;
- снимки изменений, резервные копии и восстановление после обновлений Steam;
- необязательная CK3Loc Community Database из Steam Workshop.

## Быстрый запуск

Требуется Windows и Python 3.12+.

```bat
install.bat
run.bat
```

Либо из активированного окружения:

```powershell
python -m pip install -r requirements.txt
python -m ck3loc.desktop
```

Подробное пользовательское руководство: [README-запуск.md](README-запуск.md).

## Community Database

Подписная база хранит проверенные связи оригинальных модов с русификаторами, общие глоссарии и безопасные правила обработки отдельных модов. Её не нужно включать в playset. Приложение находит marker `ck3loc-database.json` в `steamapps/workshop/content/1158310/<ID>/`, проверяет схему и применяет только JSON-данные.

Пользовательские термины всегда имеют приоритет. Связь из реестра принимается только тогда, когда оба мода установлены и действительно содержат пересекающиеся localization-ключи.

## Тесты и сборка

```powershell
python -m unittest discover -s tests -v
python tools/validate_community_db.py
build_release.bat
```

Готовый архив появляется в `dist/CK3LocalizationManager-<version>-win64.zip`.

## Данные и безопасность

Переводы, история и резервные копии находятся в `%LOCALAPPDATA%\ck3loc`. API-ключи сохраняются через Windows Credential Manager. Community Database не содержит исполняемого кода, а её JSON-файлы проходят проверку размера, полей и версии схемы.

Инструкция для владельца проекта по первой публикации и последующим обновлениям: [PUBLISHING.md](PUBLISHING.md).
