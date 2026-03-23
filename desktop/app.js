/**
 * ROSA OS Desktop — Main UI logic
 * WebSocket chat + REST API for tasks/reflections
 */

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  serverUrl: localStorage.getItem("rosa_server") || "http://localhost:8000",
  defaultMode: localStorage.getItem("rosa_mode") || "",
  ws: null,
  sessionId: null,
  reconnectTimer: null,
  sending: false,
};

// ── DOM helpers ───────────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function setStatus(state, text) {
  const dot = $("#status-dot");
  const label = $("#status-text");
  dot.className = `dot ${state}`;
  label.textContent = text;
}

// ── Panel navigation ──────────────────────────────────────────────────────────

function activatePanel(name) {
  $$(".nav-tab").forEach((t) => t.classList.toggle("active", t.dataset.panel === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
  if (name === "tasks")       loadTasks();
  if (name === "reflections") loadReflections();
}

$$(".nav-tab").forEach((tab) => {
  tab.addEventListener("click", () => activatePanel(tab.dataset.panel));
});

// ── Theme toggle ──────────────────────────────────────────────────────────────

const themeBtn = $("#theme-toggle");
themeBtn.addEventListener("click", () => {
  const html = document.documentElement;
  const next = html.dataset.theme === "dark" ? "light" : "dark";
  html.dataset.theme = next;
  themeBtn.textContent = next === "dark" ? "☀️" : "🌙";
  localStorage.setItem("rosa_theme", next);
});

const savedTheme = localStorage.getItem("rosa_theme");
if (savedTheme) {
  document.documentElement.dataset.theme = savedTheme;
  themeBtn.textContent = savedTheme === "dark" ? "☀️" : "🌙";
}

// ── WebSocket chat ────────────────────────────────────────────────────────────

function wsUrl() {
  return state.serverUrl.replace(/^http/, "ws") + "/api/ws/chat";
}

function connect() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) return;

  setStatus("connecting", "Connecting…");
  try {
    state.ws = new WebSocket(wsUrl());
  } catch (e) {
    setStatus("disconnected", "Connection failed");
    scheduleReconnect();
    return;
  }

  state.ws.addEventListener("open", () => {
    setStatus("connecting", "Handshaking…");
  });

  state.ws.addEventListener("message", (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }

    if (msg.type === "connected") {
      state.sessionId = msg.session_id;
      setStatus("connected", "Connected");
    } else if (msg.type === "thinking") {
      showThinking();
    } else if (msg.type === "response") {
      hideThinking();
      addMessage("assistant", msg.response, {
        model: msg.model,
        brain: msg.brain_used,
        type: msg.task_type,
      });
      setSending(false);
    } else if (msg.type === "error") {
      hideThinking();
      addMessage("assistant", `Error: ${msg.message}`, null, true);
      setSending(false);
    }
  });

  state.ws.addEventListener("close", () => {
    setStatus("disconnected", "Disconnected");
    scheduleReconnect();
  });

  state.ws.addEventListener("error", () => {
    setStatus("disconnected", "Error");
  });
}

function scheduleReconnect() {
  if (state.reconnectTimer) return;
  state.reconnectTimer = setTimeout(() => {
    state.reconnectTimer = null;
    connect();
  }, 3000);
}

function sendMessage(text, mode) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    addMessage("assistant", "Not connected to ROSA. Retrying…", null, true);
    connect();
    return;
  }
  state.ws.send(JSON.stringify({ message: text, mode: mode || undefined }));
}

// ── Message rendering ─────────────────────────────────────────────────────────

let thinkingEl = null;

function showThinking() {
  if (thinkingEl) return;
  thinkingEl = createMessageEl("assistant thinking", "Rosa is thinking…", null);
  $("#messages").appendChild(thinkingEl);
  scrollMessages();
}

function hideThinking() {
  if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
}

function createMessageEl(cls, text, meta, isError = false) {
  const wrap = document.createElement("div");
  wrap.className = `message ${cls}`;

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.innerHTML = renderMarkdown(text);
  if (isError) bubble.style.color = "var(--error)";
  wrap.appendChild(bubble);

  if (meta) {
    const metaEl = document.createElement("div");
    metaEl.className = "message-meta";
    metaEl.textContent = `${meta.brain || ""} · ${meta.model || ""} · ${meta.type || ""}`;
    wrap.appendChild(metaEl);
  }

  return wrap;
}

function addMessage(role, text, meta, isError = false) {
  const el = createMessageEl(role, text, meta, isError);
  $("#messages").appendChild(el);
  scrollMessages();
}

function scrollMessages() {
  const msgs = $("#messages");
  msgs.scrollTop = msgs.scrollHeight;
}

// Very lightweight markdown → HTML (code blocks + inline code only)
function renderMarkdown(text) {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Fenced code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="language-${lang}">${code.trimEnd()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Line breaks
  html = html.replace(/\n/g, "<br>");

  return html;
}

// ── Chat form ─────────────────────────────────────────────────────────────────

function setSending(v) {
  state.sending = v;
  $(".send-btn").disabled = v;
  $("#chat-input").disabled = v;
}

$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text || state.sending) return;

  const mode = $("#chat-mode").value;
  addMessage("user", text, null);
  setSending(true);
  input.value = "";
  input.style.height = "auto";
  sendMessage(text, mode);
});

