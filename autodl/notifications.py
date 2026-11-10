"""Notifications Discord et Telegram."""
from __future__ import annotations

import json
import re
import time
import urllib.request

from .commun import USER_AGENT, __version__, _human, log

# Couleur de la barre latérale des embeds Discord, d'après l'emoji qui ouvre le message
COLORS = {"📥": 0x2ECC71, "✅": 0x2ECC71, "▶️": 0x2ECC71, "🎉": 0xF1C40F, "📊": 0x5865F2,
          "⏸️": 0xE67E22, "⚠️": 0xE74C3C, "🗑️": 0x95A5A6, "💤": 0x95A5A6, "🔚": 0x95A5A6}
DEFAULT_COLOR = 0x5865F2


def text_embed(text: str) -> dict:
    """Embed Discord tiré d'un message texte : la première ligne devient le titre, le reste la description."""
    first, _, rest = text.partition("\n")
    color = next((c for emoji, c in COLORS.items() if first.startswith(emoji)), DEFAULT_COLOR)
    title = first.replace("**", "")
    if len(title) > 256:  # titre trop long : il passe en tête de la description
        rest = first + ("\n" + rest if rest else "")
        title = title[:120] + "…"
    embed = {"title": title, "color": color}
    if rest.strip():
        embed["description"] = rest.strip()[:4096]
    return finish_embed(embed)


def finish_embed(embed: dict) -> dict:
    """Pied de page (version) et horodatage, que Discord affiche à l'heure locale du lecteur."""
    embed.setdefault("footer", {"text": f"c411-autodl {__version__}"})
    embed.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return embed


class Notifier:
    """Envoie des messages sur Discord (webhook) et/ou Telegram (bot). Tout est optionnel."""

    def __init__(self, discord_webhook: str, tg_token: str, tg_chat: str, pauses: bool):
        self.discord = discord_webhook
        self.tg_token, self.tg_chat = tg_token, tg_chat
        self.pauses = pauses

    @property
    def enabled(self) -> bool:
        return bool(self.discord or (self.tg_token and self.tg_chat))

    def _post(self, url: str, payload: dict) -> None:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
            "Content-Type": "application/json", "User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()

    def send(self, text: str, embed: dict | None = None) -> None:
        """Texte au format Markdown simple : **gras** et [titre](lien).

        Discord reçoit un embed (celui fourni, sinon construit à partir du texte), Telegram le texte.
        """
        if self.discord:
            payload = {"embeds": [finish_embed(embed) if embed else text_embed(text)],
                       "allowed_mentions": {"parse": []}}  # jamais de @everyone, même dans un titre de torrent
            try:
                self._post(self.discord, payload)
            except Exception as e:
                log.warning("Notification Discord échouée : %s", e)
        if self.tg_token and self.tg_chat:
            html = _md_to_html(text)[:4096]
            try:
                self._post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                           {"chat_id": self.tg_chat, "text": html, "parse_mode": "HTML",
                            "disable_web_page_preview": True})
            except Exception as e:
                log.warning("Notification Telegram échouée : %s", e)

    def status(self, text: str) -> None:
        if self.pauses:
            self.send(text)

    def added(self, items: list[dict], total_bytes: int, ratio: float | None) -> None:
        head = f"📥 **{len(items)} torrent(s) ajouté(s) à la seedbox** ({_human(total_bytes)})"
        if ratio is not None:
            head += f" · ratio ≈ {ratio:.2f}"
        lines = [head]
        for it in items[:15]:
            title = it["title"].replace("[", "(").replace("]", ")")
            name = f"[{title}]({it['page']})" if it.get("page") else title
            free = " · freeleech" if it.get("dl_factor") == 0 else ""
            lines.append(f"• {name} — {_human(it['size'])}{free}")
        if len(items) > 15:
            lines.append(f"… et {len(items) - 15} autre(s)")
        self.send("\n".join(lines))


def _md_to_html(text: str) -> str:
    import html
    import re
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out
