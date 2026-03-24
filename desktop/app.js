/* ============================================================
   ROSA Desktop v5.0 — SuperJarvis UI
   Full ChatGPT-level frontend: streaming WS, markdown, all views
   ============================================================ */

// ── STATE ─────────────────────────────────────────────────────────────────

const state = {
  serverUrl: localStorage.getItem("rosa_server") || "http://localhost:8000",
  ws: null,
  statusWs: null,
  reconnectTimer: null,
  statusReconnectTimer: null,
  sending: false,

  currentView: "chat",
  currentSessionId: null,
  sessions: [],

  // Status
  currentStatus: "ОНЛАЙН",
  currentStatusColor: "green",
  agentCount: 0,

  // Streaming
  streamBuffer: "",
  streamMsgId: null,

  // Swarm
  swarmRunning: false,

  // Projects
  projects: [],
  currentProjectId: null,

  // Knowledge
  knowledgeResults: [],

  // Missions
  currentMission: null,
};

// ── HELPERS ───────────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMd(text) {
  if (typeof marked !== "undefined") {
    try {
      const html = marked.parse(text, { breaks: true, gfm: true });
      return html;
    } catch (e) {}
  }
  // Fallback minimal renderer
  return text
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code class="lang-${escHtml(lang)}">${escHtml(code.trim())}</code></pre>`)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br>");
}

function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2);
}

function timeAgo(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d) / 1000;
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч`;
  return d.toLocaleDateString("ru-RU");
}

async function api(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(state.serverUrl + path, opts);
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status}: ${t}`);
  }
  return r.json();
}

// ── MARKDOWN CONFIG ───────────────────────────────────────────────────────

if (typeof marked !== "undefined") {
  marked.setOptions({
    highlight: (code, lang) => {
      if (typeof hljs !== "undefined" && lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
      return escHtml(code);
    },
    langPrefix: "hljs language-",
    breaks: true,
    gfm: true,
  });
}

// ── VIEW SWITCHING ────────────────────────────────────────────────────────

function showView(name) {
  state.currentView = name;
  $$(".view").forEach((v) => v.classList.remove("active"));
  const el = $(`#view-${name}`);
  if (el) el.classList.add("active");

  $$(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.view === name);
  });

  if (name === "improve") loadImproveView();
  if (name === "settings") loadSettingsView();
  if (name === "knowledge") loadKnowledgeStats();
  if (name === "projects") loadProjects();
  if (name === "swarm") loadSwarmRoles();
}

// ── SIDEBAR ───────────────────────────────────────────────────────────────

function toggleSidebar() {
  $(".sidebar").classList.toggle("collapsed");
  $(".main-area").classList.toggle("sidebar-hidden");
}

async function loadChatList() {
  try {
    // Use memory/turns to get unique sessions
    const data = await api("GET", "/api/memory/turns?limit=200");
    const sessions = {};
    (data.turns || []).forEach((t) => {
      if (!sessions[t.session_id]) {
        sessions[t.session_id] = {
          id: t.session_id,
          preview: t.content ? t.content.slice(0, 50) : "Чат",
          ts: t.created_at || new Date().toISOString(),
        };
      }
    });
    state.sessions = Object.values(sessions).sort(
      (a, b) => new Date(b.ts) - new Date(a.ts)
    );
    renderChatList();
  } catch (e) {
    console.warn("loadChatList:", e.message);
  }
}

function renderChatList() {
  const list = $("#chatList");
  if (!list) return;
  list.innerHTML = "";
  state.sessions.slice(0, 30).forEach((s) => {
    const div = document.createElement("div");
    div.className =
      "chat-item" + (s.id === state.currentSessionId ? " active" : "");
    div.innerHTML = `<span class="chat-item-title">${escHtml(s.preview || "Новый чат")}</span>
      <span class="chat-item-time">${timeAgo(s.ts)}</span>`;
    div.onclick = () => loadSession(s.id);
    list.appendChild(div);
  });
}

async function loadSession(sessionId) {
  state.currentSessionId = sessionId;
  renderChatList();
  showView("chat");
  try {
    const data = await api("GET", `/api/memory/turns?session_id=${sessionId}&limit=100`);
    const msgs = $("#messagesList");
    if (!msgs) return;
    msgs.innerHTML = "";
    const turns = (data.turns || []).sort(
      (a, b) => new Date(a.created_at) - new Date(b.created_at)
    );
    turns.forEach((t) => {
      appendMessage(t.role === "user" ? "user" : "rosa", t.content, false);
    });
    scrollToBottom();
  } catch (e) {
    console.warn("loadSession:", e.message);
  }
}

function newChat() {
  state.currentSessionId = uid();
  const msgs = $("#messagesList");
  if (msgs) msgs.innerHTML = "";
  showWelcome();
  renderChatList();
  showView("chat");
}

function showWelcome() {
  const welcome = $("#welcomeScreen");
  const msgs = $("#messagesList");
  if (welcome) welcome.style.display = "flex";
  if (msgs && msgs.children.length === 0 && welcome) {
    // keep welcome visible
  } else if (welcome) {
    welcome.style.display = "none";
  }
}

// ── CHAT: WEBSOCKET ───────────────────────────────────────────────────────

function connectWs() {
  const wsUrl = state.serverUrl.replace("http", "ws") + "/api/ws/chat";
  if (state.ws) {
    try { state.ws.close(); } catch (e) {}
  }
  state.ws = new WebSocket(wsUrl);
  state.ws.onopen = () => {
    clearTimeout(state.reconnectTimer);
    console.log("Rosa WS connected");
  };
  state.ws.onmessage = (e) => handleWsMessage(JSON.parse(e.data));
  state.ws.onerror = () => scheduleReconnect();
  state.ws.onclose = () => scheduleReconnect();
}

