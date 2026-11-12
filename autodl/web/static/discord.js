// c411-autodl : page « Bot Discord » (listes des serveurs, salons et rôles fournies par le bot).
// Les noms reçus sont insérés comme texte, jamais comme HTML.
(() => {
  const form = document.getElementById("config-form");
  const status = document.getElementById("bot-status");
  if (!form || !status) return;
  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const invite = document.getElementById("bot-invite");
  const button = document.getElementById("bot-charger");
  const selects = (type) => [...form.querySelectorAll(`select[data-discord="${type}"]`)];

  const option = (value, text, selected) => {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = text;
    if (selected) o.selected = true;
    return o;
  };

  function fill(select, items, label) {
    const current = select.value || select.dataset.value || "";
    const empty = select.dataset.optional ? "— salon principal —" : "— choisir —";
    const opts = [option("", empty, !current)];
    let groupName = null, group = null;
    for (const it of items) {
      const cat = it.categorie || "";
      if (cat !== groupName) {
        groupName = cat;
        group = cat ? Object.assign(document.createElement("optgroup"), { label: cat }) : null;
        if (group) opts.push(group);
      }
      const o = option(it.id, label(it), it.id === current);
      (group || { append: (x) => opts.push(x) }).append(o);
    }
    // valeur enregistrée qui n'existe plus (salon supprimé, bot retiré du serveur) : on la garde visible
    if (current && !items.some((it) => it.id === current)) opts.push(option(current, `${current} (introuvable)`, true));
    select.replaceChildren(...opts);
  }

  const values = () => {
    const v = {};
    new FormData(form).forEach((value, key) => { if (key !== "csrf") v[key] = String(value); });
    return v;
  };

  async function load() {
    button.disabled = true;
    status.textContent = "Connexion à Discord…";
    status.className = "bot-status";
    try {
      const r = await fetch("/api/discord/listes", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ valeurs: values() }),
      });
      if (r.status === 401) { location.href = "/connexion"; return; }
      const data = await r.json();
      if (!data.ok) {
        status.textContent = data.message || data.erreur || "Réponse inattendue.";
        status.className = "bot-status is-ko";
        return;
      }
      invite.href = data.invitation;
      invite.hidden = false;
      selects("guild").forEach((s) => fill(s, data.serveurs, (g) => g.nom));
      if (data.serveur) selects("guild").forEach((s) => { s.value = data.serveur; });
      selects("channel").forEach((s) => fill(s, data.salons, (c) => `# ${c.nom}`));
      selects("role").forEach((s) => fill(s, data.roles, (r) => `@ ${r.nom}`));
      status.textContent = !data.serveurs.length
        ? `Bot « ${data.bot} » connecté, mais il n'est sur aucun serveur : invite-le avec le bouton à droite.`
        : !data.serveur ? `Bot « ${data.bot} » connecté. Choisis le serveur : les salons et les rôles s'afficheront.`
        : `Bot « ${data.bot} » connecté : ${data.salons.length} salon(s) et ${data.roles.length} rôle(s) disponibles.`;
      status.className = "bot-status is-ok";
    } catch (_) {
      status.textContent = "Impossible de joindre l'interface, réessaie.";
      status.className = "bot-status is-ko";
    } finally {
      button.disabled = false;
    }
  }

  button.addEventListener("click", load);
  selects("guild").forEach((s) => s.addEventListener("change", load));
  // Jeton déjà enregistré : on charge tout de suite
  if (form.querySelector('[name="DISCORD_BOT_TOKEN"]')?.placeholder.startsWith("Enregistrée")) load();
})();
