'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};

const COLS = [
  { key: 'state', label: 'State', group: 'Profile', def: true },
  { key: 'notes', label: 'Notes', group: 'Profile Notes', def: true },
  { key: 'folder', label: 'Folder', group: 'Profile Notes' },
  { key: 'ptype', label: 'Proxy Type', group: 'Proxy', def: true },
  { key: 'loc', label: 'Proxy & Location', group: 'Proxy', def: true },
  { key: 'pport', label: 'Proxy Port', group: 'Proxy' },
  { key: 'puser', label: 'Proxy Username', group: 'Proxy' },
  { key: 'ppass', label: 'Proxy Password', group: 'Proxy' },
  { key: 'os', label: 'OS', group: 'Profile Info', def: true },
  { key: 'device', label: 'Device', group: 'Profile Info' },
  { key: 'browser', label: 'Browser Version', group: 'Profile Info' },
  { key: 'created', label: 'Created', group: 'Date & Time' },
  { key: 'updated', label: 'Updated', group: 'Date & Time' },
  { key: 'lastrun', label: 'Last launch', group: 'Date & Time' },
];

const S = {
  page: 'profiles', profiles: [], proxies: [], meta: null, settings: null, browsers: null,
  folders: [], folder: '', q: '', pxq: '', sort: null,
  selected: new Set(), pxSelected: new Set(), busy: new Set(),
  cols: new Set(store.get('fl.cols', COLS.filter(c => c.def).map(c => c.key))),
  drawer: null, // { mode: 'edit'|'create', p, gpus, preview }
};

async function api(path, opts = {}) {
  const r = await fetch(path, {
    method: opts.method || (opts.body !== undefined ? 'POST' : 'GET'),
    headers: { 'Content-Type': 'application/json' },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && (data.detail || data.error)) || r.statusText);
  return data;
}

function toast(msg, err) {
  const t = document.createElement('div');
  t.className = 'toast' + (err ? ' err' : '');
  t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), err ? 7000 : 3000);
}

const FLAGS = cc => cc && cc.length === 2
  ? String.fromCodePoint(...[...cc.toUpperCase()].map(c => 0x1F1E6 + c.charCodeAt(0) - 65)) : '';
const OS_LABEL = { macos: 'macOS', windows: 'Windows', linux: 'Linux' };
const fmtDate = t => t ? new Date(t * 1000).toLocaleString() : '';
const pxKey = p => `${p.host}:${p.port}:${p.username || ''}`;
const allFolders = () => [...new Set([...S.folders, ...S.profiles.map(p => p.folder).filter(Boolean)])].sort();
const ICON = {
  settings: '<svg viewBox="0 0 20 20"><rect x="3" y="4" width="14" height="5" rx="2.5"/><rect x="3" y="11" width="14" height="5" rx="2.5"/></svg>',
  folder: '<svg viewBox="0 0 20 20"><path d="M3 6.5V15a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1H9.5L8 5H4a1 1 0 0 0-1 1.5Z"/></svg>',
  clone: '<svg viewBox="0 0 20 20"><rect x="6" y="6" width="10" height="10" rx="1.5"/><path d="M4 13V5a1 1 0 0 1 1-1h8"/></svg>',
  cookie: '<svg viewBox="0 0 20 20"><path d="M17 10.5A7 7 0 1 1 9.5 3a2.5 2.5 0 0 0 3 3 2.5 2.5 0 0 0 4.5 4.5Z"/><circle cx="8" cy="9" r=".8"/><circle cx="11" cy="13" r=".8"/><circle cx="7" cy="13" r=".8"/></svg>',
  refresh: '<svg viewBox="0 0 20 20"><path d="M16 10a6 6 0 1 1-1.8-4.3M16 4v3.5h-3.5"/></svg>',
  dice: '<svg viewBox="0 0 20 20"><rect x="3" y="3" width="14" height="14" rx="3"/><circle cx="7" cy="7" r="1" fill="currentColor"/><circle cx="13" cy="13" r="1" fill="currentColor"/><circle cx="10" cy="10" r="1" fill="currentColor"/></svg>',
  update: '<svg viewBox="0 0 20 20"><path d="M10 3v9M6 8l4 4 4-4M4 15h12"/></svg>',
  link: '<svg viewBox="0 0 20 20"><path d="M8.5 11.5a3 3 0 0 0 4.2 0l2.6-2.6a3 3 0 0 0-4.2-4.2l-.9.9M11.5 8.5a3 3 0 0 0-4.2 0l-2.6 2.6a3 3 0 0 0 4.2 4.2l.9-.9"/></svg>',
  id: '<svg viewBox="0 0 20 20"><rect x="4" y="3" width="10" height="13" rx="1.5"/><path d="M7 16v1h9V6h-1"/></svg>',
  pin: '<svg viewBox="0 0 20 20"><path d="M12 3l5 5-3 1-3 3 .5 3.5L4 8l3.5.5 3-3 1.5-2.5ZM8 12l-4 4"/></svg>',
  trash: '<svg viewBox="0 0 20 20"><path d="M4 6h12M8 6V4h4v2M6 6l1 10h6l1-10"/></svg>',
  auto: '<svg viewBox="0 0 20 20"><path d="M7 6 3 10l4 4M13 6l4 4-4 4"/></svg>',
  play: '<svg viewBox="0 0 20 20"><path d="M6 4l10 6-10 6z"/></svg>',
  eye: '<svg viewBox="0 0 20 20" width="18" height="18"><path d="M2 10s3-5.5 8-5.5S18 10 18 10s-3 5.5-8 5.5S2 10 2 10Z"/><circle cx="10" cy="10" r="2.3"/></svg>',
  eyeOff: '<svg viewBox="0 0 20 20" width="18" height="18"><path d="M2 10s3-5.5 8-5.5S18 10 18 10s-3 5.5-8 5.5S2 10 2 10Z"/><path d="M3 17 17 3"/></svg>',
};

/* ================================================================== data */
async function load() {
  const [profiles, folders, proxies] = await Promise.all([api('/api/profiles'), api('/api/folders'), api('/api/proxies')]);
  S.profiles = profiles; S.folders = folders; S.proxies = proxies;
  renderAll();
}
async function loadProxies() { S.proxies = await api('/api/proxies'); renderAll(); }

async function pollStates() {
  try {
    const { states: st, errors } = await api('/api/states');
    for (const [id, msg] of Object.entries(errors)) {
      const p = S.profiles.find(x => x.id === id);
      toast(`${p ? p.name : id}: ${msg}`, true);
    }
    let changed = false;
    for (const p of S.profiles) {
      const s = st[p.id] || 'ready';
      if (p.state !== s) { p.state = s; changed = true; }
    }
    if (changed) await load();
  } catch (e) { /* server restarting */ }
}

/* =============================================================== routing */
function go(page) {
  S.page = page;
  if (location.hash !== '#' + page) history.replaceState(null, '', '#' + page);
  $$('.page').forEach(el => el.hidden = el.id !== 'page-' + page);
  renderAll();
  if (page === 'settings') loadSettingsPage();
  if (page === 'api') renderApi();
}

function renderAll() {
  $('#countAll').textContent = S.profiles.length;
  $('#countProxies').textContent = S.proxies.length || '';
  $('#planSub').textContent = `${S.profiles.length} profiles · no limit`;
  const crumbs = { profiles: S.folder || 'All profiles', proxies: 'Proxies', settings: 'Settings', api: 'API & Automation' };
  $('#crumb').textContent = crumbs[S.page];
  $$('#nav .nav-item').forEach(a => a.classList.toggle('active',
    a.dataset.page === S.page && (S.page !== 'profiles' || (a.dataset.folder ?? null) === S.folder)));
  $('#folderList').innerHTML = allFolders().map(f => `
    <a class="nav-item ${S.page === 'profiles' && S.folder === f ? 'active' : ''}" data-page="profiles" data-folder="${esc(f)}">
      ${ICON.folder}<span>${esc(f)}</span><span class="count">${S.profiles.filter(p => p.folder === f).length}</span></a>`).join('');
  if (S.page === 'profiles') renderProfiles();
  if (S.page === 'proxies') renderProxies();
}

/* ============================================================== profiles */
function visible() {
  let list = S.profiles.filter(p => !S.folder || p.folder === S.folder);
  if (S.q) {
    const q = S.q.toLowerCase();
    list = list.filter(p => [p.name, p.notes, p.proxy.host, p.device, p.folder].join(' ').toLowerCase().includes(q));
  }
  if (S.sort) {
    const [k, dir] = S.sort;
    const key = p => k === 'name' ? p.name.toLowerCase() : (p.proxy.type || '');
    list = [...list].sort((a, b) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0) * dir);
  }
  return [...list.filter(p => p.pinned), ...list.filter(p => !p.pinned)];
}