function scheduleReconnect() {
  clearTimeout(state.reconnectTimer);
  state.reconnectTimer = setTimeout(connectWs, 3000);
}

function handleWsMessage(msg) {
  switch (msg.type) {
    case "token":
      handleToken(msg.token);
      break;
    case "response":
      handleFullResponse(msg);
      break;
    case "error":
      handleError(msg.message);
      break;
    case "status":
      // status updates from chat endpoint
      break;
  }
}

function handleToken(token) {
  state.streamBuffer += token;
  if (!state.streamMsgId) {
    state.streamMsgId = uid();
    appendMessage("rosa", "", true, state.streamMsgId);
    hideTyping();
  }
  const el = $(`#msg-${state.streamMsgId} .msg-content`);
  if (el) {
    el.innerHTML = renderMd(state.streamBuffer);
    if (typeof hljs !== "undefined") {
      el.querySelectorAll("pre code").forEach((b) => hljs.highlightElement(b));
    }
  }
  scrollToBottom();
}

function handleFullResponse(msg) {
  state.sending = false;
  const content = msg.response || state.streamBuffer;

  if (state.streamMsgId) {
    const el = $(`#msg-${state.streamMsgId} .msg-content`);
    if (el) {
      el.innerHTML = renderMd(content);
      if (typeof hljs !== "undefined") {
        el.querySelectorAll("pre code").forEach((b) => hljs.highlightElement(b));
      }
    }
    state.streamBuffer = "";
    state.streamMsgId = null;
  } else {
    appendMessage("rosa", content);
  }

  hideTyping();
  setSendState(false);
  scrollToBottom();

  // Check for mission plan in response
  if (msg.mission) showMissionPlan(msg.mission);

  // Refresh chat list
  loadChatList();
}

function handleError(message) {
  state.sending = false;
  state.streamBuffer = "";
  state.streamMsgId = null;
  hideTyping();
  setSendState(false);
  appendMessage("rosa", `⚠️ Ошибка: ${message}`);
}

// ── CHAT: STATUS WEBSOCKET ────────────────────────────────────────────────

function connectStatusWs() {
  const wsUrl = state.serverUrl.replace("http", "ws") + "/api/ws/status";
  if (state.statusWs) {
    try { state.statusWs.close(); } catch (e) {}
  }
  state.statusWs = new WebSocket(wsUrl);
  state.statusWs.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "keepalive") return;
      updateStatusBar(msg);
    } catch (ex) {}
  };
  state.statusWs.onclose = () => {
    state.statusReconnectTimer = setTimeout(connectStatusWs, 5000);
  };
}

function updateStatusBar(event) {
  const dot = $(".status-dot");
  const text = $(".status-text");
  const badge = $(".agent-badge");

  if (!dot || !text) return;

  const status = event.status || event.current_status || "ОНЛАЙН";
  const color = event.color || "green";
  const detail = event.detail || "";
  const agentCount = event.agent_count || 0;

  state.currentStatus = status;
  state.currentStatusColor = color;
  state.agentCount = agentCount;

  dot.className = `status-dot status-${color}`;
  text.textContent = status + (detail ? ` — ${detail}` : "");

  if (badge) {
    badge.style.display = agentCount > 0 ? "inline-flex" : "none";
    badge.textContent = `${agentCount} агентов`;
  }
}

// ── CHAT: MESSAGES ────────────────────────────────────────────────────────

function appendMessage(role, content, streaming = false, customId = null) {
  const welcome = $("#welcomeScreen");
  if (welcome) welcome.style.display = "none";

  const msgs = $("#messagesList");
  if (!msgs) return;

  const id = customId || uid();
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.id = `msg-${id}`;

  const avatarHtml =
    role === "rosa"
      ? `<div class="msg-avatar rosa-avatar">🌹</div>`
      : `<div class="msg-avatar user-avatar">👤</div>`;

  const actionsHtml =
    role === "rosa"
      ? `<div class="msg-actions">
          <button onclick="copyMessage('${id}')" title="Копировать">📋</button>
          <button onclick="likeMessage('${id}', 1)" title="Хорошо">👍</button>
          <button onclick="likeMessage('${id}', -1)" title="Плохо">👎</button>
        </div>`
      : "";

  div.innerHTML = `
    ${avatarHtml}
    <div class="msg-body">
      <div class="msg-content">${streaming ? "" : renderMd(content)}</div>
      ${actionsHtml}
    </div>`;

  msgs.appendChild(div);

  if (!streaming && typeof hljs !== "undefined") {
    div.querySelectorAll("pre code").forEach((b) => hljs.highlightElement(b));
  }
  scrollToBottom();
  return id;
}

function scrollToBottom() {
  const msgs = $("#messagesList");
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
  const container = $(".messages-container");
  if (container) container.scrollTop = container.scrollHeight;
}

function showTyping() {
  const el = $(".typing-indicator");
  if (el) el.style.display = "flex";
}

function hideTyping() {
  const el = $(".typing-indicator");
  if (el) el.style.display = "none";
}

function setSendState(sending) {
  state.sending = sending;
  const btn = $("#sendBtn");
  const ta = $("#chatInput");
  if (btn) btn.disabled = sending;
  if (ta) ta.disabled = sending;
}

function copyMessage(id) {
  const el = $(`#msg-${id} .msg-content`);
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).catch(() => {});
}

function likeMessage(id, val) {
  // Store rating locally; in v5 can be sent to metacognition API
  console.log("Rating message", id, val);
}

// ── CHAT: SEND ────────────────────────────────────────────────────────────

