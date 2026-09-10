# Разработка

Python 3.12+, зависимости из requirements.txt. На Windows доступны install.bat и run.bat.

```sh
python -m pip install -r requirements.txt -r requirements-build.txt
python -m ck3loc.desktop
python -m unittest discover -s tests -v
python tools/validate_community_db.py
python tools/build_release.py
```

Сборка выполняется на целевой ОС. Архив и SHA-256 появляются в dist/. На macOS используется ditto, чтобы сохранить структуру .app. Windows: build_release.bat вызывает тот же сборщик.

```sh
python tools/capture_gallery.py
```

Галерея создаётся из настоящих Qt-виджетов с временной базой и синтетическими данными. Личные данные и Steam-библиотека не нужны.

Локальные задания агентам, спецификации и вспомогательные лаунчеры исключены из Git. Тесты и синтетические fixtures являются частью проекта.