function cellFor(key, p) {
  const px = p.proxy; const hasPx = px.type !== 'none' && px.host; const a = p.applied || {};
  switch (key) {
    case 'state': {
      const running = p.state === 'running';
      return `<td><span class="state ${running ? 'running' : ''}"><i></i>${running ? (p.port ? 'running · API' : 'running') : 'ready'}</span></td>`;
    }
    case 'notes': return `<td class="notes-cell muted" data-cell="notes" title="${esc(p.notes)}">${p.notes ? esc(p.notes) : '<span class="add-note">+ Add note</span>'}</td>`;
    case 'folder': return `<td class="muted">${esc(p.folder)}</td>`;
    case 'ptype': return `<td>${hasPx ? esc(px.type.toUpperCase()) : '-'}</td>`;
    case 'pport': return `<td class="muted">${hasPx ? esc(px.port) : ''}</td>`;
    case 'puser': return `<td class="muted">${hasPx ? esc(px.username) : ''}</td>`;
    case 'ppass': return `<td class="muted">${hasPx && px.password ? '••••••' : ''}</td>`;
    case 'loc': {
      const saved = hasPx && S.proxies.find(x => pxKey(x) === pxKey(px));
      const cc = (saved && saved.check && saved.check.countryCode) || (hasPx ? '' : a.country);
      const val = hasPx ? `${FLAGS(cc)} ${esc(px.host)}:${esc(px.port)}` : (a.country ? `${FLAGS(a.country)} <span class="muted">${esc(a.ip || '')}</span>` : '');
      return `<td class="proxy-cell" data-cell="proxy">
        <span class="proxy-val ${hasPx ? '' : 'empty'}">${val}</span>
        <span class="proxy-hover ${hasPx ? '' : 'show-empty'}"><span class="ph">Search for proxy…</span>
          <button data-pact="new" title="Add proxy">+</button><button data-pact="paste" title="Paste proxies">📋</button></span></td>`;
    }
    case 'os': return `<td class="muted">${OS_LABEL[p.os] || p.os}</td>`;
    case 'device': return `<td class="muted" title="${esc(p.device)}">${esc(p.device)}</td>`;
    case 'browser': return `<td class="muted">${esc(p.browser || 'Default')}</td>`;
    case 'created': return `<td class="muted">${fmtDate(p.created_at)}</td>`;
    case 'updated': return `<td class="muted">${fmtDate(p.updated_at)}</td>`;
    case 'lastrun': return `<td class="muted">${fmtDate(a.at)}</td>`;
  }
  return '<td></td>';
}

function renderProfiles() {
  const cols = COLS.filter(c => S.cols.has(c.key));
  $('#thead').innerHTML = `<tr>
    <th class="c-chk"><input type="checkbox" id="chkAll"></th>
    <th class="c-name"><button class="th-sort" data-sort="name">Name <span>⇅</span></button></th>
    <th class="c-act"></th>
    ${cols.map(c => c.key === 'ptype'
      ? `<th><button class="th-sort" data-sort="ptype">Proxy Type <span>⇅</span></button></th>`
      : `<th>${esc(c.label)}</th>`).join('')}</tr>`;
  $('#tabs').innerHTML = [['', 'All profiles'], ...allFolders().map(f => [f, f])]
    .map(([v, l]) => `<button class="tab ${S.folder === v ? 'active' : ''}" data-tab="${esc(v)}">${esc(l)}</button>`).join('');
  const list = visible();
  $('#empty').hidden = S.profiles.length > 0;
  $('#rows').innerHTML = list.map(p => {
    const running = p.state === 'running'; const busy = S.busy.has(p.id);
    return `<tr data-id="${p.id}" class="${S.selected.has(p.id) ? 'selected' : ''}">
      <td class="c-chk"><input type="checkbox" class="chk" ${S.selected.has(p.id) ? 'checked' : ''}></td>
      <td class="name" data-cell="name" title="${esc(p.name)} (double-click to rename)">${p.pinned ? '<span class="pin-ico">●</span>' : ''}${esc(p.name)}</td>
      <td><div class="row-actions">
        <button class="settings-link" data-act="edit" title="Open quick profile settings">Settings ›</button>
        <button class="btn-run ${running ? 'stop' : ''} ${busy ? 'busy' : ''}" data-act="${running ? 'stop' : 'run'}">${busy ? '…' : running ? 'Stop' : 'Run'}</button>
        <button class="dots" data-act="menu">•••</button>
      </div></td>
      ${cols.map(c => cellFor(c.key, p)).join('')}
    </tr>`;
  }).join('');
  $('#chkAll').checked = list.length > 0 && list.every(p => S.selected.has(p.id));
  $('#bulkBar').hidden = S.selected.size === 0;
  $('#bulkCount').textContent = `${S.selected.size} selected`;
}

async function runProfile(id) {
  S.busy.add(id); renderAll();
  try {
    await api(`/api/profiles/${id}/run`, { method: 'POST' });
    const p = S.profiles.find(x => x.id === id); if (p) p.state = 'running';
  } catch (e) { toast(e.message, true); }
  S.busy.delete(id); renderAll();
}
async function stopProfile(id) {
  S.busy.add(id); renderAll();
  try { await api(`/api/profiles/${id}/stop`, { method: 'POST' }); } catch (e) { toast(e.message, true); }
  S.busy.delete(id); await load();
}
async function patchProfile(id, body) {
  const p = await api(`/api/profiles/${id}`, { method: 'PATCH', body });
  const i = S.profiles.findIndex(x => x.id === id);
  if (i >= 0) S.profiles[i] = p;
  return p;
}
async function deleteProfiles(ids) {
  if (!confirm(`Delete ${ids.length} profile(s)? Browser data and cookies are removed too.`)) return;
  await api('/api/profiles/delete', { body: ids });
  ids.forEach(i => S.selected.delete(i));
  await load(); toast(`Deleted ${ids.length} profile(s)`);
}

/* ------------------------------------------------------------- modal */
function modal(title, html, onOk, okLabel = 'OK', wide = false) {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = html;
  $('#modalOk').textContent = okLabel;
  $('#modalFoot').hidden = !onOk;
  $('.modal-card').classList.toggle('wide', wide);
  $('#modal').hidden = false;
  const close = () => { $('#modal').hidden = true; $('#modalOk').onclick = null; };
  $('#modalCancel').onclick = close; $('#modalX').onclick = close;
  $('#modalOk').onclick = async () => {
    $('#modalOk').disabled = true;
    try { if ((await onOk()) !== false) close(); } catch (e) { toast(e.message, true); }
    $('#modalOk').disabled = false;
  };
  const first = $('#modalBody input, #modalBody textarea');
  if (first) first.focus();
}

function cookiesModal(id) {
  const p = S.profiles.find(x => x.id === id); const c = p.cookies || {};
  modal(`Cookies · ${p.name}`, `
    ${c.total ? `<div class="cookie-tags" style="margin-bottom:10px">${c.domains.map(([d, n]) => `<span>${esc(d)}<b>${n}</b></span>`).join('')}</div>` : '<p class="muted">No cookies saved yet.</p>'}
    <div style="margin-bottom:8px"><a class="linkbtn" href="/api/profiles/${id}/cookies/export" download="cookies-${esc(p.name)}.json">⬇ Export cookies (JSON)</a></div>
    <label>Import cookies: paste JSON (EditThisCookie, Cookie-Editor or Playwright format)</label>
    <textarea id="ckJson" placeholder='[{"name":"sid","value":"…","domain":".example.com","path":"/"}]'></textarea>
    <div class="sub">Imported cookies are added the next time the profile starts.</div>`, async () => {
    const raw = $('#ckJson').value.trim(); if (!raw) return;
    let arr; try { arr = JSON.parse(raw); } catch (e) { throw new Error('Invalid JSON'); }
    if (!Array.isArray(arr)) arr = arr.cookies || [];
    const r = await api(`/api/profiles/${id}/cookies`, { body: arr });
    toast(`${r.queued} cookies queued for next launch`);
  }, 'Import');
}

function bulkCreate() {
  const d = S.settings?.defaults?.os || S.meta.hostOs;
  modal('Create multiple profiles', `
    <label>Number of profiles</label><input id="bkCount" type="number" min="1" max="1000" value="10">
    <label>Name prefix (optional)</label><input id="bkPrefix" placeholder="profile">
    <label>Operating system</label>
    <select id="bkOs">${Object.entries(OS_LABEL).map(([k, v]) => `<option value="${k}" ${k === d ? 'selected' : ''}>${v}</option>`).join('')}</select>
    <label>Folder (optional)</label><input id="bkFolder" value="${esc(S.folder)}">
    <div class="sub">Each profile gets its own realistic device (screen, GPU, audio seed, media devices) on top of your default settings.</div>`,
  async () => {
    const count = +$('#bkCount').value || 1;
    toast(`Creating ${count} profiles…`);
    const r = await api('/api/profiles/bulk', { body: {
      count, prefix: $('#bkPrefix').value, template: { os: $('#bkOs').value, folder: $('#bkFolder').value.trim() },
    } });
    await load(); toast(`Created ${r.created.length} profiles`);
  }, 'Create');
}

function importProfiles() {
  modal('Import profiles', `
    <label>One profile per line: <code>name|proxy|notes|folder|os|start_url</code>. Only the name is required.</label>
    <textarea id="impText" style="min-height:200px" placeholder="shop 01|http://user:pass@203.0.113.10:8080/|main account|Shops|mac
shop 02|203.0.113.11:8080:user:pass||Shops|windows
shop 03"></textarea>
    <div class="sub">Proxy accepts Webshare formats (<code>http://user:pass@host:port</code>, <code>host:port:user:pass</code>, <code>socks5://…</code>). OS: mac, windows, linux. Imported proxies are also saved to the Proxies list.</div>
    <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="impRand" checked style="width:auto"> Random realistic device for each profile</label>`,
  async () => {
    const text = $('#impText').value;
    const r = await api('/api/profiles/import', { body: { text } });
    const proxies = text.split('\n').map(l => (l.split('|')[1] || '').trim()).filter(Boolean);
    if (proxies.length) await api('/api/proxies/import', { body: { text: proxies.join('\n') } });
    if ($('#impRand').checked) await Promise.all(r.created.map(id => api(`/api/profiles/${id}/randomize`, { method: 'POST' })));
    await load();
    toast(`Imported ${r.created.length} profiles`);
    if (r.errors.length) toast(r.errors.join('\n'), true);
  }, 'Import', true);
}

function newFolder() {
  modal('New folder', `<label>Folder name</label><input id="fdName">`, async () => {
    const name = $('#fdName').value.trim(); if (!name) return false;
    S.folders = await api('/api/folders', { body: { name } }); renderAll();
  }, 'Create');
}

function moveToFolder(ids) {
  modal('Move to folder', `<label>Folder</label>
    <input id="mvFolder" list="mvList" placeholder="Folder name (empty = none)">
    <datalist id="mvList">${allFolders().map(f => `<option value="${esc(f)}">`).join('')}</datalist>`, async () => {
    const folder = $('#mvFolder').value.trim();
    await Promise.all(ids.map(id => api(`/api/profiles/${id}`, { method: 'PATCH', body: { folder } })));
    await load();
  }, 'Move');
}

