"""Стартовый глобальный глоссарий CK3 (EN → RU).

Соответствия сверены с официальной русской локализацией игры.
Пользователь может редактировать и дополнять глоссарий в приложении.
"""

from __future__ import annotations

SEED_EN_RU: list[tuple[str, str, str]] = [
    # (термин, перевод, режим)
    ("Realm", "Держава", "required"),
    ("Holding", "Владение", "required"),
    ("County", "Графство", "required"),
    ("Duchy", "Герцогство", "required"),
    ("Kingdom", "Королевство", "required"),
    ("Empire", "Империя", "required"),
    ("Barony", "Баронство", "required"),
    ("Ruler", "Правитель", "preferred"),
    ("Liege", "Сюзерен", "required"),
    ("Vassal", "Вассал", "required"),
    ("Courtier", "Придворный", "preferred"),
    ("Council", "Совет", "required"),
    ("Councillor", "Член совета", "preferred"),
    ("Steward", "Управитель", "required"),
    ("Marshal", "Маршал", "required"),
    ("Chancellor", "Канцлер", "required"),
    ("Spymaster", "Тайный советник", "required"),
    ("Court Chaplain", "Придворный священник", "required"),
    ("Court Physician", "Придворный врач", "preferred"),
    ("Regent", "Регент", "required"),
    ("Heir", "Наследник", "required"),
    ("Dynasty", "Династия", "required"),
    ("House", "Дом", "required"),
    ("Cadet Branch", "Побочная ветвь", "preferred"),
    ("Claim", "Претензия", "required"),
    ("Claimant", "Претендент", "required"),
    ("Title", "Титул", "required"),
    ("De Jure", "Де-юре", "required"),
    ("De Facto", "Де-факто", "required"),
    ("Prestige", "Престиж", "required"),
    ("Piety", "Благочестие", "required"),
    ("Gold", "Золото", "required"),
    ("Renown", "Известность", "required"),
    ("Stress", "Стресс", "required"),
    ("Dread", "Ужас", "required"),
    ("Tyranny", "Тирания", "required"),
    ("Opinion", "Отношение", "preferred"),
    ("Scheme", "Интрига", "required"),
    ("Hook", "Рычаг давления", "required"),
    ("Secret", "Тайна", "required"),
    ("Trait", "Черта", "required"),
    ("Lifestyle", "Стиль жизни", "required"),
    ("Perk", "Навык", "preferred"),
    ("Focus", "Фокус", "preferred"),
    ("Casus Belli", "Казус белли", "required"),
    ("Levy", "Ополчение", "required"),
    ("Men-at-Arms", "Латники", "required"),
    ("Knight", "Рыцарь", "required"),
    ("Siege", "Осада", "required"),
    ("Culture", "Культура", "required"),
    ("Faith", "Вера", "required"),
    ("Religion", "Религия", "required"),
    ("Tenet", "Догмат", "required"),
    ("Doctrine", "Доктрина", "required"),
    ("Sin", "Грех", "preferred"),
    ("Virtue", "Добродетель", "preferred"),
    ("Crusade", "Крестовый поход", "required"),
    ("Jihad", "Джихад", "required"),
    ("Feast", "Пир", "required"),
    ("Hunt", "Охота", "required"),
    ("Pilgrimage", "Паломничество", "required"),
    ("Ward", "Воспитанник", "preferred"),
    ("Guardian", "Опекун", "preferred"),
    ("Betrothal", "Помолвка", "required"),
    ("Ruler Designer", "Редактор правителя", "required"),
    ("Game Rule", "Правило игры", "required"),
]


def seed_glossary(conn) -> int:
    """Добавить отсутствующие стартовые EN→RU термины без перезаписи своих."""
    added = 0
    for source, target, mode in SEED_EN_RU:
        exists = conn.execute(
            """SELECT 1 FROM glossary_terms
               WHERE level='global' AND source_lang='english'
                 AND target_lang='russian' AND source_term=? LIMIT 1""",
            (source,),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT INTO glossary_terms
                   (level, source_lang, target_lang, source_term, target_term,
                    mode, origin)
               VALUES ('global', 'english', 'russian', ?, ?, ?, 'builtin')""",
            (source, target, mode),
        )
        added += 1
    conn.commit()
    return added


def load_glossary(
    conn,
    mod_id: str = "",
    source_lang: str = "english",
    target_lang: str = "russian",
) -> list[tuple[str, str]]:
    """Глоссарий для перевода: глобальный + уровня мода (мод переопределяет)."""
    terms: dict[str, str] = {}
    for r in conn.execute(
        "SELECT source_term, target_term FROM glossary_terms "
        "WHERE level='global' AND source_lang=? AND target_lang=? "
        "AND mode != 'forbidden' ORDER BY id",
        (source_lang, target_lang),
    ):
        terms[r["source_term"]] = r["target_term"]
    if mod_id:
        for r in conn.execute(
            "SELECT source_term, target_term FROM glossary_terms "
            "WHERE level='mod' AND mod_id=? AND source_lang=? AND target_lang=? "
            "AND mode != 'forbidden' ORDER BY id",
            (mod_id, source_lang, target_lang),
        ):
            terms[r["source_term"]] = r["target_term"]
    return sorted(terms.items())
