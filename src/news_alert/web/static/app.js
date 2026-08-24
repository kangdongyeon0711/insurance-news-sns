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

async function loadInsurers() {
  const select = document.getElementById("insurer-filter");
  try {
    const res = await fetch("/api/insurers");
    const insurers = await res.json();
    insurers.sort((a, b) => a.localeCompare(b, "ko"));
    for (const name of insurers) {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      select.appendChild(option);
    }
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

document.getElementById("insurer-filter").addEventListener("change", (event) => {
  state.insurer = event.target.value;
  loadArticles();
});

loadInsurers();
loadArticles();