function columnsModal() {
  const groups = [...new Set(COLS.map(c => c.group))];
  const draw = () => groups.map(g => `<div class="col-group">${g}</div>` + COLS.filter(c => c.group === g).map(c =>
    `<div class="col-row ${S.cols.has(c.key) ? 'on' : ''}" data-col="${c.key}"><span>${c.label}</span><span class="eye">${S.cols.has(c.key) ? ICON.eye : ICON.eyeOff}</span></div>`).join('')).join('');
  modal('Column Settings', `<div id="colList">${draw()}</div>`, null);
  $('#colList').onclick = e => {
    const r = e.target.closest('[data-col]'); if (!r) return;
    const k = r.dataset.col; S.cols.has(k) ? S.cols.delete(k) : S.cols.add(k);
    store.set('fl.cols', [...S.cols]); $('#colList').innerHTML = draw(); renderAll();
  };
}

function browserModal(id) {
  const p = S.profiles.find(x => x.id === id);
  const inst = (S.browsers && S.browsers.installed) || [];
  modal(`Browser core · ${p.name}`, `
    <label>Camoufox build used by this profile</label>
    <select id="brSel"><option value="">App default${S.settings?.browser ? ` (${esc(S.settings.browser)})` : ''}</option>
      ${inst.map(v => `<option value="${esc(v.version)}" ${p.browser === v.version ? 'selected' : ''}>${esc(v.version)}${v.prerelease ? ' (prerelease)' : ''}</option>`).join('')}</select>
    <div class="sub">Install newer or older builds in Settings › Browser core.</div>`, async () => {
    await patchProfile(id, { browser: $('#brSel').value }); renderAll(); toast('Browser core updated');
  }, 'Save');
}

function automationModal(id) {
  const p = S.profiles.find(x => x.id === id);
  modal(`Automation · ${p.name}`, codeBlocks(id), null, 'OK', true);
}

/* ------------------------------------------------------------ row menu */
function openRowMenu(id, anchor) {
  const p = S.profiles.find(x => x.id === id);
  const m = $('#rowMenu');
  const item = (act, icon, label, dis) => `<button data-ract="${act}" ${dis ? 'disabled' : ''}>${ICON[icon]}${label}</button>`;
  m.innerHTML = [
    item('edit', 'settings', 'Settings'), item('folder', 'folder', 'Folders'), item('clone', 'clone', 'Clone'),
    '<div class="sep"></div>',
    item('run', 'play', p.state === 'running' ? 'Stop' : 'Run'), item('cookies', 'cookie', 'Cookies'),
    item('random', 'dice', 'Random fingerprint', p.state === 'running'),
    item('refresh', 'refresh', 'Refresh fingerprint', p.state === 'running'),
    item('browser', 'update', 'Update browser'),
    '<div class="sep"></div>',
    item('runlink', 'link', 'Copy “Run” link'), item('copyid', 'id', 'Copy ID'), item('pin', 'pin', p.pinned ? 'Unpin' : 'Pin'),
    '<div class="sep"></div>',
    `<button data-ract="delete" class="danger">${ICON.trash}Delete</button>`, item('automation', 'auto', 'Automation'),
  ].join('');
  m.dataset.id = id; m.hidden = false;
  const r = anchor.getBoundingClientRect();
  m.style.left = Math.min(r.left, innerWidth - 220) + 'px';
  m.style.top = Math.max(8, Math.min(r.bottom + 4, innerHeight - m.offsetHeight - 8)) + 'px';
}

async function rowAction(act, id) {
  const p = S.profiles.find(x => x.id === id);
  if (act === 'edit') openDrawer('edit', p);
  if (act === 'folder') moveToFolder([id]);
  if (act === 'clone') { const c = await api(`/api/profiles/${id}/clone`, { method: 'POST' }); await load(); toast(`Cloned as ${c.name}`); }
  if (act === 'run') p.state === 'running' ? stopProfile(id) : runProfile(id);
  if (act === 'cookies') cookiesModal(id);
  if (act === 'random') { await api(`/api/profiles/${id}/randomize`, { method: 'POST' }); await load(); toast('New random device generated'); }
  if (act === 'refresh') { await api(`/api/profiles/${id}/refresh`, { method: 'POST' }); await load(); toast('New fingerprint generated'); }
  if (act === 'browser') { if (!S.browsers) S.browsers = await api('/api/browsers'); browserModal(id); }
  if (act === 'runlink') { await copy(`${location.origin}/run/${id}`); toast('Run link copied'); }
  if (act === 'copyid') { await copy(id); toast('Profile ID copied'); }
  if (act === 'pin') { await patchProfile(id, { pinned: !p.pinned }); renderAll(); }
  if (act === 'delete') deleteProfiles([id]);
  if (act === 'automation') automationModal(id);
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) { const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); }
}

/* ------------------------------------------------------ inline editing */
function inlineEdit(td, field, id) {
  const p = S.profiles.find(x => x.id === id);
  const key = field === 'name' ? 'name' : 'notes';
  const input = document.createElement('input');
  input.className = field === 'name' ? 'name-input' : 'note-input';
  input.value = p[key] || '';
  input.placeholder = field === 'name' ? 'Profile name' : 'Add note';
  td.innerHTML = ''; td.appendChild(input); input.focus(); input.select();
  let done = false;
  const finish = async save => {
    if (done) return; done = true;
    const v = input.value.trim();
    if (save && v !== (p[key] || '') && !(key === 'name' && !v)) {
      try { await patchProfile(id, { [key]: v }); } catch (e) { toast(e.message, true); }
    }
    renderAll();
  };
  input.onblur = () => finish(true);
  input.onkeydown = e => { if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); };
}

/* ----------------------------------------------------- proxy popover */
// target: { type: 'profile', id } | { type: 'bulk', ids } | { type: 'drawer' }
function openProxyPop(anchor, target) {
  const pop = $('#proxyPop');
  const draw = q => {
    const list = S.proxies.filter(x => !q || `${x.host}:${x.port} ${x.username} ${x.check?.country || ''}`.toLowerCase().includes(q.toLowerCase()));
    $('.pop-list', pop).innerHTML = `
      <button class="pop-item" data-px=""><span class="dot"></span>No proxy</button>
      <div class="pop-h">Saved proxies (${S.proxies.length})</div>
      ${list.map(x => `<button class="pop-item" data-px="${x.id}">
        <span class="dot ${x.check?.ok ? 'ok' : x.check?.ok === false ? 'bad' : ''}"></span>
        ${FLAGS(x.check?.countryCode)} ${esc(x.host)}:${esc(x.port)} <span class="muted">${esc(x.type)}</span>
        <span class="cnt">${x.profiles || ''}</span></button>`).join('') || '<div class="pop-h">No saved proxies yet</div>'}`;
  };
  pop.innerHTML = `<input class="pop-search" placeholder="Search, or paste host:port:user:pass and press Enter">
    <div class="pop-list"></div>
    <div class="pop-foot"><button class="chip" data-pf="paste">📋 Paste proxies</button><button class="chip" data-pf="manage">Manage proxies</button></div>`;
  draw('');
  pop.hidden = false;
  const r = anchor.getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(r.left, innerWidth - 350)) + 'px';
  pop.style.top = (r.bottom + 360 > innerHeight ? Math.max(8, r.top - 364) : r.bottom + 4) + 'px';
  const search = $('.pop-search', pop);
  search.focus();
  search.oninput = () => draw(search.value);
  search.onkeydown = async e => {
    if (e.key === 'Enter' && search.value.trim()) { const v = search.value; closePop(); await assignProxyText(v, target); }
    if (e.key === 'Escape') closePop();
  };
  pop.onclick = async e => {
    e.stopPropagation();
    const it = e.target.closest('[data-px]');
    if (it) {
      const x = S.proxies.find(y => y.id === it.dataset.px);
      const px = x ? { type: x.type, host: x.host, port: x.port, username: x.username, password: x.password } : { type: 'none', host: '', port: '', username: '', password: '' };
      closePop(); await assignProxies([px], target); return;
    }
    const pf = e.target.closest('[data-pf]')?.dataset.pf;
    if (pf === 'paste') {
      let text = '';
      try { text = await navigator.clipboard.readText(); } catch (err) { /* permission denied */ }
      closePop();
      if (text.trim()) await assignProxyText(text, target);
      else pasteModal(target);
    }
    if (pf === 'manage') { closePop(); closeDrawer(); go('proxies'); }
  };
}
function closePop() { $('#proxyPop').hidden = true; }

function pasteModal(target) {
  const n = target.type === 'bulk' ? target.ids.length : 1;
  modal('Paste proxies', `<label>One proxy per line (Webshare: <code>http://user:pass@host:port/</code> or <code>host:port:user:pass</code>)</label>
    <textarea id="pasteTxt"></textarea>
    <div class="sub">${n > 1 ? `Proxies are assigned in order to the ${n} selected profiles (cycling if fewer).` : 'The first proxy is assigned; all are saved to the Proxies list.'}</div>`,
  async () => { await assignProxyText($('#pasteTxt').value, target); }, 'Apply');
}

async function assignProxyText(text, target) {
  const r = await api('/api/proxies/import', { body: { text } });
  const parsed = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try { parsed.push(await api('/api/proxies/parse', { body: { text: line } })); } catch (e) { /* reported below */ }
  }
  if (!parsed.length) { toast('No valid proxy found in the text', true); return; }
  if (r.invalid.length) toast(`${r.invalid.length} line(s) not recognised`, true);
  await assignProxies(parsed, target);
  await loadProxies();
}

