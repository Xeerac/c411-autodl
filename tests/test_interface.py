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

def enable_logging(test: unittest.TestCase) -> None:
    """Les autres tests coupent les journaux (logging.disable) : on les rallume le temps d'un test."""
    import logging
    previous = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    test.addCleanup(logging.disable, previous)


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

class WebCase(unittest.TestCase):
    """Préparation commune (application, fichiers temporaires, outils). Ne contient aucun test."""

    def setUp(self):
        if not HAS_WEB:
            self.skipTest("dépendances de l'interface absentes")
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



@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestInterface(WebCase):
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


# --------------------------------------------------------------------------- formulaires de configuration

class TestFormulaire(unittest.TestCase):
    def setUp(self):
        from autodl.reglages import ConfigStore
        self.tmp = Path(tempfile.mkdtemp())
        self.store = ConfigStore(self.tmp / "config.json", self.tmp / ".env")
        self.store.save({**BASE_ENV, "QBIT_PASS": "ancien-mdp", "QBIT_PAUSED": "true"})

    def form(self, **values):
        from autodl.web import formulaire
        return formulaire

    def test_secret_vide_conserve(self):
        from autodl.web.formulaire import merge
        merged, changed = merge("qbittorrent", {"QBIT_URL": "http://q", "QBIT_USER": "u", "QBIT_PASS": ""},
                                self.store.values())
        self.assertEqual(merged["QBIT_PASS"], "ancien-mdp")
        self.assertNotIn("QBIT_PASS", changed)

    def test_secret_efface_ou_remplace(self):
        from autodl.web.formulaire import merge
        merged, _ = merge("qbittorrent", {"QBIT_PASS__effacer": "on"}, self.store.values())
        self.assertEqual(merged["QBIT_PASS"], "")
        merged, changed = merge("qbittorrent", {"QBIT_PASS": "nouveau"}, self.store.values())
        self.assertEqual(merged["QBIT_PASS"], "nouveau")
        self.assertIn("QBIT_PASS", changed)

    def test_case_decochee_vaut_false(self):
        from autodl.web.formulaire import merge
        merged, changed = merge("qbittorrent", {"QBIT_PASS": ""}, self.store.values())  # QBIT_PAUSED absent
        self.assertEqual(merged["QBIT_PAUSED"], "false")
        self.assertIn("QBIT_PAUSED", changed)

    def test_rien_n_est_enregistre_en_cas_d_erreur(self):
        from autodl.web.formulaire import save_group
        before = self.store.values()
        cfg, errors, _, _ = save_group("filtres", {"MIN_SEEDERS": "beaucoup"}, self.store)
        self.assertIsNone(cfg)
        self.assertTrue(any("MIN_SEEDERS" in e for e in errors))
        self.assertEqual(self.store.values(), before)

    def test_jamais_de_secret_dans_les_champs(self):
        from autodl.web.formulaire import fields
        for f in fields("qbittorrent", self.store.values(), []):
            if f["kind"] == "secret":
                self.assertEqual(f["value"], "")
                self.assertTrue(f["stored"])

    def test_ancien_nom_remplace(self):
        from autodl.web.formulaire import save_group
        self.store.save({**self.store.values(), "MAX_SIZE_MB": "800"})
        cfg, errors, _, _ = save_group("filtres", {"TAILLE_MAX": "2Go", "MIN_COMPLETED": "1", "MIN_SEEDERS": "1"},
                                    self.store)
        self.assertEqual(errors, [])
        self.assertNotIn("MAX_SIZE_MB", self.store.values())
        self.assertEqual(cfg["max_size"], 2 * 1024**3)


