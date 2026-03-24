/* ============================================================
   ROSA OS — Desktop App v3.0
   Single-file frontend. Sections marked with ── comment banners.
   ============================================================ */

// ── STATE ─────────────────────────────────────────────────────────────────

const state = {
  serverUrl: localStorage.getItem("rosa_server") || "http://localhost:8000",
  ws: null,
  reconnectTimer: null,
  sending: false,

  currentView: "chat",
  currentSessionId: null,
  sessions: [],
  folders: [],

  // Knowledge graph
  knowledgeNodes: [],
  selectedNodeId: null,

  liveMode: false,
  liveTimer: null,
  voiceRecording: false,
  urlMode: false,
  pendingFiles: [],   // [{file_id, filename, extracted_text, content_type}]
  mediaRecorder: null,
  audioChunks: [],
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

/** Very minimal Markdown → HTML (bold, italic, code, pre, links). */
function renderMd(text) {
  // Fenced code blocks
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code class="lang-${escHtml(lang)}">${escHtml(code.trim())}</code></pre>`
  );
  // Inline code
  text = text.replace(/`([^`]+)`/g, (_, c) => `<code>${escHtml(c)}</code>`);
  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // Links
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Newlines to <br> outside pre blocks
  text = text.replace(/\n/g, "<br>");
  return text;
}

function relativeTime(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} дн назад`;
  return d.toLocaleDateString("ru-RU");
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(state.serverUrl + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} ${txt}`);
  }
  return res.json();
}

// ── MODAL ─────────────────────────────────────────────────────────────────

let _modalResolve = null;

function showModal(title, body) {
  return new Promise((resolve) => {
    _modalResolve = resolve;
    $("#modal-title").textContent = title;
    $("#modal-body").textContent = body;
    $("#modal-overlay").classList.remove("hidden");
  });
}

function closeModal(confirmed) {
  $("#modal-overlay").classList.add("hidden");
  if (_modalResolve) { _modalResolve(confirmed); _modalResolve = null; }
}

$("#modal-cancel").addEventListener("click", () => closeModal(false));
$("#modal-confirm").addEventListener("click", () => closeModal(true));
$("#modal-overlay").addEventListener("click", (e) => {
  if (e.target === $("#modal-overlay")) closeModal(false);
});

// ── STATUS ────────────────────────────────────────────────────────────────

function setStatus(state_str, text) {
  const dot = $("#status-dot");
  const label = $("#status-text");
  dot.className = `dot ${state_str}`;
  label.textContent = text;
}

// ── ROUTER (view switching) ────────────────────────────────────────────────