async function sendMessage() {
  const ta = $("#chatInput");
  if (!ta) return;
  const msg = ta.value.trim();
  if (!msg || state.sending) return;

  ta.value = "";
  autoResize(ta);
  setSendState(true);
  showTyping();

  if (!state.currentSessionId) state.currentSessionId = uid();
  appendMessage("user", msg);

  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.streamBuffer = "";
    state.streamMsgId = null;
    state.ws.send(JSON.stringify({
      message: msg,
      session_id: state.currentSessionId,
    }));
  } else {
    // Fallback to HTTP
    try {
      const data = await api("POST", "/api/chat", {
        message: msg,
        session_id: state.currentSessionId,
      });
      handleFullResponse({ response: data.response, mission: data.mission });
    } catch (e) {
      handleError(e.message);
    }
  }
}

function sendSuggestion(text) {
  const ta = $("#chatInput");
  if (ta) {
    ta.value = text;
    sendMessage();
  }
}

// ── CHAT: INPUT ───────────────────────────────────────────────────────────

function autoResize(ta) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
}

function initChatInput() {
  const ta = $("#chatInput");
  if (!ta) return;
  ta.addEventListener("input", () => autoResize(ta));
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

// ── STATUS WS ─────────────────────────────────────────────────────────────

async function loadCurrentStatus() {
  try {
    const data = await api("GET", "/api/status/current");
    updateStatusBar(data);
  } catch (e) {}
}

// ── SWARM VIEW ────────────────────────────────────────────────────────────

async function loadSwarmRoles() {
  try {
    const data = await api("GET", "/api/swarm/roles");
    const list = $("#swarmAgentList");
    if (list && data.roles) {
      list.innerHTML = data.roles
        .map((r) => `<div class="agent-card"><div class="agent-icon">🤖</div>
          <div class="agent-info"><strong>${escHtml(r.role)}</strong>
          <p>${escHtml(r.description || "")}</p></div></div>`)
        .join("");
    }
  } catch (e) {}
}

async function runSwarm() {
  const ta = $("#swarmTask");
  if (!ta) return;
  const task = ta.value.trim();
  if (!task || state.swarmRunning) return;

  state.swarmRunning = true;
  const btn = $("#swarmRunBtn");
  if (btn) btn.disabled = true;

  const resultDiv = $("#swarmSynthesis");
  if (resultDiv) resultDiv.innerHTML = '<div class="thinking">Рой думает...</div>';

  const agentList = $("#swarmAgentList");
  if (agentList) agentList.innerHTML = '<div class="thinking">Подбираю агентов...</div>';

  try {
    const data = await api("POST", "/api/swarm/auto", { task });

    // Render agents
    if (agentList && data.agents) {
      agentList.innerHTML = data.agents
        .map((a) => `<div class="agent-card ${a.status === 'done' ? 'done' : ''}">
          <div class="agent-icon">${a.status === 'done' ? '✅' : '🤖'}</div>
          <div class="agent-info">
            <strong>${escHtml(a.role)}</strong>
            <p>${escHtml(a.result ? a.result.slice(0, 100) : a.subtask || "")}</p>
          </div></div>`)
        .join("");
    }

    // Render synthesis
    if (resultDiv) {
      resultDiv.innerHTML = `<div class="synthesis-result">${renderMd(data.synthesis || "Нет результата")}</div>`;
      if (typeof hljs !== "undefined") {
        resultDiv.querySelectorAll("pre code").forEach((b) => hljs.highlightElement(b));
      }
    }
  } catch (e) {
    if (resultDiv) resultDiv.innerHTML = `<div class="error-msg">Ошибка: ${escHtml(e.message)}</div>`;
  } finally {
    state.swarmRunning = false;
    if (btn) btn.disabled = false;
  }
}

async function analyzeComplexity() {
  const ta = $("#swarmTask");
  if (!ta || !ta.value.trim()) return;
  try {
    const data = await api("POST", "/api/swarm/complexity", { task: ta.value.trim() });
    const badge = $("#complexityBadge");
    if (badge) {
      badge.textContent = `${data.complexity} · ${data.agent_count} агентов`;
      badge.style.display = "inline-block";
    }
  } catch (e) {}
}

// ── KNOWLEDGE VIEW ────────────────────────────────────────────────────────

async function loadKnowledgeStats() {
  try {
    const data = await api("GET", "/api/memory/knowledge/stats");
    const el = $("#knowledgeStats");
    if (el && data) {
      el.innerHTML = `
        <div class="stat-card"><div class="stat-num">${data.total || 0}</div><div>Всего узлов</div></div>
        <div class="stat-card"><div class="stat-num">${data.insights || 0}</div><div>Инсайтов</div></div>
        <div class="stat-card"><div class="stat-num">${data.sources || 0}</div><div>Источников</div></div>`;
    }
  } catch (e) {}
}

async function searchKnowledge() {
  const q = $("#knowledgeSearch")?.value?.trim();
  if (!q) return;
  try {
    const data = await api("GET", `/api/memory/knowledge?query=${encodeURIComponent(q)}&limit=20`);
    const results = $("#knowledgeResults");
    if (!results) return;
    const nodes = data.nodes || [];
    if (!nodes.length) {
      results.innerHTML = "<p class='text-muted'>Ничего не найдено</p>";
      return;
    }
    results.innerHTML = nodes
      .map((n) => `<div class="knowledge-card">
        <div class="kn-header">
          <span class="kn-type badge">${escHtml(n.node_type || "insight")}</span>
          <span class="kn-source text-muted">${escHtml(n.source_type || "")}</span>
        </div>
        <div class="kn-content">${renderMd(n.content ? n.content.slice(0, 300) : "")}</div>
        <div class="kn-footer text-muted">${timeAgo(n.created_at || new Date().toISOString())}</div>
      </div>`)
      .join("");
  } catch (e) {
    const results = $("#knowledgeResults");
    if (results) results.innerHTML = `<p class='error-msg'>Ошибка: ${escHtml(e.message)}</p>`;
  }
}

async function runHyperSearch() {
  const q = $("#knowledgeSearch")?.value?.trim();
  if (!q) return;
  const btn = $("#hyperSearchBtn");
  if (btn) btn.disabled = true;
  const results = $("#knowledgeResults");
  if (results) results.innerHTML = '<div class="thinking">HyperSearch запущен...</div>';
  try {
    const data = await api("POST", "/api/search", { query: q, synthesize: true });
    if (results) {
      const items = data.results || [];
      results.innerHTML = `
        <div class="synthesis-box">${renderMd(data.synthesis || "")}</div>
        ${items.map((r) => `<div class="search-result-card">
          <a href="${escHtml(r.url || "#")}" target="_blank" rel="noopener">${escHtml(r.title || r.url || "")}</a>
          <p>${escHtml(r.snippet ? r.snippet.slice(0, 200) : "")}</p>
          <span class="badge">${escHtml(r.source || "")}</span>
        </div>`).join("")}`;
    }
  } catch (e) {
    if (results) results.innerHTML = `<p class='error-msg'>Ошибка: ${escHtml(e.message)}</p>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── PROJECTS VIEW ─────────────────────────────────────────────────────────

async function loadProjects() {
  try {
    const data = await api("GET", "/api/tasks?limit=50");
    state.projects = data.tasks || [];
    renderProjectList();
  } catch (e) {}
}

function renderProjectList() {
  const list = $("#projectList");
  if (!list) return;
  list.innerHTML = state.projects
    .map((p) => `<div class="project-item ${p.id === state.currentProjectId ? 'active' : ''}"
        onclick="openProject('${p.id}')">
      <div class="project-title">${escHtml(p.title || "Без названия")}</div>
      <div class="project-meta">
        <span class="badge badge-${p.status}">${escHtml(p.status || "pending")}</span>
        <span class="text-muted">${timeAgo(p.created_at || new Date().toISOString())}</span>
      </div>
    </div>`)
    .join("") || "<p class='text-muted' style='padding:16px'>Нет задач</p>";
}

async function openProject(id) {
  state.currentProjectId = id;
  renderProjectList();
  const task = state.projects.find((p) => p.id === id);
  const detail = $("#projectDetail");
  if (!detail || !task) return;
  detail.innerHTML = `
    <h2>${escHtml(task.title || "Задача")}</h2>
    <p class="text-muted">${escHtml(task.description || "")}</p>
    <div class="task-meta">
      <span class="badge badge-${task.status}">${escHtml(task.status)}</span>
      <span class="text-muted">Приоритет: ${task.priority || "medium"}</span>
    </div>
    <div class="task-actions" style="margin-top:16px;display:flex;gap:8px">
      <button class="btn-primary" onclick="updateTaskStatus('${id}', 'in_progress')">▶ В работу</button>
      <button class="btn-success" onclick="updateTaskStatus('${id}', 'done')">✅ Готово</button>
      <button class="btn-danger" onclick="deleteTask('${id}')">🗑 Удалить</button>
    </div>`;
}

async function updateTaskStatus(id, status) {
  try {
    await api("PATCH", `/api/tasks/${id}`, { status });
    await loadProjects();
    if (state.currentProjectId === id) openProject(id);
  } catch (e) { alert("Ошибка: " + e.message); }
}

async function deleteTask(id) {
  if (!confirm("Удалить задачу?")) return;
  try {
    await api("DELETE", `/api/tasks/${id}`);
    state.currentProjectId = null;
    const detail = $("#projectDetail");
    if (detail) detail.innerHTML = "<p class='text-muted'>Выберите задачу</p>";
    await loadProjects();
  } catch (e) { alert("Ошибка: " + e.message); }
}

function showNewProjectModal() {
  const modal = $("#newProjectModal");
  if (modal) modal.style.display = "flex";
}

function closeNewProjectModal() {
  const modal = $("#newProjectModal");
  if (modal) modal.style.display = "none";
}

async function createProject() {
  const title = $("#newProjectTitle")?.value?.trim();
  const desc = $("#newProjectDesc")?.value?.trim();
  if (!title) return;
  try {
    await api("POST", "/api/tasks", { title, description: desc || "", status: "pending" });
    closeNewProjectModal();
    await loadProjects();
  } catch (e) { alert("Ошибка: " + e.message); }
}

// ── IMPROVE VIEW ──────────────────────────────────────────────────────────

async function loadImproveView() {
  await Promise.all([loadQualityStats(), loadProposals(), loadStatusHistory()]);
}

async function loadQualityStats() {
  try {
    const data = await api("GET", "/api/metacognition/stats");
    renderQualityCards(data);
    renderWeakPoints(data.top_weak_points || []);
  } catch (e) {
    renderQualityCards({});
  }
}

function renderQualityCards(data) {
  const metrics = [
    { key: "completeness_avg", label: "Полнота", icon: "📊" },
    { key: "accuracy_avg", label: "Точность", icon: "🎯" },
    { key: "helpfulness_avg", label: "Полезность", icon: "💡" },
    { key: "overall_avg", label: "Общая", icon: "⭐" },
  ];
  metrics.forEach((m) => {
    const card = $(`#quality-${m.key.replace("_avg", "")}`);
    if (!card) return;
    const val = data[m.key] || 0;
    const pct = (val / 10) * 100;
    card.innerHTML = `
      <div class="quality-icon">${m.icon}</div>
      <div class="quality-label">${m.label}</div>
      <div class="quality-score">${val.toFixed(1)}/10</div>
      <div class="quality-bar"><div class="quality-fill" style="width:${pct}%"></div></div>`;
  });
}

