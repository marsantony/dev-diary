/* Dev Diary - 前端主邏輯 */

let state = {
  dates: [],          // 可用日期列表
  weeklyDates: [],    // 可用週報日期列表（週六）
  currentIndex: -1,   // 目前顯示的日期 index（daily 模式）
  weeklyIndex: -1,    // 目前顯示的週報 index（weekly 模式）
  currentView: "daily",
  idToken: null,      // Google ID Token
  userName: null,
  sessionDates: {},   // {sessionId: [dates]} 跨日 session 資訊
  // 快取：避免重複請求
  publicCache: {},
  privateCache: {},
};

// ── 初始化 ──

async function init() {
  const indexData = await fetchData("/api/summaries?type=list");
  if (!indexData || !indexData.dates || indexData.dates.length === 0) {
    showEmpty();
    return;
  }
  state.dates = indexData.dates.sort();
  state.weeklyDates = (indexData.weeklyDates || []).sort();
  state.sessionDates = indexData.sessionDates || {};
  state.currentIndex = state.dates.length - 1; // 預設最新一天
  state.weeklyIndex = state.weeklyDates.length - 1; // 預設最新一週

  // 點擊日期文字開啟日曆
  document.getElementById("current-date").addEventListener("click", toggleCalendar);
  // 點擊日曆外部關閉
  document.addEventListener("click", (e) => {
    const cal = document.getElementById("calendar-panel");
    const dateEl = document.getElementById("current-date");
    if (cal && !cal.hidden && !cal.contains(e.target) && e.target !== dateEl) {
      cal.hidden = true;
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const cal = document.getElementById("calendar-panel");
      if (cal) cal.hidden = true;
    }
  });

  await loadCurrentDate();
}

// ── 資料載入 ──

async function loadCurrentDate() {
  if (state.currentView === "daily") {
    const date = state.dates[state.currentIndex];
    document.getElementById("current-date").textContent = date;
    updateNavButtons();
    await loadDaily(date);
  } else {
    const weekEnd = state.weeklyDates[state.weeklyIndex];
    if (weekEnd) {
      const d = new Date(weekEnd + "T00:00:00+08:00");
      d.setDate(d.getDate() - 6);
      const weekStart = d.toISOString().slice(0, 10);
      document.getElementById("current-date").textContent = `${weekStart} ~ ${weekEnd}`;
    }
    updateNavButtons();
    await loadWeekly();
  }
}

async function loadDayData(date) {
  // 登入時讀完整版，未登入讀公開版，都走同一個 API（middleware 根據 token 決定回傳版本）
  const cacheKey = state.idToken ? "privateCache" : "publicCache";
  let data = state[cacheKey][date];
  if (!data) {
    data = await fetchData(`/api/summaries?type=daily&date=${date}`);
    if (data) state[cacheKey][date] = data;
  }
  return data;
}

async function loadDaily(date) {
  document.getElementById("daily-view").hidden = false;
  document.getElementById("weekly-view").hidden = true;
  document.getElementById("empty-state").hidden = true;

  const data = await loadDayData(date);
  if (!data) {
    showEmpty();
    return;
  }

  renderDaily(data);
}

async function loadWeekly() {
  document.getElementById("daily-view").hidden = true;
  document.getElementById("weekly-view").hidden = false;
  document.getElementById("empty-state").hidden = true;

  const weekEnd = state.weeklyDates[state.weeklyIndex];
  if (!weekEnd) {
    document.getElementById("weekly-content").innerHTML = "<p>尚無週報資料。</p>";
    return;
  }

  const data = await fetchData(`/api/summaries?type=weekly&date=${weekEnd}`);

  if (!data) {
    document.getElementById("weekly-content").innerHTML = "<p>尚無週報資料。</p>";
    return;
  }

  renderWeekly(data);
}

// ── 渲染 ──

