// c411-autodl : mise à jour du tableau de bord et actions. Aucune dépendance.
(() => {
  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const $ = (id) => document.getElementById(id);
  const hero = $("hero");
  if (!hero) return;

  const STATES = {
    demarrage:   ["Démarrage", "Premier passage en préparation."],
    actif:       ["Actif", "Le programme surveille c411 et ajoute ce qui correspond à tes critères."],
    passage:     ["Passage en cours", "Recherche sur c411 et ajout dans qBittorrent…"],
    pause:       ["En pause", "Mis en pause depuis l'interface. Rien n'est ajouté."],
    pause_ratio: ["En pause : ratio", "Ton ratio est sous le minimum. Reprise automatique dès qu'il remonte."],
    freeleech:   ["Freeleech actif", "Mode élargi : ce que tu télécharges ne compte pas dans ton ratio."],
    panne:       ["En panne", "Plusieurs passages ont échoué d'affilée. Le programme continue de réessayer."],
  };

  const fmtTime = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "–";
  const fmtIn = (ts) => {
    if (!ts) return "–";
    const s = Math.round(ts - Date.now() / 1000);
    if (s <= 0) return "imminent";
    return s < 60 ? `dans ${s} s` : `dans ${Math.round(s / 60)} min`;
  };

  let last = null;
  function render(e) {
    last = e;
    const [title, detail] = STATES[e.state] || [e.state, ""];
    hero.dataset.state = e.state;
    $("state-pill").textContent = title;
    $("state-title").textContent = title;
    $("state-detail").textContent = e.read_only ? `${detail} (lecture seule : rien n'est ajouté ni supprimé)` : detail;

    const ratio = $("kpi-ratio");
    ratio.textContent = e.ratio == null ? "–" : e.ratio.toFixed(2);
    ratio.className = "kpi-value " + (e.ratio == null ? "" : e.ratio > e.min_ratio ? "ok" : "warn");
    $("kpi-last-added").textContent = e.last_pass_at ? e.last_added : "–";
    $("kpi-total-added").textContent = `${e.total_added} depuis le démarrage`;
    $("kpi-last-pass").textContent = fmtTime(e.last_pass_at);
    $("kpi-duration").textContent = e.last_duration != null ? `durée ${e.last_duration} s` : "";
    $("kpi-next-pass").textContent = e.paused ? "en pause" : e.state === "passage" ? "en cours" : fmtIn(e.next_pass_at);

    $("btn-pause").hidden = e.paused;
    $("btn-reprise").hidden = !e.paused;
    $("btn-passage").disabled = e.state === "passage" || e.paused;

    const err = $("last-error");
    err.hidden = !e.last_error;
    err.textContent = e.last_error ? `Dernière erreur : ${e.last_error}` : "";
  }

  async function refresh() {
    try {
      const r = await fetch("/api/etat", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/connexion"; return; }
      const data = await r.json();
      if (data.moteur) render(data.moteur);
    } catch (_) { /* hors ligne : on réessaie au prochain tour */ }
  }

  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await fetch(`/api/action/${btn.dataset.action}`, {
          method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf },
        });
      } finally {
        setTimeout(refresh, 400);
        setTimeout(() => { btn.disabled = false; refresh(); }, 1500);
      }
    });
  });

  refresh();
  setInterval(refresh, 5000);
  setInterval(() => last && ($("kpi-next-pass").textContent =
    last.paused ? "en pause" : last.state === "passage" ? "en cours" : fmtIn(last.next_pass_at)), 1000);
})();
