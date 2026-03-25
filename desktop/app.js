/**
 * ROSA OS v5 — Desktop Application
 * Autonomous AI with Self-Improvement Capabilities
 */

class RosaDesktop {
    constructor() {
        this.apiUrl = window.location.origin;
        this.currentSession = null;
        this.messages = [];
        this.mode = 'cloud';
        this.isTyping = false;
        this.currentView = 'chat';
        this.metrics = {
            messages: 0,
            sessions: 0,
            improvements: 0
        };
        
        this.init();
    }

    init() {
        this.loadSessions();
        this.setupEventListeners();
        this.checkHealth();
        this.updateMetrics();
        
        // Auto-refresh metrics
        setInterval(() => this.updateMetrics(), 30000);
        
        console.log('🌹 Rosa Desktop initialized');
    }

    // ==================== API Communication ====================

    async api(endpoint, options = {}) {
        const url = `${this.apiUrl}/api${endpoint}`;
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };
        
        try {
            const startTime = performance.now();
            const response = await fetch(url, { ...defaultOptions, ...options });
            const latency = Math.round(performance.now() - startTime);
            this.updateLatency(latency);
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    async checkHealth() {
        try {
            const response = await fetch(`${this.apiUrl}/health`);
            const data = await response.json();
            
            if (data.status === 'ok') {
                document.getElementById('connection-status').textContent = 'Connected';
                document.getElementById('connection-status').style.color = 'var(--success)';
            }
        } catch (error) {
            document.getElementById('connection-status').textContent = 'Disconnected';
            document.getElementById('connection-status').style.color = 'var(--error)';
        }
    }

    // ==================== View Navigation ====================

    switchView(viewName) {
        this.currentView = viewName;
        
        // Update nav buttons
        document.querySelectorAll('.nav-tab, .nav-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.view === viewName) {
                btn.classList.add('active');
            }
        });
        
        // Hide all views
        document.getElementById('chat-view').style.display = 'none';
        document.getElementById('memory-view').style.display = 'none';
        document.getElementById('tasks-view').style.display = 'none';
        document.getElementById('code-view').style.display = 'none';
        
        // Show selected view
        const viewMap = {
            'chat': 'chat-view',
            'memory': 'memory-view',
            'tasks': 'tasks-view',
            'code': 'code-view'
        };
        
        const viewId = viewMap[viewName];
        if (viewId) {
            document.getElementById(viewId).style.display = 'block';
        }
        