function renderDaily(data) {
  const isPrivate = !!data.dayDetails;
  const badge = isPrivate ? '<span class="private-badge">完整版</span>' : "";
  const currentDate = data.date || state.dates[state.currentIndex];

  // Sessions
  const sessionsHTML = (data.sessions || [])
    .map((s) => {
      let detailsHTML = "";
      if (s.details) {
        detailsHTML = `<div class="session-details">${escapeHTML(s.details)}</div>`;
      }

      // 跨日標記：只算有資料的日期
      let crossDayHTML = "";
      const datesSet = new Set(state.dates);
      const availableDates = (state.sessionDates[s.id] || []).filter((d) => datesSet.has(d));
      if (availableDates.length > 1) {
        crossDayHTML = `<div class="cross-day-section">
          <button class="cross-day-toggle" data-session-id="${escapeHTML(s.id)}" data-dates='${JSON.stringify(availableDates)}'>跨日對話（${availableDates[0]} ~ ${availableDates[availableDates.length - 1]}）</button>
          <div class="cross-day-expanded" id="cross-day-${escapeHTML(s.id)}" hidden></div>
        </div>`;
      }

      return `
        <div class="session-card">
          <div class="session-header">
            <span class="session-time">${escapeHTML(s.time)}</span>
            <span class="session-id">${escapeHTML(s.id)}</span>
          </div>
          <div class="session-summary">${escapeHTML(s.summary)}</div>
          ${detailsHTML}
          ${crossDayHTML}
        </div>`;
    })
    .join("");

  document.getElementById("sessions-list").innerHTML = sessionsHTML;

  // 綁定跨日展開按鈕
  document.querySelectorAll(".cross-day-toggle").forEach((btn) => {
    btn.addEventListener("click", () => toggleCrossDay(btn));
  });

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

// ── 跨日對話展開 ──

async function toggleCrossDay(btn) {
  const sessionId = btn.dataset.sessionId;
  const container = document.getElementById(`cross-day-${sessionId}`);

  // 收合
  if (!container.hidden) {
    container.hidden = true;
    btn.classList.remove("expanded");
    return;
  }

  // 展開：載入其他天的資料
  const dates = JSON.parse(btn.dataset.dates);
  btn.classList.add("expanded");
  container.hidden = false;
  container.innerHTML = '<div class="cross-day-loading">載入中...</div>';

  let html = "";
  for (const date of dates) {
    const data = await loadDayData(date);
    if (!data) continue;

    // 找到同一個 session ID 的摘要
    const session = (data.sessions || []).find((s) => s.id === sessionId);
    if (!session) continue;

    const summaryText = escapeHTML(session.summary);
    const detailsText = session.details ? `<div class="cross-day-details">${escapeHTML(session.details)}</div>` : "";

    html += `<div class="cross-day-entry">
      <div class="cross-day-date">${escapeHTML(date)}</div>
      <div class="cross-day-summary">${summaryText}</div>
      ${detailsText}
    </div>`;
  }

  container.innerHTML = html || '<div class="cross-day-loading">沒有找到其他天的摘要。</div>';
}

// ── 日曆 ──

function toggleCalendar() {
  const panel = document.getElementById("calendar-panel");
  if (panel.hidden) {
    let currentDate;
    if (state.currentView === "weekly") {
      currentDate = state.weeklyDates[state.weeklyIndex] || new Date().toISOString().slice(0, 10);
    } else {
      currentDate = state.dates[state.currentIndex] || new Date().toISOString().slice(0, 10);
    }
    const [year, month] = currentDate.split("-").map(Number);
    renderCalendar(year, month);
    panel.hidden = false;
  } else {
    panel.hidden = true;
  }
}

function renderCalendar(year, month) {
  const panel = document.getElementById("calendar-panel");
  const today = new Date().toISOString().slice(0, 10);
  const isWeekly = state.currentView === "weekly";
  const datesSet = new Set(isWeekly ? state.weeklyDates : state.dates);
  const selectedDate = isWeekly
    ? state.weeklyDates[state.weeklyIndex]
    : state.dates[state.currentIndex];

  // 該月第一天與天數
  const firstDay = new Date(year, month - 1, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month, 0).getDate();

  const monthNames = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

  let html = `<div class="cal-header">
    <button class="cal-nav" data-year="${month === 1 ? year - 1 : year}" data-month="${month === 1 ? 12 : month - 1}">&larr;</button>
    <span>${year} 年 ${monthNames[month - 1]}</span>
    <button class="cal-nav" data-year="${month === 12 ? year + 1 : year}" data-month="${month === 12 ? 1 : month + 1}">&rarr;</button>
  </div>`;

  html += `<div class="cal-weekdays"><span>日</span><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span></div>`;
  html += `<div class="cal-days">`;

  // 空白填充
  for (let i = 0; i < firstDay; i++) {
    html += `<span class="cal-day empty"></span>`;
  }

  // 日期格
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const hasData = datesSet.has(dateStr);
    const isToday = dateStr === today;
    const isSelected = dateStr === selectedDate;

    let cls = "cal-day";
    if (hasData) cls += " has-data";
    if (isToday) cls += " today";
    if (isSelected) cls += " selected";

    if (hasData) {
      html += `<span class="${cls}" data-date="${dateStr}">${d}</span>`;
    } else {
      html += `<span class="${cls}">${d}</span>`;
    }
  }

  html += `</div>`;
  panel.innerHTML = html;

  // 綁定事件
  panel.querySelectorAll(".cal-day.has-data").forEach((el) => {
    el.addEventListener("click", () => {
      if (isWeekly) {
        const idx = state.weeklyDates.indexOf(el.dataset.date);
        if (idx !== -1) {
          state.weeklyIndex = idx;
          panel.hidden = true;
          loadCurrentDate();
        }
      } else {
        const idx = state.dates.indexOf(el.dataset.date);
        if (idx !== -1) {
          state.currentIndex = idx;
          panel.hidden = true;
          loadCurrentDate();
        }
      }
    });
  });

  panel.querySelectorAll(".cal-nav").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      renderCalendar(Number(btn.dataset.year), Number(btn.dataset.month));
    });
  });
}

