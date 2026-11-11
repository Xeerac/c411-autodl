// c411-autodl : page « Ajouts » (recherche, filtres, tri). Données insérées comme texte, jamais comme HTML.
(() => {
  const $ = (id) => document.getElementById(id);
  const table = $("liste-ajouts");
  if (!table) return;
  const PAGE = 50;
  let rows = [];
  let shown = PAGE;

  const el = (tag, props = {}, children = []) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (v == null) return;
      if (k === "text") node.textContent = v; else if (k === "class") node.className = v; else node.setAttribute(k, v);
    });
    children.forEach((c) => c && node.append(c));
    return node;
  };
  const HR = { quitte: ["quitte", "is-good"], seed: ["H&R en cours", ""], telechargement: ["téléchargement", ""],
               risque: ["H&R à risque", "is-bad"] };

  function filtered() {
    const q = $("f-recherche").value.trim().toLowerCase();
    const type = $("f-type").value;
    const etat = $("f-etat").value;
    let out = rows.filter((r) => (!q || r.titre.toLowerCase().includes(q)) && (!type || r.type === type));
    if (etat === "seed") out = out.filter((r) => r.present);
    if (etat === "absent") out = out.filter((r) => !r.present);
    if (etat === "hr") out = out.filter((r) => r.hitrun && r.hitrun !== "quitte");
    if (etat === "risque") out = out.filter((r) => r.hitrun === "risque");
    if (etat === "zero") out = out.filter((r) => r.present && !r.envoye);
    const tri = $("f-tri").value;
    const by = {
      date: (a, b) => b.ajoute_le.localeCompare(a.ajoute_le),
      rendement: (a, b) => (b.rendement ?? -1) - (a.rendement ?? -1),
      envoye: (a, b) => b.envoye - a.envoye,
      taille: (a, b) => b.taille - a.taille,
      titre: (a, b) => a.titre.localeCompare(b.titre, "fr"),
    }[tri];
    return out.sort(by);
  }

  function render() {
    const list = filtered();
    const body = table.tBodies[0];
    if (!list.length) {
      body.replaceChildren(el("tr", {}, [el("td", { colspan: "7", class: "muted", text: rows.length ? "Aucun torrent ne correspond à ces filtres." : "Aucun ajout pour l'instant." })]));
    } else {
      body.replaceChildren(...list.slice(0, shown).map((r) => {
        const hr = HR[r.hitrun];
        return el("tr", { class: r.present ? "" : "is-absent" }, [
          el("td", { class: "title-cell" }, [
            el("a", { href: r.lien, target: "_blank", rel: "noopener noreferrer", text: r.titre, title: r.titre }),
            el("span", { class: "muted small", text: r.ajoute_le + (r.categorie ? ` · ${r.categorie}` : "") }),
          ]),
          el("td", {}, [el("span", { class: "chip", "data-type": r.type, text: r.type })]),
          el("td", { class: "num", text: r.taille_txt }),
          el("td", { class: "num" }, [document.createTextNode(r.envoye_txt),
            r.rendement ? el("span", { class: "yield" + (r.rendement >= 1 ? " is-good" : ""), text: ` ×${r.rendement}` }) : null]),
          el("td", { class: "num", text: r.ratio == null ? "–" : r.ratio.toFixed(2) }),
          el("td", { class: "num", text: r.seed_h == null ? "–" : r.seed_h >= 48 ? `${Math.round(r.seed_h / 24)} j` : `${Math.round(r.seed_h)} h` }),
          el("td", { class: "cell-state small" }, [document.createTextNode(r.etat),
            hr && r.hitrun !== "quitte" ? el("span", { class: `hr-tag ${hr[1]}`, text: hr[0] }) : null]),
        ]);
      }));
    }
    $("ajouts-compte").textContent = `${Math.min(shown, list.length)} affiché(s) sur ${list.length}` +
      (list.length !== rows.length ? ` (${rows.length} au total)` : "");
    $("ajouts-plus").hidden = shown >= list.length;
  }

  async function load() {
    try {
      const r = await fetch("/api/ajouts", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/connexion"; return; }
      const data = await r.json();
      if (data.erreur) { $("ajouts-maj").textContent = data.erreur; return; }
      rows = data.ajouts;
      const types = [...new Set(rows.map((x) => x.type))].sort();
      const select = $("f-type");
      const current = select.value;
      select.replaceChildren(el("option", { value: "", text: "Tous les types" }),
        ...types.map((t) => el("option", { value: t, text: `${t} (${rows.filter((x) => x.type === t).length})` })));
      select.value = current;
      const present = rows.filter((x) => x.present);
      $("ajouts-resume").textContent = `${rows.length} torrents ajoutés par le programme, dont ${present.length} encore dans qBittorrent.`;
      $("ajouts-maj").textContent = `mis à jour à ${new Date(data.genere_le * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
      render();
    } catch (_) {
      $("ajouts-maj").textContent = "Impossible de lire les ajouts pour l'instant.";
    }
  }

  // Lien direct vers un filtre, par exemple /ajouts?etat=hr depuis le tableau de bord
  const wanted = new URLSearchParams(location.search).get("etat");
  if (wanted && [...$("f-etat").options].some((o) => o.value === wanted)) $("f-etat").value = wanted;

  ["f-type", "f-etat", "f-tri"].forEach((id) => $(id).addEventListener("change", () => { shown = PAGE; render(); }));
  $("f-recherche").addEventListener("input", () => { shown = PAGE; render(); });
  $("ajouts-plus").addEventListener("click", () => { shown += PAGE; render(); });

  load();
  setInterval(load, 60000);
})();
