"""Formulaires de configuration, générés à partir du schéma (config.SETTINGS).

Règles :
- un champ secret n'est JAMAIS renvoyé au navigateur. On indique seulement s'il est enregistré. Le laisser
  vide garde la valeur actuelle ; la case « Effacer » le vide ;
- une case à cocher absente du formulaire vaut « false » (comportement normal des cases HTML) ;
- on enregistre un groupe à la fois, fusionné avec le reste de la configuration ;
- tout passe par config.build_cfg() : si une erreur apparaît, rien n'est enregistré.
"""
from __future__ import annotations

from ..config import BY_ENV, GROUPS, SETTINGS, Setting, build_cfg

INPUT_TYPES = {"int": "number", "float": "number", "secret": "password"}
HINTS = {"size": "Exemples : 500Mo, 2Go. 0 = pas de limite.", "size_opt": "Exemples : 5Go, 30Go.",
         "words": "Séparés par des virgules.", "list": "Séparés par des virgules."}


def group_settings(group: str) -> list[Setting]:
    return [s for s in SETTINGS if s.group == group]


def fields(group: str, values: dict[str, str], errors: list[str], submitted: dict[str, str] | None = None) -> list[dict]:
    """Champs à afficher pour un groupe. `submitted` : ce que l'utilisateur vient de saisir (après une erreur)."""
    out = []
    for s in group_settings(group):
        current = values.get(s.env, "")
        if not current and s.aliases:
            current = next((values[a] for a in s.aliases if values.get(a)), "")
        shown = submitted.get(s.env, current) if submitted is not None else current
        field = {
            "env": s.env, "label": s.label, "help": s.help or HINTS.get(s.kind, ""), "kind": s.kind,
            "input_type": INPUT_TYPES.get(s.kind, "text"), "required": s.required, "advanced": s.advanced,
            "choices": s.choices, "placeholder": _placeholder(s),
            "error": next((e for e in errors if e.startswith(s.env) or f" {s.env} " in f" {e} "), None),
            "step": "any" if s.kind == "float" else "1", "min": s.minimum, "section": s.section,
        }
        if s.secret:
            field.update(value="", stored=bool(current))  # jamais la valeur
        elif s.kind == "bool":
            field["checked"] = (shown.strip().lower() in ("1", "true", "yes", "oui", "on")) if shown.strip() \
                else bool(s.default)
        else:
            field["value"] = shown
        out.append(field)
    return out


def _placeholder(s: Setting) -> str:
    if s.kind in ("bool", "secret") or s.default in (None, "", [], 0) and s.kind not in ("int", "float"):
        return ""
    if isinstance(s.default, list):
        return ",".join(s.default)
    return f"{s.default:g}" if isinstance(s.default, float) else str(s.default)


def merge(group: str, form: dict[str, str], values: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Fusionne la saisie d'un groupe avec la configuration actuelle. Retourne (valeurs, réglages modifiés)."""
    merged = dict(values)
    changed = []
    for s in group_settings(group):
        old = merged.get(s.env, "")
        if s.kind == "bool":
            new = "true" if form.get(s.env) in ("on", "true", "1") else "false"
        elif s.secret:
            if form.get(f"{s.env}__effacer"):
                new = ""
            else:
                typed = form.get(s.env, "").strip()
                new = typed if typed else old  # vide = on garde la valeur enregistrée
        else:
            new = form.get(s.env, "").strip()
        if s.aliases and new != old:  # l'ancien nom ne doit plus masquer le nouveau
            for a in s.aliases:
                merged.pop(a, None)
        if new != old:
            changed.append(s.env)
        merged[s.env] = new
    return merged, changed


def field_errors(group: str, errors: list[str]) -> list[str]:
    """Erreurs qui concernent directement un réglage de ce groupe (valeur invalide ou manquante)."""
    envs = [s.env for s in group_settings(group)]
    return [e for e in errors if any(e.startswith(env + " ") or e.endswith(": " + env) for env in envs)]


def save_group(group: str, form: dict[str, str], store, strict: bool = True):
    """Vérifie puis enregistre un groupe.

    strict=True (le moteur tourne) : la moindre erreur bloque, pour ne jamais casser une configuration valide.
    strict=False (configuration incomplète) : seules les erreurs du groupe bloquent ; les autres sont renvoyées
    comme « à compléter », pour pouvoir remplir la configuration groupe par groupe.

    Retourne (cfg ou None, erreurs bloquantes, réglages modifiés, erreurs restantes).
    cfg n'est renvoyé que si la configuration complète est valide.
    """
    if group not in GROUPS:
        return None, ["Groupe de réglages inconnu."], [], []
    merged, changed = merge(group, form, store.values())
    cfg, errors = build_cfg(merged)
    blocking = errors if strict else field_errors(group, errors)
    if blocking:
        return None, blocking, changed, []
    if changed:
        store.save(merged)
    remaining = [e for e in errors if e not in blocking]
    return (None if remaining else cfg), [], changed, remaining


def preview_cfg(group: str, form: dict[str, str], store) -> tuple[dict, list[str]]:
    """Configuration « comme si on enregistrait », sans rien écrire (pour les boutons Tester)."""
    merged, _ = merge(group, form, store.values())
    return build_cfg(merged)


def describe(changed: list[str]) -> str:
    """Liste lisible des réglages modifiés, pour le journal (jamais de valeur)."""
    return ", ".join(f"{BY_ENV[e].label} ({e})" for e in changed if e in BY_ENV)
