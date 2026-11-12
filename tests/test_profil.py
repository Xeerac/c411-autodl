"""Tests du récap quotidien du profil c411. Aucun accès réseau. Exemple tiré de la documentation de c411."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_c411_autodl import args, base_cfg, m  # noqa: E402

from autodl import profil  # noqa: E402

EXEMPLE = {
    "id": 48213, "username": "membre", "avatarUrl": "/avatars/48213.webp", "memberSince": "2025-03-14T09:12:44.000Z",
    "level": {"level": 37, "xp": 18420, "xpIntoLevel": 310, "xpToNextLevel": 239},
    "class": {"slug": "team_mainstream", "effectiveSlug": "team_resident_mainstream", "foundation": "seed",
              "treeBonusBp": 250,
              "progress": {"questsCompleted": 23, "questsTotal": 40, "stars": 2, "grade": {"tier": "argent", "level": 2}},
              "voies": {"seed": {"star": True, "questsCompleted": 8, "questsTotal": 8},
                        "upload": {"star": False, "questsCompleted": 5, "questsTotal": 11},
                        "specialization": {"star": True, "questsCompleted": 6, "questsTotal": 6},
                        "competitivity": {"star": False, "questsCompleted": 4, "questsTotal": 15}}},
    "team": {"name": "Example Team", "slug": "example-team", "tag": "EXT", "role": "member"},
    "zen": {"balance": 1840, "totalEarned": 12650, "totalSpent": 10810},
    "transfer": {"uploaded": {"actual": 5497558138880, "credit": 107374182400, "total": 5604932321280},
                 "downloaded": {"actual": 3298534883328, "credit": 53687091200, "total": 3244847792128}},
    "download": {"allowed": True, "blockedReason": None},
    "freeleech": {"active": True, "sources": ["campaign"]},
    "silverLeech": False, "leechBonuses": [],
}


class TestRecap(unittest.TestCase):
    def fields(self, embed):
        return {f["name"]: f["value"] for f in embed["fields"]}

    def test_embed_complet(self):
        e = profil.recap_embed(EXEMPLE)
        self.assertEqual(e["title"], "👤 Profil c411 de membre")
        self.assertEqual(e["description"], "Membre depuis le 14/03/2025")
        f = self.fields(e)
        self.assertIn("**37**", f["🎖️ Niveau"])
        self.assertIn("310 / 549 XP", f["🎖️ Niveau"])
        self.assertIn("56 %", f["🎖️ Niveau"])
        self.assertIn("🥈 Argent 2 ⭐⭐", f["🧭 Classe"])
        self.assertIn("+2,50 %", f["🧭 Classe"])
        self.assertIn("**23 / 40**", f["📜 Quêtes"])
        self.assertIn("⭐ **Seed**", f["🛤️ Voies"])
        self.assertIn("▫️ **Upload**", f["🛤️ Voies"])
        self.assertIn("**1 840**", f["💰 Zen"])
        self.assertIn("Officiel : **1.73**", f["⚖️ Ratio"])          # total (avec crédit)
        self.assertIn("Mesuré par le tracker : 1.67", f["⚖️ Ratio"])  # actual
        self.assertIn("[EXT]", f["👥 Équipe"])
        self.assertIn("événement du site", f["📌 État du compte"])
        self.assertTrue(all(len(v) <= 1024 for v in f.values()))

    def test_comparaison_avec_la_veille(self):
        prev = {"level": 36, "xp": 18000, "quests": 21, "zen": 2000, "envoye_reel": 5497558138880 - 10 * 1024**3}
        f = self.fields(profil.recap_embed(EXEMPLE, prev))
        self.assertIn("(+1)", f["🎖️ Niveau"])
        self.assertIn("(+420)", f["🎖️ Niveau"])
        self.assertIn("(+2)", f["📜 Quêtes"])
        self.assertIn("(-160)", f["💰 Zen"])
        self.assertIn("+10.00 Go depuis hier", f["📤 Envoyé"])

    def test_profil_minimal(self):
        e = profil.recap_embed({"username": "x", "class": None, "team": None})
        self.assertEqual(e["fields"], [])  # rien ne casse quand les données manquent
        bloque = dict(EXEMPLE, download={"allowed": False, "blockedReason": "insufficient_balance"})
        self.assertIn("solde insuffisant", self.fields(profil.recap_embed(bloque))["📌 État du compte"])


class TestEnvoiQuotidien(unittest.TestCase):
    def ctx(self):
        prof = types.SimpleNamespace(last_profile=EXEMPLE, ratio=lambda: (1.7, 1, 1, True))
        return {"profile": prof, "tracking": m.Tracking(Path(tempfile.mkdtemp()) / "t.json"), "notifier": mock.Mock()}

    def test_une_fois_par_jour_dans_le_salon_profil(self):
        ctx = self.ctx()
        cfg = base_cfg(profil_recap=True, bilan_heure=0)
        self.assertIsNotNone(profil.maybe_recap(args(), cfg, ctx))
        self.assertEqual(ctx["notifier"].send.call_args.kwargs["kind"], "profil")
        self.assertEqual(ctx["tracking"].data["profil_veille"]["level"], 37)
        self.assertIsNone(profil.maybe_recap(args(), cfg, ctx))  # déjà envoyé aujourd'hui
        ctx["notifier"].send.assert_called_once()

    def test_desactive_ou_essai(self):
        ctx = self.ctx()
        self.assertIsNone(profil.maybe_recap(args(), base_cfg(profil_recap=False, bilan_heure=0), ctx))
        self.assertIsNone(profil.maybe_recap(args(dry_run=True), base_cfg(profil_recap=True, bilan_heure=0), ctx))
        ctx["notifier"].send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