function switchView(view) {
  state.currentView = view;
  $$(".view").forEach((el) => el.classList.remove("active"));
  $(`#view-${view}`).classList.add("active");
  $$(".bottom-nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  if (view === "selfimprove") loadSelfImprove();
  if (view === "settings") { renderFolderManager(); renderIntegrations(); }
  if (view === "knowledge") loadKnowledge();
}

$$(".bottom-nav-btn").forEach((btn) =>
  btn.addEventListener("click", () => switchView(btn.dataset.view))
);

// ── WEBSOCKET ─────────────────────────────────────────────────────────────

function wsUrl() {
  const base = state.serverUrl.replace(/^http/, "ws");
  const params = state.currentSessionId
    ? `?session_id=${state.currentSessionId}`
    : "";
  return `${base}/api/ws/chat${params}`;
}

function wsConnect() {
  if (state.ws && state.ws.readyState < 2) return; // already open/connecting
  clearTimeout(state.reconnectTimer);
  setStatus("connecting", "Подключение…");

  const ws = new WebSocket(wsUrl());
  state.ws = ws;

  ws.onopen = () => setStatus("connected", "Подключено");

  ws.onmessage = (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch { return; }

    if (data.type === "token") {
      appendStreamToken(data.content);
    } else if (data.type === "done") {
      finalizeStream(data.model, data.mode);
      state.sending = false;
      setSending(false);
    } else if (data.type === "response") {
      // Non-streaming full response from server
      appendStreamToken(data.response || "");
      finalizeStream(data.model, data.brain_used);
      state.sending = false;
      setSending(false);
    } else if (data.type === "thinking") {
      // Already showing stream cursor — nothing extra needed
    } else if (data.type === "error") {
      appendErrorBubble(data.message || "Неизвестная ошибка");
      state.sending = false;
      setSending(false);
    }
  };

  ws.onclose = () => {
    setStatus("disconnected", "Отключено");
    state.reconnectTimer = setTimeout(wsConnect, 3000);
  };

  ws.onerror = () => ws.close();
}

// ── CHAT — RENDER ─────────────────────────────────────────────────────────

let _streamBubble = null;
let _streamContent = "";

function clearWelcome() {
  const w = $(".welcome-screen");
  if (w) w.remove();
}

function appendBubble(role, html, meta) {
  clearWelcome();
  const msgs = $("#messages");
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;
  wrap.innerHTML = `
    <div class="bubble">${html}</div>
    ${meta ? `<div class="msg-meta">${escHtml(meta)}</div>` : ""}
  `;
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
  return wrap;
}

function startStream() {
  clearWelcome();
  _streamContent = "";
  const msgs = $("#messages");
  const wrap = document.createElement("div");
  wrap.className = "message assistant";
  wrap.innerHTML = `<div class="bubble streaming"><span class="cursor">&#9611;</span></div><div class="msg-meta"></div>`;
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
  _streamBubble = wrap;
}

function appendStreamToken(token) {
  if (!_streamBubble) startStream();
  _streamContent += token;
  const bubble = _streamBubble.querySelector(".bubble");
  bubble.innerHTML = renderMd(_streamContent) + '<span class="cursor">&#9611;</span>';
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

function finalizeStream(model, mode) {
  if (!_streamBubble) return;
  const bubble = _streamBubble.querySelector(".bubble");
  bubble.innerHTML = renderMd(_streamContent);
  bubble.classList.remove("streaming");
  const meta = _streamBubble.querySelector(".msg-meta");
  if (meta) meta.textContent = [model, mode].filter(Boolean).join(" · ");
  _streamBubble = null;
  _streamContent = "";
  // Refresh session list to show updated preview
  loadSessions();
}

function appendErrorBubble(msg) {
  if (_streamBubble) {
    const bubble = _streamBubble.querySelector(".bubble");
    bubble.innerHTML = `<span class="error-text">&#9888; ${escHtml(msg)}</span>`;
    bubble.classList.remove("streaming");
    _streamBubble = null;
    _streamContent = "";
  } else {
    appendBubble("assistant", `<span class="error-text">&#9888; ${escHtml(msg)}</span>`);
  }
}

function setSending(on) {
  state.sending = on;
  $("#send-btn").disabled = on;
  $("#chat-input").disabled = on;
}

// ── CHAT — SEND ───────────────────────────────────────────────────────────

async function sendMessage() {
  if (state.sending) return;
  let text = $("#chat-input").value.trim();
  if (!text && state.pendingFiles.length === 0) return;

  // URL mode: prepend fetched web content
  if (state.urlMode && $("#url-input").value.trim()) {
    try {
      const res = await apiFetch("/api/parse-url", {
        method: "POST",
        body: JSON.stringify({ url: $("#url-input").value.trim() }),
      });
      text = `[WEB: ${res.url}]\n${res.content}\n\n${text}`;
      closeUrlMode();
    } catch (err) {
      appendErrorBubble(`Ошибка загрузки URL: ${err.message}`);
      return;
    }
  }

  // Attach file content
  let fileContext = "";
  for (const f of state.pendingFiles) {
    if (f.extracted_text) {
      fileContext += `\n\n[ФАЙЛ: ${f.filename}]\n${f.extracted_text}`;
    } else if (f.needs_vision) {
      fileContext += `\n\n[ИЗОБРАЖЕНИЕ: ${f.filename} — анализ через vision пока недоступен]`;
    }
  }
  const fullText = text + fileContext;

  if (!fullText.trim()) return;

  // Ensure session exists
  if (!state.currentSessionId) {
    await createSession();
  }

  setSending(true);

  // Render user bubble
  let userHtml = escHtml(text);
  if (state.pendingFiles.length > 0) {
    userHtml += state.pendingFiles
      .map((f) => `<br><span class="file-ref">&#128206; ${escHtml(f.filename)}</span>`)
      .join("");
  }
  appendBubble("user", userHtml);
  clearFileChips();
  state.pendingFiles = [];

  // Clear input
  $("#chat-input").value = "";
  autoResizeTextarea();

  // Ensure WS connected with correct session
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    wsConnect();
    await new Promise((r) => setTimeout(r, 500));
  }

  startStream();

  const mode = $("#chat-mode").value;
  state.ws.send(JSON.stringify({
    message: fullText,
    session_id: state.currentSessionId,
    mode: mode || undefined,
  }));
}

$("#send-btn").addEventListener("click", sendMessage);
$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

function autoResizeTextarea() {
  const ta = $("#chat-input");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
}
$("#chat-input").addEventListener("input", autoResizeTextarea);

// ── SESSIONS ──────────────────────────────────────────────────────────────

async function loadSessions() {
  try {
    const data = await apiFetch("/api/sessions");
    state.sessions = Array.isArray(data) ? data : (data.sessions || []);
    const fData = await apiFetch("/api/folders");
    state.folders = Array.isArray(fData) ? fData : [];
    renderSidebar();
  } catch (err) {
    console.error("loadSessions:", err);
  }
}

async function createSession(title) {
  title = title || "Новый чат";
  const s = await apiFetch("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  state.currentSessionId = s.id;
  await loadSessions();
  // Reconnect WS for new session
  if (state.ws) state.ws.close();
  wsConnect();
  renderChatHeader(title);
  // Clear messages
  $("#messages").innerHTML = `
    <div class="welcome-screen">
      <div class="welcome-logo">&#127801;</div>
      <h2>ROSA OS</h2>
      <p>Гибридный ИИ-ассистент на базе Kimi K2.5</p>
      <div class="welcome-hints">
        <div class="hint-chip">&#128206; Прикрепить файлы</div>
        <div class="hint-chip">&#127760; Парсить URL</div>
        <div class="hint-chip">&#127908; Голосовой ввод</div>
        <div class="hint-chip">&#9889; Live-режим</div>
      </div>
    </div>`;
  return s;
}

async function openSession(id) {
  state.currentSessionId = id;
  if (state.ws) state.ws.close();
  wsConnect();

  // Load messages
  try {
    const detail = await apiFetch(`/api/sessions/${id}`);
    renderChatHeader(detail.title);
    $("#messages").innerHTML = "";
    const messages = detail.messages || [];
    for (const turn of messages) {
      appendBubble(turn.role, renderMd(turn.content), turn.model_used || "");
    }
    if (messages.length === 0) {
      $("#messages").innerHTML = `<div style="margin:2rem auto;text-align:center;color:var(--text3)">Сообщений пока нет — начните диалог!</div>`;
    }
  } catch (err) {
    appendErrorBubble(`Не удалось загрузить сессию: ${err.message}`);
  }
  renderSidebar();
}

async function deleteSession(id) {
  const ok = await showModal("Удалить чат?", "Это удалит чат и все его сообщения. Действие необратимо.");
  if (!ok) return;
  await apiFetch(`/api/sessions/${id}`, { method: "DELETE" });
  if (state.currentSessionId === id) {
    state.currentSessionId = null;
    await createSession();
  } else {
    await loadSessions();
  }
}

async function renameSession(id, currentTitle) {
  const title = prompt("Переименовать чат:", currentTitle);
  if (!title || title === currentTitle) return;
  await apiFetch(`/api/sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
  await loadSessions();
  if (state.currentSessionId === id) renderChatHeader(title);
}

function renderChatHeader(title) {
  if (title !== undefined) $("#chat-title").textContent = title;
}

// ── SIDEBAR RENDER ────────────────────────────────────────────────────────

function renderSidebar() {
  const container = $("#sidebar-sessions");
  const search = $("#session-search").value.toLowerCase();

  // Group sessions by date
  const groups = { "Сегодня": [], "Вчера": [], "На этой неделе": [], "Раньше": [] };
  const now = new Date();
  const today = now.toDateString();
  const yesterday = new Date(now - 86400000).toDateString();

  let sessions = state.sessions;
  if (search) {
    sessions = sessions.filter((s) =>
      s.title.toLowerCase().includes(search) ||
      (s.last_message || "").toLowerCase().includes(search)
    );
  }

  for (const s of sessions) {
    const d = new Date(s.updated_at || s.created_at);
    const ds = d.toDateString();
    const diffDays = (now - d) / 86400000;
    if (ds === today) groups["Сегодня"].push(s);
    else if (ds === yesterday) groups["Вчера"].push(s);
    else if (diffDays < 7) groups["На этой неделе"].push(s);
    else groups["Раньше"].push(s);
  }

  let html = "";

  // Folders
  if (state.folders.length > 0) {
    html += `<div class="sidebar-group-label">&#128193; Папки</div>`;
    for (const folder of state.folders) {
      const folderSessions = sessions.filter((s) => s.folder_id === folder.id);
      html += `
        <div class="folder-header" data-folder="${escHtml(folder.id)}">
          <span class="folder-toggle">&#9662;</span>
          <span class="folder-name">${escHtml(folder.name)}</span>
          <span class="session-actions">
            <button class="action-btn rename-folder" data-id="${escHtml(folder.id)}" data-name="${escHtml(folder.name)}" title="Переименовать">&#9998;</button>
            <button class="action-btn delete-folder" data-id="${escHtml(folder.id)}" title="Удалить">&#128465;</button>
          </span>
        </div>
        <div class="folder-sessions" data-folder-body="${escHtml(folder.id)}">
          ${folderSessions.map((s) => sessionItemHtml(s)).join("")}
        </div>`;
    }
  }

  // Ungrouped sessions by date
  for (const [label, list] of Object.entries(groups)) {
    const ungrouped = list.filter((s) => !s.folder_id);
    if (ungrouped.length === 0) continue;
    html += `<div class="sidebar-group-label">${label}</div>`;
    html += ungrouped.map((s) => sessionItemHtml(s)).join("");
  }

  if (sessions.length === 0) {
    html = `<p class="empty-state">Чатов пока нет</p>`;
  }

  container.innerHTML = html;

  // Attach events
  $$(".session-item").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.closest(".session-actions")) return;
      openSession(el.dataset.id);
    });
  });

  $$(".delete-session").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(btn.dataset.id);
    })
  );

  $$(".rename-session").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      renameSession(btn.dataset.id, btn.dataset.title);
    })
  );

  $$(".rename-folder").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      renameFolder(btn.dataset.id, btn.dataset.name);
    })
  );

  $$(".delete-folder").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteFolder(btn.dataset.id);
    })
  );
}

