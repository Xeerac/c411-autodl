"""Tests du bot Discord (envoi par l'API, rôles, réponses, interface). Aucun accès réseau."""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_c411_autodl import base_cfg  # noqa: E402
from test_interface import HAS_WEB, WebCase  # noqa: E402

from autodl import config, contexte, discord_bot, discordapi, verifications  # noqa: E402
from autodl import engine as engine_mod  # noqa: E402

GUILD, MAIN, ADDS, ROLE = "111111111111111111", "222222222222222222", "333333333333333333", "444444444444444444"
BASE = {"C411_API_KEY": "k", "QBIT_URL": "u", "QBIT_USER": "u", "QBIT_PASS": "p", "MIN_RATIO": "0"}


class TestConfiguration(unittest.TestCase):
    def test_identifiants_et_verification(self):
        cfg, errors = config.build_cfg({**BASE, "DISCORD_BOT_ACTIF": "true", "DISCORD_BOT_TOKEN": "t",
                                        "DISCORD_SERVEUR": GUILD, "DISCORD_SALON": MAIN, "DISCORD_SALON_AJOUTS": ADDS})
        self.assertEqual(errors, [])
        self.assertEqual(cfg["bot_channel_ajout"], ADDS)
        _, errors = config.build_cfg({**BASE, "DISCORD_SALON": "#general"})
        self.assertTrue(any("identifiant Discord invalide" in e for e in errors))
        _, errors = config.build_cfg({**BASE, "DISCORD_BOT_ACTIF": "true"})
        self.assertTrue(any("DISCORD_BOT_TOKEN" in e and "DISCORD_SALON" in e for e in errors))
        self.assertTrue(config.BY_ENV["DISCORD_BOT_TOKEN"].secret)
        self.assertNotIn("DISCORD_WEBHOOK_AJOUTS", config.BY_ENV)  # remplacés par le bot


class TestEnvoi(unittest.TestCase):
    def cfg(self, **over):
        cfg, _ = config.build_cfg({**BASE, "DISCORD_WEBHOOK_URL": "https://webhook", "DISCORD_BOT_ACTIF": "true",
                                   "DISCORD_BOT_TOKEN": "jeton", "DISCORD_SERVEUR": GUILD, "DISCORD_SALON": MAIN,
                                   "DISCORD_SALON_AJOUTS": ADDS, **over})
        return cfg

    def test_le_bot_remplace_le_webhook(self):
        n = contexte.make_notifier(self.cfg())
        n._post = mock.Mock()
        with mock.patch.object(discordapi, "send") as send:
            n.added([dict(title="Livre", size=1, page="")], 1, None)
            n.send("⚠️ disque", kind="disque")
        self.assertEqual([c.args[1] for c in send.call_args_list], [ADDS, MAIN])
        self.assertEqual(send.call_args.args[0], "jeton")
        n._post.assert_not_called()  # le webhook n'est plus utilisé

    def test_webhook_si_bot_desactive(self):
        n = contexte.make_notifier(self.cfg(DISCORD_BOT_ACTIF="false"))
        n._post = mock.Mock()
        with mock.patch.object(discordapi, "send") as send:
            n.send("x")
        send.assert_not_called()
        self.assertEqual(n._post.call_args.args[0], "https://webhook")

    def test_bouton_tester_le_bot(self):
        with mock.patch.object(discordapi, "me", return_value={"id": "9", "username": "autodl"}), \
                mock.patch.object(discordapi, "guilds", return_value=[{"id": GUILD, "nom": "Serveur"}]), \
                mock.patch.object(discordapi, "send") as send:
            result = verifications.test_discord_bot(self.cfg(DISCORD_ROLE=ROLE))
        self.assertTrue(result["ok"], result)
        self.assertEqual(sorted(c.args[1] for c in send.call_args_list), sorted([MAIN, ADDS]))
        texts = {c.args[1]: c.args[2]["embeds"][0]["description"] for c in send.call_args_list}
        self.assertIn("Ajouts", texts[ADDS])
        self.assertIn("Bilan quotidien", texts[MAIN])

    def test_bot_absent_du_serveur(self):
        with mock.patch.object(discordapi, "me", return_value={"id": "9", "username": "autodl"}), \
                mock.patch.object(discordapi, "guilds", return_value=[]):
            self.assertFalse(verifications.test_discord_bot(self.cfg())["ok"])


