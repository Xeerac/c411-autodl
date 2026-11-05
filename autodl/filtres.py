"""Recherche, tri et filtrage des torrents c411."""
from __future__ import annotations

import re

from .c411 import C411
from .commun import log


MAX_PAGES = 6  # c411 plafonne chaque recherche à 600 résultats (offset max 500)


def _scan(c411: C411, args, cfg: dict):
    """Enchaîne les recherches Torznab et renvoie chaque torrent une seule fois.

    Passage normal : une recherche toutes catégories confondues, sur --pages pages.
    Rattrapage : une recherche par catégorie et par mot-clé, chacune jusqu'à 600 résultats,
    pour contourner le plafond de c411.
    """
    if args.rattrapage:
        cats = [c.strip() for c in cfg["cats"].split(",") if c.strip()]
        searches = [(c, q) for c in cats for q in [""] + cfg["queries"]]
        pages = MAX_PAGES
    else:
        searches = [(cfg["cats"], "")]
        pages = min(args.pages, MAX_PAGES)

    seen: set[str] = set()
    for cats, query in searches:
        label = f"cat {cats}" + (f", « {query} »" if query else "")
        found = 0
        for page in range(pages):
            items = c411.search(cats, page * cfg["page_size"], cfg["page_size"], query)
            new = [it for it in items if (it["infohash"] or it["link"] or it["title"]) not in seen]
            for it in new:
                seen.add(it["infohash"] or it["link"] or it["title"])
            found += len(new)
            for it in new:
                yield it
            if len(items) < cfg["page_size"] or not new:
                break
        (log.debug if args.boucle else log.info)(
            "Recherche %s : %d nouveaux torrents (%d au total)", label, found, len(seen))


def _ordered(items, cfg: dict):
    """TRI=interet : traite d'abord les torrents les plus demandés (beaucoup de leechers pour peu
    de seeders), ceux qui rapporteront le plus d'upload. TRI=recent : ordre de c411 (plus récents d'abord)."""
    if cfg["tri"] != "interet":
        yield from items
        return
    items = list(items)
    # Tri stable : à intérêt égal, l'ordre de c411 (le plus récent d'abord) est conservé
    items.sort(key=_interest, reverse=True)
    yield from items


def _interest(it: dict) -> float:
    leechers = max(it.get("leechers", -1), 0)
    seeders = max(it.get("seeders", -1), 0)
    return (leechers + 1) / (seeders + 1)


def _has_token(title: str, token: str) -> bool:
    """Le mot apparaît-il dans le titre comme un élément à part (« [EPUB] », « .epub », « -EPUB- ») ?"""
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", title) is not None


def _group(title: str) -> str:
    """Groupe de release : ce qui suit le dernier tiret (« …[EPUB]-NOTAG » -> « notag »)."""
    m = re.search(r"-\s*([A-Za-z0-9_.]+)\s*$", title)
    return m.group(1).lower() if m else ""


def _reject(it: dict, cfg: dict) -> str | None:
    if it["completed"] < cfg["min_completed"]:
        return "complétés" if it["completed"] >= 0 else "complétés inconnu"
    if it["seeders"] >= 0 and it["seeders"] < cfg["min_seeders"]:
        return "seeders"
    if cfg["max_seeders"] and it["seeders"] > cfg["max_seeders"]:
        return "trop de seeders"
    if cfg["min_leechers"] and it.get("leechers", -1) < cfg["min_leechers"]:
        return "pas assez de leechers"
    if cfg["max_size"] and it["size"] > cfg["max_size"]:
        return "trop gros"
    if cfg["min_size"] and it["size"] < cfg["min_size"]:
        return "trop petit"
    title = it["title"].lower()
    if any(w in title for w in cfg["exclude"]):
        return "mot exclu"
    if cfg["formats"] and not any(_has_token(title, f) for f in cfg["formats"]):
        return "format non accepté"
    if cfg["required"] and not any(w in title for w in cfg["required"]):
        return "aucun mot requis"
    if cfg["excluded_groups"] and _group(it["title"]) in cfg["excluded_groups"]:
        return "groupe exclu"
    if cfg["exclude_regex"] and cfg["exclude_regex"].search(it["title"]):
        return "regex d'exclusion"
    return None