@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestPagesConfiguration(WebCase):
    """Compte créé et session ouverte avant chaque test."""

    def setUp(self):
        super().setUp()
        self.install()
        self.csrf = re.search(r'name="csrf" content="([^"]+)"', self.client.get("/").text).group(1)

    def test_page_par_groupe(self):
        r = self.client.get("/configuration/qbittorrent")
        self.assertEqual(r.status_code, 200)
        for name in ("QBIT_URL", "QBIT_USER", "QBIT_PASS", "QBIT_CATEGORIE_PAR_TYPE", "Tester la connexion"):
            self.assertIn(name, r.text)
        self.assertNotIn("mdp-qbit", r.text)  # le mot de passe n'est jamais renvoyé
        self.assertIn("enregistrée", r.text)

    def test_tous_les_groupes_s_affichent(self):
        from autodl.config import GROUPS
        for group in GROUPS:
            r = self.client.get(f"/configuration/{group}")
            self.assertEqual(r.status_code, 200, group)
            for secret in ("cle-secrete-123", "mdp-qbit"):
                self.assertNotIn(secret, r.text, group)

    def test_page_protegee(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/configuration/c411", follow_redirects=False).headers["location"],
                         "/connexion")

    def test_enregistrement_applique_au_moteur(self):
        r = self.client.post("/configuration/filtres", data={
            "csrf": self.csrf, "MIN_COMPLETED": "3", "MIN_SEEDERS": "2", "TAILLE_MAX": "1Go", "EXCLUDE_WORDS": ""},
            follow_redirects=False)
        self.assertEqual(r.headers["location"], "/configuration/filtres?ok=1")
        self.assertEqual(self.store.values()["MIN_COMPLETED"], "3")
        self.assertEqual(self.store.values()["C411_API_KEY"], "cle-secrete-123")  # le reste est intact
        cfg = self.engine.reload.call_args[0][0]
        self.assertEqual((cfg["min_completed"], cfg["max_size"]), (3, 1024**3))

    def test_erreur_affichee_rien_enregistre(self):
        r = self.client.post("/configuration/filtres", data={"csrf": self.csrf, "MIN_SEEDERS": "abc"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("MIN_SEEDERS doit être un nombre entier", r.text)
        self.assertEqual(self.store.values().get("MIN_SEEDERS", ""), "")
        self.engine.reload.assert_not_called()

    def test_jeton_obligatoire(self):
        r = self.client.post("/configuration/filtres", data={"csrf": "faux", "MIN_SEEDERS": "5"})
        self.assertEqual(r.status_code, 403)
        self.assertNotEqual(self.store.values().get("MIN_SEEDERS"), "5")

    def test_bouton_tester_avec_valeurs_non_enregistrees(self):
        from autodl.web import app as app_mod
        seen = {}
        fake = lambda cfg: seen.update(url=cfg["qbit_url"], pw=cfg["qbit_pass"]) or {"ok": True, "message": "ok"}
        with mock.patch.dict(app_mod.SERVICES, {"qbittorrent": (fake, "qbittorrent", "Tester")}):
            r = self.client.post("/api/tester/qbittorrent", headers={"X-CSRF-Token": self.csrf},
                                 json={"valeurs": {"QBIT_URL": "http://nouvelle", "QBIT_USER": "u", "QBIT_PASS": ""}})
        self.assertEqual(r.json(), {"ok": True, "message": "ok"})
        self.assertEqual(seen, {"url": "http://nouvelle", "pw": "mdp-qbit"})  # secret vide = celui enregistré
        self.assertNotEqual(self.store.values()["QBIT_URL"], "http://nouvelle")  # rien d'enregistré

    def test_tester_protege(self):
        self.assertEqual(self.client.post("/api/tester/c411", json={}).status_code, 403)
        r = self.client.post("/api/tester/inconnu", headers={"X-CSRF-Token": self.csrf}, json={})
        self.assertEqual(r.status_code, 404)


@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestDemarrageDifere(unittest.TestCase):
    """Configuration incomplète au démarrage : le moteur démarre dès qu'elle devient valide."""

    def test_moteur_cree_quand_la_config_devient_valide(self):
        from autodl.reglages import ConfigStore
        from autodl.web.app import create_app
        from autodl.web.auth import Auth
        tmp = Path(tempfile.mkdtemp())
        store = ConfigStore(tmp / "config.json", tmp / ".env")
        auth = Auth(tmp / "interface.json")
        engine = mock.Mock()
        engine.snapshot.return_value = {"state": "actif", "read_only": True, "min_ratio": 0.0, "interval": 300}
        factory = mock.Mock(return_value=engine)
        client = TestClient(create_app(None, auth, store, ["Variable manquante dans .env : C411_API_KEY"],
                                       engine_factory=factory), base_url="http://localhost")
        page = client.get("/installation")
        client.post("/installation", data={"code": auth.setup_code, "utilisateur": "a", "mot_de_passe": "x" * 12,
                                           "confirmation": "x" * 12,
                                           "csrf": re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)})
        home = client.get("/")
        self.assertIn("Configuration incomplète", home.text)
        csrf = re.search(r'name="csrf" content="([^"]+)"', home.text).group(1)
        client.post("/configuration/c411", data={"csrf": csrf, "C411_API_KEY": "k", "C411_CATEGORIES": "7020"})
        factory.assert_not_called()  # il manque encore qBittorrent
        client.post("/configuration/qbittorrent", data={"csrf": csrf, "QBIT_URL": "http://q", "QBIT_USER": "u",
                                                        "QBIT_PASS": "p"})
        client.post("/configuration/ratio", data={"csrf": csrf, "MIN_RATIO": "0"})
        factory.assert_called_once()
        engine.start.assert_called_once()
        self.assertNotIn("Configuration incomplète", client.get("/").text)


class TestRechargement(unittest.TestCase):
    def test_etat_conserve(self):
        e = engine_mod.Engine(cfg(), interval=300, ctx={"last_ratio": 2.7, "freeleech": True, "categories_ok": {"x"}})
        with mock.patch.object(engine_mod, "build_context", return_value={}):
            e.apply(cfg(MIN_SEEDERS="9", BOUCLE_SECONDES="600"))
        self.assertEqual(e.cfg["min_seeders"], 9)
        self.assertEqual((e.ctx["last_ratio"], e.ctx["freeleech"], e.interval), (2.7, True, 600))

    def test_rechargement_entre_deux_passages(self):
        e = engine_mod.Engine(cfg(), interval=300, ctx={"tracking": types.SimpleNamespace(data={}, save=lambda: None)})
        run = mock.Mock(return_value=0)
        with mock.patch.multiple(engine_mod, run_once=run, maybe_cleanup=mock.Mock(), maybe_crossseed=mock.Mock(),
                                 maybe_report=mock.Mock(), build_context=mock.Mock(return_value={})):
            e.start()
            TestEngine._wait(lambda: run.call_count >= 1)
            e.reload(cfg(MIN_SEEDERS="7"))
            TestEngine._wait(lambda: e.cfg["min_seeders"] == 7)
            self.assertEqual(run.call_count, 1)  # pas de passage en plus : l'heure prévue est gardée
            e.stop(5)


# --------------------------------------------------------------------------- étape 4 : tableau, tâches, journal

class TestJournal(unittest.TestCase):
    def setUp(self):
        import logging
        from autodl.journal import LogBuffer
        enable_logging(self)
        self.buf = LogBuffer(capacity=50)
        self.log = logging.getLogger("test-journal")
        self.log.setLevel(logging.INFO)
        self.log.addHandler(self.buf)
        self.addCleanup(self.log.removeHandler, self.buf)

    def test_secrets_masques(self):
        self.buf.set_secrets(["cle-tres-secrete", "mdp-qbit-123", ""])
        self.log.error("Erreur avec cle-tres-secrete et mdp-qbit-123 dans https://x/api?t=get&apikey=abcdef123&id=1")
        msg = self.buf.since(0)[-1]["message"]
        for secret in ("cle-tres-secrete", "mdp-qbit-123", "abcdef123"):
            self.assertNotIn(secret, msg)
        self.assertIn("***", msg)

    def test_suivi_par_numero_et_categories(self):
        self.log.info("+ Livre.FR.[EPUB]-X (2 Mo)")
        self.log.warning("Freeleech actif sur c411")
        first = self.buf.since(0)
        self.assertEqual([m["categorie"] for m in first], ["ajout", "freeleech"])
        self.log.info("autre")
        self.assertEqual([m["message"] for m in self.buf.since(first[-1]["id"])], ["autre"])

    def test_capacite_limitee(self):
        for i in range(80):
            self.log.info("message %d", i)
        self.assertEqual(len(self.buf.since(0)), 50)


class TestTableau(unittest.TestCase):
    def setUp(self):
        from autodl.stockage import State
        self.state = State(Path(tempfile.mkdtemp()) / "s.json")
        self.state.add("a", "BD.T01.[CBZ]-X", "bd", 100 * 1024**2)
        self.state.add("b", "Livre.[EPUB]-X", "ebook", 1024**2)

    def test_rendement_par_type(self):
        from autodl.tableau import type_stats
        torrents = [{"hash": "a", "name": "BD", "size": 100, "uploaded": 500},
                    {"hash": "b", "name": "Livre", "size": 100, "uploaded": 100}]
        rows = type_stats(torrents, self.state)
        self.assertEqual([(r["type"], r["rendement"], r["barre"]) for r in rows], [("bd", 5.0, 100), ("ebook", 1.0, 20)])

    def test_derniers_ajouts(self):
        from autodl.tableau import recent_additions
        rows = recent_additions(self.state, {"a": {"size": 100 * 1024**2, "uploaded": 250 * 1024**2, "state": "stalledUP"}})
        by_title = {r["titre"]: r for r in rows}
        self.assertEqual(by_title["BD.T01.[CBZ]-X"]["rendement"], 2.5)
        self.assertEqual(by_title["BD.T01.[CBZ]-X"]["etat"], "en seed")
        self.assertEqual(by_title["Livre.[EPUB]-X"]["etat"], "absent de qBittorrent")

    def test_services_affiches_seulement_si_configures(self):
        from autodl.tableau import Dashboard
        d = Dashboard()
        with mock.patch.object(Dashboard, "_qbittorrent", return_value=([], {"id": "qbittorrent", "ok": True})):
            ids = [s["id"] for s in d.data(cfg(), self.state)["services"]]
            self.assertEqual(ids, ["qbittorrent"])  # ni cross-seed ni Prowlarr configurés
            d.invalidate()
            with mock.patch.object(Dashboard, "_crossseed", return_value={"id": "crossseed"}), \
                 mock.patch.object(Dashboard, "_prowlarr", return_value={"id": "prowlarr"}):
                c = cfg(CROSS_SEED_URL="http://cs", CROSS_SEED_API_KEY="k", PROWLARR_URL="http://p")
                ids = [s["id"] for s in d.data(c, self.state)["services"]]
        self.assertEqual(ids, ["qbittorrent", "crossseed", "prowlarr"])


class TestTaches(unittest.TestCase):
    def make(self, read_only=False):
        ctx = {"tracking": types.SimpleNamespace(data={}, save=lambda: None)}
        return engine_mod.Engine(cfg(), interval=300, read_only=read_only, ctx=ctx)

    def test_les_apercus_sont_toujours_a_blanc(self):
        """Même hors lecture seule, un aperçu ne peut rien modifier."""
        e = self.make(read_only=False)
        seen = []
        record = lambda a, *rest, **kw: seen.append(a.dry_run) or ({} if kw.get("summary") else 0)
        with mock.patch.multiple(engine_mod, run_once=mock.Mock(side_effect=lambda a, c, x: seen.append(a.dry_run) or 3),
                                 cleanup=mock.Mock(side_effect=lambda a, c, x: seen.append(a.dry_run) or 0),
                                 recategorize=mock.Mock(side_effect=lambda a, c, x: seen.append(a.dry_run) or {"c411-bd": 2})):
            r1 = e.run_task("essai")
            r2 = e.run_task("nettoyage_apercu")
            r3 = e.run_task("rangement_apercu")
        self.assertEqual(seen, [True, True, True])
        self.assertFalse(e.args.dry_run)  # le moteur lui-même n'est pas modifié
        self.assertIn("3 torrent(s) seraient ajoutés", r1["resultat"])
        self.assertIn("rien à nettoyer", r2["resultat"])
        self.assertIn("2 vers c411-bd", r3["resultat"])
        self.assertEqual(e.snapshot()["task"]["id"], "rangement_apercu")

    def test_tache_en_echec(self):
        e = self.make()
        with mock.patch.object(engine_mod, "run_once", side_effect=RuntimeError("c411 injoignable")):
            r = e.run_task("essai")
        self.assertFalse(r["ok"])
        self.assertIn("c411 injoignable", r["resultat"])

    def test_tache_en_tache_de_fond(self):
        e = self.make()
        with mock.patch.multiple(engine_mod, run_once=mock.Mock(return_value=0), maybe_cleanup=mock.Mock(),
                                 maybe_crossseed=mock.Mock(), maybe_report=mock.Mock()):
            e.start()
            TestEngine._wait(lambda: e.snapshot()["last_pass_at"])
            e.submit("bilan")
            TestEngine._wait(lambda: (e.snapshot()["task"] or {}).get("fin"))
            e.stop(5)
        self.assertTrue(e.snapshot()["task"]["ok"])


@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestPagesTableau(WebCase):
    def setUp(self):
        super().setUp()
        self.install()
        self.csrf = re.search(r'name="csrf" content="([^"]+)"', self.client.get("/").text).group(1)

    def test_pages_et_api_protegees(self):
        self.assertEqual(self.client.get("/journal").status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/journal", follow_redirects=False).headers["location"], "/connexion")
        self.assertEqual(self.client.get("/api/journal").status_code, 401)
        self.assertEqual(self.client.get("/api/tableau").status_code, 401)

    def test_journal_sans_secret(self):
        import logging
        enable_logging(self)
        logging.getLogger("c411").error("échec avec cle-secrete-123 et mdp-qbit")
        messages = self.client.get("/api/journal").json()["messages"]
        text = repr(messages)
        self.assertIn("échec avec", text)
        self.assertNotIn("cle-secrete-123", text)
        self.assertNotIn("mdp-qbit", text)

    def test_actions_de_taches_acceptees(self):
        for action in ("essai", "bilan", "nettoyage_apercu", "rangement_apercu"):
            r = self.client.post(f"/api/action/{action}", headers={"X-CSRF-Token": self.csrf})
            self.assertEqual(r.json(), {"ok": True, "action": action})
        self.assertEqual(self.client.post("/api/action/nettoyage", headers={"X-CSRF-Token": self.csrf}).status_code, 404)

    def test_tableau(self):
        self.engine.cfg = cfg()
        self.engine.ctx = {"state": types.SimpleNamespace(seen={})}
        from autodl.tableau import Dashboard
        with mock.patch.object(Dashboard, "_qbittorrent", return_value=([], {"id": "qbittorrent", "ok": True,
                                                                             "nom": "qBittorrent", "detail": ""})):
            data = self.client.get("/api/tableau").json()
        self.assertEqual([s["id"] for s in data["services"]], ["qbittorrent"])
        self.assertEqual((data["ajouts"], data["types"]), ([], []))


class TestCodeInstallation(unittest.TestCase):
    def test_code_conserve_entre_deux_redemarrages_puis_supprime(self):
        if not HAS_WEB:
            self.skipTest("dépendances de l'interface absentes")
        from autodl.web.auth import Auth
        tmp = Path(tempfile.mkdtemp())
        first = Auth(tmp / "interface.json").setup_code
        second = Auth(tmp / "interface.json")
        self.assertEqual(second.setup_code, first)
        self.assertTrue((tmp / "code-installation.txt").exists())
        self.assertIsNone(second.create_admin("a", "x" * 12, first))
        self.assertFalse((tmp / "code-installation.txt").exists())


if __name__ == "__main__":
    unittest.main()
