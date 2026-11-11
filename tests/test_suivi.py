"""Tests du suivi Hit & Run et du rendement par catégorie dans les relevés. Aucun accès réseau."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_c411_autodl import MB, FakeQbit, args, base_cfg, m, tor  # noqa: E402

from autodl import hitrun, releves  # noqa: E402

NOW = 2_000_000_000.0
H = 3600


def t(h, seed_h=0, ratio=0.0, state="stalledUP", progress=1.0, added_h_ago=10, **kw):
    x = tor(h, **kw)
    x.update(seeding_time=seed_h * H, ratio=ratio, state=state, progress=progress, added_on=NOW - added_h_ago * H)
    return x


class TestHitRun(unittest.TestCase):
    def test_etats(self):
        self.assertEqual(hitrun.status(t("a", seed_h=72), NOW)["etat"], "quitte")
        self.assertEqual(hitrun.status(t("b", seed_h=5, ratio=1.2), NOW)["etat"], "quitte")
        s = hitrun.status(t("c", seed_h=30, ratio=0.4), NOW)
        self.assertEqual((s["etat"], s["reste_h"], s["progression"]), ("seed", 42.0, 42))
        self.assertEqual(hitrun.status(t("d", progress=0.5, added_h_ago=3), NOW)["etat"], "telechargement")
        self.assertEqual(hitrun.status(t("e", progress=0.5, added_h_ago=30), NOW)["etat"], "risque")
        self.assertEqual(hitrun.status(t("f", seed_h=10, state="stoppedUP"), NOW)["etat"], "risque")
        self.assertEqual(hitrun.status(t("g", seed_h=80, state="stoppedUP"), NOW)["etat"], "quitte")

    def test_resume(self):
        torrents = [t("a", seed_h=80), t("b", seed_h=60), t("c", seed_h=5, state="error"),
                    t("z", seed_h=1, tags="cross-seed")]
        s = hitrun.summary(torrents, "autodl", NOW)
        self.assertEqual(s["compteurs"], {"quitte": 1, "seed": 1, "telechargement": 0, "risque": 1})
        self.assertEqual(s["total"], 3)  # le cross-seed n'est pas suivi
        self.assertEqual([r["hash"] for r in s["a_surveiller"]], ["c", "b"])  # à risque en premier

    def test_alerte_une_seule_fois(self):
        tmp = Path(tempfile.mkdtemp())
        notifier = mock.Mock()
        qbit = FakeQbit([t("a", seed_h=5, state="pausedUP"), t("b", seed_h=60)])
        ctx = {"qbit": qbit, "tracking": m.Tracking(tmp / "t.json"), "notifier": notifier}
        self.assertEqual([r["hash"] for r in hitrun.maybe_alert(args(), base_cfg(), ctx, NOW, force=True)], ["a"])
        notifier.send.assert_called_once()
        self.assertIn("Hit & Run", notifier.send.call_args[0][0])
        self.assertEqual(hitrun.maybe_alert(args(), base_cfg(), ctx, NOW, force=True), [])  # déjà signalé
        notifier.send.assert_called_once()
        # relancé puis de nouveau arrêté : on prévient à nouveau
        qbit.t[0]["state"] = "stalledUP"
        hitrun.maybe_alert(args(), base_cfg(), ctx, NOW, force=True)
        qbit.t[0]["state"] = "pausedUP"
        self.assertEqual(len(hitrun.maybe_alert(args(), base_cfg(), ctx, NOW, force=True)), 1)

    def test_rien_en_essai_ou_desactive(self):
        ctx = {"qbit": FakeQbit([t("a", state="pausedUP")]), "tracking": mock.Mock(data={})}
        self.assertEqual(hitrun.maybe_alert(args(dry_run=True), base_cfg(), ctx, NOW, force=True), [])
        self.assertEqual(hitrun.maybe_alert(args(), base_cfg(hr_alert=False), ctx, NOW, force=True), [])


class TestReleveParType(unittest.TestCase):
    def test_envoye_du_jour_et_rendement(self):
        r = releves.Releves(Path(tempfile.mkdtemp()) / "r.json")
        r.add("2026-11-10", 3.0, 100, 50, {"types": {"bd": {"n": 2, "taille": 100 * MB, "envoye": 500 * MB}}})
        r.add("2026-11-11", 3.1, 120, 51, {"types": {"bd": {"n": 3, "taille": 120 * MB, "envoye": 800 * MB},
                                                      "musique": {"n": 1, "taille": 50 * MB, "envoye": 10 * MB}}})
        last = r.rows()[0]["types"]
        self.assertEqual(last["bd"]["envoye_jour"], 300 * MB)
        self.assertEqual(last["bd"]["rendement"], 6.67)
        self.assertIsNone(last["musique"]["envoye_jour"])  # nouvelle catégorie : pas de veille

    def test_releve_du_jour_complete_une_fois(self):
        r = releves.Releves(Path(tempfile.mkdtemp()) / "r.json")
        r.add("2026-11-11", 3.0, 1, 1)
        snap = mock.Mock(return_value={"bd": {"n": 1, "taille": 1, "envoye": 2}})
        r.complete_types("2026-11-11", snap)
        r.complete_types("2026-11-11", snap)
        snap.assert_called_once()
        self.assertIn("types", releves.Releves(r.path).items[0])  # enregistré

    def test_instantane_par_type(self):
        state = m.State(Path(tempfile.mkdtemp()) / "s.json")
        state.add("a", "BD.[CBZ]-X", "bd", 10)
        ctx = {"qbit": FakeQbit([tor("a", size=10, uploaded=30), tor("b", size=5, uploaded=5, name="Livre.[EPUB]-X")]),
               "state": state}
        snap = releves._types_snapshot(base_cfg(), ctx)
        self.assertEqual(snap["bd"], {"n": 1, "taille": 10, "envoye": 30})
        self.assertEqual(snap["ebook"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