function renderWeakPoints(points) {
  const el = $("#weakPoints");
  if (!el) return;
  if (!points.length) {
    el.innerHTML = "<span class='text-muted'>Нет данных</span>";
    return;
  }
  el.innerHTML = points
    .map((p) => `<span class="weak-tag">${escHtml(p)}</span>`)
    .join(" ");
}

async function loadProposals() {
  try {
    const data = await api("GET", "/api/self-improve/proposals");
    const list = $("#proposalList");
    if (!list) return;
    const proposals = data.proposals || [];
    if (!proposals.length) {
      list.innerHTML = "<p class='text-muted'>Нет предложений</p>";
      return;
    }
    list.innerHTML = proposals
      .map((p) => `<div class="proposal-card">
        <div class="proposal-header">
          <span class="badge">${escHtml(p.category || "общее")}</span>
          <span class="text-muted">${timeAgo(p.created_at || new Date().toISOString())}</span>
        </div>
        <p>${escHtml(p.description || "")}</p>
        <div class="proposal-actions">
          <button class="btn-primary btn-sm" onclick="applyProposal('${p.id}')">Применить</button>
        </div>
      </div>`)
      .join("");
  } catch (e) {}
}

async function applyProposal(id) {
  try {
    await api("POST", `/api/self-improve/proposals/${id}/apply`);
    await loadProposals();
  } catch (e) { alert("Ошибка: " + e.message); }
}

