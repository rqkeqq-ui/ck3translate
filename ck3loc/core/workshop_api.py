"""Открытый Steam Workshop API: названия и время обновления по ID.

Работает best-effort: без интернета приложение полностью функционально,
просто без воркшопных названий. Ключ API не требуется.
"""

from __future__ import annotations

from dataclasses import dataclass

_API_URL = (
    "https://api.steampowered.com/ISteamRemoteStorage/"
    "GetPublishedFileDetails/v1/"
)


WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={id}"


@dataclass
class WorkshopDetails:
    item_id: str
    title: str = ""
    time_updated: int = 0
    preview_url: str = ""
    result_ok: bool = False


def workshop_page_url(mod_id: str) -> str:
    return WORKSHOP_URL.format(id=mod_id)


def fetch_details(item_ids: list[str], timeout: float = 10.0) -> dict[str, WorkshopDetails]:
    """Запросить детали для списка ID. Возвращает {} при любой сетевой ошибке."""
    if not item_ids:
        return {}
    try:
        import httpx
    except ImportError:
        return {}
    data = {"itemcount": str(len(item_ids))}
    for i, item in enumerate(item_ids):
        data[f"publishedfileids[{i}]"] = str(item)
    try:
        resp = httpx.post(_API_URL, data=data, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return {}
    out: dict[str, WorkshopDetails] = {}
    for item in payload.get("response", {}).get("publishedfiledetails", []):
        item_id = str(item.get("publishedfileid", ""))
        ok = item.get("result") == 1
        out[item_id] = WorkshopDetails(
            item_id=item_id,
            title=item.get("title", "") if ok else "",
            time_updated=int(item.get("time_updated", 0) or 0),
            preview_url=item.get("preview_url", "") if ok else "",
            result_ok=ok,
        )
    return out