async function assignProxies(list, target) {
  if (target.type === 'drawer') {
    if (!S.drawer) return;
    Object.assign(S.drawer.p.proxy, list[0]);
    queueSave({ proxy: list[0] }, true); renderDrawer(); return;
  }
  const ids = target.type === 'bulk' ? target.ids : [target.id];
  try {
    await Promise.all(ids.map((id, i) => patchProfile(id, { proxy: list[i % list.length] })));
    toast(ids.length > 1 ? `Proxy set on ${ids.length} profiles` : 'Proxy updated');
  } catch (e) { toast(e.message, true); }
  await load();
}

/* ================================================================ forms */
const DEFAULT_DRAFT = () => ({
  ...JSON.parse(JSON.stringify(S.settings.defaults)),
  name: '', notes: '', folder: S.folder, browser: '', device: '',
  proxy: { type: 'none', host: '', port: '', username: '', password: '' },
});

const seg = (path, opts, val) => `<div class="seg" data-seg="${path}">${opts.map(([v, l]) =>
  `<button type="button" data-v="${v}" class="${v === val ? 'on' : ''}">${l}</button>`).join('')}</div>`;
const row = (label, body, hint = '') => `<div class="frow"><label>${label}</label><div>${body}</div><div class="hint">${hint}</div></div>`;
const section = (title, rows, key) => `<div class="sec-title" data-sec="${key}">${title}</div><div class="card" data-card="${key}">${rows.join('')}</div>`;
const txt = (path, val, ph = '') => `<input type="text" data-path="${path}" value="${esc(val)}" placeholder="${esc(ph)}">`;
// Mirrors core.dock_label
function dockLabel(p) {
  const b = p.dock_badge || { mode: 'auto' };
  if (b.mode === 'off') return '';
  if (b.mode === 'custom') return (b.text || '').trim().slice(0, 4);
  const name = (p.name || '').trim(); const last = name.split(/\s+/).at(-1) || '';
  return last && last.length <= 4 ? last.toUpperCase() : name.slice(0, 2).toUpperCase();
}
const tog = (path, on) => `<label class="switch"><input type="checkbox" data-path="${path}" ${on ? 'checked' : ''}><span></span></label>`;

// mode: 'create' | 'edit' | 'template'
function renderFields(p, mode, extra = {}) {
  const tmpl = mode === 'template';
  const pv = extra.preview || {}; const a = p.applied || {};
  const tzs = (Intl.supportedValuesOf ? Intl.supportedValuesOf('timeZone') : []);
  const ipHint = p.proxy && p.proxy.type !== 'none' ? 'Based on proxy IP' : 'Based on IP';
  const gpus = extra.gpus || (S.meta.gpus[p.os] || []);
  const notHost = p.os !== S.meta.hostOs;
  const html = [];

  const ess = [];
  if (!tmpl) {
    ess.push(row('Name', txt('name', p.name, 'Profile name')));
    ess.push(row('Note', `<textarea data-path="notes" rows="1" placeholder="+ Add note">${esc(p.notes)}</textarea>`));
    ess.push(row('Folder', `<input type="text" data-path="folder" list="dlFolders" value="${esc(p.folder)}" placeholder="+ Add folder">
      <datalist id="dlFolders">${allFolders().map(f => `<option value="${esc(f)}">`).join('')}</datalist>`));
  }
  ess.push(row('OS', seg('os', [['macos', 'macOS'], ['windows', 'Windows'], ['linux', 'Linux']], p.os)
    + (notHost ? `<div class="sub warn">This machine runs ${OS_LABEL[S.meta.hostOs]}. iphey and browserscan still score 100, but pixelscan recognises this computer's audio hardware and won't confirm a ${OS_LABEL[p.os]} identity.</div>` : ''),
    tmpl ? '' : 'Changes fingerprint'));
  if (!tmpl && p.device) ess.push(row('Device', `<span class="device-chip">${ICON.dice.replace('<svg', '<svg width="14" height="14"')} ${esc(p.device)}</span>`, 'Random fingerprint'));
  ess.push(row('Start URL', txt('start_url', p.start_url, 'https://… (optional)')));
  ess.push(row('Languages', seg('language.mode', [['ip', 'Based on IP'], ['custom', 'Custom']], p.language.mode)
    + (p.language.mode === 'custom' ? `<div style="margin-top:4px">${txt('language.value', p.language.value, 'vi-VN,vi,en-US,en')}</div>` : ''),
    p.language.mode === 'ip' ? ipHint : ''));
  ess.push(row('Timezone', seg('timezone.mode', [['ip', 'Based on IP'], ['custom', 'Custom']], p.timezone.mode)
    + (p.timezone.mode === 'custom' ? `<div style="margin-top:4px"><select data-path="timezone.value"><option value="">Choose…</option>
      ${tzs.map(t => `<option ${t === p.timezone.value ? 'selected' : ''}>${t}</option>`).join('')}</select></div>` : ''),
    p.timezone.mode === 'ip' ? ipHint : ''));
  ess.push(row('Geolocation', seg('geolocation.mode', [['ip', 'Based on IP'], ['custom', 'Custom'], ['block', 'Block']], p.geolocation.mode)
    + (p.geolocation.mode === 'custom' ? `<div class="inline" style="margin-top:4px">${txt('geolocation.lat', p.geolocation.lat, 'latitude')}${txt('geolocation.lon', p.geolocation.lon, 'longitude')}${txt('geolocation.accuracy', p.geolocation.accuracy, 'accuracy m')}</div>` : '')
    + (p.geolocation.mode !== 'block' ? `<div style="margin-top:6px">${seg('geolocation.permission', [['prompt', 'Prompt'], ['allow', 'Always allow']], p.geolocation.permission || 'prompt')}</div>` : ''),
    p.geolocation.mode === 'ip' ? ipHint : ''));
  if (mode === 'edit') {
    const c = p.cookies || {};
    ess.push(row('Cookies', c.total ? `<div class="cookie-tags">${c.domains.map(([d, n]) => `<span>${esc(d)}<b>${n}</b></span>`).join('')}</div>` : '<span class="muted">No cookies yet</span>',
      '<button type="button" class="linkbtn" data-dact="cookies">Import / export</button>'));
    ess.push(row('New fingerprint', `<button type="button" class="linkbtn" data-dact="refresh">${ICON.refresh.replace('<svg', '<svg width="16" height="16"')} Refresh fingerprint</button>`));
    ess.push(row('Default settings', '<button type="button" class="linkbtn" data-dact="reset">Reset to defaults</button>', 'Keeps name, proxy, OS and device'));
  }
  html.push(section(tmpl ? 'Identity &amp; location' : 'Profile essentials', ess, 'ess'));

  if (!tmpl) {
    const px = p.proxy;
    html.push(section('Proxy &amp; Location', [
      row('Proxy', `
        <div class="inline">
          <select data-path="proxy.type" style="max-width:110px">
            ${['none', 'http', 'socks5'].map(t => `<option value="${t}" ${px.type === t ? 'selected' : ''}>${t === 'none' ? 'No proxy' : t.toUpperCase()}</option>`).join('')}
          </select>
          ${px.type !== 'none' ? `${txt('proxy.host', px.host, 'host')}${txt('proxy.port', px.port, 'port')}` : ''}
          <button type="button" class="chip" data-dact="pickproxy" style="flex:none">Saved…</button>
        </div>
        ${px.type !== 'none' ? `<div class="inline" style="margin-top:4px">${txt('proxy.username', px.username, 'login')}${txt('proxy.password', px.password, 'password')}</div>` : ''}
        <div class="inline" style="margin-top:4px">${txt('_paste', '', 'Paste http://user:pass@host:port or host:port:user:pass')}
          ${px.type !== 'none' ? '<button type="button" class="chip" id="btnCheckProxy" style="flex:none">Check proxy</button>' : ''}</div>
        <div class="sub" id="proxyResult"></div>`),
      row('WebRTC', seg('webrtc.mode', [['ip', 'Based on IP'], ['real', 'Real'], ['disabled', 'Disabled']], p.webrtc.mode),
        p.webrtc.mode === 'ip' ? 'Public IP = proxy IP' : ''),
    ], 'proxy'));
  } else {
    html.push(section('WebRTC', [row('WebRTC', seg('webrtc.mode', [['ip', 'Based on IP'], ['real', 'Real'], ['disabled', 'Disabled']], p.webrtc.mode))], 'proxy'));
  }

  const md = p.media_devices; const wi = p.webgl_info;
  html.push(section('Hardware', [
    row('Resolution', `<select data-path="resolution">
      <option value="auto" ${p.resolution === 'auto' ? 'selected' : ''}>Auto (real-world for ${OS_LABEL[p.os]})</option>
      ${S.meta.resolutions.map(r => `<option ${r === p.resolution ? 'selected' : ''}>${r}</option>`).join('')}</select>
      ${a.screen ? `<div class="sub">Last launch: ${esc(a.screen)}</div>` : ''}`, tmpl ? '' : 'Changes fingerprint'),
    row('Device memory', '<span class="muted">Not exposed</span>', 'Firefox has no navigator.deviceMemory'),
    row('Number of threads', `<span>${pv.threads ? pv.threads + ' threads' : (navigator.hardwareConcurrency ? navigator.hardwareConcurrency + ' threads' : '—')}</span>`, 'Matches this CPU'),
    row('Media Devices', seg('media_devices.mode', [['masked', 'Masked'], ['real', 'Real']], md.mode)
      + (md.mode === 'masked' ? `<div class="inline mini" style="margin-top:6px">
        <label class="sub">Cam.</label><input type="number" min="0" max="4" data-path="media_devices.webcams" value="${md.webcams}">
        <label class="sub">Mic.</label><input type="number" min="0" max="4" data-path="media_devices.micros" value="${md.micros}">
        <label class="sub">Sp.</label><input type="number" min="0" max="4" data-path="media_devices.speakers" value="${md.speakers}"></div>` : ''),
      md.mode === 'masked' ? `Cam. ${md.webcams} / Mic. ${md.micros} / Sp. ${md.speakers}` : ''),
    row('Canvas', seg('canvas', [['noise', 'Noise'], ['real', 'Real']], p.canvas), p.canvas === 'noise' ? 'Engine-level noise' : ''),
    row('WebGL Image', seg('webgl_image', [['noise', 'Noise'], ['real', 'Off']], p.webgl_image),
      p.webgl_image === 'noise' ? '<span class="warn">pixelscan detects WebGL read-back noise</span>' : 'Recommended'),
    row('WebGL info', seg('webgl_info.mode', [['masked', 'Masked'], ['real', 'Real'], ['off', 'Off']], wi.mode)
      + (wi.mode === 'masked' && !tmpl ? `<div style="margin-top:4px"><select data-path="webgl_info.pair">
        ${gpus.map(([v, r]) => `<option value="${esc(v)}|${esc(r)}" ${r === wi.renderer ? 'selected' : ''}>${esc(r)}</option>`).join('')}
        </select></div>${gpus.length === 1 ? '<div class="sub">Every Apple Silicon Mac reports this in Firefox; anything else would contradict the hardware.</div>' : ''}` : ''),
      wi.mode === 'masked' && !tmpl ? esc(wi.vendor) : ''),
    row('Audio Context', seg('audio', [['noise', 'Noise'], ['real', 'Real']], p.audio), p.audio === 'noise' ? 'Masked with noise' : ''),
  ], 'hw'));

  const ext = [
    row('Allow to install extensions', tog('allow_extensions', p.allow_extensions)),
    row('uBlock Origin', tog('ublock', p.ublock), 'Built-in ad blocker'),
    row('Block images', tog('block_images', p.block_images)),
  ];
  if (S.meta.hostOs === 'macos') {
    const db = p.dock_badge || { mode: 'auto', text: '' }; const lbl = dockLabel(p);
    ext.push(row('Dock badge', seg('dock_badge.mode', tmpl ? [['auto', 'Auto'], ['off', 'Off']] : [['auto', 'Auto'], ['custom', 'Custom'], ['off', 'Off']], db.mode)
      + (db.mode === 'custom' && !tmpl ? `<div style="margin-top:4px"><input type="text" maxlength="4" data-path="dock_badge.text" value="${esc(db.text)}" placeholder="e.g. 3"></div>` : ''),
      tmpl ? (db.mode === 'auto' ? 'Number from the profile name' : '') : lbl ? `Badge <b>${esc(lbl)}</b> on the Dock icon (next launch)` : 'No badge'));
  }
  if (!tmpl) {
    const inst = (S.browsers && S.browsers.installed) || [];
    ext.push(row('Browser core', `<select data-path="browser"><option value="">App default${S.settings?.browser ? ` (${esc(S.settings.browser)})` : ''}</option>
      ${inst.map(v => `<option value="${esc(v.version)}" ${p.browser === v.version ? 'selected' : ''}>${esc(v.version)}${v.prerelease ? ' (prerelease)' : ''}</option>`).join('')}</select>`, 'Camoufox build'));
  }
  html.push(section(tmpl ? 'Extensions' : 'Extensions &amp; browser', ext, 'ext'));

  if (mode === 'edit') {
    html.push(section('Fingerprint summary', [`<div class="frow" style="display:block"><div class="summary">
      ${pv.error ? `<span class="bad">${esc(pv.error)}</span>` : !extra.preview ? 'Loading…' : `
      <b>User agent:</b> ${esc(pv.userAgent)}<br>
      <b>Platform:</b> ${esc(pv.platform)} · <b>Screen:</b> ${esc(pv.screen)} · <b>Threads:</b> ${esc(pv.threads)}<br>
      <b>WebGL:</b> ${esc(pv.webglVendor)} / ${esc(pv.webglRenderer)}<br>
      <b>Fonts:</b> ${pv.fonts} · <b>Voices:</b> ${pv.voices} · <b>Media:</b> cam ${pv.webcams ?? '-'} / mic ${pv.micros ?? '-'} / sp ${pv.speakers ?? '-'} · <b>Audio seed:</b> ${pv.audioSeed}`}
      ${a.at ? `<br><br><b>Last launch</b> (${fmtDate(a.at)}): ${esc(a.ip || '')} ${FLAGS(a.country)} · ${esc(a.timezone)} · ${esc(a.languages)}` : ''}
      </div></div>`], 'sum'));
  }
  return html.join('');
}

