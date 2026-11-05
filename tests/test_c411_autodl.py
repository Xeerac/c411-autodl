"""Tests de c411-autodl. Aucun accès réseau : c411, qBittorrent et cross-seed sont simulés.

Lancer :  python -m unittest discover -s tests -v
"""
import hashlib
import logging
import re
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from autodl import (c411, cli, commun, config, contenu, filtres, moteur,  # noqa: E402
                    notifications, qbit, stockage)

# Tous les éléments du programme réunis sous « m », comme avant le découpage en modules
m = types.SimpleNamespace()
for _module in (commun, config, c411, qbit, notifications, stockage, contenu, filtres, moteur, cli):
    for _name in dir(_module):
        if not _name.startswith("__") or _name == "__version__":
            setattr(m, _name, getattr(_module, _name))

logging.disable(logging.CRITICAL)  # pas de journal pendant les tests
MB, GB = 1024**2, 1024**3


def base_cfg(**over):
    cfg = dict(cats="7020", page_size=100, queries=[], min_completed=1, min_seeders=1, max_seeders=0,
               min_leechers=0, max_size=0, min_size=0, exclude=[], formats=[], required=[],
               excluded_groups=[], exclude_regex=None, tri="recent", max_per_run=50, min_free_gb=20,
               min_ratio=2.0, profile_key="x", qbit_category="c411-ebook", qbit_tags="c411,autodl",
               qbit_savepath="", qbit_paused=False, cat_par_type=False, cat_prefix="c411",
               own_tag="autodl", cleanup_action="fichiers", cs_url="", cs_key="", bilan=False, bilan_heure=8,
               fl_mode=False, fl_cats=[], fl_max_per_run=100, fl_max_size=None, fl_ignore_formats=True,
               alert=True, alert_after=3)
    cfg.update(over)
    return cfg


def item(title="Livre.FR.[EPUB]-NOTAG", size=2 * MB, completed=3, seeders=5, leechers=2,
         infohash="", category="7020", dl_factor=1.0):
    return dict(title=title, link="https://c411.org/dl/" + title, size=size, infohash=infohash,
                completed=completed, seeders=seeders, leechers=leechers, category=category,
                page="https://c411.org/torrents/x", dl_factor=dl_factor)


def args(**over):
    a = dict(dry_run=False, rattrapage=False, pages=1, boucle=300)
    a.update(over)
    return types.SimpleNamespace(**a)


# --------------------------------------------------------------------------- outils de base

class TestOutils(unittest.TestCase):
    def test_infohash(self):
        info = b"d6:lengthi10e4:name6:a.epub12:piece lengthi16384e6:pieces20:" + b"x" * 20 + b"7:privatei1ee"
        torrent = b"d8:announce10:http://x/a4:info" + info + b"e"
        self.assertEqual(m.infohash_of(torrent), hashlib.sha1(info).hexdigest())

    def test_infohash_invalide(self):
        with self.assertRaises(ValueError):
            m.infohash_of(b"<html>pas un torrent</html>")

    def test_parse_size(self):
        for raw, expected in [("500Mo", 500 * MB), ("2Go", 2 * GB), ("1,5 GB", int(1.5 * GB)),
                              ("800", 800 * MB), ("100Ko", 100 * 1024), ("0", 0), ("", 0)]:
            self.assertEqual(m.parse_size(raw), expected, raw)

    def test_leechers(self):
        self.assertEqual(m._leechers({"leechers": "7", "seeders": "2", "peers": "3"}), 7)
        self.assertEqual(m._leechers({"seeders": "2", "peers": "5"}), 3)
        self.assertEqual(m._leechers({"seeders": "4", "peers": "2"}), 0)
        self.assertEqual(m._leechers({}), -1)

    def test_groupe_et_formats(self):
        self.assertEqual(m._group("Les.Collabos.Laurent.Joly.FR.[Epub]-NOTAG"), "notag")
        self.assertEqual(m._group("Titre - OneShot - [CBZ-PDF]"), "")
        self.assertTrue(m._has_token("radiant.t20.fr.[cbz]-themouche", "cbz"))
        self.assertFalse(m._has_token("radiant.t20.fr.[cbz]-themouche", "cb"))
        self.assertFalse(m._has_token("epubfoo", "epub"))