async function runSelfImprove() {
  const btn = $("#selfImproveBtn");
  if (btn) { btn.disabled = true; btn.textContent = "Анализирую..."; }
  try {
    await api("POST", "/api/self-improve/run");
    await loadProposals();
    alert("Анализ завершён. Новые предложения загружены.");
  } catch (e) {
    alert("Ошибка: " + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "▶ Запустить анализ"; }
  }
}

async function loadStatusHistory() {
  try {
    const data = await api("GET", "/api/status/history?limit=20");
    const list = $("#statusHistory");
    if (!list) return;
    const events = data.history || [];
    if (!events.length) {
      list.innerHTML = "<p class='text-muted'>Нет истории</p>";
      return;
    }
    list.innerHTML = events
      .map((e) => `<div class="status-history-item">
        <span class="status-dot status-${e.color || 'green'}" style="width:8px;height:8px"></span>
        <span>${escHtml(e.status)}</span>
        <span class="text-muted">${escHtml(e.detail || "")}</span>
        <span class="text-muted" style="margin-left:auto">${timeAgo(e.ts || new Date().toISOString())}</span>
      </div>`)
      .join("");
  } catch (e) {}
}

// ── SETTINGS VIEW ─────────────────────────────────────────────────────────

async function loadSettingsView() {
  await Promise.all([loadEconomyStats(), loadEnvStatus()]);
}

async function loadEconomyStats() {
  try {
    const data = await api("GET", "/api/economy/stats");
    const el = $("#economyStats");
    if (!el) return;
    el.innerHTML = `
      <div class="stat-row"><span>Сегодня</span><span>$${(data.today_cost || 0).toFixed(4)}</span></div>
      <div class="stat-row"><span>Месяц</span><span>$${(data.month_cost || 0).toFixed(4)}</span></div>
      <div class="stat-row"><span>Кэш попаданий</span><span>${data.cache_hits || 0}</span></div>
      <div class="stat-row"><span>Кэш промахов</span><span>${data.cache_misses || 0}</span></div>`;
  } catch (e) {}
}

async function loadEnvStatus() {
  try {
    const data = await api("GET", "/api/economy/env");
    const el = $("#envStatus");
    if (!el) return;
    const configured = data.configured || [];
    const missing = data.missing || [];
    el.innerHTML = `
      <div class="env-section">
        <strong>Настроены:</strong>
        ${configured.map((k) => `<span class="badge badge-success">${escHtml(k)}</span>`).join(" ") || "<span class='text-muted'>Нет</span>"}
      </div>
      <div class="env-section" style="margin-top:8px">
        <strong>Отсутствуют:</strong>
        ${missing.map((k) => `<span class="badge badge-danger">${escHtml(k)}</span>`).join(" ") || "<span class='text-muted'>Всё есть</span>"}
      </div>`;
  } catch (e) {}
}

async function analyzeTikTok() {
  const urlEl = $("#tiktokUrl");
  if (!urlEl) return;
  const url = urlEl.value.trim();
  if (!url) return;
  const status = $("#tiktokStatus");
  if (status) status.textContent = "Анализирую...";
  try {
    const data = await api("POST", "/api/integrations/tiktok/analyze", { url });
    const nodes = data.nodes_added || 0;
    if (status) status.textContent = `✅ Добавлено ${nodes} узлов в граф знаний`;
  } catch (e) {
    if (status) status.textContent = `❌ Ошибка: ${e.message}`;
  }
}

async function ingestGitHub() {
  const urlEl = $("#githubUrl");
  if (!urlEl) return;
  const url = urlEl.value.trim();
  if (!url) return;
  const status = $("#githubStatus");
  if (status) status.textContent = "Загружаю репозиторий...";
  try {
    const data = await api("POST", "/api/integrations/github/ingest", { url, max_files: 10 });
    const nodes = data.nodes_added || 0;
    if (status) status.textContent = `✅ ${data.files_processed || 0} файлов → ${nodes} узлов`;
  } catch (e) {
    if (status) status.textContent = `❌ Ошибка: ${e.message}`;
  }
}