function setPath(obj, path, val) {
  const ks = path.split('.'); let o = obj;
  for (const k of ks.slice(0, -1)) o = o[k];
  o[ks.at(-1)] = val;
}
const changeFor = (path, val) => {
  const ks = path.split('.');
  return ks.length === 1 ? { [ks[0]]: val } : { [ks[0]]: { [ks[1]]: val } };
};
const formTarget = el => el.closest('[data-form]')?.dataset.form;
const formObj = form => form === 'drawer' ? S.drawer?.p : form === 'settings' ? S.settings?.defaults : null;
function rerenderForm(form) { form === 'drawer' ? renderDrawer() : renderSettingsTemplate(); }

/* --------------------------------------------------------------- drawer */
async function openDrawer(mode, p) {
  if (!S.browsers) api('/api/browsers').then(b => { S.browsers = b; if (S.drawer) renderDrawer(); }).catch(() => {});
  S.drawer = { mode, p: JSON.parse(JSON.stringify(p || DEFAULT_DRAFT())), gpus: null, preview: null };
  $('#drawerTitle').textContent = mode === 'create' ? 'Create profile' : S.drawer.p.name;
  $('#btnCreate').hidden = mode !== 'create';
  $('#savedHint').textContent = '';
  $('#drawer').hidden = false; $('#scrim').hidden = false;
  renderDrawer();
  if (mode === 'edit') loadDrawerExtras();
}
function closeDrawer() { $('#drawer').hidden = true; $('#scrim').hidden = true; S.drawer = null; }
async function loadDrawerExtras() {
  const d = S.drawer; if (!d || d.mode !== 'edit') return;
  const id = d.p.id;
  const [gpus, preview] = await Promise.all([
    api(`/api/profiles/${id}/gpus`).catch(() => null),
    api(`/api/profiles/${id}/preview`).catch(e => ({ error: e.message })),
  ]);
  if (S.drawer && S.drawer.p.id === id) { S.drawer.gpus = gpus; S.drawer.preview = preview; renderDrawer(); }
}
function renderDrawer() {
  const d = S.drawer; if (!d) return;
  const body = $('#drawerBody'); const top = body.scrollTop;
  const collapsed = $$('.sec-title.collapsed', body).map(e => e.dataset.sec);
  body.innerHTML = renderFields(d.p, d.mode, d);
  collapsed.forEach(k => { $(`[data-sec="${k}"]`, body)?.classList.add('collapsed'); $(`[data-card="${k}"]`, body)?.classList.add('collapsed'); });
  body.scrollTop = top;
}

let saveTimer = null; let pending = {};
function queueSave(change, immediate) {
  const d = S.drawer; if (!d || d.mode !== 'edit') return;
  for (const [k, v] of Object.entries(change)) {
    pending[k] = (typeof v === 'object' && v && !Array.isArray(v)) ? { ...(pending[k] || {}), ...v } : v;
  }
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, immediate ? 0 : 500);
}
async function flushSave() {
  const d = S.drawer; if (!d) return;
  const body = pending; pending = {};
  if (!Object.keys(body).length) return;
  const refetch = ['os', 'resolution', 'webgl_info', 'media_devices', 'audio', 'browser'].some(k => k in body);
  try {
    const p = await patchProfile(d.p.id, body);
    if (S.drawer && S.drawer.p.id === p.id) {
      S.drawer.p = p;
      $('#drawerTitle').textContent = p.name;
      $('#savedHint').textContent = 'Saved';
      setTimeout(() => { $('#savedHint').textContent = ''; }, 1500);
      if (refetch) { S.drawer.preview = null; S.drawer.gpus = null; renderDrawer(); loadDrawerExtras(); }
    }
    renderAll();
  } catch (e) { toast(e.message, true); }
}

let settingsTimer = null; let settingsPending = {};
function queueSettingsSave(change) {
  for (const [k, v] of Object.entries(change)) {
    settingsPending[k] = (typeof v === 'object' && v && !Array.isArray(v)) ? { ...(settingsPending[k] || {}), ...v } : v;
  }
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(async () => {
    const body = settingsPending; settingsPending = {};
    try { S.settings = await api('/api/settings', { method: 'PATCH', body: { defaults: body } }); toast('Default settings saved'); }
    catch (e) { toast(e.message, true); }
  }, 600);
}
function onFormChange(form, change, structural) {
  if (form === 'drawer') queueSave(change, structural);
  else queueSettingsSave(change);
  if (structural) rerenderForm(form);
}

async function onFormInput(e) {
  const form = formTarget(e.target); const obj = formObj(form); if (!obj) return;
  const el = e.target; const path = el.dataset.path; if (!path) return;
  if (path === '_paste') {
    if (!el.value.trim()) return;
    try {
      const px = await api('/api/proxies/parse', { body: { text: el.value } });
      Object.assign(obj.proxy, px);
      onFormChange(form, { proxy: px }, true);
      api('/api/proxies/import', { body: { text: el.value } }).then(loadProxies);
    } catch (err) { /* keep typing */ }
    return;
  }
  const val = el.type === 'checkbox' ? el.checked : el.type === 'number' ? +el.value : el.value;
  if (path === 'webgl_info.pair') {
    const [vendor, renderer] = el.value.split('|');
    Object.assign(obj.webgl_info, { vendor, renderer });
    onFormChange(form, { webgl_info: { vendor, renderer } }, false);
    return;
  }
  setPath(obj, path, val);
  onFormChange(form, changeFor(path, val), el.tagName === 'SELECT' || el.type === 'checkbox');
}