function sessionItemHtml(s) {
  const active = s.id === state.currentSessionId ? " active" : "";
  const preview = escHtml((s.last_message || "").slice(0, 60));
  return `
    <div class="session-item${active}" data-id="${escHtml(s.id)}">
      <div class="session-title">${escHtml(s.title)}</div>
      ${preview ? `<div class="session-preview">${preview}</div>` : ""}
      <span class="session-actions">
        <button class="action-btn rename-session" data-id="${escHtml(s.id)}" data-title="${escHtml(s.title)}" title="Переименовать">&#9998;</button>
        <button class="action-btn delete-session" data-id="${escHtml(s.id)}" title="Удалить">&#128465;</button>
      </span>
    </div>`;
}

$("#session-search").addEventListener("input", renderSidebar);

// New chat button
$("#new-chat-btn").addEventListener("click", () => {
  switchView("chat");
  createSession();
});

// ── FOLDERS ───────────────────────────────────────────────────────────────

async function createFolder(name) {
  await apiFetch("/api/folders", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  await loadSessions();
}

async function renameFolder(id, currentName) {
  const name = prompt("Переименовать папку:", currentName);
  if (!name || name === currentName) return;
  await apiFetch(`/api/folders/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
  await loadSessions();
}

async function deleteFolder(id) {
  const ok = await showModal("Удалить папку?", "Чаты внутри переместятся в корень. Действие необратимо.");
  if (!ok) return;
  await apiFetch(`/api/folders/${id}`, { method: "DELETE" });
  await loadSessions();
}

// ── FILE UPLOAD ───────────────────────────────────────────────────────────

$("#attach-btn").addEventListener("click", () => {
  $("#file-input").click();
});

$("#file-input").addEventListener("change", async (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  if (!files.length) return;

  for (const file of files) {
    const chip = addFileChip(file.name, "загрузка…");
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (state.currentSessionId) {
        fd.append("session_id", state.currentSessionId);
      }
      const res = await fetch(state.serverUrl + "/api/files/upload", {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      state.pendingFiles.push(data);
      chip.dataset.fileId = data.file_id;
      chip.querySelector(".chip-status").textContent = data.needs_vision ? "изображение" : "готово";
    } catch (err) {
      chip.querySelector(".chip-status").textContent = "ошибка";
      chip.classList.add("chip-error");
      console.error("upload:", err);
    }
  }
  showFileChips();
});

function addFileChip(name, status) {
  const chips = $("#file-chips");
  const chip = document.createElement("div");
  chip.className = "file-chip";
  chip.innerHTML = `
    <span class="chip-name">${escHtml(name)}</span>
    <span class="chip-status">${escHtml(status)}</span>
    <button class="chip-remove" title="Убрать">&#10005;</button>
  `;
  chip.querySelector(".chip-remove").addEventListener("click", () => {
    const idx = state.pendingFiles.findIndex((f) => f.file_id === chip.dataset.fileId);
    if (idx !== -1) state.pendingFiles.splice(idx, 1);
    chip.remove();
    if ($("#file-chips").children.length === 0) hideFileChips();
  });
  chips.appendChild(chip);
  return chip;
}

function showFileChips() {
  $("#file-chips").classList.remove("hidden");
}

function hideFileChips() {
  $("#file-chips").classList.add("hidden");
}

function clearFileChips() {
  $("#file-chips").innerHTML = "";
  hideFileChips();
}

// ── VOICE ─────────────────────────────────────────────────────────────────

let _recognition = null;

function startVoiceBrowserSTT() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;

  _recognition = new SR();
  _recognition.lang = "ru-RU";
  _recognition.interimResults = true;
  _recognition.maxAlternatives = 1;

  _recognition.onstart = () => {
    state.voiceRecording = true;
    $("#voice-btn").classList.add("recording");
  };

  _recognition.onresult = (e) => {
    const transcript = [...e.results]
      .map((r) => r[0].transcript)
      .join("");
    $("#chat-input").value = transcript;
    autoResizeTextarea();
  };

  _recognition.onerror = (e) => {
    console.error("STT error:", e.error);
    stopVoice();
  };

  _recognition.onend = () => stopVoice();

  _recognition.start();
  return true;
}

function stopVoice() {
  state.voiceRecording = false;
  $("#voice-btn").classList.remove("recording");
  if (_recognition) { try { _recognition.stop(); } catch (_) {} _recognition = null; }
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    state.mediaRecorder.stop();
  }
}

async function startVoiceWhisper() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.audioChunks = [];
    state.mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    state.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) state.audioChunks.push(e.data);
    };
    state.mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(state.audioChunks, { type: "audio/webm" });
      const fd = new FormData();
      fd.append("audio", blob, "recording.webm");
      try {
        const res = await fetch(state.serverUrl + "/api/voice/transcribe", {
          method: "POST", body: fd,
        });
        if (res.ok) {
          const data = await res.json();
          $("#chat-input").value = data.text || "";
          autoResizeTextarea();
        }
      } catch (err) {
        console.error("Whisper fallback:", err);
      }
    };
    state.mediaRecorder.start();
    state.voiceRecording = true;
    $("#voice-btn").classList.add("recording");
  } catch (_) {
    alert("Доступ к микрофону запрещён или недоступен.");
  }
}

$("#voice-btn").addEventListener("click", () => {
  if (state.voiceRecording) {
    stopVoice();
    return;
  }
  const used = startVoiceBrowserSTT();
  if (!used) startVoiceWhisper();
});

// ── URL PARSER ────────────────────────────────────────────────────────────

function openUrlMode() {
  state.urlMode = true;
  $("#url-row").classList.remove("hidden");
  $("#url-input").focus();
  $("#url-btn").classList.add("active");
}

function closeUrlMode() {
  state.urlMode = false;
  $("#url-row").classList.add("hidden");
  $("#url-input").value = "";
  $("#url-btn").classList.remove("active");
}

$("#url-btn").addEventListener("click", () => {
  if (state.urlMode) closeUrlMode(); else openUrlMode();
});

$("#url-close-btn").addEventListener("click", closeUrlMode);

$("#url-fetch-btn").addEventListener("click", async () => {
  const url = $("#url-input").value.trim();
  if (!url) return;
  $("#url-fetch-btn").textContent = "…";
  try {
    const res = await apiFetch("/api/parse-url", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    const snippet = `[WEB: ${res.url}]\n${res.content}\n\n`;
    $("#chat-input").value = snippet + $("#chat-input").value;
    autoResizeTextarea();
    closeUrlMode();
  } catch (err) {
    alert(`Ошибка загрузки URL: ${err.message}`);
  } finally {
    $("#url-fetch-btn").textContent = "Загрузить";
  }
});

// ── LIVE MODE ─────────────────────────────────────────────────────────────

$("#live-btn").addEventListener("click", () => {
  state.liveMode = !state.liveMode;
  $("#live-btn").classList.toggle("active", state.liveMode);
  if (state.liveMode) {
    state.liveTimer = setInterval(() => {
      // Хук для интеграции Perplexity Computer
      if (state.currentSessionId) loadSessions();
    }, 3000);
  } else {
    clearInterval(state.liveTimer);
  }
});

// ── CHAT HEADER — RENAME ──────────────────────────────────────────────────

$("#rename-btn").addEventListener("click", () => {
  if (!state.currentSessionId) return;
  const current = $("#chat-title").textContent;
  renameSession(state.currentSessionId, current);
});

// ── KNOWLEDGE GRAPH ───────────────────────────────────────────────────────

const NODE_ICONS = { insight: "💡", entity: "📌", concept: "🧠", fact: "📎" };
const NODE_LABELS = { insight: "Инсайт", entity: "Сущность", concept: "Концепция", fact: "Факт" };

async function loadKnowledge() {
  const filter = $("#node-type-filter") ? $("#node-type-filter").value : "";
  const list = $("#knowledge-nodes-list");
  list.innerHTML = `<p class="empty-state">Загрузка…</p>`;
  try {
    const params = new URLSearchParams({ limit: 100 });
    if (filter) params.set("type", filter);
    const data = await apiFetch(`/api/knowledge/nodes?${params}`);
    state.knowledgeNodes = Array.isArray(data) ? data : (data.nodes || []);
    renderKnowledgeNodes();
  } catch (err) {
    // Knowledge API may not exist yet (Phase 2) — show friendly stub
    list.innerHTML = `<p class="empty-state">🔧 Граф знаний появится в фазе 2.<br><small>API /api/knowledge пока не готово.</small></p>`;
  }
}

function renderKnowledgeNodes() {
  const list = $("#knowledge-nodes-list");
  if (!state.knowledgeNodes.length) {
    list.innerHTML = `<p class="empty-state">Нет узлов. Добавьте инсайт ниже.</p>`;
    return;
  }
  list.innerHTML = state.knowledgeNodes.map((node) => {
    const icon = NODE_ICONS[node.type] || "📄";
    const label = NODE_LABELS[node.type] || node.type;
    const active = node.id === state.selectedNodeId ? " active" : "";
    return `
      <div class="knowledge-node-item${active}" data-id="${escHtml(node.id)}">
        <span class="node-icon">${icon}</span>
        <div class="node-info">
          <div class="node-title">${escHtml(node.title)}</div>
          <div class="node-meta">${label} · ${relativeTime(node.created_at)}</div>
        </div>
      </div>`;
  }).join("");

  $$(".knowledge-node-item").forEach((el) =>
    el.addEventListener("click", () => openNodeDetail(el.dataset.id))
  );
}

async function openNodeDetail(nodeId) {
  state.selectedNodeId = nodeId;
  renderKnowledgeNodes(); // re-render to show active state

  const titleEl = $("#node-detail-title");
  const bodyEl = $("#node-detail-body");
  const node = state.knowledgeNodes.find((n) => n.id === nodeId);
  if (!node) return;

  titleEl.textContent = `${NODE_ICONS[node.type] || "📄"} ${node.title}`;
  bodyEl.innerHTML = `<p class="empty-state">Загрузка связей…</p>`;

  try {
    const data = await apiFetch(`/api/knowledge/graph?query=${encodeURIComponent(node.title)}&limit=10`);
    const edges = (data.edges || []).filter(
      (e) => e.from_node_id === nodeId || e.to_node_id === nodeId
    );
    const relatedIds = new Set(edges.flatMap((e) => [e.from_node_id, e.to_node_id]).filter((id) => id !== nodeId));
    const relatedNodes = (data.nodes || []).filter((n) => relatedIds.has(n.id));

    bodyEl.innerHTML = `
      <div class="node-summary">${escHtml(node.summary || "")}</div>
      <div class="node-source">Источник: ${escHtml(node.source_type || "—")}</div>
      ${edges.length ? `
        <h4>Связи (${edges.length})</h4>
        <div class="edges-list">
          ${edges.map((e) => {
            const otherId = e.from_node_id === nodeId ? e.to_node_id : e.from_node_id;
            const direction = e.from_node_id === nodeId ? "→" : "←";
            const other = state.knowledgeNodes.find((n) => n.id === otherId) ||
              relatedNodes.find((n) => n.id === otherId);
            const otherTitle = other ? other.title : otherId.slice(0, 8) + "…";
            return `<div class="edge-item">
              <span class="edge-direction">${direction}</span>
              <span class="edge-relation">${escHtml(e.relation_type)}</span>
              <span class="edge-target">${escHtml(otherTitle)}</span>
            </div>`;
          }).join("")}
        </div>` : `<p class="empty-state">Нет связей с другими узлами.</p>`}`;
  } catch (err) {
    bodyEl.innerHTML = `<div class="node-summary">${escHtml(node.summary || "")}</div><p class="empty-state">Ошибка загрузки связей.</p>`;
  }
}

// Add insight button
$("#add-insight-btn").addEventListener("click", async () => {
  const text = $("#insight-input").value.trim();
  if (!text) return;
  const btn = $("#add-insight-btn");
  btn.disabled = true;
  btn.textContent = "Добавление…";
  try {
    const res = await apiFetch("/api/knowledge/insights", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    $("#insight-input").value = "";
    const added = res.nodes_created || 0;
    alert(`✅ Добавлено узлов: ${added}`);
    await loadKnowledge();
  } catch (err) {
    alert(`Ошибка: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "💡 Добавить инсайт";
  }
});