class TestTorznab(unittest.TestCase):
    XML = b'''<?xml version="1.0"?><rss xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel>
<item><title>Livre A</title><link>https://c411.org/torrents/abc</link><comments>https://c411.org/torrents/abc</comments>
<enclosure url="https://c411.org/api?t=get&amp;id=abc" length="1048576"/>
<torznab:attr name="seeders" value="3"/><torznab:attr name="peers" value="8"/><torznab:attr name="grabs" value="0"/>
<torznab:attr name="infohash" value="ABC"/><torznab:attr name="category" value="7030"/>
<torznab:attr name="downloadvolumefactor" value="0"/></item>
</channel></rss>'''

    def test_lecture(self):
        c = m.C411("https://c411.org", "k", 0)
        c._get = lambda url: self.XML
        it = c.search("7020", 0, 100)[0]
        self.assertEqual(it["link"], "https://c411.org/api?t=get&id=abc")  # l'enclosure, pas la page web
        self.assertEqual((it["infohash"], it["seeders"], it["leechers"], it["completed"]), ("abc", 3, 5, 0))
        self.assertEqual((it["category"], it["dl_factor"], it["size"]), ("7030", 0.0, 1048576))


# --------------------------------------------------------------------------- filtres et tri

class TestFiltres(unittest.TestCase):
    def check(self, over, it, expected):
        self.assertEqual(m._reject(it, base_cfg(**over)), expected)

    def test_accepte(self):
        self.check({}, item(), None)

    def test_completes_et_seeders(self):
        self.check({}, item(completed=0), "complétés")
        self.check({}, item(seeders=0), "seeders")
        self.check({"max_seeders": 10}, item(seeders=50), "trop de seeders")
        self.check({"max_seeders": 10}, item(seeders=10), None)

    def test_leechers(self):
        self.check({"min_leechers": 1}, item(leechers=0), "pas assez de leechers")
        self.check({"min_leechers": 1}, item(leechers=-1), "pas assez de leechers")

    def test_tailles(self):
        self.check({"min_size": 100 * 1024}, item(size=10 * 1024), "trop petit")
        self.check({"max_size": MB}, item(size=2 * MB), "trop gros")

    def test_qualite(self):
        self.check({"formats": ["epub", "cbz"]}, item(title="Scan.FR.[PDF]-NOTAG"), "format non accepté")
        self.check({"formats": ["epub", "cbz"]}, item(title="BD.T01.FR.[CBZ]-PRINTER"), None)
        self.check({"required": ["fr", "french"]}, item(title="Book.EN.[EPUB]-X"), "aucun mot requis")
        self.check({"excluded_groups": ["notag"]}, item(), "groupe exclu")
        self.check({"exclude": ["sample"]}, item(title="Livre.Sample.[EPUB]-X"), "mot exclu")
        self.check({"exclude_regex": re.compile(r"\bscann?e?\b|\bocr\b", re.I)},
                   item(title="Livre.Scanne.FR.[PDF]-X"), "regex d'exclusion")
        self.check({"exclude_regex": re.compile(r"\bscann?e?\b|\bocr\b", re.I)},
                   item(title="Le.Scandale.FR.[EPUB]-X"), None)

    def test_tri(self):
        items = [item(title="A", seeders=50, leechers=0), item(title="B", seeders=1, leechers=5),
                 item(title="C", seeders=3, leechers=3), item(title="D", seeders=1, leechers=5)]
        self.assertEqual([i["title"] for i in m._ordered(iter(items), {"tri": "interet"})], ["B", "D", "C", "A"])
        self.assertEqual([i["title"] for i in m._ordered(iter(items), {"tri": "recent"})], ["A", "B", "C", "D"])


# --------------------------------------------------------------------------- types et catégories

class TestTypes(unittest.TestCase):
    def test_categories_torznab(self):
        for cat, kind in [("7020", "ebook"), ("7030", "bd"), ("7010", "presse"), ("3030", "livre-audio"),
                          ("3010", "musique"), ("2030", "film"), ("5000", "serie"), ("4050", "logiciel"),
                          ("1080", "jeu"), ("6010", "adulte")]:
            self.assertEqual(m.content_type(cat), kind, cat)

    def test_devine_d_apres_le_titre(self):
        self.assertEqual(m.content_type("", "Radiant.T20.FR.[CBZ]-X"), "bd")
        self.assertEqual(m.guess_type("Victor.Hugo.FR.[MP3.64.Kbps]-NOTAG"), "livre-audio")
        self.assertEqual(m.guess_type("Le.Livre.FR.[EPUB]-NOTAG"), "ebook")

    def test_categorie_qbittorrent(self):
        self.assertEqual(m.qbit_category("bd", base_cfg()), "c411-ebook")
        self.assertEqual(m.qbit_category("bd", base_cfg(cat_par_type=True)), "c411-bd")
        self.assertEqual(m.qbit_category("presse", base_cfg(cat_par_type=True, cat_prefix="tk")), "tk-presse")