async function onFormClick(e) {
  const form = formTarget(e.target); const obj = formObj(form); if (!obj) return;
  const sec = e.target.closest('.sec-title');
  if (sec) { sec.classList.toggle('collapsed'); sec.nextElementSibling.classList.toggle('collapsed'); return; }
  const sb = e.target.closest('[data-seg] button');
  if (sb) {
    const path = sb.closest('[data-seg]').dataset.seg; const v = sb.dataset.v;
    setPath(obj, path, v);
    if (path === 'webgl_info.mode' && v === 'masked' && !obj.webgl_info.renderer && form === 'drawer') {
      const g = (S.drawer.gpus || S.meta.gpus[obj.os])[0];
      if (g) Object.assign(obj.webgl_info, { vendor: g[0], renderer: g[1] });
    }
    if (path === 'os') {
      const gs = S.meta.gpus[v]; const g = gs[Math.floor(Math.random() * gs.length)];
      obj.webgl_info = { ...obj.webgl_info, vendor: g[0], renderer: g[1] };
      if (form === 'drawer') S.drawer.gpus = null;
      onFormChange(form, { os: v, webgl_info: form === 'drawer' ? obj.webgl_info : { mode: obj.webgl_info.mode } }, true);
    } else if (path === 'webgl_info.mode') {
      onFormChange(form, { webgl_info: form === 'drawer' ? obj.webgl_info : { mode: v } }, true);
    } else onFormChange(form, changeFor(path, v), true);
    return;
  }
  const dact = e.target.closest('[data-dact]')?.dataset.dact;
  if (dact === 'refresh') {
    try {
      const p = await api(`/api/profiles/${obj.id}/refresh`, { method: 'POST' });
      S.drawer.p = p; S.drawer.preview = null; S.drawer.gpus = null; renderDrawer(); loadDrawerExtras();
      toast('New fingerprint generated'); load();
    } catch (err) { toast(err.message, true); }
  }
  if (dact === 'reset') {
    if (!confirm('Reset this profile\'s masks, location and extension settings to the defaults from Settings?')) return;
    try {
      await flushSave();
      const p = await api(`/api/profiles/${obj.id}/reset`, { method: 'POST' });
      S.drawer.p = p; S.drawer.preview = null; S.drawer.gpus = null; renderDrawer(); loadDrawerExtras();
      toast('Profile reset to default settings'); load();
    } catch (err) { toast(err.message, true); }
  }
  if (dact === 'cookies') cookiesModal(obj.id);
  if (dact === 'pickproxy') { e.stopPropagation(); openProxyPop(e.target, { type: 'drawer' }); }
  if (e.target.id === 'btnCheckProxy') {
    const out = $('#proxyResult'); out.textContent = 'Checking…';
    try {
      const r = await api('/api/proxy/check', { body: obj.proxy });
      out.innerHTML = r.ok
        ? `<span class="ok">✓ ${FLAGS(r.countryCode)} ${esc(r.ip)} · ${esc(r.city || '')}, ${esc(r.country)} · ${esc(r.timezone)} · ${r.ms} ms</span>`
        : `<span class="bad">✗ ${esc(r.error)}</span>`;
    } catch (err) { out.innerHTML = `<span class="bad">✗ ${esc(err.message)}</span>`; }
  }
}

async function randomFingerprint() {
  const d = S.drawer; if (!d) return;
  try {
    if (d.mode === 'create') {
      const dev = await api(`/api/random-device?os=${d.p.os}`);
      Object.assign(d.p, { device: dev.device, resolution: dev.resolution });
      d.p.media_devices = { ...d.p.media_devices, ...dev.media_devices };
      if (d.p.webgl_info.mode === 'masked') d.p.webgl_info = { ...d.p.webgl_info, ...dev.webgl_info };
      renderDrawer();
    } else {
      await flushSave();
      const p = await api(`/api/profiles/${d.p.id}/randomize`, { method: 'POST' });
      S.drawer.p = p; S.drawer.preview = null; S.drawer.gpus = null; renderDrawer(); loadDrawerExtras(); load();
    }
    toast(`Random device: ${S.drawer.p.device}`);
  } catch (e) { toast(e.message, true); }
}

/* =============================================================== proxies */
function renderProxies() {
  const q = S.pxq.toLowerCase();
  const list = S.proxies.filter(x => !q || `${x.host}:${x.port} ${x.username} ${x.check?.country || ''} ${x.check?.ip || ''}`.toLowerCase().includes(q));
  $('#pxEmpty').hidden = S.proxies.length > 0;
  $('#pxRows').innerHTML = list.map(x => {
    const c = x.check || {};
    const status = c.ok ? `<span class="ok">✓ ${c.ms} ms</span>` : c.ok === false ? `<span class="bad" title="${esc(c.error)}">✗ failed</span>` : '<span class="muted">not checked</span>';
    return `<tr data-xid="${x.id}" class="${S.pxSelected.has(x.id) ? 'selected' : ''}">
      <td class="c-chk"><input type="checkbox" class="pxchk" ${S.pxSelected.has(x.id) ? 'checked' : ''}></td>
      <td title="${esc(x.type)}://${esc(x.host)}:${esc(x.port)}"><span class="tag">${esc(x.type.toUpperCase())}</span> ${esc(x.host)}:${esc(x.port)}</td>
      <td class="muted">${esc(x.username)}</td>
      <td>${c.ok ? `${FLAGS(c.countryCode)} ${esc(c.ip)} <span class="muted">${esc(c.city || '')}${c.city ? ', ' : ''}${esc(c.country || '')}</span>` : ''}</td>
      <td>${status}</td>
      <td class="muted">${x.profiles || 0}</td>
      <td><div class="row-actions"><button class="chip" data-xact="check">Check</button><button class="chip" data-xact="copy">Copy</button><button class="chip danger" data-xact="del">✕</button></div></td>
    </tr>`;
  }).join('');
  $('#pxAll').checked = list.length > 0 && list.every(x => S.pxSelected.has(x.id));
  $('#pxBulk').hidden = S.pxSelected.size === 0;
  $('#pxBulkCount').textContent = `${S.pxSelected.size} selected`;
}

function addProxiesModal() {
  modal('Add proxies', `
    <label>One proxy per line. Webshare format works as-is:</label>
    <textarea id="pxText" style="min-height:200px" placeholder="http://user:pass@203.0.113.10:8080/
203.0.113.11:8080:user:pass
socks5://user:pass@1.2.3.4:1080"></textarea>
    <label>Type for lines without a scheme</label>
    <select id="pxType"><option value="http">HTTP</option><option value="socks5">SOCKS5</option></select>
    <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="pxCheckNow" checked style="width:auto"> Check them now</label>`,
  async () => {
    const r = await api('/api/proxies/import', { body: { text: $('#pxText').value, type: $('#pxType').value } });
    toast(`Added ${r.added.length} proxies${r.invalid.length ? `, ${r.invalid.length} invalid line(s)` : ''}`, r.invalid.length > 0 && !r.added.length);
    const checkNow = $('#pxCheckNow').checked;
    await loadProxies();
    if (checkNow && r.added.length) checkProxies(r.added.map(x => x.id));
  }, 'Add', true);
}

async function checkProxies(ids) {
  if (!ids.length) return;
  toast(`Checking ${ids.length} proxies…`);
  try {
    const res = await api('/api/proxies/check', { body: ids });
    const ok = Object.values(res).filter(r => r.ok).length;
    toast(`${ok}/${ids.length} proxies working`, ok < ids.length);
  } catch (e) { toast(e.message, true); }
  await loadProxies();
}