// Node type filter
if ($("#node-type-filter")) {
  $("#node-type-filter").addEventListener("change", loadKnowledge);
}

// Refresh knowledge
if ($("#refresh-knowledge-btn")) {
  $("#refresh-knowledge-btn").addEventListener("click", loadKnowledge);
}

// ── SELF-IMPROVE PANEL ────────────────────────────────────────────────────

async function loadSelfImprove() {
  loadEvents();
  loadProposals();
}

async function loadEvents() {
  const list = $("#events-list");
  const severity = $("#event-severity-filter").value;
  list.innerHTML = `<p class="empty-state">Загрузка…</p>`;
  try {
    const params = new URLSearchParams({ limit: 50 });
    if (severity) params.set("severity", severity);
    const events = await apiFetch(`/api/self-improve/events?${params}`);
    if (!events.length) {
      list.innerHTML = `<p class="empty-state">Событий пока нет.</p>`;
      return;
    }
    list.innerHTML = events.map((ev) => `
      <div class="event-card" data-severity="${escHtml(ev.severity)}">
        <div class="event-header">
          <span class="badge badge-${escHtml(ev.severity)}">${escHtml(ev.severity)}</span>
          <span class="event-type">${escHtml(ev.event_type)}</span>
          <span class="event-time">${relativeTime(ev.created_at)}</span>
        </div>
        <div class="event-desc">${escHtml(ev.description)}</div>
      </div>`).join("");
  } catch (err) {
    list.innerHTML = `<p class="empty-state">Ошибка: ${escHtml(err.message)}</p>`;
  }
}

