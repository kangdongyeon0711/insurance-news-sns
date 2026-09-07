const state = { insurer: "" };

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function formatPublishedAt(isoString) {
  const parsed = new Date(isoString);
  return Number.isNaN(parsed.getTime()) ? isoString : parsed.toLocaleString("ko-KR");
}

function renderArticleCard(article) {
  const card = document.createElement("article");
  card.className = "card";

  const insurerTags = article.insurers
    .map((name) => `<span class="tag tag-insurer">${escapeHtml(name)}</span>`)
    .join("");
  const keywordTags = article.keywords
    .map((keyword) => `<span class="tag tag-keyword">${escapeHtml(keyword)}</span>`)
    .join("");

  card.innerHTML = `
    <a class="card-title" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">
      ${escapeHtml(article.title)}
    </a>
    <div class="card-meta">${escapeHtml(article.source)} · ${escapeHtml(formatPublishedAt(article.published_at))}</div>
    <p class="card-summary">${escapeHtml(article.summary)}</p>
    <div class="card-tags">${insurerTags}${keywordTags}</div>
  `;
  return card;
}

let filterSelects = [];

function buildFilterGroups(grouped) {
  const container = document.getElementById("filter-groups");
  container.innerHTML = "";
  filterSelects = [];

  for (const [label, names] of Object.entries(grouped)) {
    const selectId = `filter-${label}`;

    const labelEl = document.createElement("label");
    labelEl.setAttribute("for", selectId);
    labelEl.textContent = label;

    const select = document.createElement("select");
    select.id = selectId;

    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "전체";
    select.appendChild(allOption);

    const sorted = [...names].sort((a, b) => a.localeCompare(b, "ko"));
    for (const name of sorted) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      select.appendChild(option);
    }

    select.addEventListener("change", (event) => {
      state.insurer = event.target.value;
      // 필터는 한 번에 하나만 적용 — 다른 드롭다운은 "전체"로 초기화
      for (const other of filterSelects) {
        if (other !== select) other.value = "";
      }
      loadArticles();
    });

    filterSelects.push(select);

    const group = document.createElement("div");
    group.className = "filter-group";
    group.appendChild(labelEl);
    group.appendChild(select);
    container.appendChild(group);
  }
}

async function loadInsurers() {
  try {
    const res = await fetch("/api/insurers");
    const grouped = await res.json();
    buildFilterGroups(grouped);
  } catch (err) {
    console.error("failed to load insurers", err);
  }
}

async function loadArticles() {
  const listEl = document.getElementById("article-list");
  const countEl = document.getElementById("article-count");
  listEl.innerHTML = '<p class="status">불러오는 중...</p>';

  const params = new URLSearchParams({ limit: "100" });
  if (state.insurer) params.set("insurer", state.insurer);

  try {
    const res = await fetch(`/api/articles?${params}`);
    const articles = await res.json();

    countEl.textContent = `${articles.length}건`;

    if (articles.length === 0) {
      listEl.innerHTML = '<p class="status">표시할 기사가 없습니다.</p>';
      return;
    }

    listEl.innerHTML = "";
    for (const article of articles) {
      listEl.appendChild(renderArticleCard(article));
    }
  } catch (err) {
    listEl.innerHTML = '<p class="status">기사를 불러오지 못했습니다.</p>';
    console.error("failed to load articles", err);
  }
}

loadInsurers();
loadArticles();