async function startTelegramAuth() {
  const apiId = $("#tgApiId")?.value?.trim();
  const apiHash = $("#tgApiHash")?.value?.trim();
  const phone = $("#tgPhone")?.value?.trim();
  if (!apiId || !apiHash || !phone) {
    alert("Заполните API ID, API Hash и номер телефона");
    return;
  }
  try {
    const data = await api("POST", "/api/integrations/telegram/auth/start", {
      api_id: apiId,
      api_hash: apiHash,
      phone,
    });
    const otpSection = $("#tgOtpSection");
    if (otpSection) {
      otpSection.style.display = "block";
      otpSection.dataset.phoneCodeHash = data.phone_code_hash || "";
    }
  } catch (e) { alert("Ошибка: " + e.message); }
}

async function verifyTelegramAuth() {
  const code = $("#tgOtpCode")?.value?.trim();
  const otpSection = $("#tgOtpSection");
  const phoneCodeHash = otpSection?.dataset?.phoneCodeHash || "";
  if (!code) return;
  try {
    await api("POST", "/api/integrations/telegram/auth/verify", {
      code,
      phone_code_hash: phoneCodeHash,
    });
    const status = $("#tgStatus");
    if (status) status.textContent = "✅ Telegram авторизован";
    const importSection = $("#tgImportSection");
    if (importSection) importSection.style.display = "block";
  } catch (e) { alert("Ошибка: " + e.message); }
}

async function importTelegram() {
  const chatId = $("#tgChatId")?.value?.trim();
  const limit = parseInt($("#tgLimit")?.value || "100");
  if (!chatId) return;
  const status = $("#tgImportStatus");
  if (status) status.textContent = "Импортирую...";
  try {
    const data = await api("POST", "/api/integrations/telegram/import", {
      chat_id: chatId,
      limit,
    });
    if (status) status.textContent = `✅ ${data.messages_imported || 0} сообщений → ${data.nodes_added || 0} узлов`;
  } catch (e) {
    if (status) status.textContent = `❌ Ошибка: ${e.message}`;
  }
}

// ── MISSION PLAN UI ───────────────────────────────────────────────────────

function showMissionPlan(mission) {
  state.currentMission = mission;
  const modal = $("#missionModal");
  if (!modal) return;

  const steps = mission.steps || [];
  modal.innerHTML = `
    <div class="mission-modal-content">
      <h2>🎯 Миссия: ${escHtml(mission.intent || "Новая миссия")}</h2>
      <p class="text-muted">${escHtml(mission.original_message || "")}</p>
      <p>Сложность: <strong>${escHtml(mission.complexity || "medium")}</strong>
         · Ориентировочно: ${escHtml(mission.estimated_duration || "неизвестно")}</p>
      <div class="mission-steps">
        ${steps.map((s, i) => `
          <div class="mission-step" id="mstep-${s.id}">
            <label>
              <input type="checkbox" id="step-check-${s.id}" ${s.requires_permission ? "" : "checked"}>
              <strong>${i + 1}. ${escHtml(s.title)}</strong>
            </label>
            <p class="text-muted">${escHtml(s.description || "")}</p>
            ${s.requires_permission
              ? `<div class="permission-warn">⚠️ Требует разрешения: ${escHtml(s.permission_reason || "")}</div>`
              : ""}
          </div>`).join("")}
      </div>
      <div class="mission-actions">
        <button class="btn-primary" onclick="approveMission('${mission.id}')">✅ Утвердить и выполнить</button>
        <button class="btn-secondary" onclick="closeMissionModal()">❌ Отмена</button>
      </div>
    </div>`;

  modal.style.display = "flex";
}

async function approveMission(missionId) {
  const approvedStepIds = [];
  $$(`.mission-step input[type="checkbox"]`).forEach((cb) => {
    if (cb.checked) {
      const stepId = cb.id.replace("step-check-", "");
      approvedStepIds.push(stepId);
    }
  });

  try {
    await api("POST", `/api/planning/missions/${missionId}/approve`, {
      approved_step_ids: approvedStepIds,
    });
    closeMissionModal();
    appendMessage("rosa", "✅ Миссия утверждена. Начинаю выполнение...");
    // Execute in background
    api("POST", `/api/planning/missions/${missionId}/execute`).then((data) => {
      appendMessage("rosa", `🎯 Миссия выполнена!\n\n${data.summary || ""}`);
    }).catch((e) => {
      appendMessage("rosa", `⚠️ Ошибка при выполнении миссии: ${e.message}`);
    });
  } catch (e) {
    alert("Ошибка: " + e.message);
  }
}

function closeMissionModal() {
  const modal = $("#missionModal");
  if (modal) modal.style.display = "none";
  state.currentMission = null;
}

// ── SHORTCUTS MODAL ───────────────────────────────────────────────────────

function showShortcuts() {
  const modal = $("#shortcutsModal");
  if (modal) modal.style.display = "flex";
}

function closeShortcuts() {
  const modal = $("#shortcutsModal");
  if (modal) modal.style.display = "none";
}

// ── HOTKEYS ───────────────────────────────────────────────────────────────

function initHotkeys() {
  document.addEventListener("keydown", (e) => {
    const tag = document.activeElement?.tagName?.toLowerCase();
    const inInput = tag === "textarea" || tag === "input";

    if (e.ctrlKey && e.key === "n") {
      e.preventDefault();
      newChat();
    }
    if (e.ctrlKey && e.key === "k") {
      e.preventDefault();
      const searchEl = $("#sidebarSearch");
      if (searchEl) searchEl.focus();
    }
    if (e.ctrlKey && e.key === "/") {
      e.preventDefault();
      showShortcuts();
    }
    if (e.ctrlKey && e.key === "Enter" && inInput) {
      sendMessage();
    }
    if (e.key === "Escape") {
      closeShortcuts();
      closeMissionModal();
      closeNewProjectModal();
    }
  });
}

