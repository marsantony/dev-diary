/* Dev Diary - 前端主邏輯 */

let state = {
  dates: [],          // 可用日期列表
  currentIndex: -1,   // 目前顯示的日期 index
  currentView: "daily",
  idToken: null,      // Google ID Token
  userName: null,
  // 快取：避免重複請求
  publicCache: {},
  privateCache: {},
};

// ── 初始化 ──

async function init() {
  const indexData = await fetchJSON("/data/index.json");
  if (!indexData || !indexData.dates || indexData.dates.length === 0) {
    showEmpty();
    return;
  }
  state.dates = indexData.dates.sort();
  state.currentIndex = state.dates.length - 1; // 預設最新一天
  await loadCurrentDate();
}

// ── 資料載入 ──

async function loadCurrentDate() {
  const date = state.dates[state.currentIndex];
  document.getElementById("current-date").textContent = date;
  updateNavButtons();

  if (state.currentView === "daily") {
    await loadDaily(date);
  } else {
    await loadWeekly(date);
  }
}

async function loadDaily(date) {
  document.getElementById("daily-view").hidden = false;
  document.getElementById("weekly-view").hidden = true;
  document.getElementById("empty-state").hidden = true;

  // 先載入公開版
  let data = state.publicCache[date];
  if (!data) {
    data = await fetchJSON(`/data/daily-${date}.json`);
    if (data) state.publicCache[date] = data;
  }

  // 如果已登入，嘗試載入完整版
  if (state.idToken) {
    let privateData = state.privateCache[date];
    if (!privateData) {
      privateData = await fetchAPI(`/api/summaries?type=daily&date=${date}`);
      if (privateData) state.privateCache[date] = privateData;
    }
    if (privateData) data = privateData;
  }

  if (!data) {
    showEmpty();
    return;
  }

  renderDaily(data);
}

async function loadWeekly(date) {
  document.getElementById("daily-view").hidden = true;
  document.getElementById("weekly-view").hidden = false;
  document.getElementById("empty-state").hidden = true;

  // 找到包含 date 的最近一個週六（週報 key）
  const weekEnd = findWeekEnd(date);
  if (!weekEnd) {
    document.getElementById("weekly-content").innerHTML = "<p>此日期範圍尚無週報。</p>";
    return;
  }

  let data;
  if (state.idToken) {
    data = await fetchAPI(`/api/summaries?type=weekly&date=${weekEnd}`);
  }
  if (!data) {
    data = await fetchJSON(`/data/weekly-${weekEnd}.json`);
  }

  if (!data) {
    document.getElementById("weekly-content").innerHTML = "<p>此日期範圍尚無週報。</p>";
    return;
  }

  renderWeekly(data);
}

// ── 渲染 ──

function renderDaily(data) {
  const isPrivate = !!data.dayDetails;
  const badge = isPrivate ? '<span class="private-badge">完整版</span>' : "";

  // Sessions
  const sessionsHTML = (data.sessions || [])
    .map((s) => {
      let detailsHTML = "";
      if (s.details) {
        detailsHTML = `<div class="session-details">${escapeHTML(s.details)}</div>`;
      }
      return `
        <div class="session-card">
          <div class="session-header">
            <span class="session-time">${escapeHTML(s.time)}</span>
            <span class="session-id">${escapeHTML(s.id)}</span>
          </div>
          <div class="session-summary">${escapeHTML(s.summary)}</div>
          ${detailsHTML}
        </div>`;
    })
    .join("");

  document.getElementById("sessions-list").innerHTML = sessionsHTML;

  // Day summary
  let summaryHTML = `<h3>當日彙整${badge}</h3><p>${escapeHTML(data.daySummary || "")}</p>`;
  if (data.dayDetails) {
    summaryHTML += `<div class="day-details">${escapeHTML(data.dayDetails)}</div>`;
  }
  document.getElementById("day-summary").innerHTML = summaryHTML;
}

function renderWeekly(data) {
  const isPrivate = !!data.details;
  const badge = isPrivate ? '<span class="private-badge">完整版</span>' : "";
  const period = `${data.weekStart || "?"} ~ ${data.weekEnd || "?"}`;

  let html = `<h2>${period} 週報${badge}</h2>`;
  html += `<div class="markdown">${renderMarkdown(data.summary || "")}</div>`;

  if (data.details) {
    html += `<div class="weekly-details"><div class="markdown">${renderMarkdown(data.details)}</div></div>`;
  }

  document.getElementById("weekly-content").innerHTML = html;
}

// ── 導航 ──

function navigate(delta) {
  const newIndex = state.currentIndex + delta;
  if (newIndex < 0 || newIndex >= state.dates.length) return;
  state.currentIndex = newIndex;
  loadCurrentDate();
}

function updateNavButtons() {
  document.getElementById("prev-btn").disabled = state.currentIndex <= 0;
  document.getElementById("next-btn").disabled = state.currentIndex >= state.dates.length - 1;
}

function switchView(view) {
  state.currentView = view;
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.view === view);
  });
  loadCurrentDate();
}

// ── Google Sign-In ──

function onGoogleSignIn(response) {
  try {
    state.idToken = response.credential;
    // 從 JWT payload 取得使用者名稱（base64url → base64 → UTF-8 decode）
    const base64Url = response.credential.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const payload = JSON.parse(new TextDecoder().decode(bytes));
    state.userName = payload.name || payload.email;

    document.querySelector(".g_id_signin").hidden = true;
    const userInfo = document.getElementById("user-info");
    userInfo.hidden = false;
    document.getElementById("user-name").textContent = state.userName;

    // 清除快取，重新載入完整版
    state.privateCache = {};
    loadCurrentDate();
  } catch (err) {
    console.error("Google Sign-In callback error:", err);
  }
}

function signOut() {
  state.idToken = null;
  state.userName = null;
  state.privateCache = {};

  document.querySelector(".g_id_signin").hidden = false;
  document.getElementById("user-info").hidden = true;

  loadCurrentDate();
}

// ── API 與工具函式 ──

async function fetchJSON(url) {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

async function fetchAPI(url) {
  if (!state.idToken) return null;
  try {
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${state.idToken}` },
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

function findWeekEnd(date) {
  // 找到 date 所在週的週六（週報以週六為 key）
  const d = new Date(date + "T00:00:00+08:00");
  const day = d.getDay(); // 0=Sun, 6=Sat
  const diff = 6 - day; // days until Saturday
  d.setDate(d.getDate() + diff);
  const weekEnd = d.toISOString().slice(0, 10);
  // 檢查是否有這個週報的日期存在（近似檢查）
  return weekEnd;
}

function showEmpty() {
  document.getElementById("daily-view").hidden = true;
  document.getElementById("weekly-view").hidden = true;
  document.getElementById("empty-state").hidden = false;
}

function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderMarkdown(text) {
  // 極簡 markdown 渲染（只處理 h3、ul/li、粗體）
  return escapeHTML(text)
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

// ── 啟動 ──

document.addEventListener("DOMContentLoaded", init);
