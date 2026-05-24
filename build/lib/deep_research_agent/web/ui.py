INDEX_HTML = """<!DOCTYPE html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Deep Research Console</title>
  <style>
    :root {
      color-scheme: light;
      --page: #f5f1e8;
      --surface: rgba(255, 252, 246, 0.94);
      --surface-strong: #fffdf9;
      --ink: #161513;
      --muted: #635d53;
      --line: rgba(22, 21, 19, 0.1);
      --accent: #136f63;
      --accent-soft: rgba(19, 111, 99, 0.12);
      --warm: #b45309;
      --warm-soft: rgba(180, 83, 9, 0.12);
      --danger: #b42318;
      --danger-soft: rgba(180, 35, 24, 0.1);
      --shadow: 0 20px 45px rgba(54, 40, 19, 0.12);
      --radius: 24px;
      --radius-sm: 16px;
      --mono: \"SFMono-Regular\", \"Liberation Mono\", Menlo, Consolas, monospace;
      --sans: \"Avenir Next\", \"Segoe UI\", sans-serif;
      --serif: \"Iowan Old Style\", \"Palatino Linotype\", Georgia, serif;
    }

    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; }
    body {
      font-family: var(--sans);
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(19, 111, 99, 0.16), transparent 24%),
        radial-gradient(circle at bottom right, rgba(180, 83, 9, 0.16), transparent 24%),
        linear-gradient(180deg, #f7f3ea 0%, #f5f1e8 100%);
    }

    button, input, textarea, select { font: inherit; }
    .app-shell {
      width: min(1440px, calc(100% - 24px));
      margin: 0 auto;
      padding: 18px 0 24px;
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 18px;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(18px);
    }
    .sidebar {
      display: flex;
      flex-direction: column;
      min-height: calc(100vh - 36px);
      position: sticky;
      top: 18px;
    }
    .sidebar-header,
    .section-header,
    .composer,
    .workspace-header,
    .approval-box,
    .report-box,
    .timeline-box,
    .tasks-box,
    .sources-box {
      padding: 18px;
    }
    .brand-mark {
      width: 44px;
      height: 44px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      font-family: var(--mono);
      font-weight: 700;
      color: white;
      background: linear-gradient(135deg, var(--accent) 0%, #21967f 100%);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.3);
    }
    .eyebrow {
      margin: 0 0 8px;
      font-size: 0.74rem;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
    }
    h1, h2, h3, h4, p { margin: 0; }
    h1 {
      font-size: 1.3rem;
      line-height: 1.1;
      margin-top: 10px;
    }
    .subtle {
      color: var(--muted);
      margin-top: 10px;
      line-height: 1.5;
      font-size: 0.95rem;
    }
    .run-list {
      padding: 0 12px 12px;
      overflow: auto;
      display: grid;
      gap: 10px;
    }
    .run-card {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--surface-strong);
      padding: 14px;
      cursor: pointer;
      transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
    }
    .run-card:hover,
    .run-card.active {
      transform: translateY(-1px);
      border-color: rgba(19, 111, 99, 0.28);
      box-shadow: 0 14px 28px rgba(19, 111, 99, 0.12);
    }
    .run-card-title {
      font-size: 0.95rem;
      font-weight: 700;
      line-height: 1.35;
      margin-bottom: 10px;
    }
    .meta-row,
    .pill-row,
    .stat-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .pill,
    .status-pill {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 0 11px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 700;
      background: rgba(99, 93, 83, 0.1);
      color: var(--muted);
      border: 1px solid rgba(99, 93, 83, 0.12);
    }
    .status-created, .status-running { background: var(--accent-soft); color: var(--accent); border-color: rgba(19,111,99,0.16); }
    .status-interrupted { background: var(--warm-soft); color: var(--warm); border-color: rgba(180,83,9,0.18); }
    .status-completed { background: rgba(16, 110, 63, 0.1); color: #106e3f; border-color: rgba(16,110,63,0.16); }
    .status-failed, .status-cancelled { background: var(--danger-soft); color: var(--danger); border-color: rgba(180,35,24,0.16); }
    .workspace {
      display: grid;
      gap: 18px;
      min-width: 0;
    }
    .workspace-header {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: start;
    }
    .headline {
      font-size: clamp(1.7rem, 3vw, 2.7rem);
      line-height: 1;
      margin-top: 8px;
    }
    .workspace-copy {
      color: var(--muted);
      line-height: 1.5;
      max-width: 64ch;
      margin-top: 12px;
    }
    .composer {
      border-top: 1px solid var(--line);
      display: grid;
      gap: 14px;
    }
    textarea,
    input,
    select {
      width: 100%;
      border: 1px solid rgba(22, 21, 19, 0.12);
      border-radius: 16px;
      background: rgba(255,255,255,0.78);
      color: var(--ink);
      padding: 13px 14px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
    }
    textarea {
      resize: vertical;
      min-height: 108px;
      line-height: 1.5;
    }
    .field-grid {
      display: grid;
      grid-template-columns: 1.3fr 0.9fr;
      gap: 12px;
    }
    .field-stack {
      display: grid;
      gap: 10px;
    }
    .button-row { display: flex; gap: 10px; flex-wrap: wrap; }
    .button {
      min-height: 46px;
      border: 1px solid transparent;
      border-radius: 999px;
      padding: 0 18px;
      cursor: pointer;
      font-weight: 700;
      transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
    }
    .button:hover { transform: translateY(-1px); }
    .button-primary {
      background: linear-gradient(135deg, var(--accent) 0%, #1b8d77 100%);
      color: white;
      box-shadow: 0 12px 26px rgba(19,111,99,0.2);
    }
    .button-secondary {
      background: var(--surface-strong);
      color: var(--ink);
      border-color: var(--line);
    }
    .button-danger {
      background: var(--danger-soft);
      color: var(--danger);
      border-color: rgba(180,35,24,0.14);
    }
    .content-grid {
      display: grid;
      grid-template-columns: minmax(0, 0.95fr) minmax(320px, 0.75fr);
      gap: 18px;
    }
    .timeline-list, .tasks-list, .sources-list, .section-list {
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }
    .timeline-item, .task-card, .section-card, .source-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,255,255,0.72);
    }
    .timeline-item {
      position: relative;
      padding-left: 18px;
    }
    .timeline-item::before {
      content: \"\";
      position: absolute;
      left: 0;
      top: 18px;
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 6px rgba(19,111,99,0.12);
    }
    .task-title, .section-title, .source-title {
      font-weight: 700;
      line-height: 1.35;
      margin-bottom: 8px;
    }
    .mono {
      font-family: var(--mono);
      font-size: 0.82rem;
      color: var(--muted);
    }
    .report-box pre {
      margin: 0;
      white-space: pre-wrap;
      line-height: 1.6;
      color: var(--ink);
      font-family: var(--serif);
      font-size: 1rem;
    }
    .empty-state {
      border: 1px dashed rgba(22,21,19,0.18);
      border-radius: 18px;
      padding: 18px;
      color: var(--muted);
      background: rgba(255,255,255,0.52);
    }
    .approval-box {
      border-top: 1px solid var(--line);
      background: linear-gradient(135deg, rgba(19,111,99,0.08), rgba(180,83,9,0.08));
    }
    .approval-box.hidden { display: none; }
    .count-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 16px;
    }
    .count-card {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255,255,255,0.68);
    }
    .count-card strong { display: block; font-size: 1.35rem; margin-bottom: 4px; }
    .mobile-toggle { display: none; }

    @media (max-width: 1080px) {
      .app-shell, .content-grid, .field-grid {
        grid-template-columns: 1fr;
      }
      .sidebar {
        position: static;
        min-height: auto;
      }
      .count-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    @media (max-width: 720px) {
      .app-shell { width: min(100%, calc(100% - 16px)); }
      .workspace-header { flex-direction: column; }
      .count-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"app-shell\">
    <aside class=\"panel sidebar\">
      <div class=\"sidebar-header\">
        <div class=\"brand-mark\">DR</div>
        <p class=\"eyebrow\">Deep Research</p>
        <h1>Deep Research Console</h1>
        <p class=\"subtle\">Una interfaz local para lanzar investigaciones, seguir el flujo real del grafo y resolver checkpoints HITL sin salir del navegador.</p>
      </div>
      <div class=\"section-header\">
        <div class=\"meta-row\">
          <h2 style=\"font-size:1rem\">Corridas recientes</h2>
          <button id=\"refresh-runs\" class=\"button button-secondary\" type=\"button\">Actualizar</button>
        </div>
      </div>
      <div id=\"run-list\" class=\"run-list\"></div>
    </aside>

    <main class=\"workspace\">
      <section class=\"panel\">
        <div class=\"workspace-header\">
          <div>
            <p class=\"eyebrow\">Local Console</p>
            <h2 id=\"headline\" class=\"headline\">Lanzar una nueva investigación</h2>
            <p id=\"workspace-copy\" class=\"workspace-copy\">Elegí tu modelo local, escribí la consigna y la consola va a mostrar cada etapa: planning, búsqueda, extracción, reflexión, review humana y síntesis final.</p>
          </div>
          <div class=\"pill-row\">
            <span id=\"status-pill\" class=\"status-pill status-created\">idle</span>
            <span id=\"thread-pill\" class=\"pill mono\">sin thread activo</span>
          </div>
        </div>
        <form id=\"run-form\" class=\"composer\">
          <textarea id=\"query\" name=\"query\" placeholder=\"Ejemplo: Evaluá llama.cpp como backend local compatible con OpenAI, incluyendo compatibilidad HTTP, rendimiento, limitaciones y workflow de despliegue.\" required></textarea>
          <div class=\"field-grid\">
            <div class=\"field-stack\">
              <label for=\"base-url\">OpenAI-compatible base URL</label>
              <input id=\"base-url\" name=\"base_url\" value=\"http://127.0.0.1:8085/v1\">
            </div>
            <div class=\"field-stack\">
              <label for=\"model-name\">Modelo</label>
              <select id=\"model-name\" name=\"model_name\"></select>
            </div>
          </div>
          <div class=\"button-row\">
            <button class=\"button button-primary\" type=\"submit\">Iniciar Deep Research</button>
            <button id=\"refresh-models\" class=\"button button-secondary\" type=\"button\">Recargar modelos</button>
          </div>
        </form>
        <div id=\"approval-box\" class=\"approval-box hidden\">
          <p class=\"eyebrow\">Checkpoint HITL</p>
          <h3 id=\"approval-title\">Esperando decisión</h3>
          <p id=\"approval-prompt\" class=\"subtle\"></p>
          <textarea id=\"approval-summary\" placeholder=\"Opcional: agregá aclaraciones o feedback para el agente.\"></textarea>
          <div class=\"button-row\" style=\"margin-top:12px\">
            <button class=\"button button-primary\" type=\"button\" data-decision=\"approve\">Approve</button>
            <button class=\"button button-secondary\" type=\"button\" data-decision=\"clarify\">Clarify</button>
            <button class=\"button button-danger\" type=\"button\" data-decision=\"stop\">Stop</button>
            <button class=\"button button-secondary\" type=\"button\" data-decision=\"continue\">Continue</button>
          </div>
        </div>
      </section>

      <div class=\"content-grid\">
        <section class=\"panel timeline-box\">
          <p class=\"eyebrow\">Timeline</p>
          <div id=\"stats\" class=\"count-grid\"></div>
          <div id=\"timeline-list\" class=\"timeline-list\"></div>
        </section>

        <div class=\"workspace\" style=\"gap:18px\">
          <section class=\"panel tasks-box\">
            <div class=\"meta-row\">
              <p class=\"eyebrow\">Tasks</p>
              <span id=\"tasks-count\" class=\"pill\">0</span>
            </div>
            <div id=\"tasks-list\" class=\"tasks-list\"></div>
          </section>

          <section class=\"panel sources-box\">
            <div class=\"meta-row\">
              <p class=\"eyebrow\">Sources</p>
              <span id=\"sources-count\" class=\"pill\">0</span>
            </div>
            <div id=\"sources-list\" class=\"sources-list\"></div>
          </section>

          <section class=\"panel report-box\">
            <div class=\"meta-row\">
              <p class=\"eyebrow\">Final Report</p>
              <span id=\"report-status\" class=\"pill\">sin reporte</span>
            </div>
            <div id=\"sections-list\" class=\"section-list\"></div>
            <div id=\"report-markdown\" style=\"margin-top:16px\"></div>
          </section>
        </div>
      </div>
    </main>
  </div>

  <script>
    const state = {
      currentThreadId: null,
      pollHandle: null,
      runs: [],
    };

    const elements = {
      runForm: document.getElementById('run-form'),
      query: document.getElementById('query'),
      baseUrl: document.getElementById('base-url'),
      modelName: document.getElementById('model-name'),
      refreshModels: document.getElementById('refresh-models'),
      refreshRuns: document.getElementById('refresh-runs'),
      runList: document.getElementById('run-list'),
      headline: document.getElementById('headline'),
      workspaceCopy: document.getElementById('workspace-copy'),
      statusPill: document.getElementById('status-pill'),
      threadPill: document.getElementById('thread-pill'),
      stats: document.getElementById('stats'),
      timelineList: document.getElementById('timeline-list'),
      tasksList: document.getElementById('tasks-list'),
      tasksCount: document.getElementById('tasks-count'),
      sourcesList: document.getElementById('sources-list'),
      sourcesCount: document.getElementById('sources-count'),
      approvalBox: document.getElementById('approval-box'),
      approvalTitle: document.getElementById('approval-title'),
      approvalPrompt: document.getElementById('approval-prompt'),
      approvalSummary: document.getElementById('approval-summary'),
      sectionsList: document.getElementById('sections-list'),
      reportMarkdown: document.getElementById('report-markdown'),
      reportStatus: document.getElementById('report-status'),
    };

    function escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `HTTP ${response.status}`);
      }
      return response.json();
    }

    function setStatus(statusText) {
      const normalized = (statusText || 'created').toLowerCase();
      elements.statusPill.textContent = normalized;
      elements.statusPill.className = `status-pill status-${normalized}`;
    }

    function renderRuns(runs) {
      state.runs = runs;
      if (!runs.length) {
        elements.runList.innerHTML = '<div class="empty-state">Todavía no hay corridas registradas. Iniciá una nueva desde el panel principal.</div>';
        return;
      }
      elements.runList.innerHTML = runs.map((run) => {
        const active = run.thread_id === state.currentThreadId ? ' active' : '';
        const modelName = run.runtime_config?.model_name || 'runtime default';
        return `
          <article class="run-card${active}" data-thread-id="${escapeHtml(run.thread_id)}">
            <div class="run-card-title">${escapeHtml(run.query)}</div>
            <div class="meta-row">
              <span class="status-pill status-${escapeHtml(run.status)}">${escapeHtml(run.status)}</span>
              <span class="pill mono">${escapeHtml(modelName)}</span>
            </div>
            <p class="subtle" style="margin-top:10px">${escapeHtml(run.last_message || 'Sin mensaje')}</p>
          </article>
        `;
      }).join('');
      elements.runList.querySelectorAll('.run-card').forEach((card) => {
        card.addEventListener('click', () => selectRun(card.dataset.threadId));
      });
    }

    function renderStats(run) {
      const stateSnapshot = run.state || {};
      const stats = [
        { label: 'Tareas', value: stateSnapshot.plan_tasks?.length || 0 },
        { label: 'Fuentes', value: stateSnapshot.sources?.length || 0 },
        { label: 'Reflections', value: stateSnapshot.reflections?.length || 0 },
        { label: 'Iteración', value: stateSnapshot.iteration_count || 0 },
      ];
      elements.stats.innerHTML = stats.map((item) => `
        <div class="count-card">
          <strong>${escapeHtml(item.value)}</strong>
          <span class="subtle">${escapeHtml(item.label)}</span>
        </div>
      `).join('');
    }

    function renderTimeline(run) {
      const notes = run.state?.notes || [];
      if (!notes.length) {
        elements.timelineList.innerHTML = '<div class="empty-state">El timeline va a llenarse a medida que el grafo persista notas y checkpoints.</div>';
        return;
      }
      elements.timelineList.innerHTML = notes.map((note) => `
        <div class="timeline-item">
          <p>${escapeHtml(note)}</p>
        </div>
      `).join('');
    }

    function renderTasks(run) {
      const tasks = run.state?.plan_tasks || [];
      elements.tasksCount.textContent = String(tasks.length);
      if (!tasks.length) {
        elements.tasksList.innerHTML = '<div class="empty-state">Todavía no hay tareas planificadas.</div>';
        return;
      }
      elements.tasksList.innerHTML = tasks.map((task) => `
        <article class="task-card">
          <div class="meta-row">
            <div class="task-title">${escapeHtml(task.title)}</div>
            <span class="status-pill status-${escapeHtml(task.status)}">${escapeHtml(task.status)}</span>
          </div>
          <p class="subtle">${escapeHtml(task.description)}</p>
          <p class="mono" style="margin-top:10px">query: ${escapeHtml(task.search_query)}</p>
        </article>
      `).join('');
    }

    function renderSources(run) {
      const sources = run.state?.sources || [];
      elements.sourcesCount.textContent = String(sources.length);
      if (!sources.length) {
        elements.sourcesList.innerHTML = '<div class="empty-state">Las fuentes aparecen después de la fase de búsqueda.</div>';
        return;
      }
      elements.sourcesList.innerHTML = sources.slice(0, 8).map((source) => `
        <article class="source-card">
          <div class="source-title">${escapeHtml(source.title)}</div>
          <p class="mono">${escapeHtml(source.url)}</p>
        </article>
      `).join('');
    }

    function renderReport(run) {
      const stateSnapshot = run.state || {};
      const sections = stateSnapshot.report_sections || [];
      elements.reportStatus.textContent = stateSnapshot.final_report_status || 'sin reporte';
      if (!sections.length) {
        elements.sectionsList.innerHTML = '<div class="empty-state">El reporte final y sus secciones van a aparecer cuando el workflow llegue a síntesis.</div>';
      } else {
        elements.sectionsList.innerHTML = sections.map((section) => `
          <article class="section-card">
            <div class="meta-row">
              <div class="section-title">${escapeHtml(section.title)}</div>
              <span class="status-pill status-${escapeHtml(section.status)}">${escapeHtml(section.status)}</span>
            </div>
            <p class="subtle" style="margin-top:8px">${escapeHtml(section.content_markdown || '')}</p>
          </article>
        `).join('');
      }
      if (stateSnapshot.final_report_markdown) {
        elements.reportMarkdown.innerHTML = `<pre>${escapeHtml(stateSnapshot.final_report_markdown)}</pre>`;
      } else {
        elements.reportMarkdown.innerHTML = '';
      }
    }

    function renderApproval(run) {
      if (!run.pending_human_input) {
        elements.approvalBox.classList.add('hidden');
        return;
      }
      elements.approvalBox.classList.remove('hidden');
      elements.approvalTitle.textContent = `Review: ${run.pending_human_input.review_kind}`;
      elements.approvalPrompt.textContent = run.pending_human_input.prompt || '';
      const allowed = new Set(run.pending_human_input.allowed_decisions || []);
      elements.approvalBox.querySelectorAll('button[data-decision]').forEach((button) => {
        button.hidden = !allowed.has(button.dataset.decision);
      });
    }

    function renderRun(run) {
      state.currentThreadId = run.thread_id;
      elements.headline.textContent = run.query;
      elements.workspaceCopy.textContent = run.last_message || 'La corrida está activa.';
      elements.threadPill.textContent = run.thread_id;
      setStatus(run.status);
      renderStats(run);
      renderTimeline(run);
      renderTasks(run);
      renderSources(run);
      renderReport(run);
      renderApproval(run);
      renderRuns(state.runs);
    }

    async function loadRuns() {
      const payload = await fetchJson('/api/runs?limit=20');
      renderRuns(payload.runs || []);
      if (!state.currentThreadId && payload.runs?.length) {
        await selectRun(payload.runs[0].thread_id, false);
      }
    }

    async function selectRun(threadId, restartPolling = true) {
      const payload = await fetchJson(`/api/runs/${threadId}`);
      renderRun(payload);
      if (restartPolling) startPolling(threadId);
    }

    function startPolling(threadId) {
      if (state.pollHandle) clearInterval(state.pollHandle);
      state.pollHandle = setInterval(async () => {
        try {
          await selectRun(threadId, false);
          await loadRuns();
        } catch (error) {
          console.error(error);
        }
      }, 1500);
    }

    async function loadModels() {
      const baseUrl = elements.baseUrl.value.trim();
      const payload = await fetchJson(`/api/models?base_url=${encodeURIComponent(baseUrl)}`);
      const models = payload.models || [];
      if (!models.length) {
        elements.modelName.innerHTML = '<option value="">Sin modelos detectados</option>';
        return;
      }
      elements.modelName.innerHTML = models.map((modelId) => `<option value="${escapeHtml(modelId)}">${escapeHtml(modelId)}</option>`).join('');
    }

    async function submitRun(event) {
      event.preventDefault();
      const payload = {
        query: elements.query.value.trim(),
        model_name: elements.modelName.value,
        openai_base_url: elements.baseUrl.value.trim(),
      };
      const created = await fetchJson('/api/runs', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      renderRun(created);
      await loadRuns();
      startPolling(created.thread_id);
    }

    async function submitDecision(decision) {
      if (!state.currentThreadId) return;
      const payload = {
        decision,
        summary: elements.approvalSummary.value.trim(),
      };
      const run = await fetchJson(`/api/runs/${state.currentThreadId}/decisions`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      elements.approvalSummary.value = '';
      renderRun(run);
      await loadRuns();
      startPolling(run.thread_id);
    }

    elements.runForm.addEventListener('submit', submitRun);
    elements.refreshModels.addEventListener('click', loadModels);
    elements.refreshRuns.addEventListener('click', loadRuns);
    elements.approvalBox.querySelectorAll('button[data-decision]').forEach((button) => {
      button.addEventListener('click', () => submitDecision(button.dataset.decision));
    });

    loadModels().catch(console.error);
    loadRuns().catch(console.error);
  </script>
</body>
</html>
"""
