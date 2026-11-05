"""Tests de l'interface web et du moteur en tâche de fond. Aucun accès réseau.

Nécessite requirements-interface.txt + httpx (sinon ces tests sont ignorés).
"""
import re
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
    HAS_WEB = True
except ImportError:  # dépendances de l'interface absentes
    HAS_WEB = False

from autodl import engine as engine_mod  # noqa: E402
from autodl.config import build_cfg  # noqa: E402

BASE_ENV = {"C411_API_KEY": "k", "QBIT_URL": "http://q", "QBIT_USER": "u", "QBIT_PASS": "p", "MIN_RATIO": "0"}


def cfg(**over):
    c, errors = build_cfg({**BASE_ENV, **over})
    assert not errors, errors
    return c


# --------------------------------------------------------------------------- moteur

class TestEngine(unittest.TestCase):
    def make(self, read_only=False):
        ctx = {"tracking": types.SimpleNamespace(data={}, save=lambda: None)}
        return engine_mod.Engine(cfg(), interval=300, read_only=read_only, ctx=ctx)

    def patched(self, run_once=None):
        return mock.patch.multiple(engine_mod, run_once=run_once or mock.Mock(return_value=2),
                                   maybe_cleanup=mock.Mock(), maybe_crossseed=mock.Mock(),
                                   maybe_report=mock.Mock())

    def test_un_cycle(self):
        e = self.make()
        with self.patched():
            wait = e.step()
        s = e.snapshot()
        self.assertGreater(wait, 290)
        self.assertEqual((s["state"], s["last_added"], s["total_added"], s["errors"]), ("actif", 2, 2, 0))

    def test_erreur_puis_attente_espacee(self):
        e = self.make()
        with self.patched(run_once=mock.Mock(side_effect=RuntimeError("seedbox injoignable"))):
            e.step()
            wait = e.step()
        s = e.snapshot()
        self.assertEqual(s["errors"], 2)
        self.assertIn("seedbox injoignable", s["last_error"])
        self.assertGreater(wait, 590)  # 2 erreurs : on attend 2 fois plus

    def test_lecture_seule_force_l_essai_a_blanc(self):
        e = self.make(read_only=True)
        seen = {}
        with self.patched(run_once=mock.Mock(side_effect=lambda a, c, x: seen.setdefault("dry", a.dry_run) and 0)):
            e.step()
        self.assertTrue(seen["dry"])
        self.assertTrue(e.snapshot()["read_only"])

    def test_pause_reprise_passage_en_tache_de_fond(self):
        e = self.make()
        run = mock.Mock(return_value=0)
        with self.patched(run_once=run):
            e.start()
            self._wait(lambda: run.call_count >= 1)       # premier passage au démarrage
            e.submit("pause")
            self._wait(lambda: e.snapshot()["state"] == "pause")
            calls = run.call_count
            e.submit("passage")                          # ignoré pendant la pause
            time.sleep(0.3)
            self.assertEqual(run.call_count, calls)
            e.submit("reprise")
            self._wait(lambda: run.call_count > calls)
            e.stop(5)
        self.assertFalse(e._thread.is_alive())

    def test_action_inconnue(self):
        with self.assertRaises(ValueError):
            self.make().submit("tout-supprimer")

    def test_etat_sans_secret(self):
        e = self.make()
        text = repr(e.snapshot())
        for secret in ("http://q", "'k'", "'p'"):
            self.assertNotIn(secret, text)

    @staticmethod
    def _wait(cond, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return
            time.sleep(0.05)
        raise AssertionError("délai dépassé")


# --------------------------------------------------------------------------- interface web

@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestInterface(unittest.TestCase):
    def setUp(self):
        from autodl.reglages import ConfigStore
        from autodl.web.app import create_app
        from autodl.web.auth import Auth
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".env").write_text("C411_API_KEY=cle-secrete-123\nQBIT_URL=http://q\nQBIT_USER=u\n"
                                       "QBIT_PASS=mdp-qbit\nMIN_RATIO=0\n", encoding="utf-8")
        self.store = ConfigStore(self.tmp / "config.json", self.tmp / ".env")
        self.auth = Auth(self.tmp / "interface.json")
        self.engine = mock.Mock()
        self.engine.snapshot.return_value = {"state": "actif", "read_only": True, "min_ratio": 2.0,
                                             "interval": 300, "ratio": 2.5}
        self.client = TestClient(create_app(self.engine, self.auth, self.store), base_url="http://localhost")

    # ---- outils
    def csrf_of(self, page):
        return re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)

    def install(self, code=None, pw="un-mot-de-passe-solide"):
        page = self.client.get("/installation")
        return self.client.post("/installation", data={
            "code": code or self.auth.setup_code, "utilisateur": "alexis", "mot_de_passe": pw,
            "confirmation": pw, "csrf": self.csrf_of(page)}, follow_redirects=False)

    def login(self, pw="un-mot-de-passe-solide", user="alexis"):
        page = self.client.get("/connexion")
        return self.client.post("/connexion", data={"utilisateur": user, "mot_de_passe": pw,
                                                    "csrf": self.csrf_of(page)}, follow_redirects=False)

    # ---- installation
    def test_premier_lancement_redirige_vers_l_installation(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.headers["location"], "/installation")

    def test_installation_exige_le_code(self):
        r = self.install(code="0000-0000-0000")
        self.assertIn("Code d&#39;installation incorrect", r.text)
        self.assertFalse(self.auth.has_admin())

    def test_installation_importe_le_env_et_connecte(self):
        r = self.install()
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/"))
        self.assertTrue(self.auth.has_admin() and self.store.exists())
        self.assertEqual(self.store.values()["C411_API_KEY"], "cle-secrete-123")
        self.assertEqual(self.client.get("/").status_code, 200)  # session ouverte

    def test_mot_de_passe_trop_court_ou_different(self):
        self.assertIn("10 caractères", self.install(pw="court").text)
        page = self.client.get("/installation")
        r = self.client.post("/installation", data={"code": self.auth.setup_code, "utilisateur": "a",
                                                    "mot_de_passe": "aaaaaaaaaaaa", "confirmation": "bbbbbbbbbbbb",
                                                    "csrf": self.csrf_of(page)})
        self.assertIn("ne correspondent pas", r.text)

    def test_installation_impossible_une_fois_faite(self):
        self.install()
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/installation", follow_redirects=False).headers["location"], "/")
        self.assertEqual(self.install().headers["location"], "/")

    def test_jeton_anti_falsification_obligatoire(self):
        self.client.get("/installation")
        r = self.client.post("/installation", data={"code": self.auth.setup_code, "utilisateur": "a",
                                                    "mot_de_passe": "x" * 12, "confirmation": "x" * 12,
                                                    "csrf": "faux"})
        self.assertIn("expiré", r.text)
        self.assertFalse(self.auth.has_admin())

    # ---- connexion
    def test_connexion_et_deconnexion(self):
        self.install()
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/", follow_redirects=False).headers["location"], "/connexion")
        self.assertIn("incorrect", self.login(pw="mauvais").text)
        self.assertEqual(self.login().headers["location"], "/")
        home = self.client.get("/")
        self.assertIn("Tableau de bord", home.text)
        csrf = re.search(r'name="csrf" content="([^"]+)"', home.text).group(1)
        self.client.post("/deconnexion", data={"csrf": csrf})
        self.assertEqual(self.client.get("/", follow_redirects=False).headers["location"], "/connexion")

    def test_blocage_apres_5_echecs(self):
        self.install()
        self.client.cookies.clear()
        for _ in range(5):
            self.login(pw="mauvais")
        r = self.login()  # même le bon mot de passe est refusé pendant le blocage
        self.assertIn("Trop de tentatives", r.text)

    # ---- API
    def test_api_exige_une_session_et_le_jeton(self):
        self.assertEqual(self.client.get("/api/etat").status_code, 401)
        self.install()
        self.assertEqual(self.client.get("/api/etat").json()["moteur"]["state"], "actif")
        self.assertEqual(self.client.post("/api/action/pause").status_code, 403)  # sans jeton
        csrf = re.search(r'name="csrf" content="([^"]+)"', self.client.get("/").text).group(1)
        r = self.client.post("/api/action/pause", headers={"X-CSRF-Token": csrf})
        self.assertEqual(r.json(), {"ok": True, "action": "pause"})
        self.engine.submit.assert_called_once_with("pause")
        self.assertEqual(self.client.post("/api/action/arret", headers={"X-CSRF-Token": csrf}).status_code, 404)

    def test_aucun_secret_dans_les_pages(self):
        self.install()
        for url in ("/", "/api/etat"):
            text = self.client.get(url).text
            for secret in ("cle-secrete-123", "mdp-qbit", "un-mot-de-passe-solide"):
                self.assertNotIn(secret, text, url)

    def test_entetes_de_securite(self):
        r = self.client.get("/connexion")
        h = r.headers
        self.assertIn("default-src 'self'", h["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", h["content-security-policy"])
        self.assertEqual((h["x-frame-options"], h["x-content-type-options"]), ("DENY", "nosniff"))
        cookie = r.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)

    def test_mot_de_passe_hache(self):
        self.install()
        stored = (self.tmp / "interface.json").read_text(encoding="utf-8")
        self.assertNotIn("un-mot-de-passe-solide", stored)
        self.assertIn("empreinte", stored)


if __name__ == "__main__":
    unittest.main()
