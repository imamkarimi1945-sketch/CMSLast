/* «مرکز فرماندهیِ رهگشا» — رهگشای مدیر + نگهبان، تمام‌صفحه و فقط برای مدیر ارشد
   • تنبل بار می‌شود؛ داده از /hub/api/rgm/* (hub_rgm.py)؛ هر ۹ ثانیه وقتی صفحه باز است تازه می‌شود
   • هیچ innerHTML با داده‌ی کاربر؛ فقط textContent (از h())؛ انیمیشن‌ها فقط transform/opacity */
(function () {
  'use strict';
  var h, ic, hx, tg, toast, LS, api, Sheet, goHome;
  var root, heroEl, navEl, bodyEl;
  var D = null, fetchedAt = 0, view = 'over', shown = false, pollT = 0, tickT = 0, loading = false;
  var F = { journal: 'all', capq: '', inc: 'open' }, JR = { items: [], more: true, busy: false }, PPL = null;
  var NS = 'http://www.w3.org/2000/svg';

  /* ─── ابزارها ─── */
  function fa(n) { return String(n == null ? '' : n).replace(/[0-9]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[+d]; }); }
  function div(cls, kids) { return h.apply(null, ['div', { class: cls }].concat(kids || [])); }
  function sp(t, cls) { return h('span', { class: cls || null, text: t }); }
  function dur(s) {
    s = Math.max(0, Math.round(s)); var d = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    if (d) return fa(d) + ' روز' + (hh ? ' و ' + fa(hh) + ' ساعت' : '');
    if (hh) return fa(hh) + ' ساعت' + (m ? ' و ' + fa(m) + ' دقیقه' : '');
    return fa(m) + ' دقیقه';
  }
  function clock(s) { s = Math.max(0, Math.round(s)); var hh = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; function p(n) { return (n < 10 ? '0' : '') + n; } return fa(p(hh) + ':' + p(m) + ':' + p(x)); }
  function svg(tag, attrs) { var n = document.createElementNS(NS, tag); for (var k in attrs) n.setAttribute(k, attrs[k]); return n; }
  function ring(pct, color, r, w) {
    var C = 2 * Math.PI * r, s = svg('svg', { viewBox: '0 0 ' + (2 * (r + w)) + ' ' + (2 * (r + w)), class: 'ring' });
    s.append(svg('circle', { cx: r + w, cy: r + w, r: r, fill: 'none', stroke: 'rgba(128,128,128,.25)', 'stroke-width': w }));
    var a = svg('circle', { cx: r + w, cy: r + w, r: r, fill: 'none', stroke: color, 'stroke-width': w, 'stroke-linecap': 'round', 'stroke-dasharray': C, 'stroke-dashoffset': C * (1 - Math.max(0, Math.min(100, pct)) / 100) });
    a.style.transition = 'stroke-dashoffset .8s ease'; s.append(a); return s;
  }
  function spark(vals, color) {
    var v = (vals || []).filter(function (x) { return x != null; });
    var s = svg('svg', { viewBox: '0 0 200 60', class: 'rgm-spark', preserveAspectRatio: 'none' });
    if (v.length < 2) return s;
    var mn = Math.min.apply(null, v), mx = Math.max.apply(null, v), rg = Math.max(1, mx - mn), pts = v.map(function (y, i) { return [i * 200 / (v.length - 1), 54 - (y - mn) / rg * 46]; });
    var d = 'M' + pts.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' L');
    s.append(svg('path', { d: d + ' L200 60 L0 60Z', fill: color, opacity: '.14' }), svg('path', { d: d, fill: 'none', stroke: color, 'stroke-width': 2.4, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
    return s;
  }
  function btn(text, cls, fn, icon) { return h('button', { type: 'button', class: 'rgm-b ' + (cls || ''), onclick: function (e) { hx.tap(); fn(e); } }, icon ? ic(icon) : null, text); }
  function sw(on, fn) { var b = h('button', { type: 'button', class: 'rgm-sw' + (on ? ' on' : ''), role: 'switch', 'aria-checked': on ? 'true' : 'false', onclick: function () { hx.sel(); fn(!on); } }); return b; }
  function seg(opts, val, fn) { return h('div', { class: 'rgm-seg' }, opts.map(function (o) { return h('button', { type: 'button', class: val === o[0] ? 'on' : '', onclick: function () { hx.sel(); fn(o[0]); } }, o[1]); })); }
  function card(title, icon, kids, cls, extra) { return div('rgm-card rgm-fade ' + (cls || ''), [title ? h('h4', { class: 'rgm-h' }, icon ? ic(icon) : null, sp(title), h('i', { class: 'sp' }), extra || null) : null].concat(kids)); }
  function li(title, sub, end) { return div('rgm-li', [div('m', [div('t', [title]), sub ? div('s', [sub]) : null]), end || null]); }
  function empty(t) { return div('rgm-empty', [t]); }
  function kpi(label, val, tone, sub) { return h('div', { class: 'rgm-k ' + (tone || '') }, h('b', { text: val == null ? '—' : fa(val) }), sp(label), sub ? h('i', { text: sub }) : null); }
  function lvTag(l) { return h('span', { class: 'rgm-tag l' + l, text: ['', 'مشکوک', 'خصمانه', 'بحرانی'][l] || 'سطح ' + fa(l) }); }
  function relT(s) { return s || ''; }

  function sheetOpen(o) { o.body = div('rgm-sh', [o.body]); Sheet.open(o); }
  function sheetSet(n) { Sheet.set(div('rgm-sh', [n])); }

  /* ─── شبکه ─── */
  function load(first) {
    if (loading) return Promise.resolve();
    loading = true;
    return api('/hub/api/rgm/overview' + (first ? '?fresh=1' : '')).then(function (d) { setData(d); }).catch(function (e) {
      if (!D) { bodyEl.replaceChildren(empty(e && e.code === 403 ? 'این بخش فقط برای مدیر ارشد است.' : 'اتصال برقرار نشد؛ دوباره امتحان کنید.')); }
    }).then(function () { loading = false; }, function () { loading = false; });
  }
  var lastSig = '';
  function setData(d) {
    var sig = JSON.stringify(d, function (k, v) { return (k === 'now' || k === 'now_fa') ? undefined : v; });
    D = d; fetchedAt = Date.now();
    renderHero();
    if (sig === lastSig) return;
    lastSig = sig;
    var ae = document.activeElement;
    if (ae && root.contains(ae) && /^(INPUT|TEXTAREA)$/.test(ae.tagName)) { renderNav(); return; }   // وسطِ تایپ، صفحه را از نو نساز
    renderNav(); renderBody();
  }
  function act(body, quiet) {
    return api('/hub/api/rgm/act', body).then(function (r) {
      if (r && r.overview) setData(r.overview);
      if (!quiet) toast(r && r.message ? String(r.message).split('\n')[0].slice(0, 90) : (r && r.ok ? 'انجام شد' : 'انجام نشد'));
      (r && r.ok ? hx.ok : hx.err)();
      return r;
    }).catch(function (e) { hx.err(); toast(e && e.data && e.data.message ? e.data.message : 'خطا؛ دوباره امتحان کنید.'); return null; });
  }
  function confirmSheet(title, text, label, danger, fn) {
    var b = btn(label, danger ? 'd full' : 'p full', function () { Sheet.close(); fn(); });
    sheetOpen({ title: title, body: div('', [h('p', { class: 'rgm-sub', style: 'font-size:14px;margin:6px 0 14px', text: text })]), foot: b });
  }

  /* ─── هیرو ─── */
  function state() { return !D ? 'off' : D.guard.locked ? 'lock' : D.mgr.active ? 'on' : 'off'; }
  function remainNow() { if (!D || !D.mgr.timer.active || !D.mgr.timer.timed) return null; return Math.max(0, D.mgr.timer.remaining - (Date.now() - fetchedAt) / 1000); }
  function renderHero() {
    if (!D) return;
    var s = state(), t = D.mgr.timer, g = D.guard, rem = remainNow();
    heroEl.dataset.s = s;
    var pct = t.active ? (t.timed ? (rem / t.total) * 100 : 100) : 0;
    var col = s === 'lock' ? '#ef4444' : '#22c55e';
    var orb = div('rgm-orb', [ring(pct, s === 'off' ? '#64748b' : col, 34, 5), div('core', [ic(s === 'lock' ? 'lock' : s === 'on' ? 'bolt' : 'power')])]);
    var title = s === 'lock' ? 'قفلِ اضطراری روشن است' : s === 'on' ? 'رهگشا مدیر است' : 'رهگشای مدیر خاموش است';
    var sub = s === 'off' ? 'مدیریت دست خودتان است. هر لحظه بسپارید.' : t.timed ? 'مدیریت تا پایانِ مهلت با رهگشاست.' : 'تا اطلاعِ ثانوی مدیریت با رهگشاست.';
    var ht = div('rgm-ht', [h('h3', { text: title }), t.active && t.timed ? h('span', { class: 'rgm-time', id: 'rgm-clk', text: clock(rem) }) : null, h('p', { text: s === 'lock' ? (g.lock_reason || 'نگهبان قفل کرد.') : sub })]);
    var pills = div('rgm-pills', [
      sp('🛡️ نگهبان: ' + modeFa(g.eff_mode), 'rgm-pill ' + (g.eff_mode === 'off' ? '' : 'g')),
      D.mgr.full_access ? sp('👑 دسترسیِ کامل', 'rgm-pill y') : sp('🔐 ' + fa(D.mgr.caps_on) + ' از ' + fa(D.mgr.caps_all) + ' حوزه', 'rgm-pill'),
      D.kpi.incidents_open ? sp('🚨 ' + fa(D.kpi.incidents_open) + ' رویدادِ باز', 'rgm-pill r') : sp('✅ بدونِ رویدادِ باز', 'rgm-pill g'),
      D.mgr.active ? sp('🧠 دورِ بعد: ' + (D.mgr.next_round_fa || '—').split(' ').slice(-1)[0], 'rgm-pill') : null]);
    var bs = D.mgr.active
      ? div('rgm-hbtns', [btn('دور همین الان', 'gl', function () { act({ a: 'mgr_round' }); }, 'brain'), btn('تمدید', 'gl', extendSheet, 'clock'), btn('خاموشیِ فوری', 'd', function () { confirmSheet('خاموشیِ فوریِ رهگشای مدیر', 'مدیریت همین لحظه به شما برمی‌گردد و گزارشِ این دوره در پیوی می‌آید.', 'بله، خاموش کن', true, function () { act({ a: 'mgr_revoke' }); }); }, 'power')])
      : div('rgm-hbtns', [btn('بسپار به رهگشا', 'ok', grantSheet, 'bolt')]);
    heroEl.replaceChildren(div('rgm-hrow', [orb, ht]), pills, bs);
  }
  function modeFa(m) { return { off: 'خاموش', watch: 'هشدار', protect: 'هشدار+مهار', full: 'کامل' }[m] || m; }

  /* ─── ناوبری ─── */
  var TABS = [['over', 'نمای کلی', 'pulse'], ['caps', 'اختیارات', 'sliders'], ['guard', 'نگهبان', 'shield'], ['jr', 'ژورنال', 'book'], ['set', 'تنظیمات', 'gear']];
  function renderNav() {
    navEl.replaceChildren.apply(navEl, TABS.map(function (t) {
      var b = h('button', { type: 'button', class: view === t[0] ? 'on' : '', onclick: function () { if (view !== t[0]) { hx.sel(); view = t[0]; renderNav(); renderBody(); window.scrollTo(0, 0); } } }, ic(t[2]), t[1]);
      if (D && t[0] === 'guard' && D.kpi.incidents_open) b.append(sp(fa(D.kpi.incidents_open), 'rgm-tag l3'));
      return b;
    }));
  }
  function renderBody() {
    if (!D) { bodyEl.replaceChildren(div('rgm-load', ['در حال بارگذاری…'])); return; }
    var fn = { over: bodyOver, caps: bodyCaps, guard: bodyGuard, jr: bodyJournal, set: bodySet }[view];
    bodyEl.replaceChildren.apply(bodyEl, fn());
  }

  /* ─── ۱) نمای کلی ─── */
  function bodyOver() {
    var k = D.kpi, sc = k.score == null ? 0 : k.score, col = sc >= 80 ? '#2fb344' : sc >= 55 ? '#f08c00' : '#e5484d';
    var gauge = h('div', { class: 'rgm-k wide ' + (sc >= 80 ? 'ok' : sc >= 55 ? 'warn' : 'bad') }, div('rgm-gauge', [ring(sc, col, 34, 7), h('b', { text: fa(sc) })]),
      div('', [h('b', { style: 'font-size:16px', text: 'امتیازِ امنیتِ سیستم' }), h('i', { text: sc >= 80 ? 'وضعیت عالی است.' : sc >= 55 ? 'چند نکته نیاز به توجه دارد.' : 'وضعیت نگران‌کننده است؛ نگهبان را بررسی کنید.' }), h('i', { text: 'وضعیتِ سیستم: ' + ({ normal: 'عادی', bad: 'احتیاطی', danger: 'خطر', aps: 'APS' }[k.system_status] || k.system_status) })]));
    var grid = div('rgm-grid rgm-fade', [gauge,
      kpi('رویدادِ باز', k.incidents_open, k.incidents_open ? 'bad' : 'ok', fa(k.incidents_24h) + ' در ۲۴ ساعت'), kpi('فردِ مهارشده', k.incidents_contained, k.incidents_contained ? 'warn' : 'ok'),
      kpi('دورِ ۲۴ ساعت', k.rounds_24h, 'cy', fa(k.rounds_ok_24h) + ' موفق'), kpi('ژورنال', k.journal_total, 'vi'),
      kpi('غریبه‌ها', k.strangers, k.strangers ? 'warn' : 'ok'), kpi('در انتظارِ تأیید', k.pending, k.pending ? 'warn' : 'ok'),
      kpi('مدیرِ آنلاین', k.online, 'cy', 'از ' + fa(k.admins) + ' مدیر'), kpi('اقدامِ مخرب', k.destructive, k.destructive > 3 ? 'bad' : 'ok'),
      kpi('بازیکنِ دارای اخطار', k.warned, 'warn'), kpi('مسابقه بدونِ نتیجه', k.matches_pending, k.matches_pending ? 'warn' : 'ok')]);
    var tr = D.trend.map(function (x) { return x.score; });
    var trend = card('روندِ امتیازِ امنیت', 'pulse', [tr.filter(function (x) { return x != null; }).length > 1 ? spark(tr, col) : empty('هنوز داده‌ی کافی برای نمودار نیست.')]);
    var quick = card('اقدام‌های سریع', 'bolt', [div('rgm-row', [
      btn('بکاپِ فوری', '', function () { act({ a: 'gd_backup' }); }, 'inbox'),
      D.guard.locked ? btn('رفعِ قفل', 'ok', function () { act({ a: 'gd_unlock' }); }, 'unlock') : btn('قفلِ اضطراری', 'd', lockSheet, 'lock')]),
      h('div', { style: 'height:8px' }), div('rgm-row', [btn('گزارشِ دوره', '', reportSheet, 'list'), btn('اجرای یک دور', 'p', function () { if (!D.mgr.active) return toast('اول مدیریت را به رهگشا بسپارید.'); act({ a: 'mgr_round' }); }, 'brain')])]);
    var evs = [];
    D.incidents.slice(0, 5).forEach(function (i) { evs.push({ t: i.ts, c: ['', '#f08c00', '#ff7a1a', '#e5484d'][i.level], a: '🛡️ ' + i.title, b: i.actor_name + ' — ' + i.ts_fa }); });
    D.journal.slice(0, 6).forEach(function (j) { evs.push({ t: j.ts, c: j.ok ? '#38bdf8' : '#e5484d', a: '🧠 ' + j.title, b: j.ts_fa }); });
    evs.sort(function (a, b) { return a.t < b.t ? 1 : -1; });
    var tl = card('رویدادهای زنده', 'clock', evs.length ? [div('rgm-tl', evs.slice(0, 9).map(function (e) { var n = div('rgm-ev', [div('a', [e.a]), div('b', [e.b])]); n.style.setProperty('--c', e.c || 'var(--hint)'); return n; }))] : [empty('هنوز رویدادی ثبت نشده.')]);
    var risk = D.risk.length ? card('ریسکِ لحظه‌ایِ مدیران', 'alert', D.risk.map(function (r) { return li(r.replace(/^- /, ''), null); })) : null;
    return [grid, trend, quick, risk, tl].filter(Boolean);
  }

  /* ─── ۲) اختیارات ─── */
  function bodyCaps() {
    var m = D.mgr, full = m.full_access;
    var top = card('دسترسیِ کامل', 'crown', [h('p', { class: 'rgm-sub', text: 'همه‌ی حوزه‌ها روشن می‌شود و سقفِ هر دور بالاتر می‌رود (' + fa(m.limits.writes) + ' اقدام، ' + fa(m.limits.destructive) + ' اقدامِ مخرب). قفل‌های سخت — مثل اقدام علیهِ مدیر ارشد یا تغییرِ اختیارِ خودش — همچنان برقرارند.' }),
      li('دسترسیِ کامل', full ? 'روشن' : 'خاموش', sw(full, function (v) { confirmSheet(v ? 'روشن‌کردنِ دسترسیِ کامل' : 'خاموش‌کردنِ دسترسیِ کامل', v ? 'رهگشا در همه‌ی حوزه‌ها می‌تواند اقدام کند.' : 'اختیارات به تنظیمِ تک‌تکِ حوزه‌ها برمی‌گردد.', 'تأیید', v, function () { act({ a: 'mgr_full', enabled: v }); }); }))], full ? '' : '');
    var pre = card('پیش‌تنظیم‌ها', 'sliders', [div('rgm-row', [btn('محتاطانه', '', function () { act({ a: 'mgr_preset', preset: 'cautious' }); }, 'eye'), btn('متعادل', '', function () { act({ a: 'mgr_preset', preset: 'balanced' }); }, 'sliders'), btn('کامل', 'p', function () { act({ a: 'mgr_preset', preset: 'full' }); }, 'crown')]),
      h('p', { class: 'rgm-sub', style: 'margin:10px 0 0', text: 'محتاطانه: فقط خواندن و گزارش • متعادل: کارهای روتین + دفاع • کامل: همه‌چیز.' })]);
    var q = h('input', { class: 'rgm-in', placeholder: 'جست‌وجوی حوزه…', value: F.capq, oninput: function (e) { F.capq = e.target.value; list.replaceChildren.apply(list, rows()); } });
    var list = div('');
    function rows() {
      var s = F.capq.trim(), out = [];
      D.caps.filter(function (c) { return !s || c.label.indexOf(s) > -1; }).forEach(function (c) {
        var sub = c.kind === 'brain' ? c.desc : fa(c.tools) + ' ابزار';
        var r = li(c.label, sub, sw(c.on, function (v) { c.on = v; act({ a: 'mgr_caps', keys: [c.key], enabled: v }, true).then(function (r) { if (r) toast(v ? 'روشن شد' : 'خاموش شد'); }); renderBody(); }));
        if (c.kind === 'cat') { r.querySelector('.m').addEventListener('click', function () { toolsSheet(c); }); r.querySelector('.m').style.cursor = 'pointer'; }
        out.push(r);
      });
      return out.length ? out : [empty('موردی پیدا نشد.')];
    }
    var cats = card('حوزه‌ها و رفتار', 'list', [q, h('div', { style: 'height:6px' }), list], '', sp(fa(m.caps_on) + '/' + fa(m.caps_all), 'rgm-tag'));
    list.replaceChildren.apply(list, rows());
    return [top, pre, cats];
  }
  function toolsSheet(c) {
    var body = div('', [h('p', { class: 'rgm-sub', text: 'ابزارهایی که رهگشا با روشن‌بودنِ این حوزه می‌تواند صدا بزند:' }), div('rgm-pills', c.tool_names.map(function (n) { return sp(n, 'rgm-tag'); }))]);
    sheetOpen({ title: c.label, body: body });
  }

  /* ─── ۳) نگهبان ─── */
  var MODES = [['watch', 'فقط هشدار', 'eye', 'تهدید را می‌بیند و فوراً به شما خبر می‌دهد؛ خودش کاری نمی‌کند.'], ['protect', 'هشدار + مهار', 'shield', 'فردِ خصمانه را همان لحظه مهار می‌کند: قطعِ رهگشا، غیرفعال‌کردنِ مدیر، بلاکِ غریبه.'], ['full', 'کامل', 'lock', 'مهار + قفلِ اضطراری (APS و خاموشیِ ربات برای مدیران) هنگامِ تهدیدِ بحرانی + یک دورِ بررسیِ رهگشا.']];
  function bodyGuard() {
    var g = D.guard, out = [];
    out.push(div('rgm-card glass rgm-lock rgm-fade' + (g.locked ? ' on danger' : ''), [div('big', [ic(g.locked ? 'lock' : 'unlock')]), h('h4', { text: g.locked ? 'قفلِ اضطراری روشن است' : 'سیستم آزاد است' }),
      h('p', { text: g.locked ? (g.lock_reason + ' — از ' + g.lock_since_fa + ' توسطِ ' + ({ guardian: 'نگهبان', boss: 'شما', rahgosha: 'رهگشا' }[g.lock_by] || g.lock_by)) : 'قفلِ اضطراری: وضعیتِ APS + خاموشیِ ربات و ورودِ مدیران. مدیر ارشد همیشه آزاد است.' }),
      g.locked ? btn('رفعِ قفل و برگشت به حالتِ قبل', 'ok full', function () { act({ a: 'gd_unlock' }); }, 'unlock') : btn('قفلِ اضطراریِ دستی', 'd full', lockSheet, 'lock')]));
    out.push(card('حالتِ نگهبان', 'shield', [div('rgm-mode', MODES.map(function (m) { return h('button', { type: 'button', class: 'rgm-mc' + (g.mode === m[0] ? ' on' : ''), onclick: function () { hx.sel(); act({ a: 'gd_config', mode: m[0] }, true); } }, ic(m[2]), div('', [h('b', { text: m[1] }), h('span', { text: m[3] })])); })),
      h('p', { class: 'rgm-sub', style: 'margin:10px 0 0', text: g.eff_mode === g.mode ? 'حالتِ مؤثرِ الان همین است.' : 'حالتِ مؤثرِ الان «' + modeFa(g.eff_mode) + '» است؛ مهار و قفل فقط وقتی اعمال می‌شود که رهگشای مدیر روشن باشد یا «همیشه‌فعال» را بزنید.' })],
      '', sp(g.enabled ? 'روشن' : 'خاموش', 'rgm-tag ' + (g.enabled ? 'ok' : ''))));
    var th = g.thresholds;
    out.push(card('حساسیت', 'radar', [seg([['low', 'کم'], ['medium', 'متوسط'], ['high', 'بالا']], g.sens, function (v) { act({ a: 'gd_config', sens: v }, true); }),
      h('p', { class: 'rgm-sub', style: 'margin:10px 0 0', text: 'آستانه‌ی امتیازِ ریسک در ۵ دقیقه: هشدار ' + fa(th.events[0]) + ' • مهار ' + fa(th.events[1]) + ' • قفل ' + fa(th.events[2]) + '. سیلِ درخواست: هشدار ' + fa(th.rate[0]) + ' و مهار ' + fa(th.rate[1]) + ' آپدیت در ۱۰ ثانیه.' })]));
    out.push(card('کلیدها', 'sliders', [
      li('نگهبان روشن باشد', 'خاموش‌کردن یعنی هیچ دیدبانی انجام نمی‌شود.', sw(g.enabled, function (v) { act({ a: 'gd_config', enabled: v }, true); })),
      li('همیشه‌فعال', 'مهار و قفل حتی وقتی رهگشای مدیر خاموش است.', sw(g.always, function (v) { act({ a: 'gd_config', always: v }, true); })),
      li('قفلِ اضطراریِ خودکار', 'در تهدیدِ بحرانی خودش قفل می‌کند.', sw(g.auto_lockdown, function (v) { act({ a: 'gd_config', auto_lockdown: v }, true); })),
      li('آینه در گروه فرماندهی', 'خلاصه‌ی رویدادها در گروه هم ثبت شود.', sw(g.ops_group, function (v) { act({ a: 'gd_config', ops_group: v }, true); }))]));
    out.push(labCard());
    out.push(incCard());
    out.push(peopleCard());
    return out;
  }
  function labCard() {
    var inp = h('input', { class: 'rgm-in', placeholder: 'یک جمله بنویس و ببین نگهبان چه می‌کند…' }), res = div('', []);
    function run() {
      var t = inp.value.trim(); if (!t) return;
      api('/hub/api/rgm/act', { a: 'gd_classify', text: t }).then(function (r) {
        res.replaceChildren(div('rgm-row', [lvTag(r.level) , r.level ? null : sp('بی‌خطر', 'rgm-tag ok')].filter(Boolean)), h('p', { class: 'rgm-sub', style: 'margin:8px 0 0', text: r.level ? (r.tags.join(' • ') + ' — ' + (r.level === 1 ? 'فقط هشدار' : r.level === 2 ? 'مهارِ فرد' : 'مهار + قفلِ اضطراری') + ' (در حالتِ مؤثرِ مناسب)') : 'هیچ واکنشی ایجاد نمی‌شود.' }));
      }).catch(function () { toast('خطا'); });
    }
    return card('آزمایشگاهِ تهدید', 'sparkle', [h('p', { class: 'rgm-sub', text: 'بدونِ اجرای هیچ اقدامی، تشخیصِ نگهبان را روی هر جمله امتحان کنید.' }), inp, h('div', { style: 'height:8px' }), btn('بررسی', 'p full', run, 'search'), h('div', { style: 'height:8px' }), res]);
  }
  function wasContained(i) { return i.status === 'contained' || (i.actions || []).some(function (a) { return /غیرفعال|بلاک|قطع/.test(a); }); }
  function incCard() {
    var list = div(''), chips = div('rgm-chips', [['open', 'باز'], ['all', 'همه']].map(function (c) { return h('button', { type: 'button', class: 'rgm-chip' + (F.inc === c[0] ? ' on' : ''), onclick: function () { F.inc = c[0]; renderBody(); } }, c[1]); }));
    function paint(items) {
      list.replaceChildren.apply(list, items.length ? items.map(incRow) : [empty(F.inc === 'open' ? 'رویدادِ بازی نیست 🎉' : 'رویدادی ثبت نشده.')]);
    }
    paint(F.inc === 'open' ? D.incidents.filter(function (i) { return i.status !== 'closed'; }) : D.incidents);
    if (F.inc === 'all') api('/hub/api/rgm/incidents?limit=40').then(function (r) { paint(r.items); }).catch(function () {});
    var closeAll = D.kpi.incidents_open || D.kpi.incidents_contained ? btn('بستنِ همه', 'sm', function () { confirmSheet('بستنِ همه‌ی رویدادها', 'همه‌ی رویدادهای باز «بسته» علامت می‌خورد (فردِ مهارشده بازگردانده نمی‌شود).', 'بستن', false, function () { act({ a: 'gd_closeall' }); }); }) : null;
    return card('رویدادهای امنیتی', 'alert', [chips, list], '', closeAll);
  }
  function incRow(i) {
    var cont = wasContained(i), btns = [];
    if (i.status !== 'closed' && i.actor_id) {
      if (cont) { btns.push(btn('بازگردانی', 'sm', function () { act({ a: 'gd_release', uid: i.actor_id, incident: i.id }); }, 'reset'), btn('خنثی‌سازیِ کارهای امروز', 'sm', function () { confirmSheet('خنثی‌سازی', 'کارهای قابل‌بازگشتِ امروزِ این فرد برگردانده می‌شود.', 'خنثی کن', true, function () { act({ a: 'gd_undo', uid: i.actor_id }); }); }, 'trash')); }
      else { btns.push(btn('مهار', 'sm d', function () { act({ a: 'gd_contain', uid: i.actor_id, incident: i.id, reason: i.title }); }, 'shield'), btn('بلاکِ دائم', 'sm', function () { confirmSheet('بلاکِ دائم', 'این فرد بلاک می‌شود و دیگر دسترسی نخواهد داشت.', 'بلاک', true, function () { act({ a: 'gd_contain', uid: i.actor_id, incident: i.id, block: true, reason: i.title }); }); }, 'close')); }
      btns.push(btn('مشکلی نیست', 'sm', function () { act({ a: 'gd_close', id: i.id }); }, 'shield'));
    }
    return div('rgm-inc', [div('top', [lvTag(i.level), h('span', { class: 'nm', text: i.actor_name }), sp(i.status === 'closed' ? 'بسته' : cont ? 'مهارشده' : 'باز', 'rgm-tag' + (i.status === 'closed' ? ' ok' : '')), h('i', { style: 'flex:1' }), sp(i.ts_fa, 'rgm-tag')]),
      div('dt', ['#' + fa(i.id) + ' — ' + i.title + (i.detail ? ' — ' + i.detail : '')]), (i.actions || []).length ? div('ac', ['⚙️ ' + i.actions.join(' • ')]) : null, btns.length ? div('btns', btns) : null]);
  }
  function peopleCard() {
    var list = div('');
    function paint(items) {
      list.replaceChildren.apply(list, items.length ? items.map(function (p) {
        var rk = Math.min(100, p.risk * 4), bar = h('div', { class: 'rgm-bar' }, h('i', { style: 'width:100%;transform:scaleX(' + (rk / 100) + ');background:' + (rk > 60 ? 'var(--bad)' : rk > 30 ? 'var(--warn)' : 'var(--ok)') }));
        var end = p.active ? btn('مهار', 'sm d', function () { confirmSheet('مهارِ ' + p.name, 'دسترسیِ رهگشا قطع و حسابِ مدیر غیرفعال می‌شود. هر وقت خواستید بازمی‌گردد.', 'مهار', true, function () { act({ a: 'gd_contain', uid: p.id, reason: 'مهارِ دستی از پنل' }).then(loadPeople); }); }) : btn('بازگردانی', 'sm', function () { act({ a: 'gd_release', uid: p.id }).then(loadPeople); });
        return div('rgm-li', [div('m', [div('t', [p.name + (p.active ? '' : ' (غیرفعال)')]), div('s', [(p.role === 'security_manager' ? 'مسئول انتظامات' : p.role === 'tournament_manager' ? 'مسئول مسابقات' : p.role) + ' • آخرین فعالیت ' + (p.last_active || '—') + (p.incidents_7d ? ' • ' + fa(p.incidents_7d) + ' رویداد در ۷ روز' : '')]), bar]), end]);
      }) : [empty('مدیری پیدا نشد.')]);
    }
    function loadPeople() { return api('/hub/api/rgm/people').then(function (r) { PPL = r.items; paint(PPL); }).catch(function () { list.replaceChildren(empty('بارگذاریِ مدیران ناموفق بود.')); }); }
    if (PPL) paint(PPL); else list.replaceChildren(empty('در حال بارگذاری…'));
    loadPeople();
    return card('مدیران و ریسکشان', 'users', [list]);
  }
  function lockSheet() {
    var ta = h('input', { class: 'rgm-in', placeholder: 'دلیل (اختیاری)' });
    sheetOpen({ title: 'قفلِ اضطراری', body: div('', [h('p', { class: 'rgm-sub', style: 'font-size:14px', text: 'وضعیتِ سیستم روی APS می‌رود، ربات برای مدیران خاموش و ورودِ مدیرِ جدید بسته می‌شود. فقط شما آزاد می‌مانید.' }), ta]),
      foot: btn('قفل کن', 'd full', function () { Sheet.close(); act({ a: 'gd_lock', reason: ta.value.trim() || undefined }); }, 'lock') });
  }

  /* ─── ۴) ژورنال ─── */
  var KINDS = [['all', 'همه'], ['round', 'دورها'], ['directive', 'دستورها'], ['caps', 'اختیارات'], ['question', 'پرسش‌ها'], ['grant', 'اعطا'], ['revoke', 'پایان'], ['session_summary', 'گزارش‌ها']];
  var KICON = { round: '🧠', directive: '📜', caps: '🔐', question: '❓', grant: '⚡', revoke: '🛑', extend: '⏱', session_summary: '📊', announce_cfg: '📣' };
  function bodyJournal() {
    var chips = div('rgm-chips', KINDS.map(function (k) { return h('button', { type: 'button', class: 'rgm-chip' + (F.journal === k[0] ? ' on' : ''), onclick: function () { F.journal = k[0]; JR = { items: [], more: true, busy: false }; renderBody(); } }, k[1]); }));
    var list = div(''), more = div('', []);
    function paint() {
      list.replaceChildren.apply(list, JR.items.length ? JR.items.map(jRow) : [empty(JR.busy ? 'در حال بارگذاری…' : 'ثبتی پیدا نشد.')]);
      more.replaceChildren(JR.more && JR.items.length ? btn('نمایشِ بیشتر', 'full', fetchMore) : null);
    }
    function fetchMore() {
      if (JR.busy) return; JR.busy = true;
      var before = JR.items.length ? JR.items[JR.items.length - 1].id : '';
      api('/hub/api/rgm/journal?kind=' + F.journal + '&limit=20' + (before ? '&before=' + before : '')).then(function (r) { JR.items = JR.items.concat(r.items); JR.more = r.items.length >= 20; JR.busy = false; paint(); }).catch(function () { JR.busy = false; });
    }
    if (!JR.items.length) fetchMore(); else paint();
    var mem = card('حافظه‌ی رهگشا', 'brain', D.memory.length ? D.memory.map(function (m) { return li(m.text, m.ts_fa + ' • ' + m.kind); }).concat([btn('پاک‌کردنِ حافظه', 'sm full', function () { confirmSheet('پاک‌کردنِ حافظه', 'یادداشت‌های ماندگارِ رهگشا پاک می‌شود.', 'پاک کن', true, function () { act({ a: 'mgr_memory_clear' }); }); })]) : [empty('حافظه خالی است.')]);
    return [card('گزارش', 'list', [div('rgm-row', [btn('«چه کردی؟» — آخرین دوره', 'p', reportSheet, 'list')])]), card('ژورنال', 'book', [chips, list, more]), mem];
  }
  function jRow(j) {
    var meta = j.ts_fa + (j.tools && j.tools.length ? ' • ' + fa(j.tools.length) + ' ابزار' : '') + (j.ok ? '' : ' • ❌');
    var r = div('rgm-li', [div('m', [div('t', [(KICON[j.kind] || '•') + ' ' + j.title]), div('s', [(j.body || '').slice(0, 110).replace(/\n/g, ' ') || meta]), div('s', [meta])]), ic('chev')]);
    r.style.cursor = 'pointer'; r.addEventListener('click', function () { hx.tap(); jSheet(j.id); }); return r;
  }
  function jSheet(id) {
    sheetOpen({ title: 'جزئیاتِ ثبت', body: div('rgm-load', ['…']) });
    api('/hub/api/rgm/journal/' + id).then(function (r) {
      var it = r.item, kids = [h('p', { class: 'rgm-sub', text: it.ts_fa + ' • ' + it.kind }), h('pre', { class: 'rgm-pre', text: it.body || '—' })];
      if (it.tools.length) kids.push(h('h4', { class: 'rgm-h', style: 'margin-top:14px' }, ic('bolt'), sp('کارهایی که انجام شد')), div('', it.tools.map(function (t) { return li(t.tool, (t.result || t.args || '—').slice(0, 220)); })));
      sheetOpen({ title: it.title, body: div('', kids) });
    }).catch(function () { sheetSet(empty('بارگذاری ناموفق بود.')); });
  }
  function reportSheet() {
    sheetOpen({ title: 'گزارشِ دوره', body: div('rgm-load', ['در حال ساختنِ گزارش…']) });
    api('/hub/api/rgm/report?session=' + (D && D.mgr.active ? 'current' : 'last')).then(function (r) {
      sheetOpen({ title: 'رهگشا در این مدت چه کرد؟', body: r.report ? h('pre', { class: 'rgm-pre', text: r.report }) : empty('هنوز دوره‌ای ثبت نشده است.') });
    }).catch(function () { sheetSet(empty('بارگذاری ناموفق بود.')); });
  }

  /* ─── ۵) تنظیمات ─── */
  function bodySet() {
    var m = D.mgr, out = [];
    var ta = h('textarea', { class: 'rgm-ta', placeholder: 'مثلاً: هر مسابقه‌ی بدونِ نتیجه را پیگیری کن؛ هیچ مدیرِ تازه‌ای را بدونِ اجازه‌ی من تأیید نکن؛ اگر کسی تهدید کرد فوراً مهارش کن.', text: m.directive || '' });
    out.push(card('دستورِ اختصاصی', 'pencil', [h('p', { class: 'rgm-sub', text: 'وظیفه‌ی اجباریِ هر دور؛ بر هر چیز مقدم است. با ذخیره، رهگشا همان لحظه آن را اجرا می‌کند و برای هر بند وضعیت می‌دهد.' }), ta, h('div', { style: 'height:8px' }),
      div('rgm-row', [btn('ذخیره و اجرا', 'p', function () { act({ a: 'mgr_directive', mode: 'set', text: ta.value }); }, 'bolt'), btn('پاک', '', function () { act({ a: 'mgr_directive', mode: 'clear' }); }, 'trash')])]));
    var caps = {}; D.caps.forEach(function (c) { caps[c.key] = c.on; });
    var iv = [[15, '۱۵د'], [30, '۳۰د'], [60, '۱س'], [120, '۲س'], [180, '۳س'], [360, '۶س'], [720, '۱۲س'], [1440, '۲۴س']];
    var tm = h('input', { class: 'rgm-in', type: 'time', value: m.daily_time, style: 'direction:ltr;text-align:center', onchange: function (e) { act({ a: 'mgr_schedule', daily_time: e.target.value }); } });
    out.push(card('زمان‌بندیِ دورها', 'clock', [h('p', { class: 'rgm-sub', text: 'فاصله‌ی دورهای خودکار. هر چه کوتاه‌تر، رهگشا فعال‌تر (و مصرفِ هوش مصنوعی بیشتر).' }),
      div('rgm-chips', iv.map(function (x) { return h('button', { type: 'button', class: 'rgm-chip' + (m.interval_min === x[0] ? ' on' : ''), onclick: function () { act({ a: 'mgr_schedule', interval_minutes: x[0] }); } }, x[1]); })),
      li('دورهای خودکار', 'رهگشا خودش و بی‌درخواست دور می‌زند.', sw(!!caps.autonomous_rounds, function (v) { act({ a: 'mgr_schedule', autonomous: v }, true); })),
      li('ساعتِ بررسیِ روزانه‌ی امنیت', 'هر شب در این ساعت اجرا می‌شود.'),
      tm, h('div', { style: 'height:10px' }), li('بررسیِ روزانه فعال باشد', null, sw(!!caps.daily_review, function (v) { act({ a: 'mgr_schedule', daily_review: v }, true); }))]));
    var an = m.announce, rp = m.report;
    out.push(card('اعلامِ حضور و گزارش', 'chat', [
      li('اعلامِ شروعِ مدیریت', 'به مدیرها و گروه‌ها خبر بده که رهگشا مدیر است.', sw(an.on, function (v) { act({ a: 'mgr_announce', master: v }, true); })),
      h('div', { style: 'padding:4px 0 8px' }, seg([['all', 'همه‌ی مدیران'], ['none', 'هیچ‌کس']], an.admins === 'none' ? 'none' : 'all', function (v) { act({ a: 'mgr_announce', admins_mode: v }, true); })),
      li('گروهِ فرماندهی', null, sw(an.ops_group, function (v) { act({ a: 'mgr_announce', ops_group: v }, true); })), li('گروهِ اطلاعیه', null, sw(an.ann_group, function (v) { act({ a: 'mgr_announce', announcement_group: v }, true); })),
      li('گزارشِ دورها در پیوی شما', null, sw(rp.boss_pm, function (v) { act({ a: 'mgr_announce', report_boss_pm: v }, true); })), li('گزارشِ دورها در گروهِ فرماندهی', null, sw(rp.ops_group, function (v) { act({ a: 'mgr_announce', report_ops_group: v }, true); }))]));
    var msg = h('textarea', { class: 'rgm-ta', style: 'min-height:70px', placeholder: 'پیامی که با نامِ رهگشا اعلام شود…' });
    out.push(card('اعلامِ فوری', 'sparkle', [msg, h('div', { style: 'height:8px' }), btn('ارسال', 'p full', function () { if (!msg.value.trim()) return; confirmSheet('ارسالِ اعلام', 'پیام برای مدیرانِ تنظیم‌شده فرستاده می‌شود.', 'ارسال', false, function () { act({ a: 'mgr_announce_send', text: msg.value }); msg.value = ''; }); }, 'chat')]));
    out.push(card('کنترلِ سیستم', 'gear', [h('p', { class: 'rgm-sub', text: 'وضعیتِ کلیِ ربات (همان که در «پنل مدیر ارشد» هست).' }),
      seg([['normal', 'عادی'], ['bad', 'احتیاط'], ['danger', 'خطر'], ['aps', 'APS']], D.kpi.system_status, function (v) { confirmSheet('تغییرِ وضعیتِ سیستم', 'وضعیت به «' + v + '» می‌رود و مدیرها تحتِ تأثیر قرار می‌گیرند.', 'تغییر بده', v !== 'normal', function () { act({ a: 'sys_status', status: v }); }); }),
      h('div', { style: 'height:8px' }), li('رهگشا (چتِ هوشمند)', 'خاموش‌شدن یعنی هیچ مدیری با رهگشا گفتگو نمی‌کند.', sw(D.kpi.ai_online, function (v) { act({ a: 'sys_ai_online', on: v }); }))]));
    out.push(card('آمارِ استفاده', 'pulse', [li('کلِ زمانِ مدیریتِ رهگشا', dur(m.usage.total)), li('امروز', dur(m.usage.today)), li('۷ روزِ اخیر', dur(m.usage.week)), li('طولانی‌ترین دوره', dur(m.usage.longest)), li('تعدادِ دوره‌ها', fa(m.usage.count) + ' بار'), li('نوبتِ‌های اعطا', fa(m.grant_count))]));
    return out;
  }

  /* ─── اعطا / تمدید ─── */
  function grantSheet() {
    var sel = { mins: 180, forever: false, preset: 'balanced', ann: !!(D && D.mgr.announce.on) };
    var durs = [[30, '۳۰ دقیقه'], [60, '۱ ساعت'], [180, '۳ ساعت'], [360, '۶ ساعت'], [720, '۱۲ ساعت'], [1440, '۱ روز'], [4320, '۳ روز'], [0, 'تا اطلاعِ ثانوی']];
    var ta = h('textarea', { class: 'rgm-ta', style: 'min-height:74px', placeholder: 'دستورِ اختصاصی برای این دوره (اختیاری)', text: (D && D.mgr.directive) || '' });
    var wrap = div('', []);
    function paint() {
      wrap.replaceChildren(h('p', { class: 'rgm-sub', text: 'مدتِ مدیریت' }), div('rgm-dur', durs.map(function (d) { var on = d[0] === 0 ? sel.forever : (!sel.forever && sel.mins === d[0]); return h('button', { type: 'button', class: 'rgm-chip' + (on ? ' on' : ''), onclick: function () { sel.forever = d[0] === 0; if (d[0]) sel.mins = d[0]; paint(); } }, d[1]); })),
        h('p', { class: 'rgm-sub', text: 'میزانِ اختیار' }), seg([['cautious', 'محتاطانه'], ['balanced', 'متعادل'], ['full', 'کامل']], sel.preset, function (v) { sel.preset = v; paint(); }), h('div', { style: 'height:12px' }),
        h('p', { class: 'rgm-sub', text: 'دستورِ اختصاصی' }), ta, li('اعلامِ شروع به مدیرها', null, sw(sel.ann, function (v) { sel.ann = v; paint(); })));
    }
    paint();
    sheetOpen({ title: 'سپردنِ مدیریت به رهگشا', body: wrap, foot: btn('شروعِ مدیریتِ رهگشا', 'ok full', function () {
      Sheet.close();
      act({ a: 'mgr_grant', minutes: sel.forever ? null : sel.mins, until_revoked: sel.forever, preset: sel.preset, directive: ta.value.trim() || undefined, announce: sel.ann });
    }, 'bolt') });
  }
  function extendSheet() {
    var opts = [[30, '+۳۰ دقیقه'], [60, '+۱ ساعت'], [180, '+۳ ساعت'], [720, '+۱۲ ساعت'], [1440, '+۱ روز']];
    var body = div('', [h('p', { class: 'rgm-sub', text: 'مهلتِ فعلی را تمدید کنید یا بی‌پایان کنید.' }), div('rgm-dur', opts.map(function (o) { return h('button', { type: 'button', class: 'rgm-chip', onclick: function () { Sheet.close(); act({ a: 'mgr_extend', delta_minutes: o[0] }); } }, o[1]); })),
      btn('تا اطلاعِ ثانوی', 'full', function () { Sheet.close(); act({ a: 'mgr_extend', until_revoked: true }); }, 'clock')]);
    sheetOpen({ title: 'تمدیدِ مهلت', body: body });
  }

  /* ─── چرخه‌ی زندگی ─── */
  function tick() { var e = document.getElementById('rgm-clk'); var r = remainNow(); if (e && r != null) e.textContent = clock(r); }
  function onShow() { shown = true; load(!D); clearInterval(pollT); clearInterval(tickT); pollT = setInterval(function () { if (!document.hidden) load(false); }, 9000); tickT = setInterval(tick, 1000); }
  function onHide() { shown = false; clearInterval(pollT); clearInterval(tickT); }
  function open(v) { if (v && TABS.some(function (t) { return t[0] === v; })) { view = v; if (D) { renderNav(); renderBody(); } } }
  function mount(el, ctx) {
    h = ctx.h; ic = ctx.ic; hx = ctx.hx; tg = ctx.tg; toast = ctx.toast; LS = ctx.LS; api = ctx.api; Sheet = ctx.Sheet; goHome = ctx.goHome;
    root = el; el.replaceChildren();
    heroEl = h('header', { class: 'rgm-hero', 'data-s': 'off' }); navEl = h('nav', { class: 'rgm-nav', 'aria-label': 'بخش‌های مرکز فرماندهی' }); bodyEl = h('div', { class: 'rgm-body' });
    el.append(div('rgm-top', [h('button', { type: 'button', class: 'rgm-x', 'aria-label': 'بازگشت', onclick: function () { hx.tap(); goHome(); } }, ic('chev')), h('h2', { text: 'مرکزِ فرماندهیِ رهگشا' })]), heroEl, navEl, bodyEl);
    heroEl.append(div('rgm-load', ['…'])); renderNav(); renderBody();
    document.addEventListener('visibilitychange', function () { if (shown && !document.hidden) load(false); });
  }
  window.HubRgm = { mount: mount, onShow: onShow, onHide: onHide, open: open };
})();
