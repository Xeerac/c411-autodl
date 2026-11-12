"""Tests des webhooks Discord par type de message. Aucun accès réseau."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_c411_autodl import FakeQbit, args, base_cfg, m  # noqa: E402

from autodl import alertes, config, contexte, verifications  # noqa: E402
from autodl.notifications import KINDS, Notifier  # noqa: E402

MAIN, ADDS, BILAN = "https://d/principal", "https://d/ajouts", "https://d/bilan"


def notifier(**routes):
    n = Notifier(MAIN, "", "", True, routes)
    n.sent = []
    n._post = lambda url, payload: n.sent.append(url)
    return n


class TestRoutage(unittest.TestCase):
    def test_chaque_type_vers_son_webhook(self):
        n = notifier(ajout=ADDS, bilan=BILAN)
        n.added([dict(title="Livre", size=1, page="")], 1, None)
        n.send("📊 bilan", kind="bilan")
        n.send("⚠️ disque", kind="disque")   # pas de webhook propre : le principal
        n.send("⏸️ pause")                    # sans type : le principal
        self.assertEqual(n.sent, [ADDS, BILAN, MAIN, MAIN])

    def test_sans_webhook_principal(self):
        n = Notifier("", "", "", True, {"bilan": BILAN})
        n.sent = []
        n._post = lambda url, payload: n.sent.append(url)
        self.assertTrue(n.enabled)
        n.send("x", kind="bilan")
        n.send("y", kind="ajout")  # rien sur Discord : ni webhook propre, ni principal
        self.assertEqual(n.sent, [BILAN])

    def test_configuration(self):
        values = {"C411_API_KEY": "k", "QBIT_URL": "u", "QBIT_USER": "u", "QBIT_PASS": "p", "MIN_RATIO": "0",
                  "DISCORD_WEBHOOK_URL": MAIN, "DISCORD_WEBHOOK_HIT_AND_RUN": "https://d/hr"}
        cfg, errors = config.build_cfg(values)
        self.assertEqual(errors, [])
        n = contexte.make_notifier(cfg)
        self.assertEqual(n.routes, {"hitrun": "https://d/hr"})
        self.assertEqual(set(KINDS), {"ajout", "retrait", "bilan", "disque", "tracker", "ssl", "hitrun"})
        self.assertTrue(all(config.BY_ENV[e].secret for e in config.BY_ENV if e.startswith("DISCORD_WEBHOOK")))

    def test_alerte_disque_sur_son_webhook(self):
        n = notifier(disque="https://d/disque")
        qbit = FakeQbit()
        qbit.free_space = lambda: 1
        ctx = {"qbit": qbit, "tracking": m.Tracking(Path(tempfile.mkdtemp()) / "t.json"), "notifier": n}
        alertes.maybe_alerts(args(), base_cfg(alert_disk_gb=50, alert_tracker=0, alert_cert=False), ctx, force=True)
        self.assertEqual(n.sent, ["https://d/disque"])

    def test_bouton_tester(self):
        cfg = base_cfg(discord_webhook=MAIN, telegram_token="", telegram_chat="", notif_pauses=True,
                       discord_webhook_ajout=ADDS, discord_webhook_bilan=ADDS, discord_webhook_ssl=BILAN)
        sent = []
        with mock.patch.object(Notifier, "_post", lambda self, url, payload: sent.append((url, payload))):
            result = verifications.test_notifications(cfg)
        self.assertTrue(result["ok"])
        urls = [u for u, _ in sent]
        self.assertEqual(sorted(urls), sorted([MAIN, ADDS, BILAN]))  # un message par webhook distinct
        text = next(p["embeds"][0].get("description", "") for u, p in sent if u == ADDS)
        self.assertIn("Ajouts", text)
        self.assertIn("Bilan quotidien", text)


if __name__ == "__main__":
    unittest.main()
