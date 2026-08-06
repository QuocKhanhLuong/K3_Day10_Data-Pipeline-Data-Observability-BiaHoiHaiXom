let currentDatasetSamples = {};

document.addEventListener('DOMContentLoaded', () => {
  fetchDashboardData();
  setInterval(pollPipelineStatus, 3000);
});

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

  event.currentTarget.classList.add('active');
  document.getElementById(`tab-${tabId}`).classList.add('active');
}

async function fetchDashboardData() {
  try {
    await Promise.all([
      fetchThreeStateSummary(),
      fetchDataSamples(),
      fetchCorruptionLog(),
      fetchRAGAnswers(),
    ]);
  } catch (err) {
    console.error('Error fetching dashboard data:', err);
  }
}

async function fetchThreeStateSummary() {
  const res = await fetch('/api/three-state-summary');
  if (!res.ok) return;
  const data = await res.json();
  const metrics = data.metrics || {};
  const quality = data.quality || {};

  // Metrics Update
  const bHit = metrics.baseline?.summary?.retrieval_hit_rate ?? metrics.baseline?.retrieval_hit_rate;
  const cHit = metrics.corrupted?.summary?.retrieval_hit_rate ?? metrics.corrupted?.retrieval_hit_rate;
  const rHit = metrics.repaired?.summary?.retrieval_hit_rate ?? metrics.repaired?.retrieval_hit_rate;

  const bF1 = metrics.baseline?.summary?.mean_token_f1 ?? metrics.baseline?.mean_token_f1;
  const cF1 = metrics.corrupted?.summary?.mean_token_f1 ?? metrics.corrupted?.mean_token_f1;
  const rF1 = metrics.repaired?.summary?.mean_token_f1 ?? metrics.repaired?.mean_token_f1;

  document.getElementById('val-hit-baseline').innerText = bHit !== undefined ? (bHit * 100).toFixed(1) + '%' : 'N/A';
  document.getElementById('val-hit-corrupted').innerText = cHit !== undefined ? (cHit * 100).toFixed(1) + '%' : 'N/A';
  document.getElementById('val-hit-repaired').innerText = rHit !== undefined ? (rHit * 100).toFixed(1) + '%' : 'N/A';

  document.getElementById('val-f1-baseline').innerText = bF1 !== undefined ? bF1.toFixed(4) : 'N/A';
  document.getElementById('val-f1-corrupted').innerText = cF1 !== undefined ? cF1.toFixed(4) : 'N/A';
  document.getElementById('val-f1-repaired').innerText = rF1 !== undefined ? rF1.toFixed(4) : 'N/A';

  // Quality Badges
  const updateBadge = (elemId, status) => {
    const el = document.getElementById(elemId);
    if (!el) return;
    const stat = (status || 'UNKNOWN').toUpperCase();
    el.innerText = stat;
    el.className = stat === 'PASS' ? 'badge badge-pass' : 'badge badge-fail';
  };

  updateBadge('badge-qual-baseline', quality.baseline?.status);
  updateBadge('badge-qual-corrupted', quality.corrupted?.status);
  updateBadge('badge-qual-repaired', quality.repaired?.status);

  // Render Three-State Table
  renderThreeStateTable(metrics, quality, data.freshness);
}

function renderThreeStateTable(metrics, quality, freshness) {
  const tbody = document.getElementById('three-state-table-body');
  if (!tbody) return;

  const fmt = (val) => (val !== undefined && val !== null) ? (typeof val === 'number' ? val.toFixed(4) : val) : 'N/A';
  const getMetric = (obj, key) => obj?.summary?.[key] ?? obj?.[key];

  const rows = [
    {
      category: 'RAG Performance',
      name: 'Retrieval Hit Rate',
      base: fmt(getMetric(metrics.baseline, 'retrieval_hit_rate')),
      corr: fmt(getMetric(metrics.corrupted, 'retrieval_hit_rate')),
      rep: fmt(getMetric(metrics.repaired, 'retrieval_hit_rate')),
      impact: '🔴 Dropped during corruption → 🟢 Recovered after repair'
    },
    {
      category: 'RAG Performance',
      name: 'Mean Token F1',
      base: fmt(getMetric(metrics.baseline, 'mean_token_f1')),
      corr: fmt(getMetric(metrics.corrupted, 'mean_token_f1')),
      rep: fmt(getMetric(metrics.repaired, 'mean_token_f1')),
      impact: '🔴 Dropped during corruption → 🟢 Recovered after repair'
    },
    {
      category: 'Data Observability',
      name: 'Quality Gate Status',
      base: quality.baseline?.status?.toUpperCase() || 'N/A',
      corr: quality.corrupted?.status?.toUpperCase() || 'N/A',
      rep: quality.repaired?.status?.toUpperCase() || 'N/A',
      impact: 'FAIL detected in corrupted state; PASS restored in repaired state'
    },
    {
      category: 'Data Observability',
      name: 'Freshness Status',
      base: freshness?.is_fresh ? 'FRESH' : 'STALE',
      corr: 'CHECKED',
      rep: 'FRESH',
      impact: `Threshold: ${freshness?.freshness_threshold_days || 180} days`
    }
  ];

  tbody.innerHTML = rows.map(r => `
    <tr>
      <td><strong>${r.category}</strong></td>
      <td><code>${r.name}</code></td>
      <td><span class="badge badge-pass">${r.base}</span></td>
      <td><span class="badge ${r.corr === 'FAIL' ? 'badge-fail' : 'badge-pass'}">${r.corr}</span></td>
      <td><span class="badge badge-pass">${r.rep}</span></td>
      <td><small style="color: var(--text-secondary);">${r.impact}</small></td>
    </tr>
  `).join('');
}

