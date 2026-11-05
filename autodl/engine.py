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
from .moteur import _safe, maybe_cleanup, maybe_crossseed, maybe_report, run_once, watchdog

ACTIONS = ("passage", "pause", "reprise", "arret")


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
        )
        status["state"] = self._state_name(status)
        return status

    def _state_name(self, s: dict) -> str:
        if s["running_pass"]:
            return "passage"
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
        _safe(maybe_crossseed, self.args, self.cfg, self.ctx)
        maybe_report(self.args, self.cfg, self.ctx)
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

    def submit(self, action: str) -> None:
        """Demande une action ; elle est exécutée par le thread du moteur (jamais deux opérations à la fois)."""
        if action not in ACTIONS:
            raise ValueError(f"action inconnue : {action}")
        self._actions.put(action)

    def stop(self, timeout: float = 30) -> None:
        self._stop.set()
        self._actions.put("arret")
        if self._thread:
            self._thread.join(timeout)
        log.info("Moteur arrêté : %d torrents ajoutés depuis le démarrage", self.total_added)

    def _loop(self) -> None:
        wait = 0.0
        while not self._stop.is_set():
            try:
                action = self._actions.get(timeout=wait) if wait > 0 else None
            except queue.Empty:
                action = None
            if action == "arret" or self._stop.is_set():
                break
            if action == "pause":
                self.paused = True
                log.info("Mis en pause depuis l'interface")
                self._set(next_pass_at=None)
                wait = 3600
                continue
            if action == "reprise":
                self.paused = False
                log.info("Reprise depuis l'interface")
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