# --------------------------------------------------------------------------- passage complet

class FakeC411:
    def __init__(self, items):
        self.items, self.cats = items, []

    def search(self, cats, offset, limit, query=""):
        self.cats.append(cats)
        return self.items if offset == 0 else []

    def download(self, link):
        return b"d4:infod4:name1:xee"


class FakeProfile:
    def __init__(self, up, down, allowed=True, freeleech=None):
        self.v = (up, down, allowed)
        self.last_profile = {"freeleech": {"active": bool(freeleech), "sources": freeleech or []}}

    def ratio(self):
        up, down, allowed = self.v
        return up / down, up, down, allowed


class FakeQbit:
    def __init__(self, torrents=None, trackers=None):
        self.added, self.categories, self.actions = [], [], []
        self.t, self.tr = torrents or [], trackers or {}

    def login(self, quiet=False): pass
    def hashes(self): return {t["hash"] for t in self.t}
    def free_space(self): return 1000 * GB
    def ensure_category(self, name, path): self.categories.append(name)
    def add(self, fn, data, category, tags="", *a): self.added.append((fn, category)); self.tags = tags
    def set_category(self, h, cat): self.actions.append(("category", h, cat))
    def set_auto_management(self, h, enable): self.actions.append(("auto", h, enable))
    def torrents(self, tag=""): return [t for t in self.t if not tag or tag in t.get("tags", "").split(",")]
    def trackers(self, h): return self.tr[h]
    def delete(self, h, delete_files): self.actions.append(("delete", h, delete_files))
    def stop(self, h): self.actions.append(("stop", h))
    def add_tags(self, h, tags): self.actions.append(("tag", h, tags))


class TestPassage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def ctx(self, items, profile, qbit=None):
        return dict(c411=FakeC411(items), profile=profile, qbit=qbit or FakeQbit(),
                    state=m.State(self.tmp / "s.json"), tracking=m.Tracking(self.tmp / "t.json"))

    def test_pause_sous_le_ratio(self):
        ctx = self.ctx([item(infohash="a")], FakeProfile(190 * GB, 100 * GB))
        self.assertEqual(m.run_once(args(), base_cfg(), ctx), 0)
        self.assertEqual(ctx["qbit"].added, [])

    def test_bloque_par_c411(self):
        ctx = self.ctx([item(infohash="a")], FakeProfile(500 * GB, 100 * GB, allowed=False))
        self.assertEqual(m.run_once(args(), base_cfg(), ctx), 0)

    def test_ratio_projete_et_freeleech(self):
        items = [item(title="petit", infohash="p", size=1 * GB),
                 item(title="gros", infohash="g", size=30 * GB),
                 item(title="gros-freeleech", infohash="f", size=60 * GB, dl_factor=0.0)]
        ctx = self.ctx(items, FakeProfile(230 * GB, 100 * GB))
        m.run_once(args(), base_cfg(), ctx)
        self.assertEqual([fn for fn, _ in ctx["qbit"].added], ["p.torrent", "f.torrent"])

    def test_categorie_par_type_et_historique(self):
        items = [item(title="BD.T01.[CBZ]-X", infohash="b", category="7030"),
                 item(title="Journal.[PDF]-X", infohash="j", category="7010")]
        ctx = self.ctx(items, FakeProfile(500 * GB, 100 * GB))
        m.run_once(args(), base_cfg(cat_par_type=True), ctx)
        self.assertEqual(ctx["qbit"].added, [("b.torrent", "c411-bd"), ("j.torrent", "c411-presse")])
        self.assertEqual(ctx["qbit"].categories, ["c411-bd", "c411-presse"])  # créées une seule fois
        self.assertEqual(ctx["state"].seen["b"]["type"], "bd")

    def test_dry_run_n_ajoute_rien(self):
        ctx = self.ctx([item(infohash="a")], FakeProfile(500 * GB, 100 * GB))
        self.assertEqual(m.run_once(args(dry_run=True), base_cfg(), ctx), 1)
        self.assertEqual(ctx["qbit"].added, [])
        self.assertFalse((self.tmp / "s.json").exists())

    def test_deja_present(self):
        qbit = FakeQbit(torrents=[{"hash": "a"}])
        ctx = self.ctx([item(infohash="a")], FakeProfile(500 * GB, 100 * GB), qbit)
        self.assertEqual(m.run_once(args(), base_cfg(), ctx), 0)