class TestCommandes(unittest.TestCase):
    def test_roles(self):
        cfg = {"bot_role": ROLE, "bot_guild": GUILD}
        self.assertIsNone(discord_bot.allowed([int(ROLE)], int(GUILD), cfg))
        self.assertIn("rôle", discord_bot.allowed([555], int(GUILD), cfg))
        self.assertIn("serveur", discord_bot.allowed([int(ROLE)], 999, cfg))
        self.assertIn("Aucun rôle", discord_bot.allowed([int(ROLE)], int(GUILD), {"bot_guild": GUILD, "bot_role": ""}))

    def test_reponses(self):
        e = discord_bot.statut_embed({"state": "pause_ratio", "ratio": 3.5, "min_ratio": 3.7, "last_pass_at": 1000,
                                      "next_pass_at": None, "last_added": 0, "total_added": 4,
                                      "budget": {"utilise": 1024**3, "limite": 20 * 1024**3}})
        values = {f["name"]: f["value"] for f in e["fields"]}
        self.assertEqual(values["Dernier passage"], "<t:1000:R>")
        self.assertIn("20.00 Go", values["Budget du jour"])
        self.assertEqual(e["color"], discord_bot.ORANGE)
        self.assertIn("+0.30", discord_bot.ratio_embed(4.0, 1, 1, 3.7)["fields"][3]["value"])
        self.assertIn("/pause", discord_bot.aide_embed()["description"])

    def test_pas_de_bot_en_lecture_seule(self):
        cfg = {**base_cfg(pages=1), "bot_on": True, "bot_token": "t", "bot_guild": GUILD, "bot_role": ""}
        e = engine_mod.Engine(cfg, read_only=True, ctx={})
        with mock.patch.object(discord_bot.CommandBot, "start") as start:
            e._start_bot()
        start.assert_not_called()
        e2 = engine_mod.Engine(cfg, ctx={})
        with mock.patch.object(discord_bot.CommandBot, "start") as start:
            e2._start_bot()
        start.assert_called_once()

    def test_redemarrage_si_le_jeton_change(self):
        cfg = {**base_cfg(pages=1, boucle=0), "bot_on": True, "bot_token": "a", "bot_guild": GUILD, "bot_role": ""}
        e = engine_mod.Engine(cfg, ctx={})
        with mock.patch.object(engine_mod, "build_context", return_value={}), \
                mock.patch.object(e, "_start_bot") as start, mock.patch.object(e, "_stop_bot") as stop:
            e.apply(dict(cfg, min_ratio=9))  # rien à voir avec le bot
            start.assert_not_called()
            e.apply(dict(cfg, bot_token="b"))
            start.assert_called_once()
            stop.assert_called_once()


@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestPageBot(WebCase):
    def test_listes(self):
        self.install()
        page = self.client.get("/configuration/discord")
        self.assertIn('data-discord="channel"', page.text)
        self.assertIn("Charger les serveurs", page.text)
        csrf = re.search(r'name="csrf" content="([^"]+)"', page.text).group(1)
        with mock.patch.object(discordapi, "me", return_value={"id": "9", "username": "autodl"}), \
                mock.patch.object(discordapi, "guilds", return_value=[{"id": GUILD, "nom": "Serveur"}]), \
                mock.patch.object(discordapi, "channels",
                                  return_value=[{"id": MAIN, "nom": "général", "categorie": ""}]), \
                mock.patch.object(discordapi, "roles", return_value=[{"id": ROLE, "nom": "Admin"}]):
            r = self.client.post("/api/discord/listes", headers={"X-CSRF-Token": csrf},
                                 json={"valeurs": {"DISCORD_BOT_TOKEN": "jeton"}})
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["serveur"], GUILD)  # un seul serveur : choisi d'office
        self.assertEqual(data["salons"][0]["nom"], "général")
        self.assertIn("client_id=9", data["invitation"])
        self.assertEqual(self.client.post("/api/discord/listes", json={}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
