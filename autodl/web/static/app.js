// c411-autodl : tableau de bord (état, services, derniers ajouts, rendement, actions). Aucune dépendance.
// Les données reçues sont toujours insérées comme texte (textContent), jamais comme HTML.
(() => {
  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const $ = (id) => document.getElementById(id);
  const hero = $("hero");
  if (!hero) return;
  const ICONS = document.querySelector('link[rel="icon"]')?.href.replace(/logo\.svg$/, "icons.svg") || "/static/icons.svg";

  const STATES = {
    demarrage:   ["Démarrage", "Premier passage en préparation."],
    actif:       ["Actif", "Le programme surveille c411 et ajoute ce qui correspond à tes critères."],
    passage:     ["Passage en cours", "Recherche sur c411 et ajout dans qBittorrent…"],
    tache:       ["Tâche en cours", "Une action lancée depuis l'interface est en cours."],
    pause:       ["En pause", "Mis en pause depuis l'interface. Rien n'est ajouté jusqu'à la reprise."],
    pause_ratio: ["En pause : ratio", "Ton ratio est sous le minimum. Reprise automatique dès qu'il remonte."],
    freeleech:   ["Freeleech actif", "Mode élargi : ce que tu télécharges ne compte pas dans ton ratio."],
    panne:       ["En panne", "Plusieurs passages ont échoué d'affilée. Le programme continue de réessayer."],
  };
  const SERVICE_ICONS = { qbittorrent: "serveur", crossseed: "lien", prowlarr: "radar" };

  const el = (tag, props = {}, children = []) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (v == null) return;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else node.setAttribute(k, v);
    });
    children.forEach((c) => c && node.append(c));
    return node;
  };
  const icon = (name) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `${ICONS}#${name}`);
    svg.append(use);
    return svg;
  };
  const empty = (title, text) => el("div", { class: "empty" }, [icon("vide"), el("strong", { text: title }), el("span", { text })]);
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
    $("state-detail").textContent = e.read_only ? `${detail} Lecture seule : rien n'est ajouté ni supprimé.` : detail;

    const ratio = $("kpi-ratio");
    ratio.textContent = e.ratio == null ? "–" : e.ratio.toFixed(2);
    const gauge = $("ratio-gauge");
    if (e.ratio == null || !e.min_ratio) {
      gauge.hidden = true;
    } else {
      // jauge : le minimum est au milieu ; pleine à deux fois le minimum
      gauge.hidden = false;
      gauge.classList.toggle("is-low", e.ratio <= e.min_ratio * 1.1);
      gauge.firstElementChild.style.transform = `scaleX(${Math.min(1, Math.max(0.03, e.ratio / (e.min_ratio * 2)))})`;
    }
    $("kpi-last-pass").textContent = fmtTime(e.last_pass_at);
    $("kpi-last-added").textContent = e.last_pass_at
      ? `${e.last_added} ajouté(s), ${e.total_added} depuis le démarrage` : "pas encore de passage";
    updateNext();

    $("btn-pause").hidden = e.paused;
    $("btn-reprise").hidden = !e.paused;
    const busy = e.state === "passage" || e.state === "tache";
    $("btn-passage").disabled = busy || e.paused;
    document.querySelectorAll(".actions [data-action]").forEach((b) => { b.disabled = busy; });
    document.querySelectorAll(".is-busy").forEach((b) => b.classList.remove("is-busy"));

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
    const done = Boolean(task.fin);
    box.className = "task " + (done ? (task.ok ? "is-ok" : "is-ko") : "is-running");
    const head = $("task-name");
    head.replaceChildren(icon(done ? (task.ok ? "ok" : "erreur") : "eclair"),
                         document.createTextNode(done ? `${task.nom} · ${fmtTime(task.fin)}` : `${task.nom} en cours…`));
    $("task-result").textContent = done ? task.resultat : "Le résultat s'affichera ici dans quelques instants.";
  }

  async function refreshState() {
    try {
      const data = await api("/api/etat");
      if (data.moteur) renderState(data.moteur);
    } catch (_) { /* hors ligne : on réessaie au prochain tour */ }
  }

  // ------------------------------------------------------------------ tableau (services, ajouts, rendement)
  function renderServices(services) {
    $("services").replaceChildren(...services.map((s) => el("li", { class: "service " + (s.ok ? "is-ok" : "is-ko") }, [
      el("span", { class: "service-icon" }, [icon(SERVICE_ICONS[s.id] || "serveur")]),
      el("span", { class: "service-name", text: s.nom }),
      el("span", { class: "service-state", text: s.ok ? "en ligne" : "problème" }),
      el("span", { class: "service-detail", text: [s.detail, s.extra].filter(Boolean).join(" · ") }),
    ])));
  }

  function renderAdditions(rows) {
    const body = $("ajouts").tBodies[0];
    if (!rows.length) {
      body.replaceChildren(el("tr", {}, [el("td", { colspan: "5" }, [
        empty("Aucun ajout pour l'instant", "Les torrents ajoutés par le programme apparaîtront ici, avec ce qu'ils ont déjà envoyé."),
      ])]));
      return;
    }
    body.replaceChildren(...rows.map((r) => el("tr", {}, [
      el("td", { class: "title-cell" }, [
        el("a", { href: r.lien, target: "_blank", rel: "noopener noreferrer", text: r.titre, title: r.titre }),
        el("span", { class: "muted small", text: r.ajoute_le }),
      ]),
      el("td", {}, [el("span", { class: "chip", "data-type": r.type, text: r.type })]),
      el("td", { class: "num", text: r.taille }),
      el("td", { class: "num" }, [
        document.createTextNode(r.envoye),
        r.rendement != null ? el("span", { class: "yield" + (r.rendement >= 1 ? " is-good" : ""), text: ` ×${r.rendement}` }) : null,
      ]),
      el("td", { class: "cell-state small", text: r.etat }),
    ])));
  }

  function renderTypes(rows, totals) {
    const box = $("types");
    if (!rows.length) {
      box.replaceChildren(empty("Pas encore de données", "Le rendement s'affichera dès que tes torrents auront commencé à envoyer."));
    } else {
      box.replaceChildren(...rows.map((r) => {
        const fill = el("span", { class: "bar-fill" });
        return [el("div", { class: "bar-row", "data-type": r.type }, [
          el("div", { class: "bar-label" }, [el("span", { class: "chip", "data-type": r.type, text: r.type }),
            el("span", { class: "muted small", text: `${r.torrents} torrents · ${r.envoye} envoyés` })]),
          el("strong", { class: "bar-value", text: `×${r.rendement.toFixed(2)}` }),
          el("div", { class: "bar" }, [fill]),
        ]), fill, r.barre];
      }).map(([row, fill, width]) => {
        // largeur posée par le script : la politique de sécurité bloque style="…"
        requestAnimationFrame(() => { fill.style.transform = `scaleX(${Math.max(width, 2) / 100})`; });
        return row;
      }));
    }
    $("kpi-uploaded").textContent = totals.envoye_txt;
    $("kpi-uploaded-sub").textContent = `${totals.torrents} torrents · ${totals.taille_txt} au total`;
  }

  async function refreshTableau() {
    const stamp = $("tableau-maj");
    try {
      const data = await api("/api/tableau");
      if (data.erreur) { stamp.textContent = data.erreur; stamp.classList.add("is-error"); return; }
      renderServices(data.services);
      renderAdditions(data.ajouts);
      renderTypes(data.types, data.totaux);
      stamp.textContent = `mis à jour à ${fmtTime(data.genere_le)}`;
      stamp.classList.remove("is-error");
    } catch (_) {
      stamp.textContent = "Impossible de lire les données, nouvel essai dans 30 s.";
      stamp.classList.add("is-error");
    }
  }

  // ------------------------------------------------------------------ actions
  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.classList.add("is-busy");
      try {
        await api(`/api/action/${btn.dataset.action}`, { method: "POST", headers: { "X-CSRF-Token": csrf } });
      } catch (_) { btn.classList.remove("is-busy"); }
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