# --------------------------------------------------------------------------- nettoyage

REMOVED = "Torrent removed by its uploader"


def tr(host, status, msg=""):
    return {"url": f"https://{host}/announce/xxx", "status": status, "msg": msg}


def tor(h, tags="autodl,c411", path=None, progress=1.0, size=MB, uploaded=0, downloaded=0, name=None):
    return {"hash": h, "name": name or f"T-{h}", "tags": tags, "content_path": path or f"/d/{h}",
            "progress": progress, "size": size, "uploaded": uploaded, "downloaded": downloaded}


class TestNettoyage(unittest.TestCase):
    REMOVED_BOTH = [tr("c411.org", 5, REMOVED), tr("tk.c411.tw", 5, REMOVED)]

    def run_cleanup(self, torrents, trackers, exists, action="fichiers", dry=False):
        qbit = FakeQbit(torrents, trackers)
        c411 = types.SimpleNamespace(exists=lambda h: exists[h])
        n = m.cleanup(args(dry_run=dry), base_cfg(cleanup_action=action), {"qbit": qbit, "c411": c411})
        return n, qbit.actions

    def test_supprime_confirme(self):
        self.assertEqual(self.run_cleanup([tor("a")], {"a": self.REMOVED_BOTH}, {"a": False})[1],
                         [("delete", "a", True)])

    def test_jamais_sans_confirmation_de_l_api(self):
        for exists in (True, None):  # toujours sur c411, ou API injoignable
            self.assertEqual(self.run_cleanup([tor("a")], {"a": self.REMOVED_BOTH}, {"a": exists})[1], [])

    def test_jamais_si_un_tracker_fonctionne(self):
        trackers = {"a": [tr("c411.org", 2), tr("tk.c411.tw", 5, REMOVED)]}
        self.assertEqual(self.run_cleanup([tor("a")], trackers, {"a": False})[1], [])

    def test_jamais_pour_une_erreur_sans_rapport(self):
        trackers = {"a": [tr("c411.org", 4, "Connection timed out")]}
        self.assertEqual(self.run_cleanup([tor("a")], trackers, {"a": False})[1], [])

    def test_jamais_sans_le_tag(self):
        for tags in ("c411", "autodl2"):
            self.assertEqual(self.run_cleanup([tor("a", tags=tags)], {"a": self.REMOVED_BOTH}, {"a": False})[1], [])

    def test_fichiers_partages_conserves(self):
        torrents = [tor("a", path="/d/x"), tor("b", tags="cross-seed", path="/d/x")]
        trackers = {"a": self.REMOVED_BOTH, "b": [tr("tr4ker.net", 2)]}
        self.assertEqual(self.run_cleanup(torrents, trackers, {"a": False})[1], [("delete", "a", False)])

    def test_actions(self):
        self.assertEqual(self.run_cleanup([tor("a")], {"a": self.REMOVED_BOTH}, {"a": False}, "torrent")[1],
                         [("delete", "a", False)])
        self.assertEqual(self.run_cleanup([tor("a")], {"a": self.REMOVED_BOTH}, {"a": False}, "pause")[1],
                         [("stop", "a"), ("tag", "a", "c411-supprime")])

    def test_dry_run(self):
        n, actions = self.run_cleanup([tor("a")], {"a": self.REMOVED_BOTH}, {"a": False}, dry=True)
        self.assertEqual((n, actions), (1, []))


# --------------------------------------------------------------------------- cross-seed

class TestCrossSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = base_cfg(cs_url="http://localhost:2468", cs_key="k")

    def ctx(self, torrents):
        return {"qbit": FakeQbit(torrents), "tracking": m.Tracking(self.tmp / "t.json")}

    def test_premier_lancement_ne_renvoie_pas_l_existant(self):
        ctx = self.ctx([tor("a"), tor("b")])
        with mock.patch.object(moteur, "_crossseed_webhook") as hook:
            self.assertEqual(m.maybe_crossseed(args(), self.cfg, ctx), 0)
            hook.assert_not_called()
        self.assertEqual(sorted(ctx["tracking"].data["crossseed_envoyes"]), ["a", "b"])

    def test_nouveaux_termines_envoyes_une_seule_fois(self):
        ctx = self.ctx([tor("a")])
        m.maybe_crossseed(args(), self.cfg, ctx)  # premier lancement
        ctx["qbit"].t += [tor("b"), tor("c", progress=0.4), tor("d", tags="manuel")]
        with mock.patch.object(moteur, "_crossseed_webhook") as hook:
            self.assertEqual(m.maybe_crossseed(args(), self.cfg, ctx), 1)
            self.assertEqual(m.maybe_crossseed(args(), self.cfg, ctx), 0)  # déjà envoyé
        hook.assert_called_once_with(self.cfg, "b")

    def test_cross_seed_injoignable_on_reessaie(self):
        ctx = self.ctx([tor("a")])
        m.maybe_crossseed(args(), self.cfg, ctx)
        ctx["qbit"].t.append(tor("b"))
        with mock.patch.object(moteur, "_crossseed_webhook", side_effect=OSError("refusé")):
            self.assertEqual(m.maybe_crossseed(args(), self.cfg, ctx), 0)
        with mock.patch.object(moteur, "_crossseed_webhook") as hook:
            self.assertEqual(m.maybe_crossseed(args(), self.cfg, ctx), 1)
            hook.assert_called_once_with(self.cfg, "b")

    def test_desactive_sans_url(self):
        self.assertEqual(m.maybe_crossseed(args(), base_cfg(), {}), 0)


# --------------------------------------------------------------------------- bilan

class TestBilan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_bilan(self):
        state = m.State(self.tmp / "s.json")
        state.add("a", "BD.[CBZ]-X", "bd", 100 * MB)
        state.add("b", "Livre.[EPUB]-X", "ebook", MB)
        qbit = FakeQbit([tor("a", size=100 * MB, uploaded=500 * MB, downloaded=100 * MB, name="BD.[CBZ]-X"),
                         tor("b", size=MB, uploaded=1 * MB, downloaded=MB, name="Livre.[EPUB]-X")])
        tracking = m.Tracking(self.tmp / "t.json")
        tracking.data["bilan"] = {"time": 0, "uploaded": {"a": 200 * MB}, "downloaded": {"a": 100 * MB}, "ratio": 2.5}
        ctx = {"qbit": qbit, "state": state, "tracking": tracking, "profile": FakeProfile(280 * GB, 100 * GB)}
        text, snap = m.build_report(base_cfg(), ctx)
        self.assertIn("**301.0 Mo envoyés**", text)        # 300 Mo (a) + 1 Mo (b, nouveau)
        self.assertIn("Ratio c411 : 2.80 (+0.30)", text)
        self.assertLess(text.index("bd : ×5.00"), text.index("ebook : ×1.00"))  # trié par rendement
        self.assertEqual(snap["uploaded"]["a"], 500 * MB)

    def test_premier_releve_puis_une_fois_par_jour(self):
        state = m.State(self.tmp / "s.json")
        tracking = m.Tracking(self.tmp / "t.json")
        notifier = mock.Mock()
        ctx = {"qbit": FakeQbit([tor("a")]), "state": state, "tracking": tracking,
               "profile": FakeProfile(1, 1), "notifier": notifier}
        cfg = base_cfg(bilan=True, bilan_heure=0, profile_key="")
        m.maybe_report(args(), cfg, ctx)        # premier relevé : pas de message
        notifier.send.assert_not_called()
        self.assertIn("bilan", tracking.data)
        m.maybe_report(args(), cfg, ctx)        # même jour : rien
        notifier.send.assert_not_called()
        tracking.data["bilan_date"] = "2000-01-01"
        m.maybe_report(args(), cfg, ctx)        # jour suivant : bilan envoyé
        notifier.send.assert_called_once()


# --------------------------------------------------------------------------- notifications

class TestNotifications(unittest.TestCase):
    def test_discord_et_telegram(self):
        sent = []
        n = m.Notifier("https://discord.example/webhook", "TOKEN", "123", True)
        n._post = lambda url, payload: sent.append((url, payload))
        n.added([dict(title="BD <B> & co [CBZ]", page="https://c411.org/torrents/b", size=150 * MB, dl_factor=0.0)],
                150 * MB, 2.345)
        discord, telegram = sent[0][1]["content"], sent[1][1]["text"]
        self.assertIn("[BD <B> & co (CBZ)](https://c411.org/torrents/b)", discord)
        self.assertIn("freeleech", discord)
        self.assertIn('<a href="https://c411.org/torrents/b">BD &lt;B&gt; &amp; co (CBZ)</a>', telegram)
        self.assertIn("ratio ≈ 2.35", telegram)


# --------------------------------------------------------------------------- mode freeleech