/* ============================================================== settings */
async function loadSettingsPage() {
  [S.settings, S.browsers] = await Promise.all([api('/api/settings'), api('/api/browsers')]);
  renderSettings();
}
function renderSettingsTemplate() {
  const el = $('#tmplForm'); if (!el) return;
  el.innerHTML = renderFields(S.settings.defaults, 'template');
}
function renderSettings() {
  const b = S.browsers; const def = S.settings.browser;
  const cmp = (x, y) => x.localeCompare(y, undefined, { numeric: true });
  const newest = [...b.available].filter(v => v.repo === 'official').sort((x, y) => cmp(y.version, x.version));
  const newestStable = newest.find(v => !v.prerelease);
  const instTop = [...b.installed].sort((x, y) => cmp(y.version, x.version))[0];
  const showPre = store.get('fl.showPre', false);
  const avail = newest.filter(v => !v.installed && (showPre || !v.prerelease)).slice(0, 14);
  const jobs = Object.entries(b.jobs || {});
  $('#settingsBody').innerHTML = `
    <div style="display:flex;align-items:center;gap:12px"><h2 style="flex:1">Default settings for new profiles</h2>
      <button class="chip" id="btnResetDefaults">Reset to recommended</button></div>
    <p>Used by Add profile, Quick profile, bulk create and import. Existing profiles keep their own settings (profile › Reset to default settings applies these).</p>
    <p class="sub">Recommended: OS of this computer · language, timezone, geolocation (prompt) and WebRTC from the proxy IP · Canvas noise · WebGL image off · WebGL info, audio and media devices masked · no uBlock.</p>
    <div class="form" data-form="settings" id="tmplForm"></div>

    <h2>Browser core (Camoufox)</h2>
    <p>Pick which Camoufox build new launches use, install a newer one, or roll back to an older one. A single profile can also pin its own build (row menu › Update browser).</p>
    ${newestStable && instTop && cmp(newestStable.version, instTop.version) > 0 ? `<p class="warn">A newer stable build is available: <b>${esc(newestStable.version)}</b></p>` : ''}
    <div class="card">
      ${b.installed.map(v => `<div class="ver-row">
        <div><b>${esc(v.version)}</b> <span class="tag ${v.prerelease ? 'amber' : 'green'}">${v.prerelease ? 'prerelease' : 'stable'}</span>
          ${(def ? def === v.version : v.active) ? '<span class="tag green">default</span>' : ''}
          ${v.active ? '<span class="tag">camoufox active</span>' : ''}
          <div class="sub">${esc(v.repo)} · ${esc((v.date || '').slice(0, 10))}</div></div>
        <button class="chip" data-bact="default" data-v="${esc(v.version)}" ${(def ? def === v.version : v.active) ? 'disabled' : ''}>Use as default</button>
        <button class="chip danger" data-bact="remove" data-v="${esc(v.version)}" data-r="${esc(v.repo)}" ${v.active ? 'disabled' : ''}>Remove</button>
      </div>`).join('')}
    </div>
    <div style="display:flex;gap:8px;align-items:center;margin:12px 0 6px">
      <button class="chip" data-bact="sync">Check for updates</button>
      <label class="sub" style="display:flex;gap:6px;align-items:center;margin:0"><input type="checkbox" id="showPre" ${showPre ? 'checked' : ''}> Show prerelease builds</label>
    </div>
    <div class="card">
      ${avail.map(v => `<div class="ver-row">
        <div>${esc(v.version)} <span class="tag ${v.prerelease ? 'amber' : 'green'}">${v.prerelease ? 'prerelease' : 'stable'}</span>
          <div class="sub">${esc((v.date || '').slice(0, 10))}${v.size ? ' · ' + Math.round(v.size / 1048576) + ' MB' : ''}</div></div>
        <span></span>
        <button class="chip" data-bact="install" data-v="${esc(v.version)}" data-r="${esc(v.repo)}">Install</button>
      </div>`).join('') || '<div class="ver-row"><span class="muted">Every listed build is installed.</span></div>'}
    </div>
    ${jobs.length ? `<h2 style="font-size:15px">Jobs</h2><div class="card">${jobs.map(([k, j]) => `<div class="ver-row"><div><b>${esc(k)}</b> <span class="tag ${j.state === 'failed' ? 'amber' : 'green'}">${esc(j.state)}</span></div></div><div class="joblog">${esc(j.log)}</div>`).join('')}</div>` : ''}

    <h2>API</h2>
    <p>Automation endpoints live at <code>${location.origin}/api/v1</code>. Set a token to require <code>Authorization: Bearer &lt;token&gt;</code>.</p>
    <div class="card"><div class="frow"><label>API token</label><div><input type="text" id="apiToken" value="${esc(S.settings.api_token)}" placeholder="empty = no token (localhost only)"></div><div class="hint"><button class="chip" id="btnGenToken">Generate</button></div></div></div>
  `;
  renderSettingsTemplate();
  $('#btnResetDefaults').onclick = async () => {
    if (!confirm('Reset the default settings for new profiles to the recommended values?')) return;
    S.settings = await api('/api/settings/reset', { method: 'POST' }); renderSettings(); toast('Defaults reset to recommended');
  };
  $('#showPre').onchange = e => { store.set('fl.showPre', e.target.checked); renderSettings(); };
  $('#apiToken').onchange = async e => { S.settings = await api('/api/settings', { method: 'PATCH', body: { api_token: e.target.value.trim() } }); toast('API token saved'); };
  $('#btnGenToken').onclick = async () => {
    const t = [...crypto.getRandomValues(new Uint8Array(16))].map(v => v.toString(16).padStart(2, '0')).join('');
    S.settings = await api('/api/settings', { method: 'PATCH', body: { api_token: t } }); renderSettings(); toast('New API token generated');
  };
  if (jobs.some(([, j]) => j.state === 'running')) {
    clearTimeout(S.jobTimer);
    S.jobTimer = setTimeout(async () => { if (S.page === 'settings') { S.browsers = await api('/api/browsers'); renderSettings(); } }, 2500);
  }
}
async function browserAction(btn) {
  const act = btn.dataset.bact; const v = btn.dataset.v;
  try {
    if (act === 'default') { S.settings = await api('/api/browsers/default', { body: { version: v } }); toast(`New launches use ${v}`); }
    if (act === 'remove') {
      if (!confirm(`Remove Camoufox ${v}? Profiles pinned to it fall back to the default.`)) return;
      await api('/api/browsers/remove', { body: { version: v, repo: btn.dataset.r } }); toast(`Removed ${v}`);
    }
    if (act === 'install') { await api('/api/browsers/install', { body: { version: v, repo: btn.dataset.r } }); toast(`Downloading ${v} (≈1.2 GB)…`); }
    if (act === 'sync') { await api('/api/browsers/sync', { method: 'POST' }); toast('Checking repositories…'); }
  } catch (e) { toast(e.message, true); }
  S.browsers = await api('/api/browsers'); renderSettings();
}

/* =================================================================== api */
function codeBlocks(id) {
  const o = location.origin; const pid = id || 'PROFILE_ID';
  const tok = S.settings?.api_token ? `, headers: { Authorization: 'Bearer ${S.settings.api_token}' }` : '';
  const tokC = S.settings?.api_token ? ` -H "Authorization: Bearer ${S.settings.api_token}"` : '';
  const block = (title, code) => `<h2 style="font-size:15px">${title}</h2><div class="code-wrap"><button class="copy">Copy</button><pre class="code">${esc(code)}</pre></div>`;
  return block('Puppeteer (Node.js)', `// npm i puppeteer-core
const puppeteer = require('puppeteer-core');

(async () => {
  // start the profile with automation enabled
  const res = await fetch('${o}/api/v1/profiles/${pid}/start', { method: 'POST'${tok} });
  const { wsUrl } = await res.json();

  // Camoufox is Firefox: connect over WebDriver BiDi
  const browser = await puppeteer.connect({ browserWSEndpoint: wsUrl, protocol: 'webDriverBiDi' });
  const page = (await browser.pages())[0] || await browser.newPage();
  await page.goto('https://iphey.com');
  console.log(await page.title());

  await browser.disconnect();
  await fetch('${o}/api/v1/profiles/${pid}/stop', { method: 'POST'${tok} });
})();`) + block('GoLogin-compatible call', `curl -X POST ${o}/browser/start-profile${tokC} \\
  -H "Content-Type: application/json" -d '{"profileId": "${pid}"}'
# -> {"status":"success","wsUrl":"ws://…/ws/${pid}","port":…}

curl -X POST ${o}/browser/stop-profile${tokC} \\
  -H "Content-Type: application/json" -d '{"profileId": "${pid}"}'`) + block('Python (start / stop / list)', `import requests
API = "${o}/api/v1"${S.settings?.api_token ? `\nH = {"Authorization": "Bearer ${S.settings.api_token}"}` : '\nH = {}'}

profiles = requests.get(f"{API}/profiles", headers=H).json()
info = requests.post(f"{API}/profiles/${pid}/start", headers=H).json()
print(info["wsUrl"], info["port"])        # drive it with any WebDriver BiDi client
requests.post(f"{API}/profiles/${pid}/stop", headers=H)`);
}

function renderApi() {
  const eps = [
    ['GET', '/api/v1/profiles', 'List profiles (state, port, proxy, fingerprint settings). Query: folder, q'],
    ['GET', '/api/v1/profiles/{id}', 'One profile, including its automation port while running'],
    ['POST', '/api/v1/profiles', 'Create: {"name", "os", "proxy": "http://u:p@host:port", "folder", …}'],
    ['PATCH', '/api/v1/profiles/{id}', 'Update any field (proxy may be a string in Webshare format)'],
    ['DELETE', '/api/v1/profiles/{id}', 'Delete a profile and its data'],
    ['POST', '/api/v1/profiles/{id}/start', 'Start with automation. Query: headless=true. Returns {wsUrl, wsEndpoint, port}'],
    ['POST', '/api/v1/profiles/{id}/stop', 'Stop the profile (cookies are saved)'],
    ['GET', '/api/v1/running', 'Running profiles and their endpoints'],
    ['POST', '/api/v1/profiles/{id}/randomize', 'New realistic random device + fingerprint'],
    ['POST', '/api/v1/profiles/{id}/cookies', 'Queue cookies (JSON array) for the next start'],
    ['POST', '/api/v1/profiles/import', '{"text": "name|proxy|notes|folder|os|start_url\\n…"}'],
    ['GET', '/api/v1/proxies', 'Saved proxies with check results'],
    ['POST', '/api/v1/proxies/import', '{"text": "one proxy per line"}'],
    ['POST', '/browser/start-profile', 'GoLogin-compatible: {"profileId"} → {"status", "wsUrl"}'],
    ['POST', '/browser/stop-profile', 'GoLogin-compatible stop'],
  ];
  $('#apiBody').innerHTML = `
    <h2>API &amp; Automation</h2>
    <p>Local REST API in the style of GoLogin's. Starting a profile through the API opens a WebDriver BiDi endpoint (Firefox's automation protocol) that Puppeteer, Selenium 4 and other BiDi clients can drive. <code>navigator.webdriver</code> stays <code>false</code>. Profiles started with the Run button don't open that port.</p>
    <div class="card">${eps.map(([m, p, d]) => `<div class="ep"><span class="m">${m}</span><code>${esc(p)}</code><span class="d">${esc(d)}</span></div>`).join('')}</div>
    ${codeBlocks()}
    <p class="sub" style="margin-top:14px">Playwright's <code>connect()</code> speaks its own Firefox protocol and can't attach to a running profile; use Puppeteer or another WebDriver BiDi client.</p>`;
}