// Auto-resize textarea
$("#chat-input").addEventListener("input", function () {
  this.style.height = "auto";
  this.style.height = Math.min(this.scrollHeight, 160) + "px";
});

// Submit on Enter (Shift+Enter for newline)
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#chat-form").dispatchEvent(new Event("submit"));
  }
});

// ── Tasks ─────────────────────────────────────────────────────────────────────

async function loadTasks() {
  const list = $("#tasks-list");
  list.innerHTML = '<p class="empty-state">Loading…</p>';
  try {
    const res = await fetch(`${state.serverUrl}/api/tasks`);
    const tasks = await res.json();
    renderTasks(tasks);
  } catch (e) {
    list.innerHTML = `<p class="empty-state" style="color:var(--error)">Failed to load tasks: ${e.message}</p>`;
  }
}

function renderTasks(tasks) {
  const list = $("#tasks-list");
  if (!tasks.length) {
    list.innerHTML = '<p class="empty-state">No tasks yet. Create one above.</p>';
    return;
  }
  list.innerHTML = "";
  tasks.forEach((task) => {
    const statusIcon = { pending: "⏳", in_progress: "🔄", done: "✅", failed: "❌" }[task.status] || "⏳";
    const card = document.createElement("div");
    card.className = "task-card";
    card.innerHTML = `
      <div class="task-status">${statusIcon}</div>
      <div class="task-body">
        <div class="task-description">${escHtml(task.description)}</div>
        <div class="task-meta">${task.status} · ${new Date(task.created_at).toLocaleString()}</div>
      </div>
      <div class="task-rating" data-task-id="${task.id}">
        ${[1, 2, 3, 4, 5].map((n) => `
          <button class="star-btn ${(task.owner_rating || 0) >= n ? "filled" : ""}" data-star="${n}">★</button>
        `).join("")}
      </div>`;
    // Star rating click
    card.querySelectorAll(".star-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const rating = parseInt(btn.dataset.star);
        await fetch(`${state.serverUrl}/api/tasks/${task.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ owner_rating: rating }),
        });
        loadTasks();
      });
    });
    list.appendChild(card);
  });
}

// New task form
$("#new-task-btn").addEventListener("click", () => {
  $("#new-task-form").classList.toggle("hidden");
  $("#task-description").focus();
});

$("#cancel-task-btn").addEventListener("click", () => {
  $("#new-task-form").classList.add("hidden");
  $("#task-description").value = "";
});

$("#create-task-btn").addEventListener("click", async () => {
  const desc = $("#task-description").value.trim();
  if (!desc) return;
  await fetch(`${state.serverUrl}/api/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description: desc }),
  });
  $("#new-task-form").classList.add("hidden");
  $("#task-description").value = "";
  loadTasks();
});

// ── Reflections ───────────────────────────────────────────────────────────────

async function loadReflections() {
  const list = $("#reflections-list");
  list.innerHTML = '<p class="empty-state">Loading…</p>';
  try {
    const res = await fetch(`${state.serverUrl}/api/memory/reflections`);
    const data = await res.json();
    renderReflections(data);
  } catch (e) {
    list.innerHTML = `<p class="empty-state" style="color:var(--error)">Failed: ${e.message}</p>`;
  }
}

function renderReflections(items) {
  const list = $("#reflections-list");
  if (!items.length) {
    list.innerHTML = '<p class="empty-state">No reflections yet. Run an improvement cycle.</p>';
    return;
  }
  list.innerHTML = "";
  items.forEach((r) => {
    const card = document.createElement("div");
    card.className = "reflection-card";
    card.innerHTML = `
      <div class="reflection-content">${escHtml(r.content)}</div>
      ${r.suggestions ? `<div class="reflection-suggestions">${escHtml(r.suggestions)}</div>` : ""}
      <div class="reflection-meta">
        ${new Date(r.created_at).toLocaleString()}
        ${r.applied ? '<span class="applied-badge">Applied</span>' : ""}
      </div>`;
    list.appendChild(card);
  });
}

$("#run-improve-btn").addEventListener("click", async () => {
  const btn = $("#run-improve-btn");
  btn.disabled = true;
  btn.textContent = "Running…";
  try {
    const res = await fetch(`${state.serverUrl}/api/self-improve/run`, { method: "POST" });
    const data = await res.json();
    alert(data.message || data.status);
    loadReflections();
  } catch (e) {
    alert(`Error: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Improvement Cycle";
  }
});

// ── Settings ──────────────────────────────────────────────────────────────────

$("#setting-server").value = state.serverUrl;
$("#setting-model").value = state.defaultMode;

$("#save-settings-btn").addEventListener("click", () => {
  state.serverUrl = $("#setting-server").value.trim() || "http://localhost:8000";
  state.defaultMode = $("#setting-model").value;
  localStorage.setItem("rosa_server", state.serverUrl);
  localStorage.setItem("rosa_mode", state.defaultMode);
  if (state.defaultMode) $("#chat-mode").value = state.defaultMode;
  // Reconnect with new URL
  if (state.ws) { state.ws.close(); state.ws = null; }
  connect();
  alert("Settings saved. Reconnecting…");
});

// ── Utility ───────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Boot ──────────────────────────────────────────────────────────────────────

connect();