async function loadProposals() {
  const list = $("#proposals-list");
  list.innerHTML = `<p class="empty-state">Загрузка…</p>`;
  try {
    const proposals = await apiFetch("/api/self-improve/proposals");
    if (!proposals.length) {
      list.innerHTML = `<p class="empty-state">Нет предложений. Запустите цикл улучшения.</p>`;
      return;
    }
    list.innerHTML = proposals.map((p) => `
      <div class="proposal-card">
        <div class="proposal-header">
          <span class="badge badge-${escHtml(p.status || "pending")}">${escHtml(p.status || "pending")}</span>
          <span class="proposal-time">${relativeTime(p.created_at)}</span>
        </div>
        <div class="proposal-content">${escHtml(p.content.slice(0, 300))}${p.content.length > 300 ? "…" : ""}</div>
        ${p.status !== "applied" ? `<button class="btn-ghost apply-btn" data-id="${escHtml(p.id)}">Применить</button>` : ""}
      </div>`).join("");

    $$(".apply-btn").forEach((btn) =>
      btn.addEventListener("click", () => applyProposal(btn.dataset.id))
    );
  } catch (err) {
    list.innerHTML = `<p class="empty-state">Ошибка: ${escHtml(err.message)}</p>`;
  }
}

async function applyProposal(id) {
  const ok = await showModal("Применить предложение?", "Убедитесь, что проверили директорию experimental/ перед применением.");
  if (!ok) return;
  try {
    await apiFetch(`/api/self-improve/proposals/${id}/apply`, { method: "POST" });
    loadProposals();
  } catch (err) {
    alert(`Ошибка применения: ${err.message}`);
  }
}