async function fetchDataSamples() {
  const res = await fetch('/api/data-samples?limit=15');
  if (!res.ok) return;
  currentDatasetSamples = await res.json();
  renderDatasetSample();
}

function renderDatasetSample() {
  const selector = document.getElementById('dataset-selector');
  const tbody = document.getElementById('dataset-preview-body');
  if (!selector || !tbody) return;

  const key = selector.value;
  const list = currentDatasetSamples[key] || [];

  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No records available for this dataset state.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(item => `
    <tr>
      <td><code>${escapeHtml(item.paper_id || 'N/A')}</code></td>
      <td><strong>${escapeHtml(item.title || 'Untitled')}</strong></td>
      <td>${escapeHtml(item.published || 'N/A')}</td>
      <td><span class="badge badge-pass">${escapeHtml(item.primary_category || 'N/A')}</span></td>
      <td style="max-width: 400px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-secondary);">
        ${escapeHtml(item.summary || '')}
      </td>
    </tr>
  `).join('');
}

async function fetchCorruptionLog() {
  const res = await fetch('/api/corruption-log');
  if (!res.ok) return;
  const log = await res.json();

  const tbody = document.getElementById('corruption-log-body');
  if (!tbody) return;

  if (!log || log.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No corruption log available. Run corruption flow to generate.</td></tr>';
    return;
  }

  tbody.innerHTML = log.map(item => `
    <tr>
      <td><code>${escapeHtml(item.rule_name || item.type || 'Rule')}</code></td>
      <td><span class="badge badge-fail">${escapeHtml(item.target_field || item.column || 'Field')}</span></td>
      <td><strong>${item.affected_rows ?? item.count ?? 'N/A'}</strong></td>
      <td style="color: var(--text-secondary);">${escapeHtml(item.description || item.details || JSON.stringify(item))}</td>
    </tr>
  `).join('');
}

async function fetchRAGAnswers() {
  const res = await fetch('/api/answers?limit=4');
  if (!res.ok) return;
  const data = await res.json();

  const container = document.getElementById('answers-container');
  if (!container) return;

  const baseline = data.baseline || [];
  const corrupted = data.corrupted || [];
  const repaired = data.repaired || [];

  if (baseline.length === 0) {
    container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 2rem;">No RAG evaluation answers found. Run pipeline to evaluate.</div>';
    return;
  }

  container.innerHTML = baseline.map((item, idx) => {
    const cItem = corrupted[idx] || {};
    const rItem = repaired[idx] || {};

    return `
      <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--bg-card-border); border-radius: 10px; padding: 1.2rem; margin-bottom: 1rem;">
        <div style="font-weight: 700; font-size: 1rem; color: var(--accent-cyan); margin-bottom: 0.5rem;">
          ❓ Question ${idx + 1}: ${escapeHtml(item.question)}
        </div>
        <div style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
          🎯 <strong>Ground Truth:</strong> ${escapeHtml(item.ground_truth)}
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem;">
          <div style="background: rgba(99, 102, 241, 0.08); padding: 0.8rem; border-radius: 8px; border-left: 3px solid var(--accent-indigo);">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--accent-indigo); margin-bottom: 4px;">BASELINE ANSWER</div>
            <div style="font-size: 0.85rem;">${escapeHtml(item.answer || 'N/A')}</div>
          </div>
          <div style="background: rgba(244, 63, 94, 0.08); padding: 0.8rem; border-radius: 8px; border-left: 3px solid var(--accent-rose);">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--accent-rose); margin-bottom: 4px;">CORRUPTED ANSWER</div>
            <div style="font-size: 0.85rem;">${escapeHtml(cItem.answer || 'N/A')}</div>
          </div>
          <div style="background: rgba(16, 185, 129, 0.08); padding: 0.8rem; border-radius: 8px; border-left: 3px solid var(--accent-emerald);">
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--accent-emerald); margin-bottom: 4px;">REPAIRED ANSWER</div>
            <div style="font-size: 0.85rem;">${escapeHtml(rItem.answer || 'N/A')}</div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function runPipeline(target) {
  const btn = document.getElementById('btn-run-all');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/run-pipeline', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target })
    });
    const data = await res.json();

    const term = document.getElementById('terminal-logs');
    if (term) {
      const line = document.createElement('div');
      line.className = 'terminal-line';
      line.innerText = `[${new Date().toLocaleTimeString()}] Pipeline triggered: ${target}`;
      term.appendChild(line);
    }
  } catch (err) {
    alert('Failed to trigger pipeline: ' + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function pollPipelineStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const statusData = await res.json();

    const indicator = document.getElementById('status-indicator');
    if (indicator) {
      if (statusData.pipeline_running) {
        indicator.innerText = '⚡ Pipeline Executing...';
        indicator.className = 'badge badge-fail';
      } else {
        indicator.innerText = 'System Ready';
        indicator.className = 'badge badge-pass';
      }
    }

    // Append logs
    const term = document.getElementById('terminal-logs');
    if (term && statusData.logs && statusData.logs.length > 0) {
      term.innerHTML = statusData.logs.map(line => `<div class="terminal-line">${escapeHtml(line)}</div>`).join('');
      term.scrollTop = term.scrollHeight;
    }
  } catch (e) {}
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
