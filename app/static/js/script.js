/* iCal script.js v10 — clean, no emojis, production */
const API_BASE = '/api';

async function api(path, method = 'GET', body = null, _retry = true) {
  const token = localStorage.getItem('token');
  const headers = {};
  if (body)  headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(API_BASE + path, {
      method, headers,
      body: body ? JSON.stringify(body) : undefined
    });
  } catch {
    if (_retry) {
      await new Promise(r => setTimeout(r, 3000));
      return api(path, method, body, false);
    }
    throw new Error('Server unavailable — please try again.');
  }
  if (res.status === 401) { localStorage.clear(); window.location.href = '/login'; return; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `Error ${res.status}`);
  return data;
}

function setLoading(btn, on) {
  btn.classList.toggle('loading', on);
  btn.disabled = on;
}

let _toastTimer;
function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = type ? `show ${type}` : 'show';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ''; }, 3200);
}

function validateEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());
}

function markField(input, errId, valid, msg) {
  const err = document.getElementById(errId);
  input.classList.toggle('err', !valid);
  if (err) { err.textContent = valid ? '' : msg; err.classList.toggle('hidden', valid); }
  return valid;
}

function pwStrength(pw) {
  let s = 0;
  if (pw.length >= 6)  s++;
  if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw)) s++;
  if (/[0-9]/.test(pw)) s++;
  if (/[^a-zA-Z0-9]/.test(pw)) s++;
  return s;
}

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (m < 1)  return 'Just now';
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (d === 1) return 'Yesterday';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function doLogout() {
  localStorage.clear();
  window.location.href = '/login';
}