// ── 導航 ──

function navigate(delta) {
  if (state.currentView === "weekly") {
    const newIndex = state.weeklyIndex + delta;
    if (newIndex < 0 || newIndex >= state.weeklyDates.length) return;
    state.weeklyIndex = newIndex;
  } else {
    const newIndex = state.currentIndex + delta;
    if (newIndex < 0 || newIndex >= state.dates.length) return;
    state.currentIndex = newIndex;
  }
  loadCurrentDate();
}

function updateNavButtons() {
  if (state.currentView === "weekly") {
    document.getElementById("prev-btn").disabled = state.weeklyIndex <= 0;
    document.getElementById("next-btn").disabled = state.weeklyIndex >= state.weeklyDates.length - 1;
  } else {
    document.getElementById("prev-btn").disabled = state.currentIndex <= 0;
    document.getElementById("next-btn").disabled = state.currentIndex >= state.dates.length - 1;
  }
}

function switchView(view) {
  state.currentView = view;
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.view === view);
  });
  // 切到週報時，找到包含當前日期的週報
  if (view === "weekly") {
    const currentDate = state.dates[state.currentIndex];
    const weekEnd = findWeekEnd(currentDate);
    // 找最接近的可用週報（<= 該週六）
    let best = state.weeklyDates.length - 1;
    for (let i = state.weeklyDates.length - 1; i >= 0; i--) {
      if (state.weeklyDates[i] <= weekEnd) {
        best = i;
        break;
      }
    }
    state.weeklyIndex = best;
  }
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
  google.accounts.id.disableAutoSelect();
  state.idToken = null;
  state.userName = null;
  state.privateCache = {};

  document.querySelector(".g_id_signin").hidden = false;
  document.getElementById("user-info").hidden = true;

  loadCurrentDate();
}

// ── API 與工具函式 ──

async function fetchData(url) {
  try {
    const opts = {};
    if (state.idToken) {
      opts.headers = { Authorization: `Bearer ${state.idToken}` };
    }
    const resp = await fetch(url, opts);
    if (resp.status === 401) {
      console.warn("Token expired, switched to public view");
      signOut();
      return null;
    }
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

function findWeekEnd(date) {
  // 找到 date 所在週的週六（週報以週六為 key，週日~週六為一週）
  const d = new Date(date + "T00:00:00+08:00");
  const day = d.getDay(); // 0=Sun, 6=Sat
  // 週日(0)→往後6天到週六，週一(1)→往後5天，...週六(6)→當天
  const diff = 6 - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
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
