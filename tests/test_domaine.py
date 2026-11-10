"""Tests de l'accès par domaine et de la double authentification. Aucun accès réseau."""
import importlib.util
import json
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
sys.path.insert(0, str(ROOT / "tests"))

from test_interface import HAS_WEB, WebCase  # noqa: E402

from autodl import domaine  # noqa: E402
from autodl.web import totp  # noqa: E402

if HAS_WEB:
    from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- codes TOTP

class TestTotp(unittest.TestCase):
    SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # « 12345678901234567890 », vecteur de la RFC 6238

    def test_vecteur_rfc(self):
        self.assertEqual(totp.code_at(self.SECRET, 1), "287082")  # T = 59 s
        self.assertEqual(totp.verify(self.SECRET, "287 082", now=59), 1)

    def test_fenetre_et_rejeu(self):
        now = 1_000_000.0
        c = int(now // 30)
        self.assertEqual(totp.verify(self.SECRET, totp.code_at(self.SECRET, c - 1), now=now), c - 1)
        self.assertIsNone(totp.verify(self.SECRET, totp.code_at(self.SECRET, c - 3), now=now))
        self.assertIsNone(totp.verify(self.SECRET, totp.code_at(self.SECRET, c), last_counter=c, now=now))
        self.assertIsNone(totp.verify(self.SECRET, "12345", now=now))

    def test_uri(self):
        self.assertTrue(totp.uri("ABC", "alexis").startswith("otpauth://totp/c411-autodl%3Aalexis?secret=ABC"))


@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestDeuxFacteurs(WebCase):
    def test_connexion_en_deux_etapes(self):
        self.install()
        secret = totp.new_secret()
        now_c = int(time.time() // 30)
        self.assertTrue(self.auth.enable_totp(secret, totp.code_at(secret, now_c)))
        self.client.cookies.clear()
        r = self.login()
        self.assertEqual(r.headers["location"], "/connexion/code")
        self.assertEqual(self.client.get("/", follow_redirects=False).headers["location"], "/connexion")
        page = self.client.get("/connexion/code")
        r = self.client.post("/connexion/code", data={"code": "000000", "csrf": self.csrf_of(page)},
                             follow_redirects=False)
        self.assertIn("Code incorrect", r.text)
        # le code déjà utilisé pour l'activation est refusé : il faut le suivant
        r = self.client.post("/connexion/code", data={"code": totp.code_at(secret, now_c), "csrf": self.csrf_of(r)},
                             follow_redirects=False)
        self.assertIn("Code incorrect", r.text)
        r = self.client.post("/connexion/code", data={"code": totp.code_at(secret, now_c + 1),
                                                      "csrf": self.csrf_of(r)}, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/")
        self.assertEqual(self.client.get("/", follow_redirects=False).status_code, 200)

    def test_page_securite_et_activation(self):
        self.install()
        page = self.client.get("/securite")
        self.assertIn("Désactivée", page.text)
        csrf = self.csrf_of(page)
        page = self.client.post("/securite/2fa/preparer", data={"csrf": csrf})
        key = re.search(r'<div class="secret-key"><code>([A-Z2-7 ]+)</code>', page.text).group(1).replace(" ", "")
        r = self.client.post("/securite/2fa/activer",
                             data={"csrf": csrf, "code": totp.code_at(key, int(time.time() // 30))},
                             follow_redirects=False)
        self.assertEqual(r.headers["location"], "/securite?m=active")
        self.assertTrue(self.auth.totp_enabled())
        self.assertTrue(self.auth.reset_totp())  # secours en ligne de commande
        self.assertFalse(self.auth.totp_enabled())

    def test_blocage_global_depuis_internet(self):
        from autodl.web import auth as auth_mod
        self.install()
        for i in range(auth_mod.MAX_REMOTE_FAILURES):
            self.auth.login("alexis", "faux", f"203.0.113.{i}", remote=True)
        self.assertGreater(self.auth.locked("198.51.100.7", remote=True), 0)  # nouvelle adresse Internet
        self.assertEqual(self.auth.locked("172.19.0.1", remote=False), 0)  # le tunnel reste ouvert
        self.assertIsNotNone(self.auth.login("alexis", "un-mot-de-passe-solide", "172.19.0.1"))


# --------------------------------------------------------------------------- vérifications du domaine

class TestDomaine(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())

    def check(self, ips, status=None, request=None, domain="c411.exemple.fr", pub="188.0.0.1"):
        if status is not None:
            (self.base / "etat.json").write_text(json.dumps(status), encoding="utf-8")
        if request is not None:
            (self.base / "demande.json").write_text(json.dumps(request), encoding="utf-8")
        with mock.patch.object(domaine, "resolve", return_value=ips), \
                mock.patch.object(domaine, "public_ip", return_value=pub):
            out = domaine.check({"domain_on": True, "domain": domain}, base=self.base, now=10_000.0)
        return out, {s["id"]: s["etat"] for s in out["etapes"]}

    def test_inactif_par_defaut(self):
        out = domaine.check({"domain_on": False, "domain": ""}, base=self.base)
        self.assertEqual(out["etapes"][0]["etat"], "inactif")

    def test_nom_invalide(self):
        self.assertEqual(self.check([], domain="pas un domaine")[1]["nom"], "erreur")

    def test_dns(self):
        self.assertEqual(self.check([])[1]["dns"], "erreur")
        self.assertEqual(self.check(["9.9.9.9"])[1]["dns"], "erreur")  # pointe ailleurs
        self.assertEqual(self.check(["188.0.0.1"])[1]["dns"], "ok")

    def test_cloudflare_proxy_alerte(self):
        out, steps = self.check(["104.21.3.4", "172.67.1.2"])
        self.assertTrue(out["cloudflare"])
        self.assertEqual(steps["cloudflare"], "alerte")
        self.assertIn("nuage orange", next(s for s in out["etapes"] if s["id"] == "cloudflare")["message"])

    def test_assistant_absent(self):
        self.assertEqual(self.check(["188.0.0.1"])[1]["assistant"], "erreur")
        self.assertEqual(self.check(["188.0.0.1"], status={"vu_le": 1.0})[1]["assistant"], "erreur")  # muet

    def test_parcours_complet(self):
        req = {"id": 5, "actif": True, "domaine": "c411.exemple.fr"}
        status = {"vu_le": 9_990.0, "demande_id": 5, "domaine": "c411.exemple.fr", "caddy": "v2", "erreur": None,
                  "certificat": {"valide": True, "emetteur": "Let's Encrypt", "expire": "01/02/2027",
                                 "expire_ts": 10_000.0 + 80 * 86400}}
        out, steps = self.check(["188.0.0.1"], status, req)
        self.assertTrue(out["pret"])
        self.assertEqual(out["url"], "https://c411.exemple.fr")
        self.assertIn("réactiver le proxy", out["etapes"][-1]["message"])
        # certificat pas encore là, pare-feu fermé : on le dit
        status.update(certificat={"valide": False, "erreur": "Pas encore."}, pare_feu_80=False)
        out, steps = self.check(["188.0.0.1"], status, req)
        self.assertEqual(steps["ssl"], "attente")
        self.assertIn("ufw allow 80/tcp", out["etapes"][-1]["message"])
        # demande pas encore appliquée
        out, steps = self.check(["188.0.0.1"], dict(status, demande_id=4), req)
        self.assertEqual(steps["caddy"], "attente")
        # proxy réactivé après le certificat : tout va bien
        status.update(certificat={"valide": True, "emetteur": "Let's Encrypt", "expire_ts": 10_000.0 + 80 * 86400})
        out, steps = self.check(["104.21.3.4"], status, req)
        self.assertEqual(steps["cloudflare"], "ok")
        self.assertTrue(out["pret"])

    def test_demande_ne_transmet_que_le_domaine(self):
        with self.assertRaises(ValueError):
            domaine.write_request("evil.com {\n file_server", True, base=self.base)
        req = domaine.write_request("C411.Exemple.FR", True, base=self.base)
        self.assertEqual(req["domaine"], "c411.exemple.fr")
        self.assertEqual(domaine.write_request("", False, base=self.base)["domaine"], "")


class TestAssistantServeur(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("assistant", ROOT / "serveur" / "assistant_domaine.py")
        self.a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.a)

    def test_modele(self):
        content, domain = self.a.snippet_for({"actif": True, "domaine": "c411.exemple.fr"}, "127.0.0.1:8411")
        self.assertEqual(domain, "c411.exemple.fr")
        self.assertTrue(content.splitlines()[1].startswith("c411.exemple.fr {"))
        self.assertIn("reverse_proxy 127.0.0.1:8411", content)
        self.assertIn("CF-Connecting-IP", content)

    def test_refuse_toute_injection(self):
        for bad in ("a.com {\n\troot * /", "a.com/x", "*.a.com", "localhost", "a..com", "-a.com", "a.com\nb.com"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.a.snippet_for({"actif": True, "domaine": bad}, "127.0.0.1:8411")

    def test_desactive(self):
        self.assertEqual(self.a.snippet_for({"actif": False, "domaine": "a.com"}, "x"), (self.a.EMPTY, ""))


# --------------------------------------------------------------------------- hôte et adresse du visiteur

@unittest.skipUnless(HAS_WEB, "dépendances de l'interface absentes")
class TestHoteEtVisiteur(WebCase):
    def test_visiteur(self):
        from autodl.web.app import visitor

        def req(peer, host, real=None):
            headers = {"host": host}
            if real:
                headers["x-real-ip"] = real
            return types.SimpleNamespace(client=types.SimpleNamespace(host=peer), headers=headers)

        w = visitor(req("172.19.0.1", "c411.exemple.fr", "203.0.113.9"), "c411.exemple.fr")
        self.assertEqual((w["ip"], w["remote"], w["https"]), ("203.0.113.9", True, True))
        w = visitor(req("93.184.216.34", "c411.exemple.fr", "1.2.3.4"), "c411.exemple.fr")
        self.assertEqual((w["ip"], w["remote"]), ("93.184.216.34", False))  # en-tête non cru
        w = visitor(req("172.19.0.1", "localhost:8411"), "c411.exemple.fr")
        self.assertEqual((w["ip"], w["remote"], w["host"]), ("172.19.0.1", False, "localhost"))

    def test_hote_refuse_en_mode_domaine(self):
        from autodl.web.app import create_app
        self.store.save({**self.store.values(), "DOMAINE_ACTIF": "true", "DOMAINE_NOM": "c411.exemple.fr"})
        client = TestClient(create_app(self.engine, self.auth, self.store), base_url="http://localhost")
        self.assertEqual(client.get("/sante").status_code, 200)
        self.assertEqual(client.get("/sante", headers={"host": "pirate.example"}).status_code, 421)
        self.assertEqual(client.get("/sante", headers={"host": "c411.exemple.fr"}).status_code, 200)
