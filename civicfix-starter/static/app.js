const form = document.getElementById('createReportForm');
const issueList = document.getElementById('issueList');
const emptyState = document.getElementById('emptyState');
const searchInput = document.getElementById('searchInput');
const statusFilter = document.getElementById('statusFilter');
const authorityToggle = document.getElementById('authorityToggle');
const authorityNotice = document.getElementById('authorityNotice');
const toastElement = document.getElementById('toast');
let allReports = [];
let authorityMode = false;
let toastTimer;

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));

function showToast(message, isError = false) {
  toastElement.textContent = message;
  toastElement.classList.toggle('error', isError);
  toastElement.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastElement.classList.remove('show'), 3600);
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function refreshStats() {
  const total = allReports.length;
  const resolved = allReports.filter(r => r.status === 'Resolved').length;
  const open = total - resolved;
  const high = allReports.filter(r => r.severity === 'High' && r.status !== 'Resolved').length;
  document.getElementById('totalStat').textContent = total;
  document.getElementById('openStat').textContent = open;
  document.getElementById('priorityStat').textContent = high;
  document.getElementById('resolvedStat').textContent = resolved;
  document.getElementById('reportCount').textContent = total;
}

function statusClass(status) {
  return ({'Submitted':'status-submitted', 'Verified':'status-verified', 'In Progress':'status-in-progress', 'Resolved':'status-resolved'})[status] || 'status-submitted';
}
function severityClass(severity) {
  return ({'High':'priority-high', 'Medium':'priority-medium', 'Low':'priority-low'})[severity] || 'priority-medium';
}
function categoryEmoji(category) {
  if (category.includes('Pothole')) return '◉';
  if (category.includes('Garbage')) return '♻';
  if (category.includes('Water')) return '≈';
  if (category.includes('Streetlight')) return '☼';
  if (category.includes('Drainage')) return '⌁';
  return '◎';
}
function prettyDate(raw) {
  if (!raw) return 'Recently';
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? 'Recently' : date.toLocaleDateString(undefined, {day:'numeric', month:'short'});
}

function renderReports() {
  const query = searchInput.value.trim().toLowerCase();
  const selectedStatus = statusFilter.value;
  const visible = allReports.filter(report => {
    const matchStatus = selectedStatus === 'all' || report.status === selectedStatus;
    const searchable = `${report.title} ${report.category} ${report.description} ${report.location}`.toLowerCase();
    return matchStatus && searchable.includes(query);
  });
  issueList.innerHTML = '';
  emptyState.classList.toggle('hidden', visible.length !== 0);
  issueList.classList.toggle('hidden', visible.length === 0);
  if (!visible.length) return;

  issueList.innerHTML = visible.map(report => {
    const score = Math.max(0, Math.min(100, Number(report.priority_score) || 0));
    const priorityTone = report.severity === 'High' ? 'high' : (report.severity === 'Medium' ? 'medium' : '');
    const image = report.image_url ? `<img class="issue-photo" src="${esc(report.image_url)}" alt="Photo attached to report" loading="lazy">` : '';
    const admin = authorityMode ? `
      <div class="admin-controls">
        <label for="status-${report.id}">Update status
          <select id="status-${report.id}" data-status-id="${report.id}">
            ${['Submitted','Verified','In Progress','Resolved'].map(status => `<option ${report.status === status ? 'selected' : ''}>${status}</option>`).join('')}
          </select>
        </label>
        <span class="admin-note">Demo control — secure this before deployment.</span>
      </div>` : '';
    return `
      <article class="issue-card">
        <div class="issue-main">
          <div class="issue-overline"><span class="category-chip">${categoryEmoji(report.category)} ${esc(report.category)}</span><span>CF-${String(report.id).padStart(4,'0')}</span><span>·</span><span>${prettyDate(report.created_at)}</span></div>
          <h3>${esc(report.title)}</h3>
          <p class="issue-description">${esc(report.description)}</p>
          <div class="issue-location"><span aria-hidden="true">⌖</span>${esc(report.location)}</div>
          <div class="issue-meta"><span class="status-chip ${statusClass(report.status)}">${esc(report.status)}</span><span class="priority-chip ${severityClass(report.severity)}">${esc(report.severity)} severity</span>${Number(report.report_count) > 1 ? `<span class="demo-chip">${Number(report.report_count)} reports</span>` : ''}${report.is_demo ? '<span class="demo-chip">Sample data</span>' : ''}</div>
        </div>
        <div class="issue-side"><div><div class="priority-number">${score}<span style="font-size:10px;color:#8c9aa9;font-weight:500">/100</span></div><div class="priority-caption">PRIORITY</div><div class="priority-track"><div class="priority-fill ${priorityTone}" style="width:${score}%"></div></div></div>${image}</div>
        ${admin}
      </article>`;
  }).join('');

  issueList.querySelectorAll('[data-status-id]').forEach(select => {
    select.addEventListener('change', async event => {
      const id = event.currentTarget.dataset.statusId;
      try {
        await apiFetch(`/api/reports/${id}/status`, {
          method: 'PATCH', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({status: event.currentTarget.value, note: 'Updated from CivicFix authority demo mode'})
        });
        showToast(`Report CF-${String(id).padStart(4,'0')} updated.`);
        await loadReports();
      } catch (error) {
        showToast(error.message, true);
        await loadReports();
      }
    });
  });
}

