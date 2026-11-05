// c411-autodl : tableau de bord (état, services, derniers ajouts, rendement, actions). Aucune dépendance.
// Les données reçues sont toujours insérées comme texte (textContent), jamais comme HTML.
(() => {
  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const $ = (id) => document.getElementById(id);
  const hero = $("hero");
  if (!hero) return;

  const STATES = {
    demarrage:   ["Démarrage", "Premier passage en préparation."],
    actif:       ["Actif", "Le programme surveille c411 et ajoute ce qui correspond à tes critères."],
    passage:     ["Passage en cours", "Recherche sur c411 et ajout dans qBittorrent…"],
    tache:       ["Tâche en cours", "Une action lancée depuis l'interface est en cours."],
    pause:       ["En pause", "Mis en pause depuis l'interface. Rien n'est ajouté."],
    pause_ratio: ["En pause : ratio", "Ton ratio est sous le minimum. Reprise automatique dès qu'il remonte."],
    freeleech:   ["Freeleech actif", "Mode élargi : ce que tu télécharges ne compte pas dans ton ratio."],
    panne:       ["En panne", "Plusieurs passages ont échoué d'affilée. Le programme continue de réessayer."],
  };

  const el = (tag, props = {}, children = []) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else node.setAttribute(k, v);
    });
    children.forEach((c) => node.append(c));
    return node;
  };
  const fmtTime = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : "–";
  const fmtIn = (ts) => {
    if (!ts) return "–";
    const s = Math.round(ts - Date.now() / 1000);
    if (s <= 0) return "imminent";
    return s < 60 ? `dans ${s} s` : `dans ${Math.round(s / 60)} min`;
  };
  const api = async (url, options = {}) => {
    const r = await fetch(url, { credentials: "same-origin", ...options });
    if (r.status === 401) { location.href = "/connexion"; throw new Error("déconnecté"); }
    return r.json();
  };

  // ------------------------------------------------------------------ état du moteur
  let last = null;
  function renderState(e) {
    last = e;
    const [title, detail] = STATES[e.state] || [e.state, ""];
    hero.dataset.state = e.state;
    $("state-pill").textContent = title;
    $("state-title").textContent = e.state === "tache" && e.task ? e.task.nom : title;
    $("state-detail").textContent = e.read_only ? `${detail} (lecture seule : rien n'est ajouté ni supprimé)` : detail;

    const ratio = $("kpi-ratio");
    ratio.textContent = e.ratio == null ? "–" : e.ratio.toFixed(2);
    ratio.className = "kpi-value " + (e.ratio == null ? "" : e.ratio > e.min_ratio ? "ok" : "warn");
    $("kpi-last-pass").textContent = fmtTime(e.last_pass_at);
    $("kpi-last-added").textContent = e.last_pass_at
      ? `${e.last_added} ajouté(s) · ${e.total_added} depuis le démarrage` : "";
    updateNext();

    $("btn-pause").hidden = e.paused;
    $("btn-reprise").hidden = !e.paused;
    const busy = e.state === "passage" || e.state === "tache";
    $("btn-passage").disabled = busy || e.paused;
    document.querySelectorAll(".actions-grid [data-action]").forEach((b) => { b.disabled = busy; });

    const err = $("last-error");
    err.hidden = !e.last_error;
    err.textContent = e.last_error ? `Dernière erreur : ${e.last_error}` : "";
    renderTask(e.task);
  }

  function updateNext() {
    if (!last) return;
    $("kpi-next-pass").textContent = last.paused ? "en pause"
      : (last.state === "passage" || last.state === "tache") ? "en cours" : fmtIn(last.next_pass_at);
  }

  function renderTask(task) {
    const box = $("task");
    if (!task) { box.hidden = true; return; }
    box.hidden = false;
    box.className = "task " + (task.fin ? (task.ok ? "is-ok" : "is-ko") : "is-running");
    $("task-name").textContent = task.fin ? `${task.nom} · ${fmtTime(task.fin)}` : `${task.nom} en cours…`;
    $("task-result").textContent = task.fin ? task.resultat : "Résultat dans quelques instants (détails dans le journal).";
  }

  async function refreshState() {
    try {
      const data = await api("/api/etat");
      if (data.moteur) renderState(data.moteur);
    } catch (_) { /* hors ligne : on réessaie au prochain tour */ }
  }

  // ------------------------------------------------------------------ tableau (services, ajouts, rendement)
  function renderServices(services) {
    const box = $("services");
    box.replaceChildren(...services.map((s) => el("article", { class: "card service " + (s.ok ? "is-ok" : "is-ko") }, [
      el("div", { class: "service-head" }, [
        el("span", { class: "dot", "aria-hidden": "true" }),
        el("strong", { text: s.nom }),
        el("span", { class: "service-state", text: s.ok ? "en ligne" : "problème" }),
      ]),
      el("span", { class: "service-detail", text: s.detail || "" }),
      ...(s.extra ? [el("span", { class: "service-extra", text: s.extra })] : []),
    ])));
  }

  function renderAdditions(rows) {
    const body = $("ajouts").tBodies[0];
    if (!rows.length) {
      body.replaceChildren(el("tr", {}, [el("td", { colspan: "5", class: "muted", text: "Aucun ajout pour l'instant." })]));
      return;
    }
    body.replaceChildren(...rows.map((r) => el("tr", {}, [
      el("td", { class: "title-cell" }, [
        el("a", { href: r.lien, target: "_blank", rel: "noopener noreferrer", text: r.titre, title: r.titre }),
        el("span", { class: "muted small", text: r.ajoute_le }),
      ]),
      el("td", {}, [el("span", { class: "chip", text: r.type })]),
      el("td", { class: "num", text: r.taille }),
      el("td", { class: "num" + (r.rendement >= 1 ? " ok" : ""), text: r.rendement != null ? `${r.envoye} · ×${r.rendement}` : r.envoye }),
      el("td", { class: "muted small", text: r.etat }),
    ])));
  }

  function renderTypes(rows, totals) {
    const box = $("types");
    if (!rows.length) { box.replaceChildren(el("p", { class: "muted", text: "Pas encore de données." })); return; }
    box.replaceChildren(...rows.map((r) => {
      const fill = el("span", { class: "bar-fill" });
      fill.style.width = `${Math.max(r.barre, 2)}%`;  // via le script : la politique de sécurité bloque style="…"
      return el("div", { class: "bar-row" }, [
        el("div", { class: "bar-label" }, [el("span", { class: "chip", text: r.type }),
          el("span", { class: "muted small", text: `${r.torrents} · ${r.envoye} envoyés` })]),
        el("div", { class: "bar" }, [fill]),
        el("strong", { class: "bar-value", text: `×${r.rendement.toFixed(2)}` }),
      ]);
    }));
    $("kpi-uploaded").textContent = totals.envoye_txt;
    $("kpi-uploaded-sub").textContent = `${totals.torrents} torrents · ${totals.taille_txt} au total`;
  }

  async function refreshTableau() {
    try {
      const data = await api("/api/tableau");
      if (data.erreur) return;
      renderServices(data.services);
      renderAdditions(data.ajouts);
      renderTypes(data.types, data.totaux);
      $("tableau-maj").textContent = `mis à jour à ${fmtTime(data.genere_le)}`;
    } catch (_) { /* on réessaie plus tard */ }
  }

  // ------------------------------------------------------------------ actions
  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await api(`/api/action/${btn.dataset.action}`, { method: "POST", headers: { "X-CSRF-Token": csrf } });
      } catch (_) { /* affiché au prochain rafraîchissement */ }
      setTimeout(refreshState, 300);
      setTimeout(refreshState, 1500);
    });
  });

  refreshState();
  refreshTableau();
  setInterval(refreshState, 3000);
  setInterval(refreshTableau, 30000);
  setInterval(updateNext, 1000);
})();
