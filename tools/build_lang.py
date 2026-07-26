"""Сборка словарей интерфейса ck3loc/lang/*.json из общей таблицы.

Ключ — русский текст (он же исходный в коде). Порядок языков в кортеже:
en, es, fr, de, zh, ko.
"""

from __future__ import annotations

import json
from pathlib import Path

LANGS = ("en", "es", "fr", "de", "zh", "ko")

T: dict[str, tuple[str, str, str, str, str, str]] = {
    # --- навигация и общее ---
    "Библиотека": ("Library", "Biblioteca", "Bibliothèque", "Bibliothek", "模组库", "라이브러리"),
    "Глоссарий": ("Glossary", "Glosario", "Glossaire", "Glossar", "术语表", "용어집"),
    "Настройки": ("Settings", "Ajustes", "Paramètres", "Einstellungen", "设置", "설정"),
    "менеджер переводов модов": ("mod translation manager", "gestor de traducciones de mods", "gestionnaire de traductions de mods", "Mod-Übersetzungsmanager", "模组翻译管理器", "모드 번역 관리자"),
    "Библиотека модов": ("Mod library", "Biblioteca de mods", "Bibliothèque de mods", "Mod-Bibliothek", "模组库", "모드 라이브러리"),
    "Глоссарий терминов": ("Glossary of terms", "Glosario de términos", "Glossaire des termes", "Begriffsglossar", "术语表", "용어집"),
    "Уведомления": ("Notifications", "Notificaciones", "Notifications", "Benachrichtigungen", "通知", "알림"),
    "Готово": ("Done", "Listo", "Terminé", "Fertig", "完成", "완료"),
    "Отмена": ("Cancel", "Cancelar", "Annuler", "Abbrechen", "取消", "취소"),
    "Закрыть": ("Close", "Cerrar", "Fermer", "Schließen", "关闭", "닫기"),
    "Продолжить": ("Continue", "Continuar", "Continuer", "Weiter", "继续", "계속"),
    "Сохранить": ("Save", "Guardar", "Enregistrer", "Speichern", "保存", "저장"),
    "Удалить": ("Delete", "Eliminar", "Supprimer", "Löschen", "删除", "삭제"),
    "Добавить": ("Add", "Añadir", "Ajouter", "Hinzufügen", "添加", "추가"),
    "Запустить": ("Start", "Iniciar", "Démarrer", "Starten", "开始", "시작"),
    "Остановить": ("Stop", "Detener", "Arrêter", "Stoppen", "停止", "중지"),
    "Выбрать…": ("Browse…", "Elegir…", "Choisir…", "Auswählen…", "选择…", "선택…"),

    # --- плитки библиотеки ---
    "Всего модов": ("Mods total", "Mods en total", "Mods au total", "Mods insgesamt", "模组总数", "전체 모드"),
    "Без перевода": ("Untranslated", "Sin traducción", "Non traduits", "Ohne Übersetzung", "未翻译", "번역 없음"),
    "Неполный": ("Partial", "Parcial", "Partielle", "Unvollständig", "不完整", "부분 번역"),
    "Чужой перевод": ("External", "Traducción externa", "Traduction externe", "Fremdübersetzung", "外部翻译", "외부 번역"),
    "Ошибки": ("Errors", "Errores", "Erreurs", "Fehler", "错误", "오류"),
    "Переведено": ("Translated", "Traducido", "Traduit", "Übersetzt", "已翻译", "번역됨"),

    # --- источники перевода (полоска) ---
    "перевод автора мода": ("mod author's translation", "traducción del autor", "traduction de l'auteur", "Übersetzung des Autors", "作者的翻译", "제작자 번역"),
    "мод-русификатор": ("translation mod", "mod de traducción", "mod de traduction", "Übersetzungsmod", "翻译模组", "번역 모드"),
    "ваш перевод": ("your translation", "tu traducción", "votre traduction", "Ihre Übersetzung", "你的翻译", "내 번역"),
    "устарело": ("outdated", "desactualizado", "obsolète", "veraltet", "已过时", "오래됨"),
    "не хватает": ("missing", "faltan", "manquantes", "fehlen", "缺少", "누락"),

    # --- панель библиотеки ---
    "Сканировать библиотеку": ("Scan library", "Escanear biblioteca", "Analyser la bibliothèque", "Bibliothek scannen", "扫描模组库", "라이브러리 검사"),
    "Сканирование…": ("Scanning…", "Escaneando…", "Analyse…", "Wird gescannt…", "扫描中…", "검사 중…"),
    "Перевести все моды, где перевода нет…": ("Translate all mods with no translation…", "Traducir todos los mods sin traducción…", "Traduire tous les mods sans traduction…", "Alle Mods ohne Übersetzung übersetzen…", "翻译所有没有翻译的模组…", "번역이 없는 모든 모드 번역…"),
    "Перевести все моды, где перевода нет": ("Translate all mods with no translation", "Traducir todos los mods sin traducción", "Traduire tous les mods sans traduction", "Alle Mods ohne Übersetzung übersetzen", "翻译所有没有翻译的模组", "번역이 없는 모든 모드 번역"),
    "Папка модов CK3": ("CK3 mods folder", "Carpeta de mods de CK3", "Dossier des mods CK3", "CK3-Mod-Ordner", "CK3 模组文件夹", "CK3 모드 폴더"),
    "Поиск по названию или ID мода…   (Ctrl+F)": ("Search by name or mod ID…   (Ctrl+F)", "Buscar por nombre o ID…   (Ctrl+F)", "Rechercher par nom ou ID…   (Ctrl+F)", "Nach Name oder ID suchen…   (Ctrl+F)", "按名称或 ID 搜索…（Ctrl+F）", "이름 또는 ID로 검색…   (Ctrl+F)"),

    # --- фильтры ---
    "Все моды": ("All mods", "Todos los mods", "Tous les mods", "Alle Mods", "全部模组", "모든 모드"),
    "Перевод неполный": ("Partially translated", "Traducción parcial", "Traduction partielle", "Teilweise übersetzt", "部分翻译", "부분 번역됨"),
    "Перевод полный": ("Fully translated", "Traducción completa", "Traduction complète", "Vollständig übersetzt", "完全翻译", "완전 번역됨"),
    "Переведён другим модом": ("Translated by another mod", "Traducido por otro mod", "Traduit par un autre mod", "Von anderem Mod übersetzt", "由其他模组翻译", "다른 모드가 번역"),
    "Моды-русификаторы": ("Translation mods", "Mods de traducción", "Mods de traduction", "Übersetzungsmods", "翻译模组", "번역 모드"),
    "Мои проекты": ("My projects", "Mis proyectos", "Mes projets", "Meine Projekte", "我的项目", "내 프로젝트"),
    "С ошибками": ("With errors", "Con errores", "Avec erreurs", "Mit Fehlern", "有错误", "오류 있음"),
    "Без локализации": ("No localization", "Sin localización", "Sans localisation", "Ohne Lokalisierung", "无本地化", "현지화 없음"),

    # --- столбцы таблиц ---
    "Мод": ("Mod", "Mod", "Mod", "Mod", "模组", "모드"),
    "Языки": ("Languages", "Idiomas", "Langues", "Sprachen", "语言", "언어"),
    "Перевод": ("Translation", "Traducción", "Traduction", "Übersetzung", "翻译", "번역"),
    "Состояние": ("State", "Estado", "État", "Status", "状态", "상태"),
    "Обновлён": ("Updated", "Actualizado", "Mis à jour", "Aktualisiert", "更新时间", "업데이트"),
    "Статус": ("Status", "Estado", "Statut", "Status", "状态", "상태"),
    "Ключ": ("Key", "Clave", "Clé", "Schlüssel", "键", "키"),
    "Источник": ("Source", "Origen", "Source", "Quelle", "原文", "원문"),
    "Уровень": ("Level", "Nivel", "Niveau", "Ebene", "级别", "수준"),
    "Файл": ("File", "Archivo", "Fichier", "Datei", "文件", "파일"),
    "Строка": ("Line", "Línea", "Ligne", "Zeile", "行", "줄"),
    "Проблема": ("Issue", "Problema", "Problème", "Problem", "问题", "문제"),
    "Термин": ("Term", "Término", "Terme", "Begriff", "术语", "용어"),
    "Режим": ("Mode", "Modo", "Mode", "Modus", "模式", "모드"),

    # --- пустые состояния ---
    "Библиотека ещё не просканирована": ("The library has not been scanned yet", "La biblioteca aún no ha sido escaneada", "La bibliothèque n'a pas encore été analysée", "Die Bibliothek wurde noch nicht gescannt", "尚未扫描模组库", "라이브러리를 아직 검사하지 않았습니다"),
    "Ничего не найдено": ("Nothing found", "No se encontró nada", "Aucun résultat", "Nichts gefunden", "未找到内容", "찾은 항목 없음"),
    "Идёт сканирование…": ("Scanning…", "Escaneando…", "Analyse en cours…", "Scan läuft…", "正在扫描…", "검사 중…"),
    "Проблем не найдено": ("No issues found", "No se encontraron problemas", "Aucun problème détecté", "Keine Probleme gefunden", "未发现问题", "문제가 없습니다"),
    "Двойной клик по строке — открыть карточку мода": ("Double-click a row to open the mod card", "Doble clic en una fila para abrir el mod", "Double-cliquez sur une ligne pour ouvrir le mod", "Doppelklick auf eine Zeile öffnet den Mod", "双击行可打开模组卡片", "행을 두 번 클릭하면 모드 카드가 열립니다"),

    # --- карточка мода ---
    "← К библиотеке": ("← Back to library", "← A la biblioteca", "← Retour à la bibliothèque", "← Zur Bibliothek", "← 返回模组库", "← 라이브러리로"),
    "Папка мода": ("Mod folder", "Carpeta del mod", "Dossier du mod", "Mod-Ordner", "模组文件夹", "모드 폴더"),
    "Страница в Workshop": ("Workshop page", "Página en Workshop", "Page Workshop", "Workshop-Seite", "创意工坊页面", "창작마당 페이지"),
    "Обзор": ("Overview", "Resumen", "Aperçu", "Übersicht", "概览", "개요"),
    "Строки": ("Strings", "Cadenas", "Chaînes", "Zeilen", "字符串", "문자열"),
    "Изменения": ("Changes", "Cambios", "Modifications", "Änderungen", "变更", "변경"),
    "Диагностика": ("Diagnostics", "Diagnóstico", "Diagnostic", "Diagnose", "诊断", "진단"),
    "покрытие перевода": ("translation coverage", "cobertura de la traducción", "couverture de traduction", "Übersetzungsabdeckung", "翻译覆盖率", "번역 적용률"),
    "Запись в игру": ("Writing to the game", "Escritura en el juego", "Écriture dans le jeu", "Ins Spiel schreiben", "写入游戏", "게임에 기록"),
    "Журнал действий": ("Activity log", "Registro de acciones", "Journal des actions", "Aktionsprotokoll", "操作日志", "작업 기록"),
    "Перевести через API…": ("Translate via API…", "Traducir con API…", "Traduire via l'API…", "Über API übersetzen…", "通过 API 翻译…", "API로 번역…"),
    "Выгрузить задание для нейросети…": ("Export a job for an AI…", "Exportar tarea para una IA…", "Exporter une tâche pour une IA…", "Auftrag für eine KI exportieren…", "导出交给 AI 的任务…", "AI용 작업 내보내기…"),
    "Загрузить перевод из файла…": ("Import translation from file…", "Importar traducción desde archivo…", "Importer la traduction d'un fichier…", "Übersetzung aus Datei laden…", "从文件导入翻译…", "파일에서 번역 가져오기…"),
    "Записать перевод в игру": ("Write translation to the game", "Escribir la traducción en el juego", "Écrire la traduction dans le jeu", "Übersetzung ins Spiel schreiben", "将翻译写入游戏", "게임에 번역 기록"),
    "Проверить и восстановить": ("Check and restore", "Comprobar y restaurar", "Vérifier et restaurer", "Prüfen und wiederherstellen", "检查并恢复", "확인 및 복구"),
    "Куда писать:": ("Write to:", "Escribir en:", "Écrire dans :", "Schreiben nach:", "写入位置：", "기록 위치:"),
    "Внутрь мода": ("Inside the mod", "Dentro del mod", "Dans le mod", "In den Mod", "写入模组内", "모드 내부"),
    "Отдельный патч-мод": ("Separate patch mod", "Mod-parche separado", "Mod correctif séparé", "Separater Patch-Mod", "独立补丁模组", "별도 패치 모드"),
    "Перевод обеспечивает мод:": ("Translation provided by mod:", "Traducción proporcionada por el mod:", "Traduction fournie par le mod :", "Übersetzung stammt aus Mod:", "翻译来自模组：", "번역 제공 모드:"),
    "не учитывать чужой перевод": ("ignore the external translation", "ignorar la traducción externa", "ignorer la traduction externe", "Fremdübersetzung ignorieren", "忽略外部翻译", "외부 번역 무시"),

    # --- строки и редактор ---
    "Все строки": ("All strings", "Todas las cadenas", "Toutes les chaînes", "Alle Zeilen", "全部字符串", "모든 문자열"),
    "Не переведено": ("Untranslated", "Sin traducir", "Non traduit", "Nicht übersetzt", "未翻译", "번역 안 됨"),
    "Устарело": ("Outdated", "Desactualizado", "Obsolète", "Veraltet", "已过时", "오래됨"),
    "Машинный перевод": ("Machine translation", "Traducción automática", "Traduction automatique", "Maschinelle Übersetzung", "机器翻译", "기계 번역"),
    "Машинный": ("Machine", "Automática", "Automatique", "Maschinell", "机器", "기계"),
    "Проверено": ("Reviewed", "Revisado", "Vérifié", "Geprüft", "已校对", "검토됨"),
    "Утверждено": ("Approved", "Aprobado", "Approuvé", "Bestätigt", "已确认", "승인됨"),
    "Конфликт": ("Conflict", "Conflicto", "Conflit", "Konflikt", "冲突", "충돌"),
    "Осиротело": ("Orphaned", "Huérfano", "Orpheline", "Verwaist", "已孤立", "고아 항목"),
    "Родной перевод": ("Mod's own translation", "Traducción propia del mod", "Traduction propre du mod", "Eigene Übersetzung des Mods", "模组自带翻译", "모드 자체 번역"),
    "Переведено другим модом": ("Translated by another mod", "Traducido por otro mod", "Traduit par un autre mod", "Von anderem Mod übersetzt", "由其他模组翻译", "다른 모드가 번역"),
    "Правлено извне": ("Edited outside", "Editado por fuera", "Modifié à l'extérieur", "Extern bearbeitet", "外部已修改", "외부에서 수정됨"),
    "Конфликты и правки извне": ("Conflicts and outside edits", "Conflictos y ediciones externas", "Conflits et modifications externes", "Konflikte und externe Änderungen", "冲突与外部修改", "충돌 및 외부 수정"),
    "Родной перевод мода": ("Mod's own translation", "Traducción propia del mod", "Traduction propre du mod", "Eigene Übersetzung des Mods", "模组自带翻译", "모드 자체 번역"),
    "Осиротевшие / только в цели": ("Orphaned / target only", "Huérfanos / solo en destino", "Orphelines / cible seulement", "Verwaist / nur Zielsprache", "孤立 / 仅目标语言", "고아 / 대상 언어만"),
    "Поиск по ключу или тексту…": ("Search by key or text…", "Buscar por clave o texto…", "Rechercher par clé ou texte…", "Nach Schlüssel oder Text suchen…", "按键名或文本搜索…", "키 또는 텍스트로 검색…"),
    "Выберите строку в таблице": ("Select a row in the table", "Seleccione una fila en la tabla", "Sélectionnez une ligne du tableau", "Wählen Sie eine Zeile in der Tabelle", "请在表中选择一行", "표에서 행을 선택하세요"),
    "Источник при переводе": ("Source when translated", "Origen al traducir", "Source lors de la traduction", "Quelle beim Übersetzen", "翻译时的原文", "번역 당시 원문"),
    "Источник сейчас": ("Source now", "Origen actual", "Source actuelle", "Quelle jetzt", "当前原文", "현재 원문"),
    "Ваш перевод": ("Your translation", "Tu traducción", "Votre traduction", "Ihre Übersetzung", "你的翻译", "내 번역"),
    "Введите перевод…": ("Enter the translation…", "Escribe la traducción…", "Saisissez la traduction…", "Übersetzung eingeben…", "输入翻译…", "번역을 입력하세요…"),
    "Вставить оригинал": ("Insert original", "Insertar original", "Insérer l'original", "Original einfügen", "插入原文", "원문 삽입"),
    "Сохранить и следующая": ("Save and next", "Guardar y siguiente", "Enregistrer et suivant", "Speichern und weiter", "保存并下一条", "저장 후 다음"),
    "перевод пуст": ("translation is empty", "la traducción está vacía", "la traduction est vide", "Übersetzung ist leer", "翻译为空", "번역이 비어 있습니다"),
    "Игровые коды в порядке": ("Game codes are intact", "Los códigos del juego están intactos", "Les codes du jeu sont intacts", "Spielcodes sind in Ordnung", "游戏代码完好", "게임 코드 정상"),

    # --- выгрузка ---
    "Выгрузка задания для перевода": ("Export a translation job", "Exportar tarea de traducción", "Exporter une tâche de traduction", "Übersetzungsauftrag exportieren", "导出翻译任务", "번역 작업 내보내기"),
    "Что выгрузить": ("What to export", "Qué exportar", "Que faut-il exporter", "Was exportieren", "导出内容", "무엇을 내보낼까요"),
    "Только недостающие": ("Missing only", "Solo las que faltan", "Uniquement les manquantes", "Nur fehlende", "仅缺失部分", "누락된 것만"),
    "Недостающие и устаревшие": ("Missing and outdated", "Faltantes y desactualizadas", "Manquantes et obsolètes", "Fehlende und veraltete", "缺失与过时", "누락 및 오래된 항목"),
    "Только устаревшие": ("Outdated only", "Solo las desactualizadas", "Uniquement les obsolètes", "Nur veraltete", "仅过时部分", "오래된 것만"),
    "Всё, включая перевод автора мода": ("Everything, including the author's translation", "Todo, incluida la traducción del autor", "Tout, y compris la traduction de l'auteur", "Alles, auch die Übersetzung des Autors", "全部，包括作者的翻译", "제작자 번역까지 전부"),
    "Формат файла:": ("File format:", "Formato del archivo:", "Format du fichier :", "Dateiformat:", "文件格式：", "파일 형식:"),
    "Выгрузить…": ("Export…", "Exportar…", "Exporter…", "Exportieren…", "导出…", "내보내기…"),

    # --- перевод через API ---
    "Перевод через API": ("Translation via API", "Traducción con API", "Traduction via l'API", "Übersetzung über API", "通过 API 翻译", "API 번역"),
    "Смета до запуска": ("Estimate before running", "Presupuesto antes de empezar", "Estimation avant lancement", "Schätzung vor dem Start", "运行前预估", "실행 전 예상"),
    "Переводчик:": ("Translator:", "Traductor:", "Traducteur :", "Übersetzer:", "翻译器：", "번역기:"),
    "Перевести": ("Translate", "Traducir", "Traduire", "Übersetzen", "翻译", "번역"),
    "Перевести все моды без перевода": ("Translate all untranslated mods", "Traducir todos los mods sin traducción", "Traduire tous les mods non traduits", "Alle unübersetzten Mods übersetzen", "翻译所有未翻译的模组", "번역 없는 모드 전체 번역"),
    "Что произойдёт": ("What will happen", "Qué va a pasar", "Ce qui va se passer", "Was passieren wird", "将会发生什么", "무엇이 실행되나요"),
    "Нет ключа": ("No key", "Sin clave", "Pas de clé", "Kein Schlüssel", "缺少密钥", "키 없음"),

    # --- глоссарий ---
    "Загрузить стартовый словарь CK3": ("Load the starter CK3 glossary", "Cargar el glosario inicial de CK3", "Charger le glossaire CK3 de base", "CK3-Startglossar laden", "加载 CK3 初始术语表", "CK3 기본 용어집 불러오기"),
    "Удалить выбранное": ("Delete selected", "Eliminar lo seleccionado", "Supprimer la sélection", "Auswahl löschen", "删除所选", "선택 항목 삭제"),
    "Поиск по глоссарию…": ("Search the glossary…", "Buscar en el glosario…", "Rechercher dans le glossaire…", "Glossar durchsuchen…", "搜索术语表…", "용어집 검색…"),
    "обязательный": ("required", "obligatorio", "obligatoire", "verbindlich", "必须", "필수"),
    "предпочтительный": ("preferred", "preferido", "préféré", "bevorzugt", "优先", "권장"),
    "не переводить": ("do not translate", "no traducir", "ne pas traduire", "nicht übersetzen", "不翻译", "번역 안 함"),
    "глобальный": ("global", "global", "global", "global", "全局", "전역"),

    # --- настройки ---
    "Языки и запись перевода": ("Languages and writing", "Idiomas y escritura", "Langues et écriture", "Sprachen und Schreiben", "语言与写入", "언어 및 기록"),
    "Исходный язык": ("Source language", "Idioma de origen", "Langue source", "Ausgangssprache", "源语言", "원본 언어"),
    "Целевой язык": ("Target language", "Idioma de destino", "Langue cible", "Zielsprache", "目标语言", "대상 언어"),
    "Куда писать по умолчанию": ("Default write mode", "Destino por defecto", "Destination par défaut", "Standard-Schreibziel", "默认写入位置", "기본 기록 위치"),
    "Внутрь мода (рекомендуется)": ("Inside the mod (recommended)", "Dentro del mod (recomendado)", "Dans le mod (recommandé)", "In den Mod (empfohlen)", "写入模组内（推荐）", "모드 내부(권장)"),
    "Моды-русификаторы (обнаружение)": ("Translation mods (detection)", "Mods de traducción (detección)", "Mods de traduction (détection)", "Übersetzungsmods (Erkennung)", "翻译模组（检测）", "번역 모드(감지)"),
    "Учитывать моды-русификаторы": ("Take translation mods into account", "Tener en cuenta los mods de traducción", "Prendre en compte les mods de traduction", "Übersetzungsmods berücksichtigen", "考虑翻译模组", "번역 모드 반영"),
    "Порог: доля ключей": ("Threshold: share of keys", "Umbral: proporción de claves", "Seuil : part des clés", "Schwelle: Anteil der Schlüssel", "阈值：键占比", "임계값: 키 비율"),
    "Порог: минимум строк": ("Threshold: minimum strings", "Umbral: mínimo de cadenas", "Seuil : minimum de chaînes", "Schwelle: Mindestanzahl Zeilen", "阈值：最少字符串数", "임계값: 최소 문자열"),
    "Ключи API переводчиков": ("Translator API keys", "Claves API de traductores", "Clés API des traducteurs", "API-Schlüssel der Übersetzer", "翻译服务 API 密钥", "번역기 API 키"),
    "ключ сохранён": ("key saved", "clave guardada", "clé enregistrée", "Schlüssel gespeichert", "已保存密钥", "키 저장됨"),
    "ключа нет": ("no key", "sin clave", "pas de clé", "kein Schlüssel", "无密钥", "키 없음"),
    "Дополнительно для LLM и Яндекса": ("Extra settings for LLMs and Yandex", "Ajustes adicionales para LLM y Yandex", "Réglages supplémentaires pour LLM et Yandex", "Zusatzeinstellungen für LLMs und Yandex", "LLM 与 Yandex 的附加设置", "LLM 및 Yandex 추가 설정"),
    "Модель Claude": ("Claude model", "Modelo de Claude", "Modèle Claude", "Claude-Modell", "Claude 模型", "Claude 모델"),
    "Пути и данные": ("Paths and data", "Rutas y datos", "Chemins et données", "Pfade und Daten", "路径与数据", "경로 및 데이터"),
    "Папка Steam": ("Steam folder", "Carpeta de Steam", "Dossier Steam", "Steam-Ordner", "Steam 文件夹", "Steam 폴더"),
    "Установленная CK3": ("Installed CK3", "CK3 instalado", "CK3 installé", "Installiertes CK3", "已安装的 CK3", "설치된 CK3"),
    "База приложения": ("Application database", "Base de datos de la app", "Base de l'application", "Datenbank der Anwendung", "应用数据库", "앱 데이터베이스"),
    "Открыть папку": ("Open folder", "Abrir carpeta", "Ouvrir le dossier", "Ordner öffnen", "打开文件夹", "폴더 열기"),
    "Открыть резервные копии": ("Open backups", "Abrir copias de seguridad", "Ouvrir les sauvegardes", "Sicherungen öffnen", "打开备份", "백업 열기"),
    "Интерфейс": ("Interface", "Interfaz", "Interface", "Oberfläche", "界面", "인터페이스"),
    "Язык программы": ("Application language", "Idioma de la aplicación", "Langue de l'application", "Sprache der Anwendung", "程序语言", "프로그램 언어"),
    "Оформление": ("Appearance", "Apariencia", "Apparence", "Erscheinungsbild", "外观", "테마"),
    "Тёмная": ("Dark", "Oscura", "Sombre", "Dunkel", "深色", "다크"),
    "Светлая": ("Light", "Clara", "Claire", "Hell", "浅色", "라이트"),
    "Сканировать библиотеку при запуске": ("Scan the library on startup", "Escanear la biblioteca al iniciar", "Analyser la bibliothèque au démarrage", "Bibliothek beim Start scannen", "启动时扫描模组库", "시작 시 라이브러리 검사"),
    "Загружать обложки модов из мастерской": ("Download mod covers from the Workshop", "Descargar portadas de mods del Workshop", "Télécharger les vignettes depuis le Workshop", "Mod-Titelbilder aus dem Workshop laden", "从创意工坊下载模组封面", "창작마당에서 모드 표지 내려받기"),
    "Показывать обложки в списке модов": ("Show covers in the mod list", "Mostrar portadas en la lista de mods", "Afficher les vignettes dans la liste", "Titelbilder in der Mod-Liste zeigen", "在模组列表中显示封面", "모드 목록에 표지 표시"),

    # --- первый запуск ---
    "Выберите языки": ("Choose your languages", "Elige los idiomas", "Choisissez les langues", "Sprachen auswählen", "选择语言", "언어 선택"),
    "Язык перевода модов": ("Language to translate mods into", "Idioma al que traducir los mods", "Langue de traduction des mods", "Zielsprache für Mods", "模组翻译目标语言", "모드 번역 대상 언어"),
    "Слева — язык программы, справа — язык, на который будете переводить моды. Целевой язык повторяет выбор слева, но его можно задать отдельно.": (
        "On the left is the language of the application, on the right is the language you will translate mods into. The target language follows your choice on the left, but you can set it separately.",
        "A la izquierda está el idioma de la aplicación; a la derecha, el idioma al que traducirás los mods. El idioma de destino sigue tu elección de la izquierda, pero puedes cambiarlo aparte.",
        "À gauche, la langue de l'application ; à droite, la langue de traduction des mods. La langue cible suit votre choix de gauche, mais vous pouvez la définir séparément.",
        "Links die Sprache der Anwendung, rechts die Sprache, in die Sie Mods übersetzen. Die Zielsprache folgt der linken Auswahl, lässt sich aber separat festlegen.",
        "左侧是程序语言，右侧是你要把模组翻译成的语言。目标语言会跟随左侧选择，也可以单独设置。",
        "왼쪽은 프로그램 언어, 오른쪽은 모드를 번역할 언어입니다. 대상 언어는 왼쪽 선택을 따르지만 따로 지정할 수도 있습니다."),
    "Переводить моды будем на язык:": ("Mods will be translated into:", "Los mods se traducirán a:", "Les mods seront traduits en :", "Mods werden übersetzt nach:", "模组将被翻译为：", "모드를 번역할 언어:"),

    # --- динамические строки (подстановка через tr_format) ---
    "Файлы автора мода не изменяются — приложение только добавляет перевод, и всё записанное можно восстановить из базы.": (
        "The mod author's files are never changed — the application only adds a translation, and everything written can be restored from the database.",
        "Los archivos del autor del mod no se modifican: la aplicación solo añade la traducción, y todo lo escrito puede restaurarse desde la base de datos.",
        "Les fichiers de l'auteur du mod ne sont jamais modifiés : l'application ajoute seulement la traduction, et tout ce qui est écrit peut être restauré depuis la base.",
        "Die Dateien des Mod-Autors werden nie verändert — die Anwendung fügt nur die Übersetzung hinzu, und alles Geschriebene lässt sich aus der Datenbank wiederherstellen.",
        "模组作者的文件不会被修改——程序只添加翻译，写入的内容都可从数据库恢复。",
        "모드 제작자의 파일은 변경되지 않습니다. 프로그램은 번역만 추가하며, 기록된 내용은 데이터베이스에서 복구할 수 있습니다."),
    "нет перевода": ("no translation", "sin traducción", "pas de traduction", "keine Übersetzung", "无翻译", "번역 없음"),
    "полный": ("complete", "completa", "complète", "vollständig", "完整", "완료"),
    "нет локализации": ("no localization", "sin localización", "pas de localisation", "keine Lokalisierung", "无本地化", "현지화 없음"),
    "{n} пропущено": ("{n} missing", "faltan {n}", "{n} manquantes", "{n} fehlen", "缺少 {n} 条", "{n}개 누락"),
    "нет языка {lang}": ("no {lang} language", "sin idioma {lang}", "langue {lang} absente", "Sprache {lang} fehlt", "缺少 {lang} 语言", "{lang} 언어 없음"),
    "переведён другим модом": ("translated by another mod", "traducido por otro mod", "traduit par un autre mod", "von anderem Mod übersetzt", "由其他模组翻译", "다른 모드가 번역함"),
    "чужой перевод, {n} пропущено": ("external translation, {n} missing", "traducción externa, faltan {n}", "traduction externe, {n} manquantes", "Fremdübersetzung, {n} fehlen", "外部翻译，缺少 {n} 条", "외부 번역, {n}개 누락"),
    "русификатор для «{name}»": ("translation mod for “{name}”", "mod de traducción para «{name}»", "mod de traduction pour « {name} »", "Übersetzungsmod für „{name}“", "「{name}」的翻译模组", "“{name}” 번역 모드"),
    "русификатор для {n} модов": ("translation mod for {n} mods", "mod de traducción para {n} mods", "mod de traduction pour {n} mods", "Übersetzungsmod für {n} Mods", "{n} 个模组的翻译模组", "모드 {n}개의 번역 모드"),
    "{n} русификаторов": ("{n} translation mods", "{n} mods de traducción", "{n} mods de traduction", "{n} Übersetzungsmods", "{n} 个翻译模组", "번역 모드 {n}개"),
    "{n} без локализации": ("{n} without localization", "{n} sin localización", "{n} sans localisation", "{n} ohne Lokalisierung", "{n} 个无本地化", "현지화 없음 {n}개"),
    "Показано {shown} из {total} · двойной клик по строке — открыть карточку мода": (
        "Showing {shown} of {total} · double-click a row to open the mod card",
        "Mostrando {shown} de {total} · doble clic en una fila para abrir el mod",
        "Affichage de {shown} sur {total} · double-cliquez pour ouvrir le mod",
        "{shown} von {total} · Doppelklick auf eine Zeile öffnet den Mod",
        "显示 {shown} / {total} · 双击行可打开模组卡片",
        "{total}개 중 {shown}개 표시 · 행을 두 번 클릭하면 모드 카드가 열립니다"),
    "показано {shown} из {total}": ("showing {shown} of {total}", "mostrando {shown} de {total}", "{shown} sur {total}", "{shown} von {total}", "显示 {shown} / {total}", "{total}개 중 {shown}개"),
    "(можно изменить позже в настройках)": ("(you can change this later in Settings)", "(puedes cambiarlo luego en Ajustes)", "(modifiable plus tard dans les paramètres)", "(später in den Einstellungen änderbar)", "（稍后可在设置中更改）", "(나중에 설정에서 변경 가능)"),
}


def main() -> int:
    out_dir = Path(__file__).resolve().parent.parent / "ck3loc" / "lang"
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, code in enumerate(LANGS):
        data = {src: values[i] for src, values in T.items()}
        path = out_dir / f"{code}.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8",
        )
        print(f"{path.name}: {len(data)} строк")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
