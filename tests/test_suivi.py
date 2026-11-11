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


class TestAlertes(unittest.TestCase):
    def setUp(self):
        from autodl import alertes
        self.a = alertes
        self.tmp = Path(tempfile.mkdtemp())
        self.notifier = mock.Mock()

    def ctx(self, torrents=(), free=1000 * 1024**3):
        qbit = FakeQbit(list(torrents))
        qbit.free_space = lambda: free
        return {"qbit": qbit, "tracking": m.Tracking(self.tmp / "t.json"), "notifier": self.notifier}

    def test_disque_une_fois_puis_reprise(self):
        ctx = self.ctx(free=30 * 1024**3)
        cfg = base_cfg(alert_disk_gb=50, alert_tracker=0, alert_cert=False)
        self.assertEqual(len(self.a.maybe_alerts(args(), cfg, ctx, force=True)), 1)
        self.assertEqual(self.a.maybe_alerts(args(), cfg, ctx, force=True), [])  # déjà signalé
        ctx["qbit"].free_space = lambda: 200 * 1024**3  # de la place a été faite
        self.a.maybe_alerts(args(), cfg, ctx, force=True)
        ctx["qbit"].free_space = lambda: 30 * 1024**3
        self.assertEqual(len(self.a.maybe_alerts(args(), cfg, ctx, force=True)), 1)  # de nouveau bas

    def test_tracker_apres_deux_constats(self):
        broken = [dict(tor(f"h{i}"), tracker="", state="stalledUP") for i in range(3)]
        ctx = self.ctx(broken)
        cfg = base_cfg(alert_disk_gb=0, alert_tracker=3, alert_cert=False)
        self.assertEqual(self.a.maybe_alerts(args(), cfg, ctx, force=True), [])  # premier constat : on attend
        sent = self.a.maybe_alerts(args(), cfg, ctx, force=True)
        self.assertEqual(len(sent), 1)
        self.assertIn("3 torrent(s)", sent[0])
        self.assertEqual(self.a.maybe_alerts(args(), cfg, ctx, force=True), [])
        # torrents en pause : pas une panne de tracker
        ctx2 = self.ctx([dict(tor(f"p{i}"), tracker="", state="stoppedUP") for i in range(5)])
        self.a.maybe_alerts(args(), cfg, ctx2, force=True)
        self.assertEqual(self.a.maybe_alerts(args(), cfg, ctx2, force=True), [])

    def test_certificat_qui_expire(self):
        cfg = base_cfg(alert_disk_gb=0, alert_tracker=0, alert_cert=True, domain_on=True, domain="c411.exemple.fr")
        status = {"vu_le": NOW - 600, "certificat": {"valide": True, "expire_ts": NOW + 5 * 86400, "expire": "x"}}
        with mock.patch("autodl.domaine.helper_status", return_value=status):
            sent = self.a.maybe_alerts(args(), cfg, self.ctx(), now=NOW, force=True)
            self.assertEqual(len(sent), 1)
            self.assertIn("expire dans 5 jour(s)", sent[0])
        status["certificat"]["expire_ts"] = NOW + 60 * 86400
        with mock.patch("autodl.domaine.helper_status", return_value=status):
            self.assertEqual(self.a.maybe_alerts(args(), cfg, self.ctx(), now=NOW, force=True), [])

    def test_rien_en_essai_a_blanc(self):
        self.assertEqual(self.a.maybe_alerts(args(dry_run=True), base_cfg(alert_disk_gb=50), self.ctx(free=1), force=True), [])


class TestAjoutsEtActions(unittest.TestCase):
    def test_liste_des_ajouts(self):
        from autodl.tableau import all_additions
        state = m.State(Path(tempfile.mkdtemp()) / "s.json")
        state.add("a", "BD.[CBZ]-X", "bd", 10 * MB)
        state.add("b", "Livre.[EPUB]-X", "ebook", MB)
        torrent = dict(t("a", seed_h=80, ratio=2.0, size=10 * MB, uploaded=20 * MB), category="c411-bd")
        rows = {r["hash"]: r for r in all_additions(state, {"a": torrent})}
        self.assertEqual((rows["a"]["rendement"], rows["a"]["hitrun"], rows["a"]["categorie"]), (2.0, "quitte", "c411-bd"))
        self.assertFalse(rows["b"]["present"])
        self.assertEqual(rows["b"]["etat"], "absent de qBittorrent")

    def test_action_reelle_refusee_en_lecture_seule(self):
        from autodl import engine as engine_mod
        e = engine_mod.Engine(base_cfg(pages=1), read_only=True, ctx={"qbit": FakeQbit(), "tracking": mock.Mock(data={})})
        with mock.patch.object(engine_mod, "cleanup") as cleanup:
            task = e.run_task("nettoyage")
        self.assertFalse(task["ok"])
        self.assertIn("lecture seule", task["resultat"])
        cleanup.assert_not_called()

    def test_rangement_reel_ne_deplace_rien(self):
        from autodl import engine as engine_mod
        e = engine_mod.Engine(base_cfg(pages=1), ctx={"qbit": FakeQbit(), "tracking": mock.Mock(data={})})
        with mock.patch.object(engine_mod, "recategorize", return_value={}) as recat:
            task = e.run_task("rangement")
        self.assertTrue(task["ok"])
        self.assertTrue(recat.call_args.kwargs["keep_location"])
        self.assertFalse(recat.call_args.args[0].dry_run)
