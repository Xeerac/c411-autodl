// c411-autodl : page de configuration (boutons « Tester », effacement des secrets, saisie non enregistrée).
(() => {
  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const form = document.getElementById("config-form");
  if (!form) return;
  const results = document.getElementById("test-results");

  // Valeurs saisies (même non enregistrées), pour tester avant d'enregistrer
  const formValues = () => {
    const values = {};
    new FormData(form).forEach((v, k) => { if (k !== "csrf") values[k] = String(v); });
    return values;
  };

  function show(label, result) {
    const box = document.createElement("div");
    box.className = "test-result " + (result.ok ? "is-ok" : "is-ko");
    const title = document.createElement("strong");
    title.textContent = (result.ok ? "✓ " : "✗ ") + label;
    const msg = document.createElement("span");
    msg.textContent = result.message || result.erreur || "Réponse inattendue.";
    box.append(title, msg);
    results.prepend(box);
    while (results.children.length > 4) results.lastChild.remove();
  }

  form.querySelectorAll("[data-test]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const label = btn.textContent.trim();
      btn.disabled = true;
      btn.dataset.label = label;
      btn.textContent = "Test en cours…";
      try {
        const r = await fetch(`/api/tester/${btn.dataset.test}`, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({ valeurs: formValues() }),
        });
        if (r.status === 401) { location.href = "/connexion"; return; }
        show(label, await r.json());
      } catch (_) {
        show(label, { ok: false, message: "L'interface ne répond pas." });
      } finally {
        btn.disabled = false;
        btn.textContent = btn.dataset.label;
      }
    });
  });

  // « Effacer » un secret : le champ correspondant est désactivé
  form.querySelectorAll('.erase input[type="checkbox"]').forEach((box) => {
    const input = box.closest(".secret")?.querySelector('input[type="password"]');
    box.addEventListener("change", () => { if (input) { input.disabled = box.checked; input.value = ""; } });
  });

  // Prévenir si on quitte la page avec des modifications non enregistrées
  let dirty = false;
  form.addEventListener("input", () => { dirty = true; });
  form.addEventListener("submit", () => { dirty = false; });
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
})();
