// c411-autodl : journal en direct, avec filtres et recherche. Les messages sont insérés comme texte.
(() => {
  const box = document.getElementById("journal");
  if (!box) return;
  const follow = document.getElementById("journal-follow");
  const search = document.getElementById("journal-search");
  const count = document.getElementById("journal-count");
  const emptyNote = document.getElementById("journal-empty");
  const MAX = 1500;
  let lastId = 0;
  let filter = "";

  const LEVELS = { WARNING: "avert.", ERROR: "erreur", CRITICAL: "erreur", INFO: "info", DEBUG: "debug" };

  function matches(row) {
    const f = filter;
    if (f === "probleme" && !["WARNING", "ERROR", "CRITICAL"].includes(row.dataset.niveau)) return false;
    if (f && f !== "probleme" && row.dataset.categorie !== f) return false;
    const q = search.value.trim().toLowerCase();
    return !q || row.dataset.texte.includes(q);
  }

  function apply() {
    let shown = 0;
    for (const row of box.children) { const ok = matches(row); row.hidden = !ok; if (ok) shown++; }
    count.textContent = box.children.length ? `${shown} message(s) affiché(s) sur ${box.children.length}` : "";
    emptyNote.hidden = shown > 0 || !box.children.length;
  }

  function add(m) {
    const row = document.createElement("div");
    row.className = "log-row lvl-" + m.niveau.toLowerCase() + (m.categorie ? " cat-" + m.categorie : "");
    row.dataset.niveau = m.niveau;
    row.dataset.categorie = m.categorie;
    row.dataset.texte = m.message.toLowerCase();
    const time = document.createElement("time");
    const d = new Date(m.ts * 1000);
    time.textContent = d.toLocaleTimeString("fr-FR");
    time.dateTime = d.toISOString();
    const lvl = document.createElement("span");
    lvl.className = "log-level";
    lvl.textContent = LEVELS[m.niveau] || m.niveau;
    const msg = document.createElement("span");
    msg.className = "log-msg";
    msg.textContent = m.message;
    row.append(time, lvl, msg);
    row.hidden = !matches(row);
    box.append(row);
  }

  async function poll() {
    try {
      const r = await fetch(`/api/journal?depuis=${lastId}`, { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/connexion"; return; }
      const data = await r.json();
      const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
      data.messages.forEach((m) => { add(m); lastId = m.id; });
      while (box.children.length > MAX) box.firstChild.remove();
      if (data.messages.length) {
        apply();
        if (follow.checked && (atBottom || lastId === data.messages.at(-1).id)) box.scrollTop = box.scrollHeight;
      }
    } catch (_) { /* on réessaie */ }
  }

  document.querySelectorAll("[data-filtre]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("[data-filtre]").forEach((x) => x.classList.toggle("active", x === b));
    filter = b.dataset.filtre;
    apply();
  }));
  search.addEventListener("input", apply);

  poll().then(() => { box.scrollTop = box.scrollHeight; });
  setInterval(poll, 2000);
})();
