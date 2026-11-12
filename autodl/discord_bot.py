"""Bot Discord : commandes /statut, /ratio, /bilan, /hitrun, /pause, /reprise, /passage, /aide.

Tourne dans son propre thread, à côté du moteur, quand DISCORD_BOT_ACTIF est activé (nécessite discord.py,
inclus dans requirements-interface.txt et dans l'image Docker). Les messages automatiques (ajouts, bilan,
alertes) ne passent pas par ici mais par l'API REST (discordapi.py) : ils partent même si le bot est déconnecté.

Sécurité : seules les personnes qui ont le rôle DISCORD_ROLE, sur le serveur DISCORD_SERVEUR, peuvent utiliser
les commandes. Sans rôle configuré, tout est refusé. Le jeton n'est jamais écrit dans le journal.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

from .commun import _human, log

COMMANDS = {
    "statut": "État du programme : passages, ajouts, ratio",
    "ratio": "Ton ratio c411, ce que tu as envoyé et reçu",
    "bilan": "Le bilan depuis le dernier bilan quotidien (sans le remplacer)",
    "hitrun": "Torrents pas encore quittes (72 h de seed ou ratio 1,0)",
    "profil": "Ton profil c411 : niveau, quêtes, voies, Zen",
    "pause": "Met les ajouts en pause",
    "reprise": "Reprend les ajouts",
    "passage": "Lance un passage tout de suite",
    "aide": "Liste des commandes",
}
GREEN, ORANGE, RED, BLURPLE = 0x2ECC71, 0xE67E22, 0xE74C3C, 0x5865F2


def available() -> bool:
    try:
        import discord  # noqa: F401
        return True
    except ImportError:
        return False


def bot_settings(cfg: dict) -> tuple:
    """Ce qui oblige à redémarrer le bot quand il change."""
    return (bool(cfg.get("bot_on")), cfg.get("bot_token"), cfg.get("bot_guild"), cfg.get("bot_role"))


def allowed(member_roles: list[int], guild_id: int | None, cfg: dict) -> str | None:
    """Raison du refus, ou None si la personne peut utiliser les commandes."""
    if not cfg.get("bot_role"):
        return "Aucun rôle n'est autorisé : choisis-en un dans Configuration > Bot Discord."
    if str(guild_id or "") != str(cfg.get("bot_guild")):
        return "Ce bot ne répond que sur son serveur."
    if int(cfg["bot_role"]) not in member_roles:
        return "Tu n'as pas le rôle qui permet d'utiliser les commandes de c411-autodl."
    return None


# ------------------------------------------------------------------ contenu des réponses (sans discord.py, testable)

STATE_LABELS = {"actif": "🟢 Actif", "passage": "🔄 Passage en cours", "tache": "⚙️ Tâche en cours",
                "pause": "⏸️ En pause", "pause_ratio": "⏸️ Pause (ratio)", "freeleech": "🎉 Freeleech",
                "panne": "🔴 En panne", "demarrage": "⏳ Démarrage"}


def _when(ts: float | None) -> str:
    return f"<t:{int(ts)}:R>" if ts else "–"  # Discord affiche « il y a 3 minutes » à l'heure du lecteur


def statut_embed(snap: dict) -> dict:
    fields = [
        {"name": "État", "value": STATE_LABELS.get(snap["state"], snap["state"]), "inline": True},
        {"name": "Ratio c411", "value": f"**{snap['ratio']:.2f}**" if snap.get("ratio") is not None else "–",
         "inline": True},
        {"name": "Ratio minimum", "value": f"{snap['min_ratio']:.2f}" if snap.get("min_ratio") else "désactivé",
         "inline": True},
        {"name": "Dernier passage", "value": _when(snap.get("last_pass_at")), "inline": True},
        {"name": "Prochain passage", "value": _when(snap.get("next_pass_at")), "inline": True},
        {"name": "Ajouts", "value": f"{snap.get('last_added', 0)} au dernier passage, "
                                    f"{snap.get('total_added', 0)} depuis le démarrage", "inline": True},
    ]
    if snap.get("budget"):
        b = snap["budget"]
        fields.append({"name": "Budget du jour", "value": f"{_human(b['utilise'])} / {_human(b['limite'])}",
                       "inline": True})
    if snap.get("last_error"):
        fields.append({"name": "Dernière erreur", "value": str(snap["last_error"])[:500], "inline": False})
    color = RED if snap["state"] == "panne" else ORANGE if snap["state"].startswith("pause") else GREEN
    return {"title": "📡 Statut de c411-autodl", "color": color, "fields": fields}


def ratio_embed(ratio: float, up: int, down: int, min_ratio: float) -> dict:
    margin = f"{ratio - min_ratio:+.2f} au-dessus du minimum" if min_ratio else "pas de minimum"
    return {"title": "⚖️ Ratio c411", "color": GREEN if not min_ratio or ratio > min_ratio else ORANGE,
            "fields": [{"name": "Ratio", "value": f"**{ratio:.2f}**", "inline": True},
                       {"name": "Envoyé", "value": _human(up), "inline": True},
                       {"name": "Reçu", "value": _human(down), "inline": True},
                       {"name": "Marge", "value": margin, "inline": False}]}


def hitrun_embed(summary: dict) -> dict:
    c = summary["compteurs"]
    lines = [f"• {r['nom'][:70]} — {r['detail']}" for r in summary["a_surveiller"]]
    return {"title": "⏱️ Hit & Run", "color": RED if c["risque"] else GREEN,
            "description": "\n".join(lines) or "Tous les torrents suivis sont quittes.",
            "fields": [{"name": k, "value": str(v), "inline": True} for k, v in
                       (("Quittes", c["quitte"]), ("En seed", c["seed"]), ("Téléchargement", c["telechargement"]),
                        ("À risque", c["risque"]))]}


def aide_embed() -> dict:
    return {"title": "🤖 Commandes de c411-autodl", "color": BLURPLE,
            "description": "\n".join(f"**/{name}** — {text}" for name, text in COMMANDS.items())}


# ------------------------------------------------------------------ le bot

class CommandBot:
    """Le client Discord, dans un thread avec sa propre boucle asyncio."""

    def __init__(self, engine):
        self.engine = engine
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self.settings = bot_settings(engine.cfg)

    def start(self) -> None:
        if not available():
            log.warning("Bot Discord : discord.py n'est pas installé (pip install -r requirements-interface.txt)")
            return
        logging.getLogger("discord").setLevel(logging.WARNING)  # journal de discord.py : l'essentiel seulement
        self._thread = threading.Thread(target=self._run, name="bot-discord", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10) -> None:
        if self._loop and self._client:
            fut = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
            try:
                fut.result(timeout)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            log.error("Bot Discord arrêté : %s", str(e).replace(self.engine.cfg.get("bot_token") or "\0", "***"))
        finally:
            self._loop.close()

    async def _main(self) -> None:
        import discord
        from discord import app_commands

        cfg = self.engine.cfg
        intents = discord.Intents.none()
        intents.guilds = True
        client = discord.Client(intents=intents)
        self._client = client
        tree = app_commands.CommandTree(client)
        guild = discord.Object(id=int(cfg["bot_guild"]))
        engine = self.engine

        async def check(interaction) -> bool:
            roles = [r.id for r in getattr(interaction.user, "roles", [])]
            refused = allowed(roles, interaction.guild_id, engine.cfg)
            if refused:
                await interaction.response.send_message(refused, ephemeral=True)
                log.info("Bot Discord : commande /%s refusée à %s", interaction.command.name, interaction.user)
                return False
            log.info("Bot Discord : /%s par %s", interaction.command.name, interaction.user)
            return True

        def reply(embed: dict):
            return discord.Embed.from_dict({**embed, "footer": {"text": "c411-autodl"}})

        @tree.command(name="statut", description=COMMANDS["statut"], guild=guild)
        async def statut(interaction):
            if await check(interaction):
                await interaction.response.send_message(embed=reply(statut_embed(engine.snapshot())))

        @tree.command(name="ratio", description=COMMANDS["ratio"], guild=guild)
        async def ratio(interaction):
            if not await check(interaction):
                return
            await interaction.response.defer()
            try:
                r, up, down, _ = await asyncio.to_thread(engine.ctx["profile"].ratio)
                await interaction.followup.send(embed=reply(ratio_embed(r, up, down, engine.cfg["min_ratio"])))
            except Exception as e:
                await interaction.followup.send(f"Ratio indisponible : {str(e)[:200]}")

        @tree.command(name="bilan", description=COMMANDS["bilan"], guild=guild)
        async def bilan(interaction):
            if not await check(interaction):
                return
            await interaction.response.defer()
            from .moteur import report_data, report_embed
            try:
                data, _ = await asyncio.to_thread(report_data, engine.cfg, engine.ctx)
                await interaction.followup.send(embed=reply(report_embed(data)))
            except Exception as e:
                await interaction.followup.send(f"Bilan indisponible : {str(e)[:200]}")

        @tree.command(name="hitrun", description=COMMANDS["hitrun"], guild=guild)
        async def hitrun(interaction):
            if not await check(interaction):
                return
            await interaction.response.defer()
            from .hitrun import summary

            def compute():
                qbit = engine.ctx["qbit"]
                qbit.login(quiet=True)
                return summary(qbit.torrents(tag=engine.cfg["own_tag"]), engine.cfg["own_tag"], limit=10)
            try:
                await interaction.followup.send(embed=reply(hitrun_embed(await asyncio.to_thread(compute))))
            except Exception as e:
                await interaction.followup.send(f"Suivi indisponible : {str(e)[:200]}")

        @tree.command(name="profil", description=COMMANDS["profil"], guild=guild)
        async def profil(interaction):
            if not await check(interaction):
                return
            await interaction.response.defer()
            from .profil import fetch, recap_embed
            try:
                data = await asyncio.to_thread(fetch, engine.ctx)
                prev = engine.ctx["tracking"].data.get("profil_veille") if engine.ctx.get("tracking") else None
                await interaction.followup.send(embed=reply(recap_embed(data, prev)))
            except Exception as e:
                await interaction.followup.send(f"Profil indisponible : {str(e)[:200]}")

        async def action(interaction, name: str, text: str):
            if not await check(interaction):
                return
            if engine.read_only:
                await interaction.response.send_message("Lecture seule : aucune action possible.", ephemeral=True)
                return
            engine.submit(name)
            await interaction.response.send_message(text)

        @tree.command(name="pause", description=COMMANDS["pause"], guild=guild)
        async def pause(interaction):
            await action(interaction, "pause", "⏸️ Ajouts mis en pause. **/reprise** pour relancer.")

        @tree.command(name="reprise", description=COMMANDS["reprise"], guild=guild)
        async def reprise(interaction):
            await action(interaction, "reprise", "▶️ Ajouts repris.")

        @tree.command(name="passage", description=COMMANDS["passage"], guild=guild)
        async def passage(interaction):
            await action(interaction, "passage", "🔄 Passage lancé : le résultat arrivera dans le salon des ajouts.")

        @tree.command(name="aide", description=COMMANDS["aide"], guild=guild)
        async def aide(interaction):
            await interaction.response.send_message(embed=reply(aide_embed()), ephemeral=True)

        @client.event
        async def on_ready():
            try:
                synced = await tree.sync(guild=guild)  # sur le serveur seulement : disponibles tout de suite
                log.info("Bot Discord connecté (%s) : %d commande(s) sur le serveur", client.user, len(synced))
            except Exception as e:
                log.error("Bot Discord : impossible d'enregistrer les commandes (%s)", e)

        started = time.time()
        try:
            await client.start(cfg["bot_token"])
        except discord.LoginFailure:
            log.error("Bot Discord : jeton refusé (DISCORD_BOT_TOKEN)")
        finally:
            if not client.is_closed():
                await client.close()
            log.info("Bot Discord déconnecté après %d s", int(time.time() - started))
