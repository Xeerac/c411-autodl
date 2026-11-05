// c411-autodl : relevés quotidiens (comparaison avec la veille, courbe du ratio, envoyé par jour, historique).
// Graphiques en SVG construits par le script, sans bibliothèque. Données insérées comme texte.
(() => {
  const $ = (id) => document.getElementById(id);
  if (!$("compare")) return;
  const SVG = "http://www.w3.org/2000/svg";
  const ICONS = document.querySelector('link[rel="icon"]')?.href.replace(/logo\.svg$/, "icons.svg") || "/static/icons.svg";

  const el = (tag, props = {}, children = []) => {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (v == null) return;
      if (k === "text") node.textContent = v; else if (k === "class") node.className = v; else node.setAttribute(k, v);
    });
    children.forEach((c) => c && node.append(c));
    return node;
  };
  const svgEl = (tag, attrs = {}) => {
    const node = document.createElementNS(SVG, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
  };
  const icon = (name) => {
    const s = svgEl("svg", { class: "icon", "aria-hidden": "true" });
    s.append(svgEl("use", { href: `${ICONS}#${name}` }));
    return s;
  };
  const fmtDay = (d) => new Date(d + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
  const fmtPct = (p) => p == null ? "" : `${p >= 0 ? "+" : "−"}${Math.abs(p).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} %`;
  const human = (n) => {
    const a = Math.abs(n);
    if (a >= 1024 ** 4) return `${(n / 1024 ** 4).toFixed(2)} To`;
    if (a >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} Go`;
    return `${(n / 1024 ** 2).toFixed(1)} Mo`;
  };

  // Sens d'une variation : pour le reçu, une hausse fait baisser le ratio (on la montre en orange, pas en vert)
  function tone(metric, delta) {
    if (delta == null || delta === 0) return "flat";
    if (metric === "recu") return delta > 0 ? "warn" : "up";
    return delta > 0 ? "up" : "down";
  }

  function delta(metric, row) {
    const d = row[`${metric}_delta`];
    if (d == null) return el("span", { class: "delta-text muted", text: "premier relevé : la comparaison commence demain" });
    const text = metric === "ratio" ? `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(2)}` : row[`${metric}_delta_txt`];
    return el("span", { class: `delta-pill tone-${tone(metric, d)}` }, [
      icon(d > 0 ? "hausse" : d < 0 ? "baisse" : "courbe"),
      el("span", { text: `${text} · ${fmtPct(row[`${metric}_pct`]) || "0 %"}` }),
      el("span", { class: "delta-since", text: "sur la veille" }),
    ]);
  }

  function renderCompare(rows) {
    const last = rows[0];
    for (const metric of ["ratio", "envoye", "recu"]) {
      $(`cmp-${metric}`).textContent = metric === "ratio" ? last.ratio.toFixed(2) : last[`${metric}_txt`];
      $(`cmp-${metric}-delta`).replaceChildren(delta(metric, last));
    }
  }

  // ------------------------------------------------------------------ graphiques
  const W = 640, H = 200, PAD = { l: 44, r: 14, t: 14, b: 26 };

  function axes(svg, min, max, fmt, labels) {
    for (let i = 0; i <= 3; i++) {
      const y = PAD.t + (H - PAD.t - PAD.b) * (i / 3);
      const v = max - (max - min) * (i / 3);
      svg.append(svgEl("line", { x1: PAD.l, x2: W - PAD.r, y1: y, y2: y, class: "grid-line" }));
      const t = svgEl("text", { x: PAD.l - 8, y: y + 4, class: "axis-label", "text-anchor": "end" });
      t.textContent = fmt(v);
      svg.append(t);
    }
    labels.forEach(([x, text, anchor]) => {
      const t = svgEl("text", { x, y: H - 6, class: "axis-label", "text-anchor": anchor });
      t.textContent = text;
      svg.append(t);
    });
  }

  function lineChart(series) {
    const box = $("chart-ratio");
    if (series.length < 2) {
      box.replaceChildren(el("div", { class: "empty" }, [icon("courbe"), el("strong", { text: "La courbe arrive demain" }),
        el("span", { text: "Il faut au moins deux relevés pour tracer l'évolution du ratio." })]));
      return;
    }
    const vals = series.map((r) => r.ratio);
    let min = Math.min(...vals), max = Math.max(...vals);
    const pad = Math.max((max - min) * 0.15, 0.02);
    min -= pad; max += pad;
    const x = (i) => PAD.l + (W - PAD.l - PAD.r) * (i / (series.length - 1));
    const y = (v) => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - min) / (max - min));
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg" });
    axes(svg, min, max, (v) => v.toFixed(2),
         [[x(0), fmtDay(series[0].jour), "start"], [x(series.length - 1), fmtDay(series.at(-1).jour), "end"]]);
    const pts = series.map((r, i) => `${x(i).toFixed(1)},${y(r.ratio).toFixed(1)}`);
    svg.append(svgEl("path", { d: `M${pts[0]} L${pts.join(" L")} L${x(series.length - 1)},${H - PAD.b} L${x(0)},${H - PAD.b} Z`, class: "chart-area" }));
    svg.append(svgEl("polyline", { points: pts.join(" "), class: "chart-line" }));
    const lx = x(series.length - 1), ly = y(series.at(-1).ratio);
    svg.append(svgEl("circle", { cx: lx, cy: ly, r: 4, class: "chart-dot" }));
    series.forEach((r, i) => {
      const hit = svgEl("circle", { cx: x(i), cy: y(r.ratio), r: 9, class: "chart-hit" });
      const title = svgEl("title");
      title.textContent = `${fmtDay(r.jour)} : ratio ${r.ratio.toFixed(2)}`;
      hit.append(title);
      svg.append(hit);
    });
    box.replaceChildren(svg);
    $("courbe-periode").textContent = `${series.length} jours`;
  }

  function barChart(series) {
    const box = $("chart-upload");
    const days = series.filter((r) => r.envoye_delta != null);
    if (!days.length) {
      box.replaceChildren(el("div", { class: "empty" }, [icon("bilan"), el("strong", { text: "Les barres arrivent demain" }),
        el("span", { text: "Chaque barre montre ce que tu as envoyé entre deux relevés." })]));
      return;
    }
    const max = Math.max(...days.map((r) => Math.max(r.envoye_delta, 0)), 1);
    const n = days.length, slot = (W - PAD.l - PAD.r) / n, bw = Math.min(28, slot * 0.62);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg" });
    axes(svg, 0, max, human, [[PAD.l, fmtDay(days[0].jour), "start"], [W - PAD.r, fmtDay(days.at(-1).jour), "end"]]);
    days.forEach((r, i) => {
      const v = Math.max(r.envoye_delta, 0);
      const h = (H - PAD.t - PAD.b) * (v / max);
      const bar = svgEl("rect", { x: PAD.l + slot * i + (slot - bw) / 2, y: H - PAD.b - h, width: bw, height: Math.max(h, 1.5), rx: 3,
                                  class: "chart-bar" + (i === n - 1 ? " is-last" : "") });
      const title = svgEl("title");
      title.textContent = `${fmtDay(r.jour)} : ${r.envoye_delta_txt} envoyés`;
      bar.append(title);
      svg.append(bar);
    });
    box.replaceChildren(svg);
  }

  // ------------------------------------------------------------------ historique
  function cell(metric, r) {
    const main = metric === "ratio" ? r.ratio.toFixed(2) : r[`${metric}_txt`];
    const d = r[`${metric}_delta`];
    const sub = d == null ? null : el("span", { class: `cell-delta tone-${tone(metric, d)}`,
      text: metric === "ratio" ? `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(2)} (${fmtPct(r.ratio_pct)})` : `${r[`${metric}_delta_txt`]} (${fmtPct(r[`${metric}_pct`])})` });
    return el("td", { class: "num" }, [el("span", { class: "cell-main", text: main }), sub]);
  }

  function renderTable(rows) {
    const body = $("historique").tBodies[0];
    body.replaceChildren(...rows.map((r) => el("tr", {}, [
      el("td", { class: "cell-jour", text: fmtDay(r.jour) }), cell("ratio", r), cell("envoye", r), cell("recu", r),
    ])));
  }

  async function load() {
    let data;
    try {
      const r = await fetch("/api/releves", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/connexion"; return; }
      data = await r.json();
    } catch (_) {
      $("releves-note").textContent = "Impossible de lire les relevés pour l'instant.";
      return;
    }
    $("releves-note").textContent = `Un relevé par jour à ${data.heure} h, comparé au relevé précédent.`;
    const rows = data.releves || [];
    if (!rows.length) {
      const msg = data.profil ? "Le premier relevé est pris au prochain passage du programme, dans quelques minutes."
                              : "Il faut la clé API Profil (Configuration → c411) pour lire ton ratio.";
      ["ratio", "envoye", "recu"].forEach((m) => $(`cmp-${m}-delta`).replaceChildren());
      $("chart-ratio").replaceChildren(el("div", { class: "empty" }, [icon("courbe"), el("strong", { text: "Pas encore de relevé" }), el("span", { text: msg })]));
      $("chart-upload").replaceChildren();
      $("historique").tBodies[0].replaceChildren(el("tr", {}, [el("td", { colspan: "4", class: "muted", text: msg })]));
      return;
    }
    renderCompare(rows);
    const chrono = rows.slice(0, 30).reverse();
    lineChart(chrono);
    barChart(chrono);
    renderTable(rows);
  }

  load();
  setInterval(load, 5 * 60 * 1000);
})();
