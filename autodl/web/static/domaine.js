// c411-autodl : assistant « Accès par domaine » (étapes de vérification). Données insérées comme texte.
(() => {
  const list = document.getElementById("domaine-etapes");
  if (!list) return;
  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const ICONS = document.querySelector('link[rel="icon"]')?.href.replace(/logo\.svg(?=\?|$)/, "icons.svg") || "/static/icons.svg";
  const ICON_OF = { ok: "ok", erreur: "erreur", alerte: "alerte", attente: "radar", inactif: "verrou" };
  const LABEL = { ok: "OK", erreur: "À corriger", alerte: "Attention", attente: "En cours", inactif: "Inactif" };

  const icon = (name) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `${ICONS}#${name}`);
    svg.append(use);
    return svg;
  };

  function render(data) {
    list.replaceChildren(...data.etapes.map((s) => {
      const li = document.createElement("li");
      li.className = `step step-${s.etat}`;
      const badge = document.createElement("span");
      badge.className = "step-icon";
      badge.append(icon(ICON_OF[s.etat] || "radar"));
      const body = document.createElement("div");
      body.className = "step-body";
      const head = document.createElement("strong");
      head.textContent = s.titre;
      const state = document.createElement("span");
      state.className = "step-state";
      state.textContent = LABEL[s.etat] || s.etat;
      const msg = document.createElement("p");
      msg.textContent = s.message;
      body.append(head, state, msg);
      if (s.lien) {
        const a = document.createElement("a");
        a.href = s.lien;
        a.textContent = s.lien;
        a.className = "step-link";
        body.append(a);
      }
      li.append(badge, body);
      return li;
    }));
  }

  let busy = false;
  async function load() {
    if (busy) return;
    busy = true;
    try {
      const r = await fetch("/api/domaine", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/connexion"; return; }
      render(await r.json());
    } catch (_) { /* on réessaie au prochain tour */ }
    busy = false;
  }

  document.getElementById("domaine-verifier")?.addEventListener("click", load);
  const resend = document.getElementById("domaine-renvoyer");
  resend?.addEventListener("click", async () => {
    resend.disabled = true;
    try {
      await fetch("/api/domaine/renvoyer", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf } });
    } catch (_) { /* affiché par la vérification suivante */ }
    resend.disabled = false;
    load();
  });

  load();
  setInterval(load, 10000);
})();