// ── SIDEBAR SEARCH ────────────────────────────────────────────────────────

function initSidebarSearch() {
  const input = $("#sidebarSearch");
  if (!input) return;
  input.addEventListener("input", () => {
    const q = input.value.toLowerCase();
    $$(".chat-item").forEach((item) => {
      const title = item.querySelector(".chat-item-title")?.textContent?.toLowerCase() || "";
      item.style.display = title.includes(q) ? "" : "none";
    });
  });
}

// ── MACROS / TOOLS TOOLBAR ────────────────────────────────────────────────

function toggleTool(tool) {
  const btn = $(`[data-tool="${tool}"]`);
  if (btn) btn.classList.toggle("active");
  // Tool-specific activation
  if (tool === "search") {
    appendMessage("rosa", "🔍 Режим веб-поиска включён. Следующий вопрос будет искаться в интернете.");
  } else if (tool === "code") {
    appendMessage("rosa", "💻 Режим кода включён. Готова писать и исполнять код.");
  } else if (tool === "memory") {
    appendMessage("rosa", "🧠 Доступ к памяти включён. Буду использовать долгосрочную память.");
  } else if (tool === "files") {
    appendMessage("rosa", "📁 Доступ к файлам включён. Могу читать и записывать файлы.");
  }
}

// ── TOKEN COUNTER ─────────────────────────────────────────────────────────

function updateTokenCount() {
  const ta = $("#chatInput");
  const counter = $("#tokenCount");
  if (!ta || !counter) return;
  const chars = ta.value.length;
  const approx = Math.ceil(chars / 4);
  counter.textContent = `~${approx} токенов`;
}

// ── SYSTEM ACTIONS (SETTINGS) ─────────────────────────────────────────────

async function runGitCommit() {
  const msg = prompt("Сообщение коммита:");
  if (!msg) return;
  try {
    const data = await api("POST", "/api/coding/git/commit", { message: msg });
    alert(`✅ Коммит создан: ${data.hash || ""}`);
  } catch (e) { alert("Ошибка: " + e.message); }
}

async function createBackup() {
  try {
    await api("POST", "/api/memory/backup");
    alert("✅ Резервная копия создана");
  } catch (e) { alert("Ошибка: " + e.message); }
}

async function exportMemory() {
  try {
    const data = await api("GET", "/api/memory/knowledge?limit=1000");
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rosa_memory_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) { alert("Ошибка: " + e.message); }
}

// ── MODEL SWITCHER ────────────────────────────────────────────────────────

function selectModel(modelId) {
  $$(".model-card").forEach((c) => c.classList.remove("active"));
  const card = $(`[data-model="${modelId}"]`);
  if (card) card.classList.add("active");
  localStorage.setItem("rosa_model", modelId);
  // In future — send to API to update config
}

async function loadModelStatus() {
  try {
    const data = await api("GET", "/api/economy/env");
    const configured = data.configured || [];
    // Mark models as available/unavailable based on env vars
  } catch (e) {}
}

// ── CHAT TITLE EDITING ────────────────────────────────────────────────────

function initChatTitle() {
  const title = $("#chatTitle");
  if (!title) return;
  title.addEventListener("blur", () => {
    // Save title locally
    if (state.currentSessionId) {
      const session = state.sessions.find((s) => s.id === state.currentSessionId);
      if (session) session.preview = title.textContent;
      renderChatList();
    }
  });
}

// ── INGEST: DRAG & DROP ───────────────────────────────────────────────────

let ingestWs = null;
const ingestJobs = {};

function initDragDrop() {
  const chatArea = $(".chat-main") || document.body;

  chatArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const overlay = $("#dropOverlay");
    if (overlay) overlay.style.display = "flex";
  });

  chatArea.addEventListener("dragleave", (e) => {
    if (!e.relatedTarget || !chatArea.contains(e.relatedTarget)) {
      const overlay = $("#dropOverlay");
      if (overlay) overlay.style.display = "none";
    }
  });

  chatArea.addEventListener("drop", async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const overlay = $("#dropOverlay");
    if (overlay) overlay.style.display = "none";

    const files = [...(e.dataTransfer?.files || [])];
    const urls = e.dataTransfer?.getData("text/uri-list") || e.dataTransfer?.getData("text/plain") || "";

    if (files.length) {
      for (const file of files) {
        await uploadFileForIngest(file);
      }
    } else if (urls.trim().startsWith("http")) {
      await ingestUrl(urls.trim());
    }
  });

  // File input button
  const fileBtn = $("#ingestFileBtn");
  const fileInput = $("#ingestFileInput");
  if (fileBtn && fileInput) {
    fileBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      for (const file of fileInput.files) {
        await uploadFileForIngest(file);
      }
      fileInput.value = "";
    });
  }

  connectIngestWs();
}

