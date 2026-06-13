const state = {
  summary: [],
  poiRows: [],
  neighbourhoodRows: [],
  recommendationRows: [],
  movementSummaryRows: [],
  transitionRows: [],
  strategy: "all",
  query: "",
  map: null,
  markerLayer: null
};

const niceNames = {
  all: "All",
  popularity: "Popularity",
  personalized: "Personalized",
  sustainable: "Sustainable"
};

const metricSpecs = [
  ["avg_satisfaction", "Satisfaction", 3],
  ["avg_sustainability", "Sustainability", 3],
  ["poi_coverage", "POI Coverage", 3],
  ["district_gini", "District Gini", 3],
  ["wealth_gini", "Wealth Gini", 3],
  ["local_spend_share", "Local Spend Share", 3],
  ["temporal_overcap_share", "Over-Capacity Share", 3],
  ["peak_occupancy_ratio", "Peak Occupancy", 2]
];

const strategyColors = {
  popularity: "#db4437",
  personalized: "#4285f4",
  sustainable: "#0f9d58",
  all: "#555"
};

function rowsForStrategy(rows) {
  return rows.filter(row => state.strategy === "all" || row.recommender === state.strategy);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function inlineMarkdown(value) {
  let text = escapeHtml(value);
  text = text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, src) => {
    const normalizedSrc = src.startsWith("outputs/") ? `../${src}` : src;
    return `<img src="${escapeHtml(normalizedSrc)}" alt="${escapeHtml(alt)}">`;
  });
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
    const normalizedHref = href.startsWith("outputs/") ? `../${href}` : href;
    return `<a href="${escapeHtml(normalizedHref)}">${escapeHtml(label)}</a>`;
  });
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return text;
}