        // Load view-specific data
        if (viewName === 'memory') {
            this.loadMemoryView();
        } else if (viewName === 'tasks') {
            this.loadTasksView();
        } else if (viewName === 'code') {
            this.loadCodeView();
        }
    }

    async loadMemoryView() {
        const container = document.getElementById('memory-content');
        container.innerHTML = '<div class="loading">Загрузка памяти...</div>';
        
        try {
            const [turns, reflections] = await Promise.all([
                this.api('/memory/turns').catch(() => []),
                this.api('/memory/reflections').catch(() => [])
            ]);
            
            container.innerHTML = `
                <div class="memory-section">
                    <h3>📝 История разговоров</h3>
                    <div class="memory-list">
                        ${((Array.isArray(turns) ? turns : turns.turns) || []).map(t => `
                            <div class="memory-item">
                                <div class="memory-role">${t.role}</div>
                                <div class="memory-text">${t.content?.substring(0, 100)}...</div>
                                <div class="memory-time">${this.formatDate(t.timestamp)}</div>
                            </div>
                        `).join('') || '<p>Нет записей</p>'}
                    </div>
                </div>
                <div class="memory-section">
                    <h3>🤔 Рефлексии</h3>
                    <div class="memory-list">
                        ${((Array.isArray(reflections) ? reflections : reflections.reflections) || []).map(r => `
                            <div class="memory-item">
                                <div class="memory-text">${r.content?.substring(0, 150)}...</div>
                            </div>
                        `).join('') || '<p>Нет рефлексий</p>'}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `<div class="error">Ошибка загрузки: ${error.message}</div>`;
        }
    }

    async loadTasksView() {
        const container = document.getElementById('tasks-content');
        container.innerHTML = '<div class="loading">Загрузка задач...</div>';
        
        try {
            const tasks = await this.api('/tasks');
            
            container.innerHTML = `
                <div class="tasks-header">
                    <button class="btn-primary" onclick="rosa.createTask()">+ Новая задача</button>
                </div>
                <div class="tasks-list">
                    ${((Array.isArray(tasks) ? tasks : tasks.tasks) || []).map(t => `
                        <div class="task-item ${t.status}">
                            <div class="task-checkbox">
                                <input type="checkbox" ${t.status === 'done' ? 'checked' : ''} 
                                       onchange="rosa.toggleTask('${t.id}')">
                            </div>
                            <div class="task-info">
                                <div class="task-title">${t.title}</div>
                                <div class="task-meta">${t.priority || 'normal'} • ${this.formatDate(t.created_at)}</div>
                            </div>
                            <div class="task-actions">
                                <button onclick="rosa.deleteTask('${t.id}')">🗑️</button>
                            </div>
                        </div>
                    `).join('') || '<p>Нет задач</p>'}
                </div>
            `;
        } catch (error) {
            container.innerHTML = `<div class="error">Ошибка загрузки: ${error.message}</div>`;
        }
    }

    async loadCodeView() {
        const container = document.getElementById('code-content');
        container.innerHTML = `
            <div class="code-workspace">
                <div class="code-sidebar">
                    <div class="code-files">
                        <div class="code-file active" onclick="rosa.loadCodeFile('main.py')">main.py</div>
                        <div class="code-file" onclick="rosa.loadCodeFile('core/app.py')">core/app.py</div>
                        <div class="code-file" onclick="rosa.loadCodeFile('core/api/chat.py')">chat.py</div>
                    </div>
                </div>
                <div class="code-editor">
                    <div class="code-toolbar">
                        <button onclick="rosa.runCode()">▶️ Запустить</button>
                        <button onclick="rosa.saveCode()">💾 Сохранить</button>
                    </div>
                    <textarea id="code-textarea" class="code-textarea" placeholder="# Выберите файл или напишите код здесь..."></textarea>
                </div>
            </div>
        `;
    }

    // ==================== Chat Management ====================

    async loadSessions() {
        try {
            const sessions = await this.api('/sessions');
            this.renderSessions(sessions.sessions || []);
        } catch (error) {
            console.log('Sessions not available:', error.message);
        }
    }

    renderSessions(sessions) {
        const list = document.getElementById('chat-list');
        const count = document.getElementById('chat-count');
        
        count.textContent = sessions.length;
        
        if (sessions.length === 0) {
            list.innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-muted);">Нет истории чатов</div>';
            return;
        }
        
        list.innerHTML = sessions.map(session => `
            <div class="chat-item ${session.id === this.currentSession ? 'active' : ''}" 
                 onclick="rosa.loadSession('${session.id}')">
                <div class="chat-icon">💬</div>
                <div class="chat-info">
                    <div class="chat-title">${session.title || 'Без названия'}</div>
                    <div class="chat-meta">${this.formatDate(session.updated_at)}</div>
                </div>
            </div>
        `).join('');
    }

    async loadSession(sessionId) {
        this.currentSession = sessionId;
        
        try {
            const session = await this.api(`/sessions/${sessionId}`);
            this.messages = session.messages || [];
            this.renderMessages();
            this.hideWelcome();
            document.getElementById('current-chat-title').textContent = session.title || 'Чат';
        } catch (error) {
            this.showError('Не удалось загрузить сессию: ' + error.message);
        }
    }

    newChat() {
        this.currentSession = null;
        this.messages = [];
        this.renderMessages();
        this.showWelcome();
        document.getElementById('current-chat-title').textContent = 'Новый чат';
    }

    // ==================== Message Handling ====================

    async sendMessage() {
        const input = document.getElementById('message-input');
        const message = input.value.trim();
        
        if (!message || this.isTyping) return;
        
        input.value = '';
        input.style.height = 'auto';
        this.hideWelcome();
        
        // Add user message
        this.addMessage({
            role: 'user',
            content: message,
            timestamp: new Date().toISOString()
        });
        
        this.showTyping();
        
        try {
            const response = await this.api('/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: message,
                    session_id: this.currentSession,
                    mode: this.mode
                })
            });
            
            this.hideTyping();
            
            if (response.session_id) {
                this.currentSession = response.session_id;
                document.getElementById('current-chat-title').textContent = 
                    message.substring(0, 30) + (message.length > 30 ? '...' : '');
            }
            
            this.addMessage({
                role: 'assistant',
                content: response.response || response.message || 'Нет ответа',
                timestamp: new Date().toISOString(),
                metadata: response.metadata
            });
            
            this.metrics.messages++;
            this.updateMetrics();
            
        } catch (error) {
            this.hideTyping();
            
            // Check if it's an API key error
            const isAuthError = error.message.includes('401') || 
                               error.message.includes('User not found') ||
                               error.message.includes('API key');
            
            this.addMessage({
                role: 'assistant',
                content: isAuthError 
                    ? '⚠️ **Ошибка авторизации API**\n\nНеобходимо настроить API ключ в файле `/opt/rosa/.env`:\n\n```bash\nOPENROUTER_API_KEY=sk-or-v1-ВАШ_КЛЮЧ\n```\n\nИли используйте **Local Mode** (Ollama) если настроено локально.'
                    : `❌ Ошибка: ${error.message}`,
                timestamp: new Date().toISOString(),
                isError: true
            });
        }
    }

    sendQuick(text) {
        document.getElementById('message-input').value = text;
        this.sendMessage();
    }

    addMessage(msg) {
        this.messages.push(msg);
        this.renderMessages();
        this.scrollToBottom();
    }

    renderMessages() {
        const container = document.getElementById('messages');
        
        if (this.messages.length === 0) {
            container.innerHTML = '';
            return;
        }
        
        container.innerHTML = this.messages.map(msg => this.renderMessage(msg)).join('');
        
        // Highlight code blocks
        container.querySelectorAll('pre code').forEach(block => {
            if (window.hljs) hljs.highlightElement(block);
        });
    }

    renderMessage(msg) {
        const isUser = msg.role === 'user';
        const avatar = isUser ? '👤' : '🌹';
        const avatarClass = isUser ? 'user' : 'rosa';
        const author = isUser ? 'Вы' : 'Rosa';
        
        // Parse markdown for assistant messages
        let content = msg.content;
        if (!isUser && window.marked) {
            content = marked.parse(msg.content);
        }
        
        return `
            <div class="message">
                <div class="message-avatar ${avatarClass}">${avatar}</div>
                <div class="message-content">
                    <div class="message-header">
                        <span class="message-author">${author}</span>
                        <span class="message-time">${this.formatTime(msg.timestamp)}</span>
                    </div>
                    <div class="message-body">${content}</div>
                </div>
            </div>
        `;
    }

    showTyping() {
        this.isTyping = true;
        const container = document.getElementById('messages');
        container.style.display = 'block';
        
        const typingHtml = `
            <div class="message typing" id="typing-indicator">
                <div class="message-avatar rosa">🌹</div>
                <div class="message-content">
                    <div class="typing-indicator">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', typingHtml);
        this.scrollToBottom();
        
        document.getElementById('send-btn').disabled = true;
    }

    hideTyping() {
        this.isTyping = false;
        const typing = document.getElementById('typing-indicator');
        if (typing) typing.remove();
        document.getElementById('send-btn').disabled = false;
    }

    // ==================== Self-Improvement ====================

    async selfImprove(type, btn = null) {
        // accept btn directly from onclick(this); fallback gracefully
        if (!btn && typeof event !== 'undefined' && event && event.currentTarget) {
            btn = event.currentTarget;
        }
        const originalText = btn ? btn.textContent : '';
        if (btn) { btn.textContent = '⏳ Выполняется...'; btn.disabled = true; }
        
        try {
            let endpoint = '/self-improve/';
            let message = '';
            
            switch(type) {
                case 'analyze':
                    endpoint += 'run';
                    message = 'Запускаю цикл самоулучшения...';
                    break;
                case 'prompts':
                    endpoint += 'run';
                    message = 'Оптимизирую промпты...';
                    break;
                case 'knowledge':
                    endpoint += 'run';
                    message = 'Обновляю знания...';
                    break;
            }
            
            this.addMessage({
                role: 'assistant',
                content: `🔄 **Самоулучшение:** ${message}`,
                timestamp: new Date().toISOString()
            });
            
            const response = await this.api(endpoint, { method: 'POST' });
            
            this.addMessage({
                role: 'assistant',
                content: `✅ **Результат:**\n\n${response.message || response.status || 'Готто'}`,
                timestamp: new Date().toISOString()
            });
            
            this.metrics.improvements++;
            this.updateMetrics();
            
        } catch (error) {
            this.addMessage({
                role: 'assistant',
                content: `❌ **Ошибка:** ${error.message}`,
                timestamp: new Date().toISOString(),
                isError: true
            });
        } finally {
            if (btn) { btn.textContent = originalText; btn.disabled = false; }
        }
    }

    // ==================== UI Helpers ====================

    handleKeydown(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    showWelcome() {
        document.getElementById('welcome-screen').style.display = 'flex';
        document.getElementById('messages').style.display = 'none';
    }

    hideWelcome() {
        document.getElementById('welcome-screen').style.display = 'none';
        document.getElementById('messages').style.display = 'block';
    }

    scrollToBottom() {
        const container = document.getElementById('messages-area');
        if (container) container.scrollTop = container.scrollHeight;
    }

    toggleMode() {
        this.mode = this.mode === 'cloud' ? 'local' : 'cloud';
        const btn = document.getElementById('mode-btn');
        const status = document.getElementById('brain-mode');
        
        if (this.mode === 'cloud') {
            btn.textContent = '☁️ Cloud';
            status.textContent = 'Cloud Brain';
        } else {
            btn.textContent = '💻 Local';
            status.textContent = 'Local Brain';
        }
    }

    updateLatency(ms) {
        document.getElementById('latency').textContent = `${ms} ms`;
    }

    updateMetrics() {
        document.getElementById('metric-messages').textContent = this.metrics.messages;
        document.getElementById('metric-sessions').textContent = this.metrics.sessions;
        document.getElementById('metric-improvements').textContent = this.metrics.improvements;
    }

    // ==================== Utilities ====================

    formatDate(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60000) return 'Только что';
        if (diff < 3600000) return `${Math.floor(diff / 60000)} мин назад`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)} ч назад`;
        
        return date.toLocaleDateString('ru-RU');
    }

    formatTime(isoString) {
        if (!isoString) return '';
        return new Date(isoString).toLocaleTimeString('ru-RU', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }

    showError(message) {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 60px;
            right: 20px;
            background: var(--error);
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            z-index: 1000;
            animation: slideIn 0.3s ease;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        
        setTimeout(() => toast.remove(), 5000);
    }

    // Placeholder methods
    attachFile() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.txt,.pdf,.png,.jpg,.jpeg,.gif,.webp,.md,.py,.js,.json,.csv';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            this.addMessage({ role: 'user', content: 'Файл: ' + file.name + ' (' + Math.round(file.size/1024) + ' KB)', timestamp: new Date().toISOString() });
            this.showTyping();
            try {
                const res = await fetch(this.apiUrl + '/api/files/upload', { method: 'POST', body: formData });
                if (!res.ok) {
                    const errData = await res.json().catch(function() { return {}; });
                    throw new Error(errData.detail || 'HTTP ' + res.status);
                }
                const data = await res.json();
                this.hideTyping();
                const prompt = '[File: ' + file.name + ']\n\n' + data.extracted_text;
                const response = await this.api('/chat', {
                    method: 'POST',
                    body: JSON.stringify({ message: prompt, session_id: this.currentSession, mode: this.mode })
                });
                if (response.session_id) this.currentSession = response.session_id;
                this.addMessage({ role: 'assistant', content: response.response || 'File received.', timestamp: new Date().toISOString() });
            } catch (error) {
                this.hideTyping();
                this.addMessage({ role: 'assistant', content: 'Error: ' + error.message, timestamp: new Date().toISOString(), isError: true });
            }
        };
        input.click();
    }

    voiceInput() {
        alert('🎤 Голосовой ввод - в разработке');
    }

    shareChat() {
        const url = window.location.href;
        navigator.clipboard.writeText(url);
        alert('🔗 Ссылка скопирована в буфер обмена');
    }

    openSettings() {
        alert('⚙️ Настройки - в разработке');
    }

    createTask() {
        const title = prompt('Название задачи:');
        if (title) {
            this.api('/tasks', {
                method: 'POST',
                body: JSON.stringify({ title, status: 'todo' })
            }).then(() => this.loadTasksView());
        }
    }

    toggleTask(id) {
        this.api(`/tasks/${id}/toggle`, { method: 'POST' })
            .then(() => this.loadTasksView());
    }

    deleteTask(id) {
        if (confirm('Удалить задачу?')) {
            this.api(`/tasks/${id}`, { method: 'DELETE' })
                .then(() => this.loadTasksView());
        }
    }

    loadCodeFile(filename) {
        document.querySelectorAll('.code-file').forEach(f => f.classList.remove('active'));
        event.target.classList.add('active');
        document.getElementById('code-textarea').value = `# ${filename}\n# Загрузка...`;
    }

    runCode() {
        alert('▶️ Запуск кода - в разработке');
    }

    saveCode() {
        alert('💾 Сохранение - в разработке');
    }

    setupEventListeners() {
        // Auto-resize textarea
        const textarea = document.getElementById('message-input');
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
        });
        
        // Navigation
        document.querySelectorAll('.nav-tab, .nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.switchView(btn.dataset.view);
            });
        });
    }
}

// Initialize
const rosa = new RosaDesktop();

// Service Worker for PWA
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js')
        .then(reg => console.log('SW registered'))
        .catch(err => console.log('SW error:', err));
}