/* ================================================================ events */
function bind() {
  const app = $('#app');
  const setCollapsed = c => { app.classList.toggle('collapsed', c); store.set('fl.sidebar', c); };
  setCollapsed(store.get('fl.sidebar', false));
  $('#btnSidebar').onclick = () => setCollapsed(!app.classList.contains('collapsed'));

  const addNew = () => openDrawer('create');
  $('#btnAdd').onclick = addNew; $('#btnEmptyAdd').onclick = addNew;
  $('#btnAddDd').onclick = e => { e.stopPropagation(); $('#addMenu').hidden = !$('#addMenu').hidden; };
  $('#addMenu').onclick = async e => {
    const act = e.target.closest('[data-act]')?.dataset.act; $('#addMenu').hidden = true;
    if (act === 'bulk') bulkCreate();
    if (act === 'import') importProfiles();
    if (act === 'quick') { const p = await api('/api/profiles', { body: { folder: S.folder } }); await load(); toast(`Created ${p.name}`); }
  };
  $('#btnTbMore').onclick = e => { e.stopPropagation(); $('#tbMenu').hidden = !$('#tbMenu').hidden; };
  $('#tbMenu').onclick = e => {
    const a = e.target.closest('[data-tb]')?.dataset.tb; $('#tbMenu').hidden = true;
    if (a === 'import') importProfiles(); if (a === 'bulk') bulkCreate(); if (a === 'folder') newFolder();
  };
  $('#btnCols').onclick = columnsModal;
  $('#btnNewFolder').onclick = e => { e.stopPropagation(); newFolder(); };
  $('#search').oninput = e => { S.q = e.target.value; renderAll(); };
  $('#nav').onclick = e => {
    const a = e.target.closest('[data-page]'); if (!a) return;
    if (a.dataset.page === 'profiles') { S.folder = a.dataset.folder || ''; S.selected.clear(); }
    go(a.dataset.page);
  };
  $('#tabs').onclick = e => {
    const t = e.target.closest('[data-tab]'); if (!t) return;
    S.folder = t.dataset.tab; S.selected.clear(); renderAll();
  };
  $('#thead').addEventListener('click', e => {
    const b = e.target.closest('.th-sort');
    if (b) {
      const k = b.dataset.sort;
      S.sort = S.sort && S.sort[0] === k ? (S.sort[1] === 1 ? [k, -1] : null) : [k, 1];
      renderAll();
    }
  });
  $('#thead').addEventListener('change', e => {
    if (e.target.id !== 'chkAll') return;
    visible().forEach(p => e.target.checked ? S.selected.add(p.id) : S.selected.delete(p.id));
    renderAll();
  });

  $('#rows').addEventListener('click', e => {
    const tr = e.target.closest('tr'); if (!tr) return;
    const id = tr.dataset.id;
    if (e.target.classList.contains('chk')) { e.target.checked ? S.selected.add(id) : S.selected.delete(id); renderAll(); return; }
    if (e.target.closest('input')) return;
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'run') return runProfile(id);
    if (act === 'stop') return stopProfile(id);
    if (act === 'edit') return openDrawer('edit', S.profiles.find(p => p.id === id));
    if (act === 'menu') { e.stopPropagation(); return openRowMenu(id, e.target); }
    const pact = e.target.closest('[data-pact]')?.dataset.pact;
    if (pact === 'paste' || pact === 'new') { e.stopPropagation(); return pasteModal({ type: 'profile', id }); }
    const cell = e.target.closest('[data-cell]');
    if (cell?.dataset.cell === 'notes') return inlineEdit(cell, 'notes', id);
    if (cell?.dataset.cell === 'proxy') { e.stopPropagation(); return openProxyPop(cell, { type: 'profile', id }); }
  });
  $('#rows').addEventListener('dblclick', e => {
    const cell = e.target.closest('[data-cell="name"]');
    if (cell) inlineEdit(cell, 'name', cell.closest('tr').dataset.id);
  });
  $('#rowMenu').onclick = async e => {
    const b = e.target.closest('[data-ract]'); if (!b || b.disabled) return;
    $('#rowMenu').hidden = true;
    try { await rowAction(b.dataset.ract, $('#rowMenu').dataset.id); } catch (err) { toast(err.message, true); }
  };
  document.addEventListener('click', e => {
    $('#rowMenu').hidden = true; $('#addMenu').hidden = true; $('#tbMenu').hidden = true;
    if (!e.target.closest('#proxyPop')) closePop();
    const cp = e.target.closest('.code-wrap .copy');
    if (cp) { copy(cp.nextElementSibling.textContent); toast('Copied'); }
  });

  $('#bulkBar').onclick = async e => {
    const act = e.target.dataset.bulk; const ids = [...S.selected];
    if (!act || !ids.length) return;
    if (act === 'run') for (const id of ids) await runProfile(id);
    if (act === 'stop') for (const id of ids) await stopProfile(id);
    if (act === 'delete') deleteProfiles(ids);
    if (act === 'folder') moveToFolder(ids);
    if (act === 'proxy') { e.stopPropagation(); openProxyPop(e.target, { type: 'bulk', ids }); }
    if (act === 'random') {
      await Promise.all(ids.map(id => api(`/api/profiles/${id}/randomize`, { method: 'POST' }).catch(err => toast(err.message, true))));
      await load(); toast(`New random devices for ${ids.length} profiles`);
    }
  };

  // proxies page
  $('#pxSearch').oninput = e => { S.pxq = e.target.value; renderAll(); };
  $('#btnPxAdd').onclick = addProxiesModal; $('#btnPxEmptyAdd').onclick = addProxiesModal;
  $('#btnPxCheckAll').onclick = () => checkProxies(S.proxies.map(x => x.id));
  $('#btnPxCheck').onclick = () => checkProxies([...S.pxSelected]);
  $('#btnPxDelete').onclick = async () => {
    if (!confirm(`Delete ${S.pxSelected.size} proxies from the list? Profiles keep their current proxy.`)) return;
    await api('/api/proxies/delete', { body: [...S.pxSelected] }); S.pxSelected.clear(); loadProxies();
  };
  $('#pxAll').onchange = e => { S.proxies.forEach(x => e.target.checked ? S.pxSelected.add(x.id) : S.pxSelected.delete(x.id)); renderAll(); };
  $('#pxRows').addEventListener('click', async e => {
    const tr = e.target.closest('tr'); if (!tr) return; const xid = tr.dataset.xid;
    if (e.target.classList.contains('pxchk')) { e.target.checked ? S.pxSelected.add(xid) : S.pxSelected.delete(xid); renderAll(); return; }
    const a = e.target.closest('[data-xact]')?.dataset.xact; const x = S.proxies.find(y => y.id === xid);
    if (a === 'check') checkProxies([xid]);
    if (a === 'copy') { await copy(`${x.type}://${x.username ? `${x.username}:${x.password}@` : ''}${x.host}:${x.port}`); toast('Proxy copied'); }
    if (a === 'del') { await api('/api/proxies/delete', { body: [xid] }); loadProxies(); }
  });

  // forms (drawer + settings template)
  for (const root of [$('#drawerBody'), $('#settingsBody')]) {
    root.addEventListener('input', e => { if (e.target.matches('input[type=text], textarea, input[type=number]')) onFormInput(e); });
    root.addEventListener('change', e => {
      if (e.target.matches('select, input[type=checkbox]') && e.target.dataset.path) onFormInput(e);
      if (e.target.matches('input[type=text], textarea') && formTarget(e.target) === 'drawer' && S.drawer?.mode === 'edit') flushSave();
    });
    root.addEventListener('click', e => {
      const bb = e.target.closest('[data-bact]');
      if (bb) { if (!bb.disabled) browserAction(bb); return; }
      onFormClick(e);
    });
  }
  $('#btnRandom').onclick = randomFingerprint;
  $('#btnClose').onclick = async () => { await flushSave(); closeDrawer(); };
  $('#scrim').onclick = async () => { await flushSave(); closeDrawer(); };
  $('#btnCreate').onclick = async () => {
    try {
      const p = await api('/api/profiles', { body: S.drawer.p });
      closeDrawer(); await load(); toast(`Created ${p.name}`);
    } catch (e) { toast(e.message, true); }
  };
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (!$('#proxyPop').hidden) closePop();
      else if (!$('#modal').hidden) $('#modal').hidden = true;
      else if (S.drawer) { flushSave(); closeDrawer(); }
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') { e.preventDefault(); $('#btnSidebar').click(); }
  });
}

(async () => {
  [S.meta, S.settings] = await Promise.all([api('/api/meta'), api('/api/settings')]);
  bind();
  await load();
  const page = (location.hash || '#profiles').slice(1);
  go(['profiles', 'proxies', 'settings', 'api'].includes(page) ? page : 'profiles');
  setInterval(pollStates, 2000);
  firstRun();
})();

/* First launch of the packaged app: no Camoufox build is installed yet */
async function firstRun() {
  const b = await api('/api/browsers').catch(() => null);
  if (!b || b.installed.length || (b.jobs.setup && b.jobs.setup.state === 'done')) return;
  const show = (job) => {
    const failed = job && job.state === 'failed';
    modal('Install the browser core', `
      <p>FoxLogin runs every profile on <b>Camoufox</b>, a hardened Firefox. It is downloaded once
        (about 1.2 GB, plus the GeoIP database) and shared by all profiles.</p>
      ${job ? `<p>${failed ? '<span class="bad">Install failed.</span> Check your connection and try again.' : 'Downloading… you can keep using the app meanwhile.'}</p>
        <div class="joblog">${esc(job.log || 'Starting…')}</div>` : ''}`,
      job && !failed ? null : async () => {
        await api('/api/browsers/setup', { method: 'POST' }).catch(e => toast(e.message, true));
        setTimeout(poll, 500); return false;
      }, failed ? 'Retry' : 'Install now', true);
  };
  const poll = async () => {
    const st = await api('/api/browsers').catch(() => null);
    const job = st && st.jobs.setup;
    if (st && st.installed.length && (!job || job.state === 'done')) {
      $('#modal').hidden = true; toast('Camoufox installed. You can run profiles now.'); return;
    }
    if (!$('#modal').hidden || job?.state === 'failed') show(job);
    if (job && job.state === 'running') setTimeout(poll, 1500);
  };
  show(b.jobs.setup && b.jobs.setup.state !== 'done' ? b.jobs.setup : null);
  if (b.jobs.setup && b.jobs.setup.state === 'running') setTimeout(poll, 1500);
}