function renderMarkdown(markdown) {
  const lines = markdown.replaceAll("\r\n", "\n").split("\n");
  const html = [];
  let paragraph = [];
  let list = [];
  let code = [];
  let inCode = false;

  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };

  const flushList = () => {
    if (list.length) {
      html.push(`<ul>${list.map(item => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
      list = [];
    }
  };

  const isTableStart = index => {
    return lines[index]?.includes("|") && lines[index + 1]?.trim().match(/^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/);
  };

  for (let i = 0; i < lines.length; i += 1) {
    const raw = lines[i];
    const line = raw.trim();

    if (line.startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        code = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      code.push(raw);
      continue;
    }

    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    if (isTableStart(i)) {
      flushParagraph();
      flushList();
      const headers = line.split("|").map(cell => cell.trim()).filter(Boolean);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(lines[i].split("|").map(cell => cell.trim()).filter(Boolean));
        i += 1;
      }
      i -= 1;
      html.push(`
        <table>
          <thead><tr>${headers.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>
          <tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
        </table>
      `);
      continue;
    }

    if (line.startsWith("# ")) {
      flushParagraph();
      flushList();
      html.push(`<h1>${inlineMarkdown(line.slice(2))}</h1>`);
      continue;
    }

    if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      html.push(`<h2>${inlineMarkdown(line.slice(3))}</h2>`);
      continue;
    }

    if (line.startsWith("### ")) {
      flushParagraph();
      flushList();
      html.push(`<h3>${inlineMarkdown(line.slice(4))}</h3>`);
      continue;
    }

    if (line.startsWith("- ")) {
      flushParagraph();
      list.push(line.slice(2));
      continue;
    }

    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  return html.join("");
}

function parseCSV(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && next === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(cell);
      if (row.some(value => value.length > 0)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }

  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }

  const headers = rows.shift();
  return rows.map(values => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function toNumberRows(rows) {
  return rows.map(row => {
    const next = { ...row };
    Object.keys(next).forEach(key => {
      const value = Number(next[key]);
      if (next[key] !== "" && !Number.isNaN(value)) next[key] = value;
    });
    return next;
  });
}

function groupMean(rows, key) {
  const grouped = new Map();
  rows.forEach(row => {
    const name = row[key];
    if (!grouped.has(name)) grouped.set(name, []);
    grouped.get(name).push(row);
  });
  return Array.from(grouped.entries()).map(([name, values]) => {
    const result = { [key]: name };
    Object.keys(values[0]).forEach(column => {
      if (typeof values[0][column] === "number") {
        result[column] = values.reduce((sum, row) => sum + row[column], 0) / values.length;
      }
    });
    return result;
  });
}

function aggregatePoiRows() {
  const filtered = state.poiRows.filter(row => state.strategy === "all" || row.recommender === state.strategy);
  const grouped = new Map();

  filtered.forEach(row => {
    const key = state.strategy === "all" ? row.poi : `${row.recommender}|${row.poi}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(row);
  });

  return Array.from(grouped.values()).map(values => {
    const first = values[0];
    const result = {
      poi: first.poi,
      district: first.district,
      neighbourhood: first.neighbourhood,
      recommender: state.strategy === "all" ? "all" : first.recommender
    };

    ["lat", "lon", "visits", "capacity", "utilization", "popularity", "sustainability", "local_value"].forEach(column => {
      result[column] = values.reduce((sum, row) => sum + Number(row[column] || 0), 0) / values.length;
    });

    return result;
  });
}

function formatValue(value, digits = 2) {
  if (value >= 100) return Math.round(value).toLocaleString();
  return Number(value).toFixed(digits);
}

function activeSummary() {
  const means = groupMean(state.summary, "recommender");
  if (state.strategy === "all") return means;
  return means.filter(row => row.recommender === state.strategy);
}

function renderMetrics() {
  const rows = activeSummary();
  const best = rows.length === 1
    ? rows[0]
    : rows.find(row => row.recommender === "sustainable") || rows[0];

  const grid = document.getElementById("metricGrid");
  grid.innerHTML = metricSpecs.map(([key, label, digits]) => `
    <article class="metric">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${formatValue(best[key], digits)}</div>
    </article>
  `).join("");
}

function renderBars(elementId, rows, key, inverse = false) {
  const container = document.getElementById(elementId);
  const max = Math.max(...rows.map(row => row[key]), 0.001);
  container.innerHTML = rows.map(row => {
    const rawWidth = inverse ? (max - row[key]) / max : row[key] / max;
    const width = Math.max(4, Math.round(rawWidth * 100));
    return `
      <div class="bar-row">
        <div class="bar-label">${niceNames[row.recommender]}</div>
        <div class="bar-track"><div class="bar-fill ${row.recommender}" style="width:${width}%"></div></div>
        <div class="bar-value">${formatValue(row[key], 3)}</div>
      </div>
    `;
  }).join("");
}

function renderCharts() {
  const rows = activeSummary();
  renderBars("satisfactionChart", rows, "avg_satisfaction");
  renderBars("giniChart", rows, "district_gini", true);
  renderBars("sustainabilityChart", rows, "avg_sustainability");
  renderBars("precisionChart", rows, "precision_at_5");
  renderBars("recallChart", rows, "recall_at_5");
  renderBars("diversityChart", rows, "diversity_at_5");
  renderBars("exposureChart", rows, "exposure_gini", true);
}

function filteredPoiRows() {
  const q = state.query.trim().toLowerCase();
  return aggregatePoiRows()
    .filter(row => {
      if (!q) return true;
      return [row.poi, row.district, row.neighbourhood, row.recommender]
        .join(" ")
        .toLowerCase()
        .includes(q);
    })
    .sort((a, b) => b.visits - a.visits)
    .slice(0, 60);
}

function initMap() {
  if (state.map || typeof L === "undefined") return;

  state.map = L.map("poiMap", {
    scrollWheelZoom: false,
    zoomControl: true
  }).setView([41.3902, 2.1700], 12);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(state.map);

  state.markerLayer = L.layerGroup().addTo(state.map);
}

function renderMap() {
  const rows = aggregatePoiRows().filter(row => Number.isFinite(row.lat) && Number.isFinite(row.lon));
  const mapNode = document.getElementById("poiMap");

  if (typeof L === "undefined") {
    mapNode.innerHTML = "Map tiles could not load. Check the internet connection and refresh.";
    return;
  }

  initMap();
  state.markerLayer.clearLayers();

  if (!rows.length) return;

  const maxVisits = Math.max(...rows.map(row => row.visits), 1);
  const bounds = [];

  rows.forEach(row => {
    const strategy = row.recommender === "all" ? "all" : row.recommender;
    const radius = 5 + Math.sqrt(row.visits / maxVisits) * 15;
    const marker = L.circleMarker([row.lat, row.lon], {
      radius,
      color: "#fff",
      weight: 2,
      fillColor: strategyColors[strategy],
      fillOpacity: 0.78
    });
    marker.bindPopup(`
      <div class="map-popup-title">${row.poi}</div>
      <div class="map-popup-meta">${row.district} / ${row.neighbourhood}</div>
      <div class="map-popup-meta">${formatValue(row.visits, 0)} mean visits - ${formatValue(row.utilization, 3)} utilization</div>
    `);
    marker.addTo(state.markerLayer);
    bounds.push([row.lat, row.lon]);
  });

  state.map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
}

function renderTable() {
  const rows = filteredPoiRows();
  document.getElementById("resultCount").textContent = `${rows.length} results`;
  document.getElementById("poiTable").innerHTML = rows.map(row => `
    <tr>
      <td>${row.poi}</td>
      <td>${row.district}</td>
      <td><span class="pill ${row.recommender}">${niceNames[row.recommender]}</span></td>
      <td>${formatValue(row.visits, 0)}</td>
      <td>${formatValue(row.utilization, 3)}</td>
    </tr>
  `).join("");
}

function renderRecommendationTable() {
  const q = state.query.trim().toLowerCase();
  const rows = rowsForStrategy(state.recommendationRows)
    .filter(row => {
      if (!q) return true;
      return [row.primary_interests, row.recommended_pois, row.chosen_poi, row.recommender]
        .join(" ")
        .toLowerCase()
        .includes(q);
    })
    .slice(0, 40);

  document.getElementById("recommendationCount").textContent = `${rows.length} rows`;
  document.getElementById("recommendationTable").innerHTML = rows.map(row => `
    <tr>
      <td>${row.tourist_id}</td>
      <td>${String(row.primary_interests).replaceAll("|", ", ")}</td>
      <td>${String(row.recommended_pois).replaceAll("|", ", ")}</td>
      <td>${row.chosen_poi || "Skipped"}</td>
      <td>${formatValue(row.precision_at_k, 3)}</td>
    </tr>
  `).join("");
}

function renderNeighbourhoods() {
  const rows = state.neighbourhoodRows
    .filter(row => state.strategy === "all" || row.recommender === state.strategy);
  const grouped = groupMean(rows, "neighbourhood")
    .sort((a, b) => b.visits - a.visits)
    .slice(0, 12);
  const max = Math.max(...grouped.map(row => row.visits), 1);

  document.getElementById("neighbourhoodList").innerHTML = grouped.map(row => `
    <div class="neighbourhood-item">
      <div class="neighbourhood-top">
        <span>${row.neighbourhood}</span>
        <span>${formatValue(row.visits, 0)}</span>
      </div>
      <div class="bar-track"><div class="bar-fill sustainable" style="width:${Math.max(4, Math.round(row.visits / max * 100))}%"></div></div>
    </div>
  `).join("");
}

function renderMovement() {
  const summaryRows = rowsForStrategy(state.movementSummaryRows);
  const summary = summaryRows.length === 1 ? summaryRows[0] : {
    avg_distance_km: summaryRows.reduce((sum, row) => sum + row.avg_distance_km, 0) / Math.max(1, summaryRows.length),
    avg_travel_time_hours: summaryRows.reduce((sum, row) => sum + row.avg_travel_time_hours, 0) / Math.max(1, summaryRows.length),
    cross_district_share: summaryRows.reduce((sum, row) => sum + row.cross_district_share, 0) / Math.max(1, summaryRows.length),
    unique_transitions: summaryRows.reduce((sum, row) => sum + row.unique_transitions, 0),
  };

  document.getElementById("movementMetrics").innerHTML = `
    <article class="metric">
      <div class="metric-label">Avg Leg Distance</div>
      <div class="metric-value">${formatValue(summary.avg_distance_km || 0, 2)} km</div>
    </article>
    <article class="metric">
      <div class="metric-label">Avg Travel Time</div>
      <div class="metric-value">${formatValue((summary.avg_travel_time_hours || 0) * 60, 1)} min</div>
    </article>
    <article class="metric">
      <div class="metric-label">Cross-District Share</div>
      <div class="metric-value">${formatValue(summary.cross_district_share || 0, 3)}</div>
    </article>
    <article class="metric">
      <div class="metric-label">Unique Transitions</div>
      <div class="metric-value">${formatValue(summary.unique_transitions || 0, 0)}</div>
    </article>
  `;

  const sorted = rowsForStrategy(state.transitionRows)
    .sort((a, b) => b.transitions - a.transitions)
    .slice(0, 18);
  const max = Math.max(...sorted.map(row => row.transitions), 1);

  document.getElementById("transitionCount").textContent = `${sorted.length} transitions`;
  document.getElementById("transitionList").innerHTML = sorted.map(row => `
    <div class="transition-row">
      <span>${row.from_district} -> ${row.to_district}</span>
      <span class="transition-count">${formatValue(row.transitions, 0)}</span>
      <div class="bar-track"><div class="bar-fill sustainable" style="width:${Math.max(4, Math.round(row.transitions / max * 100))}%"></div></div>
    </div>
  `).join("");
}

function renderSummaryLine() {
  const runs = new Set(state.summary.map(row => row.run)).size;
  const tourists = state.summary[0]?.tourists || 0;
  const label = state.strategy === "all" ? "all recommenders" : `${niceNames[state.strategy]} recommender`;
  document.getElementById("summaryLine").textContent = `${tourists.toLocaleString()} tourists per run - ${runs} runs - ${label}`;
  document.getElementById("activeStrategyLabel").textContent = state.strategy === "all" ? "All recommenders" : niceNames[state.strategy];
}

function render() {
  renderSummaryLine();
  renderMetrics();
  renderCharts();
  renderMap();
  renderTable();
  renderNeighbourhoods();
  renderRecommendationTable();
  renderMovement();
}

async function loadReport() {
  const report = await fetch("../PROJECT_REPORT.md").then(response => response.text());
  document.getElementById("reportContent").innerHTML = renderMarkdown(report);
}

async function loadData() {
  const [summaryText, poiText, neighbourhoodText, recommendationText, movementSummaryText, transitionText] = await Promise.all([
    fetch("../outputs/summary_metrics.csv").then(response => response.text()),
    fetch("../outputs/poi_visits.csv").then(response => response.text()),
    fetch("../outputs/neighbourhood_visits.csv").then(response => response.text()),
    fetch("../outputs/recommendations_sample.csv").then(response => response.text()),
    fetch("../outputs/movement_summary.csv").then(response => response.text()),
    fetch("../outputs/movement_transitions.csv").then(response => response.text())
  ]);

  state.summary = toNumberRows(parseCSV(summaryText));
  state.poiRows = toNumberRows(parseCSV(poiText));
  state.neighbourhoodRows = toNumberRows(parseCSV(neighbourhoodText));
  state.recommendationRows = toNumberRows(parseCSV(recommendationText));
  state.movementSummaryRows = toNumberRows(parseCSV(movementSummaryText));
  state.transitionRows = toNumberRows(parseCSV(transitionText));
  render();
  await loadReport();
}

document.getElementById("searchForm").addEventListener("submit", event => {
  event.preventDefault();
  state.query = document.getElementById("searchInput").value;
  renderTable();
  renderRecommendationTable();
});

document.getElementById("searchInput").addEventListener("input", event => {
  state.query = event.target.value;
  renderTable();
  renderRecommendationTable();
});

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
    tab.classList.add("active");
    state.strategy = tab.dataset.strategy;
    render();
  });
});

document.querySelectorAll(".nav-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach(item => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach(view => view.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.view).classList.add("active");
    const isStandalone = tab.dataset.view === "reportView" || tab.dataset.view === "sensitivityView";
    document.getElementById("searchStage").style.display = isStandalone ? "none" : "";
    document.getElementById("summaryLine").style.display = isStandalone ? "none" : "";
    document.getElementById("metricGrid").style.display = isStandalone ? "none" : "";
    if (tab.dataset.view === "simulationView" && state.map) {
      setTimeout(() => state.map.invalidateSize(), 0);
    }
  });
});

loadData().catch(error => {
  document.getElementById("summaryLine").textContent = "Could not load experiment outputs. Run the experiment first.";
  console.error(error);
});