async function loadReports() {
  issueList.innerHTML = '<div class="loading-state"><span class="spinner"></span> Loading community reports…</div>';
  issueList.classList.remove('hidden');
  emptyState.classList.add('hidden');
  try {
    allReports = await apiFetch('/api/reports');
    refreshStats();
    renderReports();
  } catch (error) {
    issueList.innerHTML = `<div class="loading-state">Could not load reports: ${esc(error.message)}. Check that the Flask server is running.</div>`;
  }
}

async function loadHealth() {
  const status = document.getElementById('systemStatus');
  try {
    const health = await apiFetch('/api/health');
    status.textContent = health.ai_mode;
  } catch {
    status.textContent = 'Server unavailable';
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const submitButton = document.getElementById('submitButton');
  submitButton.disabled = true;
  submitButton.innerHTML = '<span class="spinner"></span> Submitting…';
  try {
    const formData = new FormData(form);
    const result = await apiFetch('/api/reports', {method:'POST', body:formData});
    if (result.duplicate) {
      showToast(`Possible duplicate found. Report CF-${String(result.report.id).padStart(4,'0')} now includes another report.`);
    } else {
      showToast(`Report submitted as CF-${String(result.report.id).padStart(4,'0')}.`);
      form.reset();
      document.getElementById('imagePreview').classList.add('hidden');
      document.getElementById('imagePreview').removeAttribute('src');
      document.getElementById('aiSuggestion').classList.add('hidden');
    }
    await loadReports();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = 'Submit report <span aria-hidden="true">→</span>';
  }
});

document.getElementById('analyzeButton').addEventListener('click', async () => {
  const description = document.getElementById('description').value.trim();
  const imageInput = document.getElementById('image');
  const suggestionBox = document.getElementById('aiSuggestion');
  const button = document.getElementById('analyzeButton');
  if (!description && !imageInput.files.length) {
    showToast('Add a description or image first.', true);
    return;
  }
  button.disabled = true;
  button.textContent = 'Analysing…';
  try {
    const data = new FormData();
    data.append('description', description);
    if (imageInput.files[0]) data.append('image', imageInput.files[0]);
    const result = await apiFetch('/api/analyze', {method:'POST', body:data});
    document.getElementById('category').value = result.category;
    document.getElementById('severity').value = result.severity;
    suggestionBox.innerHTML = `<strong>${esc(result.mode)} suggestion:</strong> ${esc(result.category)} · ${esc(result.severity)} severity<br>${esc(result.rationale)}<br><span>Check the suggestion and correct it if needed.</span>`;
    suggestionBox.classList.remove('hidden');
    showToast('Suggestion added to the form. Please review it.');
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
    button.innerHTML = '<span class="ai-spark">✳</span> Suggest category & severity';
  }
});

document.getElementById('image').addEventListener('change', event => {
  const file = event.target.files[0];
  const preview = document.getElementById('imagePreview');
  if (!file) {
    preview.classList.add('hidden');
    preview.removeAttribute('src');
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    event.target.value = '';
    preview.classList.add('hidden');
    showToast('Image must be 5 MB or smaller.', true);
    return;
  }
  if (!['image/png','image/jpeg','image/webp'].includes(file.type)) {
    event.target.value = '';
    preview.classList.add('hidden');
    showToast('Please choose PNG, JPG or WEBP.', true);
    return;
  }
  preview.src = URL.createObjectURL(file);
  preview.classList.remove('hidden');
});

searchInput.addEventListener('input', renderReports);
statusFilter.addEventListener('change', renderReports);
document.getElementById('refreshButton').addEventListener('click', loadReports);
authorityToggle.addEventListener('click', () => {
  authorityMode = !authorityMode;
  authorityToggle.textContent = `Authority mode: ${authorityMode ? 'On' : 'Off'}`;
  authorityToggle.classList.toggle('btn-primary', authorityMode);
  authorityNotice.classList.toggle('hidden', !authorityMode);
  renderReports();
});
document.getElementById('seedButton').addEventListener('click', async () => {
  try {
    const data = await apiFetch('/api/demo-seed', {method:'POST'});
    showToast(data.message);
    await loadReports();
  } catch (error) {
    showToast(error.message, true);
  }
});

loadHealth();
loadReports();
