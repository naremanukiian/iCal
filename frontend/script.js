/* ═══════════════════════════════════════════════
   CalorieAI — Shared Frontend Utilities
   ═══════════════════════════════════════════════ */

const API_BASE = 'https://calorie-ai-backend-dyko.onrender.com';   // ← change for production

/* ── API helper ───────────────────────────────── */
async function api(path, method = 'GET', body = null) {
  const token = localStorage.getItem('token');
  const headers = {};
  if (body) headers['Content-Type'] = 'application/json';
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(API_BASE + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('Cannot reach the server. Make sure the backend is running on port 8000.');
  }

  if (res.status === 401) {
    localStorage.clear();
    window.location.href = 'login.html';
    return;
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Error ${res.status}`);
  }
  return data;
}

/* ── Button loading state ─────────────────────── */
function setLoading(btn, on) {
  btn.classList.toggle('loading', on);
  btn.disabled = on;
}

/* ── Toast ────────────────────────────────────── */
let _toastTimer;
function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'show' + (type ? ` toast-${type}` : '');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show', `toast-${type}`), 3400);
}

/* ── Field validation ─────────────────────────── */
function validateEmail(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()); }
function validateMin(v, n) { return v.length >= n; }

function markField(input, errId, valid, msg) {
  const err = document.getElementById(errId);
  input.classList.toggle('err', !valid);
  if (err) {
    err.textContent = valid ? '' : '⚠ ' + msg;
    err.classList.toggle('hidden', valid);
  }
  return valid;
}

/* ── Password strength ────────────────────────── */
function pwStrength(pw) {
  let s = 0;
  if (pw.length >= 6)  s++;
  if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw)) s++;
  if (/[0-9]/.test(pw)) s++;
  if (/[^a-zA-Z0-9]/.test(pw)) s++;
  return s;   // 0-5
}

/* ── Relative time ────────────────────────────── */
function timeAgo(isoStr) {
  const diff = Date.now() - new Date(isoStr).getTime();
  const m = Math.floor(diff / 6e4);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (m < 1)  return 'Just now';
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (d === 1) return 'Yesterday';
  return `${d} days ago`;
}

/* ── Food emoji lookup ────────────────────────── */
const EMOJIS = {
  rice:'🍚',pasta:'🍝',noodle:'🍜',bread:'🍞',pizza:'🍕',burger:'🍔',
  sandwich:'🥪',wrap:'🌯',taco:'🌮',burrito:'🌯',hotdog:'🌭',
  chicken:'🍗',beef:'🥩',steak:'🥩',pork:'🍖',fish:'🐟',salmon:'🐠',
  shrimp:'🍤',egg:'🥚',tofu:'🫘',turkey:'🦃',
  salad:'🥗',broccoli:'🥦',carrot:'🥕',corn:'🌽',tomato:'🍅',
  avocado:'🥑',mushroom:'🍄',potato:'🥔',fries:'🍟',chips:'🍟',
  apple:'🍎',banana:'🍌',orange:'🍊',grape:'🍇',strawberry:'🍓',
  mango:'🥭',watermelon:'🍉',pineapple:'🍍',
  cake:'🎂',cookie:'🍪',donut:'🍩',chocolate:'🍫',icecream:'🍦',
  yogurt:'🥛',milk:'🥛',cheese:'🧀',butter:'🧈',
  coffee:'☕',juice:'🥤',smoothie:'🥤',soda:'🥤',tea:'🍵',
  oatmeal:'🥣',pancake:'🥞',waffle:'🧇',cereal:'🥣',
  soup:'🍲',curry:'🍛',sushi:'🍱',dumpling:'🥟',
};

function foodEmoji(name) {
  const n = name.toLowerCase().replace(/\s+/g,'');
  for (const [k, e] of Object.entries(EMOJIS)) {
    if (n.includes(k)) return e;
  }
  return '🍽️';
}

/* ── Animate counter ──────────────────────────── */
function animateCount(el, target, ms = 700) {
  const start = Date.now();
  const tick = () => {
    const p = Math.min((Date.now() - start) / ms, 1);
    el.textContent = Math.round(p * target);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
