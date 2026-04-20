/* iCal — Shared Utilities */
const API_BASE = '/api';  // Same-origin via NGINX

/* ── API with retry (handles Render sleep) ── */
async function api(path, method = 'GET', body = null, _retry = true) {
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
    if (_retry) {
      await new Promise(r => setTimeout(r, 3000));
      return api(path, method, body, false);
    }
    throw new Error('Server is starting up — please try again in 30 seconds.');
  }
  if (res.status === 401) {
    localStorage.clear();
    window.location.href = 'login.html';
    return;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `Error ${res.status}`);
  return data;
}

/* ── Button loading state ── */
function setLoading(btn, on) {
  btn.classList.toggle('loading', on);
  btn.disabled = on;
}

/* ── Toast ── */
let _toastTimer;
function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'show' + (type ? ` toast-${type}` : '');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.className = ''; }, 3200);
}

/* ── Validation ── */
function validateEmail(v) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim());
}
function markField(input, errId, valid, msg) {
  const err = document.getElementById(errId);
  input.classList.toggle('err', !valid);
  if (err) {
    err.textContent = valid ? '' : msg;
    err.classList.toggle('hidden', valid);
  }
  return valid;
}

/* ── Password strength ── */
function pwStrength(pw) {
  let s = 0;
  if (pw.length >= 6) s++;
  if (pw.length >= 10) s++;
  if (/[A-Z]/.test(pw)) s++;
  if (/[0-9]/.test(pw)) s++;
  if (/[^a-zA-Z0-9]/.test(pw)) s++;
  return s;
}

/* ── Time formatting ── */
function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 6e4);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (m < 1)  return 'Just now';
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  if (d === 1) return 'Yesterday';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/* ── Food emoji lookup ── */
const FOOD_EMOJI_MAP = {
  rice:'🍚', pasta:'🍝', noodle:'🍜', bread:'🍞', pizza:'🍕', burger:'🍔',
  sandwich:'🥪', wrap:'🌯', taco:'🌮', chicken:'🍗', beef:'🥩', steak:'🥩',
  pork:'🍖', fish:'🐟', salmon:'🐠', shrimp:'🍤', egg:'🥚', tofu:'🫘',
  turkey:'🦃', bacon:'🥓', salad:'🥗', broccoli:'🥦', carrot:'🥕',
  avocado:'🥑', corn:'🌽', tomato:'🍅', mushroom:'🍄', potato:'🥔',
  fries:'🍟', apple:'🍎', banana:'🍌', orange:'🍊', grape:'🍇',
  strawberry:'🍓', mango:'🥭', watermelon:'🍉', cake:'🎂', cookie:'🍪',
  donut:'🍩', chocolate:'🍫', icecream:'🍦', yogurt:'🥛', milk:'🥛',
  cheese:'🧀', coffee:'☕', latte:'☕', juice:'🥤', smoothie:'🥤',
  soda:'🥤', tea:'🍵', oatmeal:'🥣', pancake:'🥞', waffle:'🧇',
  soup:'🍲', curry:'🍛', sushi:'🍱', dumpling:'🥟',
};
function foodEmoji(name) {
  const n = name.toLowerCase().replace(/\s+/g, '');
  for (const [k, e] of Object.entries(FOOD_EMOJI_MAP)) {
    if (n.includes(k)) return e;
  }
  return null; // return null so caller can decide to show or not
}

/* ── Number animation ── */
function animateNum(el, target, ms = 600, decimals = 0) {
  const start = Date.now();
  const tick = () => {
    const p = Math.min((Date.now() - start) / ms, 1);
    const v = p * target;
    el.textContent = decimals ? v.toFixed(decimals) : Math.round(v);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ── Logout / Switch ── */
function doLogout() {
  localStorage.clear();
  window.location.href = 'login.html';
}
