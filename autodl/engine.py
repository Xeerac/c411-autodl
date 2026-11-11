"""Le moteur en tâche de fond : la boucle de passages, pilotable (pause, reprise, passage immédiat).

Utilisé par la ligne de commande (--boucle, au premier plan) et par l'interface web (dans un thread).
En lecture seule, toutes les opérations sont forcées en essai à blanc : rien n'est ajouté, supprimé,
rangé ni notifié. C'est le mode utilisé pour tester l'interface sur une autre machine que celle qui
fait réellement tourner le programme.
"""
from __future__ import annotations

import queue
import threading
import time
import types

from .commun import __version__, log
from .contexte import build_context
from .alertes import maybe_alerts
from .hitrun import maybe_alert as maybe_hitrun
from .inactifs import maybe_inactive, retire_inactive
from .releves import maybe_releve
from .moteur import _safe, cleanup, maybe_cleanup, maybe_crossseed, maybe_report, recategorize, run_once, watchdog

# Tâches ponctuelles lancées depuis l'interface. Les aperçus sont TOUJOURS en essai à blanc.
TASKS = {
    "essai": "Essai à blanc",
    "bilan": "Bilan",
    "nettoyage_apercu": "Aperçu du nettoyage",
    "inactifs_apercu": "Aperçu des inactifs",
    "rangement_apercu": "Aperçu du rangement",
    # Actions réelles : demandées avec une confirmation dans l'interface, jamais en lecture seule
    "nettoyage": "Nettoyage des torrents supprimés de c411",
    "inactifs": "Retrait des torrents inactifs",
    "rangement": "Rangement par type (sans déplacer les fichiers)",
}
REAL_TASKS = ("nettoyage", "inactifs", "rangement")
ACTIONS = ("passage", "pause", "reprise", "recharger", "arret", *TASKS)
# Informations d'état gardées quand la configuration change
KEEP_ON_RELOAD = ("last_ratio", "blocked", "freeleech", "last_cleanup", "last_inactive", "last_hitrun", "last_alerts", "down_since", "categories_ok", "releves")