$("#event-severity-filter").addEventListener("change", loadEvents);
$("#refresh-proposals-btn").addEventListener("click", loadProposals);

$("#run-cycle-btn").addEventListener("click", async () => {
  const btn = $("#run-cycle-btn");
  btn.disabled = true;
  btn.textContent = "Выполняется…";
  try {
    await apiFetch("/api/self-improve/run", { method: "POST" });
    await loadSelfImprove();
  } catch (err) {
    alert(`Ошибка цикла: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Запустить цикл";
  }
});

// ── SETTINGS PANEL ────────────────────────────────────────────────────────

function renderFolderManager() {
  const mgr = $("#folder-manager");
  if (!state.folders.length) {
    mgr.innerHTML = `<p class="empty-state">Папок пока нет.</p>`;
    return;
  }
  mgr.innerHTML = state.folders.map((f) => `
    <div class="folder-row">
      <span>${escHtml(f.name)}</span>
      <span class="session-actions">
        <button class="action-btn rename-folder-settings" data-id="${escHtml(f.id)}" data-name="${escHtml(f.name)}">&#9998;</button>
        <button class="action-btn delete-folder-settings" data-id="${escHtml(f.id)}">&#128465;</button>
      </span>
    </div>`).join("");

  $$(".rename-folder-settings").forEach((btn) =>
    btn.addEventListener("click", () => renameFolder(btn.dataset.id, btn.dataset.name))
  );
  $$(".delete-folder-settings").forEach((btn) =>
    btn.addEventListener("click", () => deleteFolder(btn.dataset.id))
  );
}

/** Render integrations list in Settings. */
const INTEGRATIONS = [
  { id: "telegram",    icon: "✈️",  name: "Telegram",       envKey: "TELEGRAM_BOT_TOKEN",  desc: "Чтение/отправка сообщений в Telegram" },
  { id: "discord",     icon: "💬",  name: "Discord",         envKey: "DISCORD_TOKEN",       desc: "Мониторинг серверов и DM" },
  { id: "twitter",     icon: "🐦",  name: "Twitter/X",       envKey: "TWITTER_API_KEY",     desc: "Парсинг и публикация твитов" },
  { id: "gmail",       icon: "📧",  name: "Gmail",           envKey: "GMAIL_CREDENTIALS",   desc: "Чтение и отправка почты" },
  { id: "gdrive",      icon: "📁",  name: "Google Drive",    envKey: "GOOGLE_CREDENTIALS",  desc: "Доступ к файлам и документам" },
  { id: "perplexity",  icon: "🔍",  name: "Perplexity",      envKey: "PERPLEXITY_API_KEY",  desc: "Поиск и Computer Use (будущее)" },
  { id: "openai_tts",  icon: "🗣️",  name: "OpenAI Voice",    envKey: "OPENAI_DIRECT_KEY",   desc: "Whisper STT + TTS синтез" },
];

function renderIntegrations() {
  const container = $("#integrations-list");
  if (!container) return;
  container.innerHTML = INTEGRATIONS.map((intg) => `
    <div class="integration-item">
      <span class="intg-icon">${intg.icon}</span>
      <div class="intg-info">
        <div class="intg-name">${escHtml(intg.name)}</div>
        <div class="intg-desc">${escHtml(intg.desc)}</div>
      </div>
      <span class="intg-status">🔴 Не настроено</span>
    </div>`).join("");
}

$("#add-folder-btn").addEventListener("click", async () => {
  const name = prompt("Название папки:");
  if (!name) return;
  await createFolder(name);
  renderFolderManager();
});

$("#save-settings-btn").addEventListener("click", () => {
  const server = $("#setting-server").value.trim();
  if (server) {
    state.serverUrl = server;
    localStorage.setItem("rosa_server", server);
  }
  const mode = $("#setting-mode").value;
  localStorage.setItem("rosa_default_mode", mode);
  if (mode) $("#chat-mode").value = mode;

  const theme = $("#setting-theme").value;
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("rosa_theme", theme);

  alert("Настройки сохранены.");
});

// ── KEYBOARD SHORTCUTS ────────────────────────────────────────────────────

document.addEventListener("keydown", (e) => {
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key === "n") {
    e.preventDefault();
    switchView("chat");
    createSession();
  } else if (mod && e.key === "u") {
    e.preventDefault();
    $("#attach-btn").click();
  } else if (mod && e.key === "m") {
    e.preventDefault();
    $("#voice-btn").click();
  } else if (mod && e.key === "l" && e.shiftKey) {
    e.preventDefault();
    $("#live-btn").click();
  } else if (mod && e.key === "l") {
    e.preventDefault();
    $("#url-btn").click();
  } else if (mod && e.key === "k") {
    e.preventDefault();
    switchView("knowledge");
  } else if (e.key === "Escape") {
    closeUrlMode();
    closeModal(false);
  }
});

// ── BOOT ──────────────────────────────────────────────────────────────────

async function boot() {
  // Restore settings
  const savedMode = localStorage.getItem("rosa_default_mode");
  if (savedMode) $("#chat-mode").value = savedMode;
  const savedTheme = localStorage.getItem("rosa_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
  $("#setting-theme").value = savedTheme;
  $("#setting-server").value = state.serverUrl;

  setStatus("connecting", "Подключение…");

  // Load sessions
  await loadSessions();

  // Open latest session or create new
  if (state.sessions.length > 0) {
    await openSession(state.sessions[0].id);
  } else {
    await createSession();
  }

  // Connect WS
  wsConnect();
}

boot();

// ── SWARM VIEW ────────────────────────────────────────────────────────────────

async function runSwarm() {
  const task = $("#swarm-task-input").value.trim();
  if (!task) return;

  const checkedRoles = [...document.querySelectorAll(".swarm-roles input:checked")].map(el => el.value);
  const status = $("#swarm-status");
  const synthesis = $("#swarm-synthesis");
  const agentResults = $("#swarm-agent-results");

  status.classList.remove("hidden");
  synthesis.innerHTML = "<p class='empty-state'>⟳ Агенты работают…</p>";

  try {
    const resp = await apiFetch("/api/agents/swarm", {
      method: "POST",
      body: JSON.stringify({ task, roles: checkedRoles }),
    });
    if (resp.ok) {
      const data = await resp.json();
      synthesis.innerHTML = marked ? marked.parse(data.synthesis || "") : data.synthesis || "";
      if (data.agent_results && data.agent_results.length > 0) {
        agentResults.classList.remove("hidden");
        agentResults.innerHTML = data.agent_results.map(r =>
          `<div class="agent-result-card"><strong>${r.role}</strong>: ${r.result ? r.result.substring(0, 200) + "…" : "Нет ответа"}</div>`
        ).join("");
      }
    } else {
      synthesis.innerHTML = "<p class='error-state'>Ошибка запуска роя.</p>";
    }
  } catch(e) {
    synthesis.innerHTML = `<p class='error-state'>${e.message}</p>`;
  } finally {
    status.classList.add("hidden");
  }
}

async function generateContent() {
  const topic = $("#content-topic").value.trim();
  const contentType = $("#content-type").value;
  if (!topic) return;

  const btn = $("#content-generate-btn");
  btn.textContent = "⟳ Создание…";
  btn.disabled = true;

  try {
    const resp = await apiFetch("/api/agents/content", {
      method: "POST",
      body: JSON.stringify({ topic, content_type: contentType, research: false }),
    });
    if (resp.ok) {
      const data = await resp.json();
      const result = $("#content-result");
      result.classList.remove("hidden");
      result.innerHTML = `<h4>${data.topic}</h4><div class="content-final">${marked ? marked.parse(data.final || "") : data.final}</div>`;
    }
  } catch(e) {
    console.error("Content generation failed:", e);
  } finally {
    btn.textContent = "Создать контент";
    btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Swarm
  const swarmRunBtn = $("#swarm-run-btn");
  if (swarmRunBtn) swarmRunBtn.addEventListener("click", runSwarm);
  const contentGenBtn = $("#content-generate-btn");
  if (contentGenBtn) contentGenBtn.addEventListener("click", generateContent);

  // Projects
  loadProjects();
  const newProjectBtn = $("#new-project-btn");
  if (newProjectBtn) newProjectBtn.addEventListener("click", () => {
    $("#new-project-form").classList.toggle("hidden");
  });
  const createProjectBtn = $("#create-project-btn");
  if (createProjectBtn) createProjectBtn.addEventListener("click", createProject);
  const cancelProjectBtn = $("#cancel-project-btn");
  if (cancelProjectBtn) cancelProjectBtn.addEventListener("click", () => {
    $("#new-project-form").classList.add("hidden");
  });

  // Ouroboros
  const ouroborosBtn = $("#ouroboros-btn");
  if (ouroborosBtn) ouroborosBtn.addEventListener("click", runOuroboros);

  // Load quality stats when improvement view is opened
  const navBtns = document.querySelectorAll(".bottom-nav-btn[data-view='selfimprove']");
  navBtns.forEach(btn => btn.addEventListener("click", loadQualityStats));
});

// ── PROJECTS VIEW ─────────────────────────────────────────────────────────────

async function loadProjects() {
  const list = $("#projects-list");
  if (!list) return;
  try {
    const resp = await apiFetch("/api/projects");
    if (!resp.ok) return;
    const projects = await resp.json();
    if (projects.length === 0) {
      list.innerHTML = "<p class='empty-state'>Нет проектов. Создайте первый!</p>";
      return;
    }
    list.innerHTML = projects.map(p => `
      <div class="project-card" data-id="${p.id}">
        <div class="project-card-name">${p.name}</div>
        <div class="project-card-status badge badge-mode">${p.status || "active"}</div>
        ${p.goal ? `<div class="project-card-goal">${p.goal.substring(0, 60)}…</div>` : ""}
      </div>
    `).join("");
    list.querySelectorAll(".project-card").forEach(card => {
      card.addEventListener("click", () => openProject(card.dataset.id));
    });
  } catch(e) {
    console.error("Load projects failed:", e);
  }
}

async function openProject(projectId) {
  const detail = $("#project-detail");
  if (!detail) return;
  try {
    const resp = await apiFetch(`/api/projects/${projectId}`);
    if (!resp.ok) return;
    const p = await resp.json();
    const tasks = p.tasks || [];
    detail.innerHTML = `
      <div class="project-header">
        <h3>${p.name}</h3>
        <span class="badge badge-mode">${p.status || "active"}</span>
      </div>
      ${p.goal ? `<p class="project-goal">${p.goal}</p>` : ""}
      <div class="project-progress">
        <div class="progress-bar"><div class="progress-fill" style="width:${p.progress || 0}%"></div></div>
        <span>${p.progress || 0}% завершено</span>
      </div>
      <h4>Задачи (${tasks.length})</h4>
      <div class="task-list">
        ${tasks.map(t => `
          <div class="task-item ${t.done ? "done" : ""}">
            <input type="checkbox" ${t.done ? "checked" : ""} data-task-id="${t.id}">
            <span>${t.description}</span>
            <span class="priority-badge p${t.priority}">P${t.priority}</span>
          </div>
        `).join("") || "<p class='empty-state'>Нет задач</p>"}
      </div>
      <div class="add-task-form">
        <input type="text" id="new-task-input" placeholder="Новая задача…" />
        <select id="new-task-priority"><option value="1">P1</option><option value="2" selected>P2</option><option value="3">P3</option></select>
        <button onclick="addTask('${p.id}')">Добавить</button>
      </div>
    `;
    detail.querySelectorAll("input[type=checkbox][data-task-id]").forEach(cb => {
      cb.addEventListener("change", () => {
        if (cb.checked) completeTask(cb.dataset.taskId).then(() => openProject(projectId));
      });
    });
  } catch(e) {
    console.error("Open project failed:", e);
  }
}

async function createProject() {
  const name = $("#project-name").value.trim();
  const goal = $("#project-goal").value.trim();
  const deadline = $("#project-deadline").value;
  if (!name) return;
  try {
    const resp = await apiFetch("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, goal, deadline: deadline || null }),
    });
    if (resp.ok) {
      $("#new-project-form").classList.add("hidden");
      $("#project-name").value = "";
      $("#project-goal").value = "";
      await loadProjects();
    }
  } catch(e) { console.error(e); }
}

async function addTask(projectId) {
  const desc = $("#new-task-input").value.trim();
  const priority = parseInt($("#new-task-priority").value);
  if (!desc) return;
  try {
    const resp = await apiFetch(`/api/projects/${projectId}/tasks`, {
      method: "POST",
      body: JSON.stringify({ description: desc, priority }),
    });
    if (resp.ok) openProject(projectId);
  } catch(e) { console.error(e); }
}

async function completeTask(taskId) {
  await apiFetch(`/api/projects/tasks/${taskId}/complete`, { method: "PATCH" });
}

// ── QUALITY STATS ─────────────────────────────────────────────────────────────

async function loadQualityStats() {
  try {
    const resp = await apiFetch("/api/metacognition/stats");
    if (!resp.ok) return;
    const stats = await resp.json();
    const metrics = ["completeness", "accuracy", "helpfulness", "overall"];
    for (const m of metrics) {
      const val = stats[m + "_avg"] || 0;
      const pct = (val / 10) * 100;
      const bar = $(`#q-${m}`);
      const valEl = $(`#q-${m}-val`);
      if (bar) bar.style.width = pct + "%";
      if (valEl) valEl.textContent = val ? val.toFixed(1) + "/10" : "—";
    }
    const weakPoints = stats.top_weak_points || [];
    if (weakPoints.length > 0) {
      const section = $("#weak-points-section");
      const list = $("#weak-points-list");
      if (section) section.classList.remove("hidden");
      if (list) list.innerHTML = weakPoints.map(w =>
        `<span class="weak-tag">${w}</span>`
      ).join(" ");
    }
  } catch(e) {
    console.error("Quality stats failed:", e);
  }
}

// ── OUROBOROS CYCLE ───────────────────────────────────────────────────────────

async function runOuroboros() {
  const btn = $("#ouroboros-btn");
  if (btn) { btn.disabled = true; btn.textContent = "⟳ Цикл…"; }
  try {
    const resp = await apiFetch("/api/self-improve/run", { method: "POST" });
    if (resp.ok) {
      showNotification("🐍 Цикл Уроборос запущен!");
      await loadQualityStats();
    }
  } catch(e) { console.error(e); }
  finally {
    if (btn) { btn.disabled = false; btn.textContent = "🐍 Уроборос"; }
  }
}