async function uploadFileForIngest(file) {
  const formData = new FormData();
  formData.append("file", file);
  appendMessage("rosa", `📎 Загружаю **${escHtml(file.name)}** (${(file.size / 1024).toFixed(0)} KB)...`);

  try {
    const res = await fetch(`${state.serverUrl}/api/ingest/file`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    trackIngestJob(data.job_id, file.name);
  } catch (e) {
    appendMessage("rosa", `❌ Ошибка загрузки **${escHtml(file.name)}**: ${escHtml(e.message)}`);
  }
}

async function ingestUrl(url) {
  appendMessage("rosa", `🌐 Изучаю **${escHtml(url.slice(0, 80))}**...`);
  try {
    const data = await api("POST", "/api/ingest/url", { url });
    trackIngestJob(data.job_id, url.slice(0, 60));
  } catch (e) {
    appendMessage("rosa", `❌ Ошибка: ${escHtml(e.message)}`);
  }
}

async function ingestUrlFromInput() {
  const el = $("#ingestUrlInput");
  if (!el) return;
  const url = el.value.trim();
  if (!url) return;
  el.value = "";
  await ingestUrl(url);
}

function trackIngestJob(jobId, label) {
  ingestJobs[jobId] = label;
  updateIngestStatus(jobId, "queued", 0, label);
}

function updateIngestStatus(jobId, status, progress, label) {
  const barId = `ingest-${jobId}`;
  let bar = $(`#${barId}`);
  if (!bar) {
    const container = $("#ingestProgress");
    if (!container) return;
    bar = document.createElement("div");
    bar.id = barId;
    bar.className = "ingest-job";
    container.appendChild(bar);
  }

  const icons = { queued: "⏳", processing: "🔵", done: "✅", failed: "❌", retrying: "🔄" };
  const icon = icons[status] || "⏳";
  const name = label || ingestJobs[jobId] || jobId;

  bar.innerHTML = `
    <span class="ingest-icon">${icon}</span>
    <span class="ingest-name">${escHtml(String(name).slice(0, 50))}</span>
    ${status === "processing" ? `<div class="ingest-bar"><div class="ingest-fill" style="width:${progress}%"></div></div>` : ""}
    ${status === "done" ? `<span class="ingest-pct">100%</span>` : ""}
    ${status === "failed" ? `<span class="ingest-err">Ошибка</span>` : ""}`;

  if (status === "done") {
    const sourceName = label || "данные";
    const detail = typeof label === "string" ? label.slice(0, 60) : sourceName;
    setTimeout(() => {
      bar.remove();
      appendMessage("rosa", `✅ Роза усвоила: **${escHtml(detail)}** и добавила в граф знаний`);
    }, 2000);
  }
}

function connectIngestWs() {
  if (ingestWs) return;
  try {
    const wsUrl = state.serverUrl.replace(/^http/, "ws") + "/api/ingest/ws";
    ingestWs = new WebSocket(wsUrl);

    ingestWs.onmessage = (e) => {
      try {
        const job = JSON.parse(e.data);
        if (!job.id || job.type === "ping") return;
        const label = ingestJobs[job.id] || job.source?.slice(0, 60) || job.id;
        updateIngestStatus(job.id, job.status, job.progress || 0, label);
      } catch (_) {}
    };

    ingestWs.onclose = () => {
      ingestWs = null;
      setTimeout(connectIngestWs, 5000);
    };
  } catch (_) {}
}

// ── PUSH NOTIFICATIONS ────────────────────────────────────────────────────

async function subscribeToNotifications() {
  const statusEl = $("#pushStatus");
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    if (statusEl) statusEl.textContent = "⚠️ Push не поддерживается в этом браузере";
    return;
  }
  try {
    const reg = await navigator.serviceWorker.ready;
    const vapidRes = await api("GET", "/api/notifications/vapid-key");
    const publicKey = vapidRes.vapid_public_key;
    if (!publicKey) throw new Error("VAPID ключ не настроен на сервере");

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });

    await api("POST", "/api/notifications/subscribe", sub.toJSON());
    if (statusEl) statusEl.textContent = "✅ Push-уведомления включены";
  } catch (e) {
    if (statusEl) statusEl.textContent = `❌ Ошибка: ${escHtml(e.message)}`;
  }
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) arr[i] = raw.charCodeAt(i);
  return arr;
}

// ── TUNNEL / QR ───────────────────────────────────────────────────────────

async function loadTunnelInfo() {
  try {
    const data = await api("GET", "/api/tunnel/url");
    const urlEl = $("#tunnelUrl");
    if (urlEl) urlEl.textContent = data.url || "Туннель не активен";

    if (data.url) {
      const qrData = await api("GET", "/api/tunnel/qr");
      const qrEl = $("#tunnelQr");
      if (qrEl && qrData.qr_base64) {
        qrEl.innerHTML = `<img src="data:image/png;base64,${qrData.qr_base64}" alt="QR код" style="width:180px;height:180px">`;
      }
    }
  } catch (e) {}
}

async function startTunnel() {
  try {
    await api("POST", "/api/tunnel/start");
    await loadTunnelInfo();
  } catch (e) { alert("Ошибка: " + e.message); }
}

// ── INIT ──────────────────────────────────────────────────────────────────

function init() {
  // Chat input
  initChatInput();
  initHotkeys();
  initSidebarSearch();
  initChatTitle();
  initDragDrop();

  // Nav items
  $$(".nav-item[data-view]").forEach((el) => {
    el.addEventListener("click", () => showView(el.dataset.view));
  });

  // Start session
  if (!state.currentSessionId) state.currentSessionId = uid();

  // Connect websockets
  connectWs();
  connectStatusWs();

  // Load initial data
  loadCurrentStatus();
  loadChatList();

  // Chat input token counter
  const ta = $("#chatInput");
  if (ta) ta.addEventListener("input", updateTokenCount);

  // Show chat view by default
  showView("chat");

  // Close modals on backdrop click
  document.addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-overlay")) {
      closeShortcuts();
      closeMissionModal();
      closeNewProjectModal();
    }
  });

  // Swarm task textarea
  const swarmTa = $("#swarmTask");
  if (swarmTa) swarmTa.addEventListener("blur", analyzeComplexity);

  console.log("🌹 ROSA Desktop v5.0 — SuperJarvis initialized");
}

document.addEventListener("DOMContentLoaded", init);