class Engine:
    def __init__(self, cfg: dict, interval: int = 300, read_only: bool = False, ctx: dict | None = None,
                 pages: int | None = None, rattrapage: bool = False):
        self.cfg = cfg
        self.interval = max(int(interval or 300), 1)
        self.read_only = read_only
        self.ctx = ctx if ctx is not None else build_context(cfg, dry_run=read_only)
        self.args = types.SimpleNamespace(dry_run=read_only, rattrapage=rattrapage, pages=pages or cfg["pages"],
                                          boucle=self.interval)
        self.errors = 0
        self.total_added = 0
        self.paused = False
        self._last_beat = time.monotonic()
        self._lock = threading.Lock()
        self._actions: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = {
            "version": __version__, "read_only": read_only, "started_at": time.time(), "interval": self.interval,
            "state": "demarrage", "last_pass_at": None, "next_pass_at": None, "last_duration": None,
            "last_added": 0, "total_added": 0, "errors": 0, "last_error": None, "running_pass": False,
            "task": None,  # {"id", "nom", "debut", "fin", "resultat", "ok"}
        }

    # ------------------------------------------------------------------ état

    def snapshot(self) -> dict:
        """Copie de l'état courant, sans aucun secret (affichable tel quel)."""
        with self._lock:
            status = dict(self._status)
        status.update(
            paused=self.paused,
            ratio=self.ctx.get("last_ratio"),
            ratio_block=self.ctx.get("blocked"),
            freeleech=bool(self.ctx.get("freeleech")),
            min_ratio=self.cfg["min_ratio"],
            budget=self._budget(),
        )
        status["state"] = self._state_name(status)
        return status

    def _budget(self) -> dict | None:
        """Budget de téléchargement du jour (si BUDGET_JOUR est réglé) : octets comptés et limite."""
        limit = self.cfg.get("budget_day")
        tracking = self.ctx.get("tracking")
        if not limit or tracking is None:
            return None
        data = tracking.data.get("budget") or {}
        used = data.get("total", 0) if data.get("jour") == time.strftime("%Y-%m-%d") else 0
        return {"utilise": used, "limite": limit}

    def _state_name(self, s: dict) -> str:
        if s["running_pass"]:
            return "passage"
        if s["task"] and not s["task"].get("fin"):
            return "tache"
        if self.paused:
            return "pause"
        if s["errors"] >= self.cfg["alert_after"]:
            return "panne"
        if s["ratio_block"]:
            return "pause_ratio"
        if s["freeleech"]:
            return "freeleech"
        return "actif" if s["last_pass_at"] else "demarrage"

    def _set(self, **values) -> None:
        with self._lock:
            self._status.update(values)

    # ------------------------------------------------------------------ un cycle

    def step(self) -> float:
        """Un cycle complet. Retourne le nombre de secondes à attendre avant le suivant."""
        start = time.monotonic()
        if self.paused:
            self._set(next_pass_at=None)
            return self.interval
        self._set(running_pass=True)
        added = 0
        try:
            added = run_once(self.args, self.cfg, self.ctx)
            self.total_added += added
            self.errors = watchdog(self.cfg, self.ctx, self.errors)
            last_error = None
        except Exception as e:
            self.errors = watchdog(self.cfg, self.ctx, self.errors, e)
            last_error = str(e)[:300]
        # Indépendants du ratio : tournent même quand les ajouts sont en pause
        maybe_cleanup(self.args, self.cfg, self.ctx)
        maybe_inactive(self.args, self.cfg, self.ctx)
        _safe(maybe_crossseed, self.args, self.cfg, self.ctx)
        _safe(maybe_hitrun, self.args, self.cfg, self.ctx)  # torrents pas encore quittes qui ne seedent plus
        _safe(maybe_alerts, self.args, self.cfg, self.ctx)  # disque, tracker c411, certificat SSL
        maybe_report(self.args, self.cfg, self.ctx)
        _safe(maybe_releve, self.args, self.cfg, self.ctx)  # relevé quotidien (ratio, envoyé, reçu)
        if time.monotonic() - self._last_beat >= 3600:  # signe de vie toutes les heures
            ratio = self.ctx.get("last_ratio")
            log.info("Toujours actif : %d torrents ajoutés depuis le démarrage%s", self.total_added,
                     f", ratio {ratio:.2f}" if ratio is not None else "")
            self._last_beat = time.monotonic()
        # En cas d'erreurs répétées (site ou seedbox injoignable), on espace les essais : 5 min max
        wait = self.interval * min(2 ** max(self.errors - 1, 0), 5) if self.errors else self.interval
        wait = max(1.0, wait - (time.monotonic() - start))
        self._set(running_pass=False, last_pass_at=time.time(), next_pass_at=time.time() + wait,
                  last_duration=round(time.monotonic() - start, 1), last_added=added,
                  total_added=self.total_added, errors=self.errors,
                  **({"last_error": last_error} if last_error or not self.errors else {}))
        return wait

    # ------------------------------------------------------------------ tâches ponctuelles

    def run_task(self, name: str) -> dict:
        """Exécute une tâche ponctuelle. Les aperçus sont forcés en essai à blanc."""
        task = {"id": name, "nom": TASKS[name], "debut": time.time(), "fin": None, "resultat": "", "ok": None}
        self._set(task=dict(task))
        log.info("Tâche lancée depuis l'interface : %s", task["nom"])
        dry = types.SimpleNamespace(**{**vars(self.args), "dry_run": True, "boucle": 0})
        # En lecture seule, self.args est déjà en essai à blanc : une action « réelle » n'y change rien
        real = types.SimpleNamespace(**{**vars(self.args), "boucle": 0})
        try:
            if name in REAL_TASKS and self.read_only:
                raise RuntimeError("interface en lecture seule : aucune action réelle possible")
            if name == "essai":
                n = run_once(dry, self.cfg, self.ctx)
                task["resultat"] = f"{n} torrent(s) seraient ajoutés avec les réglages actuels."
            elif name == "bilan":
                maybe_report(self.args, self.cfg, self.ctx, force=True)
                where = " et envoyé en notification" if self.ctx.get("notifier") else ""
                task["resultat"] = f"Bilan affiché dans le journal{where}."
            elif name == "nettoyage_apercu":
                n = cleanup(dry, self.cfg, self.ctx)
                task["resultat"] = (f"{n} torrent(s) supprimé(s) de c411 seraient retirés." if n
                                    else "Aucun torrent supprimé de c411 : rien à nettoyer.")
            elif name == "inactifs_apercu":
                n = retire_inactive(dry, self.cfg, self.ctx)
                task["resultat"] = (f"{n} torrent(s) inactif(s) seraient retirés (au plus "
                                    f"{self.cfg['inactive_max_per_day']} par jour)." if n
                                    else "Aucun torrent inactif : rien à retirer.")
            elif name == "nettoyage":
                n = cleanup(real, self.cfg, self.ctx)
                task["resultat"] = (f"{n} torrent(s) supprimé(s) de c411 retiré(s)." if n
                                    else "Aucun torrent supprimé de c411 : rien à nettoyer.")
            elif name == "inactifs":
                n = retire_inactive(real, self.cfg, self.ctx)
                task["resultat"] = (f"{n} torrent(s) inactif(s) retiré(s)." if n
                                    else "Aucun torrent inactif à retirer (ou plafond du jour atteint).")
            elif name == "rangement":
                summary = recategorize(real, self.cfg, self.ctx, keep_location=True)
                task["resultat"] = (", ".join(f"{n} rangé(s) dans {c}" for c, n in sorted(summary.items()))
                                    if summary else "Tout est déjà bien rangé.")
            elif name == "rangement_apercu":
                summary = recategorize(dry, self.cfg, self.ctx)
                task["resultat"] = (", ".join(f"{n} vers {c}" for c, n in sorted(summary.items()))
                                    if summary else "Tout est déjà bien rangé.")
            task["ok"] = True
        except Exception as e:
            task.update(ok=False, resultat=f"Échec : {str(e)[:200]}")
            log.error("Tâche %s interrompue : %s", task["nom"], e)
        task["fin"] = time.time()
        self._set(task=dict(task))
        return task

    # ------------------------------------------------------------------ au premier plan (ligne de commande)

    def run_forever(self) -> None:
        try:
            while True:
                time.sleep(self.step())
        except KeyboardInterrupt:
            log.info("Arrêt demandé : %d torrents ajoutés depuis le démarrage", self.total_added)

    # ------------------------------------------------------------------ en tâche de fond (interface web)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="moteur", daemon=True)
        self._thread.start()

    def submit(self, action: str, payload=None) -> None:
        """Demande une action ; elle est exécutée par le thread du moteur (jamais deux opérations à la fois)."""
        if action not in ACTIONS:
            raise ValueError(f"action inconnue : {action}")
        self._actions.put((action, payload))

    def reload(self, cfg: dict) -> None:
        """Nouvelle configuration, appliquée entre deux passages (jamais au milieu d'un passage)."""
        if self._thread and self._thread.is_alive():
            self.submit("recharger", cfg)
        else:
            self.apply(cfg)

    def apply(self, cfg: dict) -> None:
        kept = {k: self.ctx[k] for k in KEEP_ON_RELOAD if k in self.ctx}
        self.cfg = cfg
        self.ctx = build_context(cfg, dry_run=self.read_only)
        self.ctx.update(kept)
        self.args.pages = cfg["pages"]
        if cfg["boucle"]:
            self.interval = max(int(cfg["boucle"]), 1)
            self.args.boucle = self.interval
        self._set(interval=self.interval)
        log.info("Nouvelle configuration appliquée")

    def stop(self, timeout: float = 30) -> None:
        self._stop.set()
        self._actions.put(("arret", None))
        if self._thread:
            self._thread.join(timeout)
        log.info("Moteur arrêté : %d torrents ajoutés depuis le démarrage", self.total_added)

    def _loop(self) -> None:
        wait = 0.0
        while not self._stop.is_set():
            try:
                action, payload = self._actions.get(timeout=wait) if wait > 0 else (None, None)
            except queue.Empty:
                action, payload = None, None
            if action == "arret" or self._stop.is_set():
                break
            if action == "recharger":
                self.apply(payload)
                # le prochain passage garde son heure prévue
                next_at = self._status.get("next_pass_at")
                wait = max(next_at - time.time(), 0.0) if next_at else (3600 if self.paused else 0.0)
                if wait == 0 and not self.paused:
                    action = None
                else:
                    continue
            if action == "pause":
                self.paused = True
                log.info("Mis en pause depuis l'interface")
                self._set(next_pass_at=None)
                wait = 3600
                continue
            if action == "reprise":
                self.paused = False
                log.info("Reprise depuis l'interface")
            if action in TASKS:
                self.run_task(action)
                next_at = self._status.get("next_pass_at")
                wait = 3600 if self.paused else (max(next_at - time.time(), 0.0) if next_at else 0.0)
                continue
            if action in ("passage", "reprise") or action is None:
                if action == "passage":
                    log.info("Passage demandé depuis l'interface")
                try:
                    wait = self.step()
                except Exception as e:  # le thread ne doit jamais mourir
                    log.error("Erreur inattendue du moteur : %s", e)
                    wait = self.interval
                if self.paused:
                    wait = 3600
