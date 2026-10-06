const state = {
  data: [],
  meta: {}
};

const $ = (id) => document.getElementById(id);

function money(v) {
  return v == null ? "—" : "LKR " + Number(v).toLocaleString();
}
function pct(v) {
  return v == null ? "—" : Number(v).toLocaleString() + "%";
}
function num(v) {
  return v == null ? "—" : Number(v).toLocaleString();
}
function titleCase(v) {
  return String(v || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}
function escapeHtml(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}
function categoryIcon(category) {
  return ({
    cashback: "↻",
    new_customer: "✦",
    deposit_bonus: "＋",
    reload_bonus: "↗",
    free_bet: "🎁",
    racing_bonus: "🏇",
    sports_bonus: "⚡"
  })[category] || "◆";
}
function formatUpdated(v) {
  if (!v) return "Awaiting first scrape";
  return new Date(v).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function validOffers(data) {
  return data.filter(x => x.is_promotion !== false && x.quality_status !== "rejected");
}

function counterPromo(group) {
  const rivals = group.filter(x => x.platform !== "BETSS").sort((a, b) => b.score - a.score);
  const ref = rivals[0] || [...group].sort((a, b) => b.score - a.score)[0];
  if (!ref) return null;

  const category = ref.category;
  const parts = [];
  let headline = "";
  const bonus = ref.bonus_percent;
  const max = ref.max_bonus_lkr;
  const wager = ref.wagering_x;
  const minDep = ref.min_deposit_lkr;

  if (category === "cashback") {
    const suggested = bonus != null ? Math.min(20, Math.round((bonus + 1.5) * 10) / 10) : 6;
    headline = "Offer " + suggested + "% cashback";
    parts.push(suggested + "% cashback");
    if (minDep != null) parts.push("minimum qualifying deposit ≤ " + money(Math.max(0, Math.round(minDep * 0.75))));
    parts.push("prefer real-cash credit with 1x or lower rollover where commercially viable");
  } else if (category === "new_customer") {
    const suggested = bonus != null ? Math.round(bonus + 10) : 50;
    headline = suggested + "% First Deposit / Welcome Bonus";
    parts.push(suggested + "% bonus");
    if (max != null) parts.push("cap around " + money(Math.round(max * 1.1 / 1000) * 1000));
    if (minDep != null) parts.push("minimum deposit ≤ " + money(Math.max(500, Math.round(minDep * 0.75 / 100) * 100)));
    if (wager != null) parts.push("wagering ≤ " + Math.max(1, Math.ceil(wager - 1)) + "x");
  } else if (["reload_bonus", "deposit_bonus", "sports_bonus"].includes(category)) {
    const suggested = bonus != null ? Math.round(bonus + 10) : 50;
    headline = suggested + "% " + titleCase(category).replace(" Bonus", "") + " Counter Offer";
    parts.push(suggested + "% bonus");
    if (max != null) parts.push("cap ≥ " + money(Math.round(max * 1.1 / 1000) * 1000));
    if (wager != null) parts.push("wagering ≤ " + Math.max(1, Math.ceil(wager - 1)) + "x");
    if (minDep != null) parts.push("minimum deposit ≤ " + money(Math.max(500, Math.round(minDep * 0.75 / 100) * 100)));
  } else if (category === "free_bet") {
    headline = "Stronger Free Bet";
    parts.push(max != null ? "free bet value ≥ " + money(Math.round(max * 1.1 / 1000) * 1000) : "increase free-bet value by ~10%");
    parts.push("keep qualification simpler than the benchmark");
    if (wager != null) parts.push("wagering ≤ " + Math.max(1, Math.ceil(wager - 1)) + "x");
  } else if (category === "racing_bonus") {
    headline = "Racing Cashback / Bonus Counter Offer";
    parts.push(bonus != null ? Math.round(bonus + 5) + "% racing bonus" : "10% racing cashback");
    if (max != null) parts.push("cap ≥ " + money(Math.round(max * 1.1 / 1000) * 1000));
    if (wager != null) parts.push("wagering ≤ " + Math.max(1, Math.ceil(wager - 1)) + "x");
  } else {
    headline = "Simpler + stronger comparable offer";
    if (bonus != null) parts.push(Math.round(bonus + 10) + "% bonus");
    if (max != null) parts.push("cap ≥ " + money(Math.round(max * 1.1 / 1000) * 1000));
    if (wager != null) parts.push("wagering ≤ " + Math.max(1, Math.ceil(wager - 1)) + "x");
  }

  return { headline, details: parts, rationale: "Benchmark: " + ref.platform + " — " + ref.title };
}

function filteredOffers() {
  const q = $("search").value.toLowerCase();
  const cat = $("category").value;
  const plat = $("platform").value;
  return validOffers(state.data).filter(x =>
    (!q || JSON.stringify(x).toLowerCase().includes(q)) &&
    (!cat || x.category === cat) &&
    (!plat || x.platform === plat)
  );
}

function renderStats() {
  const offers = validOffers(state.data);
  const clusters = new Set(offers.map(x => x.cluster_key)).size;
  const platforms = new Set(offers.map(x => x.platform)).size;
  const best = offers.length ? Math.max(...offers.map(x => x.score || 0)) : 0;
  $("platforms").textContent = platforms;
  $("offers").textContent = offers.length;
  $("clustersCount").textContent = clusters;
  $("bestScore").textContent = best.toFixed(1);
  $("errors").textContent = (state.meta.errors || []).length;
  $("rejected").textContent = state.meta.rejected_count || Math.max(0, state.data.length - offers.length);
}

function renderInsights() {
  const offers = validOffers(state.data);
  if (!offers.length) {
    $("insights").innerHTML = '<article class="insight"><span>⌁</span><div><small>Market view</small><b>No validated offers yet</b><em>Run the scraper to populate the market.</em></div></article>';
    return;
  }

  const top = [...offers].sort((a,b) => b.score - a.score)[0];
  const lowWager = [...offers].filter(x => x.wagering_x != null).sort((a,b) => a.wagering_x - b.wagering_x)[0];
  const highCap = [...offers].filter(x => x.max_bonus_lkr != null).sort((a,b) => b.max_bonus_lkr - a.max_bonus_lkr)[0];
  const betss = offers.filter(x => x.platform === "BETSS");
  const competitorCount = new Set(offers.filter(x => x.platform !== "BETSS").map(x => x.platform)).size;

  $("insights").innerHTML = [
    ["★", "Top benchmark", top.platform + " · " + top.title, "Score " + num(top.score)],
    ["↓", "Lowest wagering", lowWager ? lowWager.platform + " · " + lowWager.title : "Not enough data", lowWager ? num(lowWager.wagering_x) + "x wagering" : "—"],
    ["↥", "Largest visible cap", highCap ? highCap.platform + " · " + highCap.title : "Not enough data", highCap ? money(highCap.max_bonus_lkr) : "—"],
    ["◎", "Market coverage", competitorCount + " competitor platforms", betss.length + " BETSS offers captured"]
  ].map(([icon,label,value,sub]) => '<article class="insight"><span class="insight-icon">' + icon + '</span><div><small>' + escapeHtml(label) + '</small><b>' + escapeHtml(value) + '</b><em>' + escapeHtml(sub) + '</em></div></article>').join("");
}

function renderClusters() {
  const filtered = filteredOffers();
  const groups = {};
  filtered.forEach(x => (groups[x.cluster_key] ??= []).push(x));

  const cards = Object.values(groups)
    .sort((a,b) => Math.max(...b.map(x => x.score || 0)) - Math.max(...a.map(x => x.score || 0)))
    .slice(0, 12);

  $("winners").innerHTML = cards.map(g => {
    const winner = [...g].sort((a,b) => b.score - a.score)[0];
    const cp = counterPromo(g);
    const betss = g.filter(x => x.platform === "BETSS").sort((a,b) => b.score - a.score)[0];
    const competitor = g.filter(x => x.platform !== "BETSS").sort((a,b) => b.score - a.score)[0];
    const gap = competitor && betss ? competitor.score - betss.score : null;
    const official = g.filter(x => x.source_type === "official").length;

    return '<article class="cluster-card">' +
      '<div class="cluster-top"><span class="category-chip">' + categoryIcon(winner.category) + ' ' + escapeHtml(titleCase(winner.category)) + '</span><span class="score-pill">' + num(winner.score) + ' score</span></div>' +
      '<div class="cluster-title">' + escapeHtml(winner.cluster_label) + '</div>' +
      '<div class="benchmark"><div><small>BEST MARKET OFFER</small><strong>' + escapeHtml(winner.platform) + '</strong><p>' + escapeHtml(winner.title) + '</p></div><div class="benchmark-score">' + num(winner.score) + '</div></div>' +
      '<div class="mini-metrics"><span><small>Bonus</small><b>' + pct(winner.bonus_percent) + '</b></span><span><small>Max</small><b>' + money(winner.max_bonus_lkr) + '</b></span><span><small>Wagering</small><b>' + (winner.wagering_x == null ? "—" : winner.wagering_x + "x") + '</b></span></div>' +
      (betss && competitor ? '<div class="gap ' + (gap > 0 ? "behind" : "ahead") + '"><b>BETSS vs benchmark</b><span>' + (gap > 0 ? "-" + gap.toFixed(1) + " score gap" : "+" + Math.abs(gap).toFixed(1) + " ahead") + '</span></div>' : '<div class="gap neutral"><b>Benchmark only</b><span>' + Math.round((official / g.length) * 100) + '% official sources</span></div>') +
      (cp ? '<div class="counter"><div class="counter-label">BETSS COUNTER-PROMO</div><strong>' + escapeHtml(cp.headline) + '</strong><ul>' + cp.details.map(x => '<li>' + escapeHtml(x) + '</li>').join("") + '</ul><small>' + escapeHtml(cp.rationale) + '</small></div>' : '') +
      '</article>';
  }).join("") || '<article class="empty-card">No matching validated promotions.</article>';

  $("clusterCount").textContent = cards.length + " clusters shown";
}

function renderTable() {
  const filtered = filteredOffers();
  $("count").textContent = filtered.length + " validated offers";

  $("rows").innerHTML = filtered.map(x => '<tr>' +
    '<td><span class="platform-dot"></span><b>' + escapeHtml(x.platform) + '</b></td>' +
    '<td><div class="promo-title">' + escapeHtml(x.title) + '</div><small class="muted">' + escapeHtml(x.sport || "All Sports") + '</small></td>' +
    '<td><span class="soft-tag">' + escapeHtml(titleCase(x.customer_type)) + '</span></td>' +
    '<td>' + escapeHtml(x.cluster_label) + '</td>' +
    '<td><b>' + pct(x.bonus_percent) + '</b></td>' +
    '<td>' + money(x.max_bonus_lkr) + '</td>' +
    '<td>' + (x.wagering_x == null ? "—" : x.wagering_x + "x") + '</td>' +
    '<td>' + money(x.min_deposit_lkr) + '</td>' +
    '<td><span class="score-small">' + num(x.score) + '</span></td>' +
    '<td><a class="source-link" target="_blank" rel="noopener" href="' + escapeHtml(x.source_url) + '">View ↗</a></td>' +
  '</tr>').join("") || '<tr><td colspan="10" class="empty-row">No validated promotions match your filters.</td></tr>';
}

function render() {
  renderStats();
  renderInsights();
  renderClusters();
  renderTable();
}

async function init() {
  const r = await fetch("data/promotions.json", { cache: "no-store" });
  if (!r.ok) throw new Error("Promotion data unavailable");
  const j = await r.json();

  state.data = j.promotions || [];
  state.meta = j;

  $("updated").textContent = formatUpdated(j.updated_at);
  $("sourceCount").textContent = new Set(state.data.map(x => x.platform)).size + " platforms scanned";
  $("qualityNote").textContent = (j.rejected_count || 0) + " low-confidence / non-promotion pages excluded from the live view";

  const categories = [...new Set(validOffers(state.data).map(x => x.category))].sort();
  const platforms = [...new Set(validOffers(state.data).map(x => x.platform))].sort();

  for (const [id, values] of [["category", categories], ["platform", platforms]]) {
    const select = $(id);
    select.innerHTML = '<option value="">All ' + (id === "category" ? "categories" : "platforms") + '</option>';
    values.forEach(v => {
      const o = document.createElement("option");
      o.value = v;
      o.textContent = titleCase(v);
      select.appendChild(o);
    });
  }

  render();
}

$("search").oninput = render;
$("category").onchange = render;
$("platform").onchange = render;
init().catch(err => {
  console.error(err);
  $("winners").innerHTML = '<article class="empty-card">Could not load promotion data. Check the latest GitHub Actions run.</article>';
});