"""Tests des réglages par catégorie et du budget quotidien. Aucun accès réseau."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_c411_autodl import GB, MB, FakeC411, FakeProfile, FakeQbit, args, base_cfg, item, m  # noqa: E402

from autodl import config, profils  # noqa: E402


class TestLectureDesProfils(unittest.TestCase):
    def test_lecture(self):
        p = profils.parse("3010: formats=flac,mp3 taille_max=2Go par_passage=3\n# commentaire\n"
                          "2000: completes_min=5 budget_jour=30Go")
        self.assertEqual(p["3010"], {"formats": ["flac", "mp3"], "max_size": 2 * GB, "max_per_run": 3})
        self.assertEqual(p["2000"], {"min_completed": 5, "budget_day": 30 * GB})

    def test_point_virgule_du_env(self):
        self.assertEqual(set(profils.parse("3010: formats=flac ; 2030: seeders_max=10")), {"3010", "2030"})

    def test_erreurs_claires(self):
        for bad, word in (("musique: formats=flac", "catégorie"), ("3010: format=flac", "inconnu"),
                          ("3010: taille_max=beaucoup", "invalide"), ("3010: par_passage=-1", "invalide"),
                          ("3010: formats=flac\n3010: par_passage=1", "deux fois")):
            with self.assertRaises(ValueError, msg=bad) as e:
                profils.parse(bad)
            self.assertIn(word, str(e.exception))

    def test_dans_la_configuration(self):
        cfg, errors = config.build_cfg({"C411_API_KEY": "k", "QBIT_URL": "u", "QBIT_USER": "u", "QBIT_PASS": "p", "MIN_RATIO": "0",
                                        "PROFILS_CATEGORIES": "3010: formats=flac", "BUDGET_JOUR": "20Go"})
        self.assertEqual(errors, [])
        self.assertEqual(cfg["profiles"]["3010"]["formats"], ["flac"])
        self.assertEqual(cfg["budget_day"], 20 * GB)
        _, errors = config.build_cfg({"C411_API_KEY": "k", "QBIT_URL": "u", "QBIT_USER": "u", "QBIT_PASS": "p", "MIN_RATIO": "0",
                                      "PROFILS_CATEGORIES": "3010 formats=flac"})
        self.assertTrue(any("PROFILS_CATEGORIES" in e for e in errors))

    def test_exact_puis_famille(self):
        p = {"2030": {"max_size": 1}, "2000": {"max_size": 2}}
        self.assertEqual(profils.match("2030", p), "2030")
        self.assertEqual(profils.match("2040", p), "2000")
        self.assertIsNone(profils.match("3010", p))
        eff, key = profils.effective(base_cfg(profiles=p, max_size=9), "2040")
        self.assertEqual((eff["max_size"], key), (2, "2000"))


class TestPassageParCategorie(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def run_pass(self, items, dry=False, **over):
        ctx = dict(c411=FakeC411(items), profile=FakeProfile(500 * GB, 100 * GB), qbit=FakeQbit(),
                   state=m.State(self.tmp / "s.json"), tracking=m.Tracking(self.tmp / "t.json"))
        n = m.run_once(args(dry_run=dry), base_cfg(**over), ctx)
        return n, [fn for fn, _ in ctx["qbit"].added], ctx

    def test_formats_propres_a_une_categorie(self):
        items = [item(title="Album.FLAC-X", infohash="a", category="3010"),
                 item(title="Album.MP3-X", infohash="b", category="3010"),
                 item(title="Livre.[EPUB]-X", infohash="c", category="7020")]
        _, added, _ = self.run_pass(items, cats="7020,3010", formats=["epub"],
                                    profiles={"3010": {"formats": ["flac"]}})
        self.assertEqual(added, ["a.torrent", "c.torrent"])  # l'epub reste accepté hors musique

    def test_par_passage_et_taille_par_categorie(self):
        items = [item(title=f"Film{i}.1080p-X", infohash=f"f{i}", category="2030", size=10 * GB) for i in range(3)]
        items.append(item(title="Gros.2160p-X", infohash="g", category="2030", size=40 * GB))
        _, added, _ = self.run_pass(items, cats="2030", max_size=0,
                                    profiles={"2000": {"max_per_run": 2, "max_size": 15 * GB}})
        self.assertEqual(added, ["f0.torrent", "f1.torrent"])

    def test_budget_du_jour(self):
        items = [item(title=f"L{i}", infohash=f"l{i}", size=8 * GB) for i in range(4)]
        _, added, ctx = self.run_pass(items, budget_day=20 * GB)
        self.assertEqual(added, ["l0.torrent", "l1.torrent"])  # 16 Go, le 3e dépasserait 20 Go
        self.assertEqual(ctx["tracking"].data["budget"]["total"], 16 * GB)
        # le budget est gardé d'un passage à l'autre (même journée)
        more = [item(title="L9", infohash="l9", size=5 * GB)]
        _, added, _ = self.run_pass(more, budget_day=20 * GB)
        self.assertEqual(added, [])

    def test_freeleech_ne_consomme_pas_de_budget(self):
        items = [item(title="Gratuit", infohash="g", size=30 * GB, dl_factor=0.0),
                 item(title="Payant", infohash="p", size=5 * GB)]
        _, added, ctx = self.run_pass(items, budget_day=10 * GB, max_size=0)
        self.assertEqual(added, ["g.torrent", "p.torrent"])
        self.assertEqual(ctx["tracking"].data["budget"]["total"], 5 * GB)

    def test_budget_par_categorie(self):
        items = [item(title="F1", infohash="f1", category="2030", size=12 * GB),
                 item(title="F2", infohash="f2", category="2030", size=12 * GB),
                 item(title="Livre", infohash="l", category="7020", size=MB)]
        _, added, _ = self.run_pass(items, cats="2030,7020", max_size=0,
                                    profiles={"2030": {"budget_day": 20 * GB}})
        self.assertEqual(added, ["f1.torrent", "l.torrent"])

    def test_essai_a_blanc_ne_touche_pas_au_budget(self):
        items = [item(title=f"L{i}", infohash=f"l{i}", size=8 * GB) for i in range(4)]
        n, _, ctx = self.run_pass(items, dry=True, budget_day=20 * GB)
        self.assertEqual(n, 2)  # simulé quand même
        self.assertNotIn("budget", ctx["tracking"].data)


if __name__ == "__main__":
    unittest.main()