class TestFreeleech(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def ctx(self, items, profile):
        return dict(c411=FakeC411(items), profile=profile, qbit=FakeQbit(), notifier=mock.Mock(),
                    state=m.State(self.tmp / "s.json"), tracking=m.Tracking(self.tmp / "t.json"))

    def test_lecture_du_profil(self):
        self.assertEqual(m.freeleech_sources({"freeleech": {"active": True, "sources": ["campaign"]}}), ["campaign"])
        self.assertEqual(m.freeleech_sources({"freeleech": {"active": False}}), [])
        self.assertEqual(m.freeleech_sources(None), [])

    def test_reglages_elargis(self):
        cfg = base_cfg(cats="7020,7030", fl_cats=["2030", "7030"], fl_max_size=50 * GB, formats=["epub"])
        fl = m.freeleech_cfg(cfg)
        self.assertEqual(fl["cats"], "7020,7030,2030")
        self.assertEqual((fl["max_per_run"], fl["max_size"], fl["formats"]), (100, 50 * GB, []))
        self.assertEqual(fl["qbit_tags"], "c411,autodl,freeleech")
        self.assertEqual(cfg["cats"], "7020,7030")  # la config normale n'est pas modifiée

    def test_pas_de_pause_ni_de_limite_de_ratio_en_freeleech(self):
        items = [item(title="Film.2160p-X", infohash="f", size=60 * GB, category="2030")]
        # Ratio 1.90 : en temps normal, pause. En freeleech, on télécharge quand même.
        ctx = self.ctx(items, FakeProfile(190 * GB, 100 * GB, freeleech=["campaign"]))
        m.run_once(args(), base_cfg(fl_mode=True, fl_cats=["2030"]), ctx)
        self.assertEqual([fn for fn, _ in ctx["qbit"].added], ["f.torrent"])
        self.assertIn("freeleech", ctx["qbit"].tags)
        self.assertEqual(ctx["c411"].cats[0], "7020,2030")

    def test_mode_desactive(self):
        ctx = self.ctx([item(infohash="a")], FakeProfile(190 * GB, 100 * GB, freeleech=["campaign"]))
        m.run_once(args(), base_cfg(fl_mode=False), ctx)
        self.assertEqual(ctx["qbit"].added, [])  # FREELEECH_MODE=false : pause normale

    def test_notification_au_debut_et_a_la_fin(self):
        ctx = self.ctx([], FakeProfile(300 * GB, 100 * GB, freeleech=["campaign"]))
        cfg = base_cfg(fl_mode=True)
        m.run_once(args(), cfg, ctx)
        m.run_once(args(), cfg, ctx)  # toujours actif : pas de nouveau message
        ctx["profile"] = FakeProfile(300 * GB, 100 * GB)
        m.run_once(args(), cfg, ctx)
        messages = [c.args[0] for c in ctx["notifier"].send.call_args_list]
        self.assertEqual(len(messages), 2)
        self.assertIn("Freeleech actif", messages[0])
        self.assertIn("Freeleech terminé", messages[1])


# --------------------------------------------------------------------------- rangement

class TestRangement(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def run_recat(self, torrents, found, keep=False, dry=False, state_types=None):
        state = m.State(self.tmp / "s.json")
        for t in torrents:
            state.add(t["hash"], t["name"], (state_types or {}).get(t["hash"], ""))
        c411 = types.SimpleNamespace(search=lambda cats, off, lim, q="": [
            item(title=q, infohash=h, category=cat) for h, cat in found.items()])
        qbit = FakeQbit(torrents)
        summary = m.recategorize(args(dry_run=dry), base_cfg(), {"qbit": qbit, "c411": c411, "state": state},
                                 keep_location=keep)
        return summary, qbit.actions, state

    def t(self, h, cat="c411-ebook", path=None, tags="autodl,c411"):
        d = tor(h, path=path, tags=tags, name=f"Titre-{h}")
        d["category"] = cat
        return d

    def test_type_retrouve_via_c411(self):
        summary, actions, state = self.run_recat([self.t("a"), self.t("b")], {"a": "7030", "b": "7010"})
        self.assertEqual(summary, {"c411-bd": 1, "c411-presse": 1})
        self.assertIn(("category", "a", "c411-bd"), actions)
        self.assertEqual(state.seen["a"]["type"], "bd")  # mémorisé pour le bilan

    def test_deja_bien_range(self):
        summary, actions, _ = self.run_recat([self.t("a", cat="c411-bd")], {"a": "7030"})
        self.assertEqual((summary, actions), ({}, []))

    def test_fichiers_partages_laisses_en_place(self):
        torrents = [self.t("a", path="/d/x"), self.t("cs", path="/d/x", tags="cross-seed")]
        summary, actions, _ = self.run_recat(torrents, {"a": "7030"})
        self.assertEqual(actions, [])

    def test_garder_emplacement(self):
        torrents = [self.t("a", path="/d/x"), self.t("cs", path="/d/x", tags="cross-seed")]
        _, actions, _ = self.run_recat(torrents, {"a": "7030"}, keep=True)
        self.assertEqual(actions, [("auto", "a", False), ("category", "a", "c411-bd")])

    def test_dry_run(self):
        summary, actions, _ = self.run_recat([self.t("a")], {"a": "7030"}, dry=True)
        self.assertEqual((summary, actions), ({"c411-bd": 1}, []))

    def test_type_deja_connu_pas_de_recherche(self):
        summary, _, _ = self.run_recat([self.t("a")], {}, state_types={"a": "livre-audio"})
        self.assertEqual(summary, {"c411-livre-audio": 1})


# --------------------------------------------------------------------------- alerte de panne

class TestAlerte(unittest.TestCase):
    def test_panne_puis_reprise(self):
        notifier = mock.Mock()
        ctx, cfg = {"notifier": notifier}, base_cfg(alert_after=3)
        errors = 0
        for _ in range(5):
            errors = m.watchdog(cfg, ctx, errors, RuntimeError("seedbox injoignable"))
        self.assertEqual(notifier.send.call_count, 1)  # une seule alerte, au 3e échec
        self.assertIn("en panne", notifier.send.call_args[0][0])
        self.assertIn("seedbox injoignable", notifier.send.call_args[0][0])
        errors = m.watchdog(cfg, ctx, errors)
        self.assertEqual(errors, 0)
        self.assertIn("fonctionne à nouveau", notifier.send.call_args[0][0])

    def test_echec_isole_sans_alerte(self):
        notifier = mock.Mock()
        ctx, cfg = {"notifier": notifier}, base_cfg(alert_after=3)
        errors = m.watchdog(cfg, ctx, 0, RuntimeError("x"))
        errors = m.watchdog(cfg, ctx, errors)
        notifier.send.assert_not_called()

    def test_alerte_desactivee(self):
        notifier = mock.Mock()
        errors = 0
        for _ in range(4):
            errors = m.watchdog(base_cfg(alert=False), {"notifier": notifier}, errors, RuntimeError("x"))
        notifier.send.assert_not_called()

    def test_duree(self):
        self.assertEqual(m._duration(5 * 60), "5 min")
        self.assertEqual(m._duration(2 * 3600 + 7 * 60), "2 h 07")


# --------------------------------------------------------------------------- schéma de configuration

class TestSchema(unittest.TestCase):
    def test_noms_et_cles_uniques(self):
        envs = [s.env for s in config.SETTINGS]
        keys = [s.key for s in config.SETTINGS]
        self.assertEqual(len(envs), len(set(envs)))
        self.assertEqual(len(keys), len(set(keys)))

    def test_groupes_et_types_connus(self):
        kinds = {"str", "secret", "int", "float", "bool", "size", "size_opt", "words", "list", "regex", "choice"}
        for s in config.SETTINGS:
            self.assertIn(s.group, config.GROUPS, s.env)
            self.assertIn(s.kind, kinds, s.env)
            self.assertTrue(s.label, s.env)
            if s.kind == "choice":
                self.assertIn(s.default, s.choices, s.env)

    def test_env_example_complet(self):
        """Chaque réglage du schéma est documenté dans .env.example, et inversement."""
        example = config.read_env_file(ROOT / ".env.example")
        schema = {s.env for s in config.SETTINGS}
        self.assertEqual(sorted(schema - set(example)), [], "absents de .env.example")
        self.assertEqual(sorted(set(example) - schema), [], "inconnus du schéma")

    def test_valeurs_par_defaut(self):
        cfg, errors = config.build_cfg({"C411_API_KEY": "k", "QBIT_URL": "u", "QBIT_USER": "u",
                                        "QBIT_PASS": "p", "MIN_RATIO": "0"})
        self.assertEqual(errors, [])
        self.assertEqual(set(cfg), {s.key for s in config.SETTINGS})
        self.assertEqual((cfg["pages"], cfg["tri"], cfg["max_per_run"], cfg["fl_max_size"]), (1, "interet", 50, None))

    def test_conversions(self):
        cfg, _ = config.build_cfg({"TAILLE_MAX": "2Go", "FORMATS": "EPUB, Cbz", "MIN_RATIO": "1,5",
                                   "QBIT_PAUSED": "oui", "TRI": "RECENT", "FREELEECH_CATEGORIES": "2030, 5000"})
        self.assertEqual((cfg["max_size"], cfg["formats"], cfg["min_ratio"]), (2 * GB, ["epub", "cbz"], 1.5))
        self.assertEqual((cfg["qbit_paused"], cfg["tri"], cfg["fl_cats"]), (True, "recent", ["2030", "5000"]))

    def test_vide_egal_defaut(self):
        cfg, _ = config.build_cfg({"C411_URL": "", "REQUEST_DELAY": " ", "NETTOYAGE_TAG": ""})
        self.assertEqual((cfg["c411_url"], cfg["delay"], cfg["own_tag"]), ("https://c411.org", 1.0, "autodl"))

    def test_ancien_nom_accepte(self):
        cfg, _ = config.build_cfg({"MAX_SIZE_MB": "800"})
        self.assertEqual(cfg["max_size"], 800 * MB)
        cfg, _ = config.build_cfg({"MAX_SIZE_MB": "800", "TAILLE_MAX": "1Go"})  # le nouveau nom l'emporte
        self.assertEqual(cfg["max_size"], GB)

    def test_toutes_les_erreurs_d_un_coup(self):
        _, errors = config.build_cfg({"MIN_SEEDERS": "abc", "NETTOYAGE_ACTION": "tout", "TAILLE_MAX": "beaucoup",
                                      "REGEX_EXCLUSION": "([", "BILAN_HEURE": "25", "MAX_SEEDERS": "-1"})
        joined = "\n".join(errors)
        for expected in ("C411_API_KEY", "QBIT_URL", "MIN_SEEDERS", "NETTOYAGE_ACTION", "TAILLE_MAX",
                         "REGEX_EXCLUSION", "BILAN_HEURE", "MAX_SEEDERS", "C411_PROFILE_API_KEY"):
            self.assertIn(expected, joined)

    def test_alerte_apres_ramenee_a_1(self):
        cfg, errors = config.build_cfg({"ALERTE_APRES": "0"})
        self.assertEqual(cfg["alert_after"], 1)
        self.assertFalse(any("ALERTE_APRES" in e for e in errors))

    def test_secrets(self):
        secrets = {s.env for s in config.SETTINGS if s.secret}
        self.assertTrue({"C411_API_KEY", "C411_PROFILE_API_KEY", "QBIT_PASS", "CROSS_SEED_API_KEY",
                         "DISCORD_WEBHOOK_URL", "TELEGRAM_BOT_TOKEN"} <= secrets)


# --------------------------------------------------------------------------- démarrage

class TestDemarrage(unittest.TestCase):
    ENV = {"C411_API_KEY": "x", "QBIT_URL": "http://127.0.0.1:9", "QBIT_USER": "x", "QBIT_PASS": "x",
           "MIN_RATIO": "0"}

    def run_cli(self, *cli, **env):
        with tempfile.TemporaryDirectory() as d:  # dossier vide : aucun .env réel n'est lu
            script = Path(d) / "c411_autodl.py"
            script.write_bytes((ROOT / "c411_autodl.py").read_bytes())
            __import__("shutil").copytree(ROOT / "autodl", Path(d) / "autodl",
                                          ignore=__import__("shutil").ignore_patterns("__pycache__"))
            full_env = {"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
                        **self.ENV, **env}
            return subprocess.run([sys.executable, "-I", str(script), *cli], capture_output=True,
                                  text=True, encoding="utf-8", env=full_env, timeout=60)

    def test_version(self):
        r = self.run_cli("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn(m.__version__, r.stdout)

    def test_regex_invalide(self):
        r = self.run_cli("--dry-run", REGEX_EXCLUSION="([")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REGEX_EXCLUSION", r.stderr)

    def test_cross_seed_sans_cle(self):
        r = self.run_cli("--dry-run", CROSS_SEED_URL="http://localhost:2468")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("CROSS_SEED_API_KEY", r.stderr)

    def test_freeleech_sans_cle_profil(self):
        r = self.run_cli("--dry-run", FREELEECH_MODE="true")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("C411_PROFILE_API_KEY", r.stderr)

    def test_action_de_nettoyage_invalide(self):
        r = self.run_cli("--dry-run", NETTOYAGE_ACTION="tout")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NETTOYAGE_ACTION", r.stderr)


if __name__ == "__main__":
    unittest.main()
