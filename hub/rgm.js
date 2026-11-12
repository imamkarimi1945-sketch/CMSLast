/* «مرکز فرماندهیِ رهگشا» — طراحیِ سوم (Command Deck) — رهگشای مدیر + نگهبان، فقط برای مدیر ارشد
   • تنبل بار می‌شود؛ داده از /hub/api/rgm/*؛ هر ۹ ثانیه تازه می‌شود (بدونِ ساختِ دوباره‌ی DOM وقتی فقط شمارنده‌ها عوض شده‌اند)
   • هیچ innerHTML با داده‌ی کاربر؛ فقط textContent؛ انیمیشن‌ها فقط transform/opacity و با prefers-reduced-motion خاموش می‌شوند */
(function () {
  'use strict';
  var BUILD = 'fx5', NS = 'http://www.w3.org/2000/svg';
  var h, ic, hx, tg, toast, LS, api, Sheet, goHome, openChat;
  var root, hdrEl, heroEl, navEl, bodyEl;
  var D = null, fetchedAt = 0, view = 'over', shown = false, pollT = 0, tickT = 0, loading = false, rendered = false;
  var F = { journal: 'all', capq: '', inc: 'open', acc: { dir: true } }, JR = { items: [], more: true, busy: false }, PPL = null;
  var FX = 'balanced', animIn = false, kIdx = 0, PT = { x: 180, y: 420 }, cntRaf = 0, heroSig = '', gidN = 0, H = {}, NAV = {}, fabWas = '';

  /* ═════════ ابزارها ═════════ */
  function fa(n) { return String(n == null ? '' : n).replace(/[0-9]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'[+d]; }); }
  function div(cls, kids) { return h.apply(null, ['div', { class: cls }].concat(kids || [])); }
  function sp(t, cls) { return h('span', { class: cls || null, text: t }); }
  function clamp(p) { return Math.max(0, Math.min(100, p)); }
  function dur(s) {
    s = Math.max(0, Math.round(s)); var d = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    if (d) return fa(d) + ' روز' + (hh ? ' و ' + fa(hh) + ' ساعت' : '');
    if (hh) return fa(hh) + ' ساعت' + (m ? ' و ' + fa(m) + ' دقیقه' : '');
    return fa(m) + ' دقیقه';
  }
  function clock(s) { s = Math.max(0, Math.round(s)); var hh = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; function p(n) { return (n < 10 ? '0' : '') + n; } return fa(p(hh) + ':' + p(m) + ':' + p(x)); }
  function svg(tag, attrs) { var n = document.createElementNS(NS, tag); for (var k in attrs) n.setAttribute(k, attrs[k]); return n; }
  function ago(ts) {
    if (!ts || !D) return '';
    var a = new Date(ts).getTime(), b = new Date(D.now).getTime(); if (isNaN(a) || isNaN(b)) return '';
    var s = Math.max(0, (b - a) / 1000 + (Date.now() - fetchedAt) / 1000);
    return s < 60 ? 'همین الان' : s < 3600 ? fa(Math.floor(s / 60)) + ' دقیقه پیش' : s < 86400 ? fa(Math.floor(s / 3600)) + ' ساعت پیش' : fa(Math.floor(s / 86400)) + ' روز پیش';
  }
  function emo(label) { var m = /^(\p{Extended_Pictographic}\uFE0F?)\s*/u.exec(label || ''); return m ? [m[1], label.slice(m[0].length)] : ['◆', label]; }

  function ring(pct, color, r, w, animate) {
    var C = 2 * Math.PI * r, d = 2 * (r + w), s = svg('svg', { viewBox: '0 0 ' + d + ' ' + d, class: 'ring' });
    s.append(svg('circle', { cx: r + w, cy: r + w, r: r, fill: 'none', stroke: 'rgba(128,128,128,.22)', 'stroke-width': w }));
    var off = C * (1 - clamp(pct) / 100);
    var a = svg('circle', { cx: r + w, cy: r + w, r: r, fill: 'none', stroke: color, 'stroke-width': w, 'stroke-linecap': 'round', 'stroke-dasharray': C });
    a.style.strokeDashoffset = animate ? C : off; a.style.transition = 'stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1), stroke .5s';
    if (animate) setTimeout(function () { a.style.strokeDashoffset = off; }, 60);
    s.append(a); s.__arc = a; s.__C = C; return s;
  }
  function spark(vals, color, animate, hgt) {
    var v = (vals || []).filter(function (x) { return x != null; }), Hh = hgt || 62;
    var s = svg('svg', { viewBox: '0 0 320 ' + Hh, class: 'rgm-spark', preserveAspectRatio: 'none' });
    if (v.length < 2) return s;
    var gid = 'rgs' + (++gidN), df = svg('defs', {}), lg = svg('linearGradient', { id: gid, x1: 0, y1: 0, x2: 0, y2: 1 });
    lg.append(svg('stop', { offset: '0', 'stop-color': color, 'stop-opacity': '.38' }), svg('stop', { offset: '1', 'stop-color': color, 'stop-opacity': '0' })); df.append(lg);
    var mn = Math.min.apply(null, v), mx = Math.max.apply(null, v), rg = Math.max(1, mx - mn), pts = v.map(function (y, i) { return [i * 320 / (v.length - 1), Hh - 10 - (y - mn) / rg * (Hh - 20)]; });
    var d = 'M' + pts.map(function (p) { return p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' L'), last = pts[pts.length - 1];
    s.append(df, svg('path', { d: d + ' L320 ' + Hh + ' L0 ' + Hh + 'Z', fill: 'url(#' + gid + ')', class: animate ? 'ar fadein' : 'ar' }),
      svg('path', { d: d, pathLength: 1, fill: 'none', stroke: color, 'stroke-width': 2.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: animate ? 'ln draw' : 'ln' }),
      svg('circle', { cx: last[0], cy: last[1], r: 7, fill: color, opacity: '.28', class: 'dotp' }), svg('circle', { cx: last[0], cy: last[1], r: 3.4, fill: '#fff' }));
    return s;
  }
  function btn(text, cls, fn, icon) { return h('button', { type: 'button', class: 'rgm-b ' + (cls || ''), onclick: function (e) { hx.tap(); fn(e); } }, icon ? ic(icon) : null, text); }
  function sw(on, fn) { return h('button', { type: 'button', class: 'rgm-sw' + (on ? ' on' : ''), role: 'switch', 'aria-checked': on ? 'true' : 'false', onclick: function () { hx.sel(); fn(!on); } }); }
  function seg(opts, val, fn) { return h('div', { class: 'rgm-seg' }, opts.map(function (o) { return h('button', { type: 'button', class: val === o[0] ? 'on' : '', onclick: function () { hx.sel(); fn(o[0]); } }, o[1]); })); }
  function card(title, icon, kids, cls, extra) { return div('rgm-card ' + (cls || ''), [title ? h('h4', { class: 'rgm-h' }, icon ? h('span', { class: 'hico' }, ic(icon)) : null, sp(title), h('i', { class: 'sp' }), extra || null) : null].concat(kids)); }
  function li(title, sub, end) { return div('rgm-li', [div('m', [div('t', [title]), sub ? div('s', [sub]) : null]), end || null]); }
  function empty(t, icon) {
    var s = svg('svg', { viewBox: '0 0 64 64', class: 'rgm-ill' });
    s.append(svg('path', { d: 'M32 6 54 14v16c0 14-9 25-22 30C19 55 10 44 10 30V14z', fill: 'none', stroke: 'currentColor', 'stroke-width': 2.4, 'stroke-linejoin': 'round' }), svg('path', { d: 'm22 32 7 7 14-15', fill: 'none', stroke: 'currentColor', 'stroke-width': 3, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
    return div('rgm-empty', [s, h('p', { text: t })]);
  }
  function skeleton() { return div('rgm-skel', [div('sk a'), div('sk b'), div('sk c'), div('sk c')]); }
  function lvTag(l) { return h('span', { class: 'rgm-tag l' + l, text: ['', 'مشکوک', 'خصمانه', 'بحرانی'][l] || 'سطح ' + fa(l) }); }
  function sheetOpen(o) { o.body = div('rgm-sh', [o.body]); Sheet.open(o); }
  function sheetSet(n) { Sheet.set(div('rgm-sh', [n])); }
  function acc(key, title, icon, kids, sub) {
    var open = F.acc[key] === true, body = div('acc-b', kids), box = div('rgm-acc' + (open ? ' open' : ''), []);
    var head = h('button', { type: 'button', class: 'acc-h', onclick: function () { hx.sel(); F.acc[key] = !(F.acc[key] === true); box.classList.toggle('open'); } }, h('span', { class: 'hico' }, ic(icon)), div('mm', [h('b', { text: title }), sub ? h('small', { text: sub }) : null]), h('span', { class: 'chv' }, ic('chev')));
    box.append(head, body); return box;
  }

  function kpi(label, val, tone, sub, icon, big) {
    var b = h('b', { text: val == null ? '—' : fa(animIn && typeof val === 'number' ? 0 : val) });
    if (typeof val === 'number') b.dataset.n = val;
    var n = h('div', { class: 'rgm-k ' + (tone || '') + (big ? ' big' : '') }, h('span', { class: 'ki' }, icon ? ic(icon) : null), b, sp(label), sub ? h('i', { text: sub }) : null);
    if (animIn) { n.classList.add('rgm-enter'); n.style.setProperty('--i', kIdx++); }
    return n;
  }
  function runCount() {
    cancelAnimationFrame(cntRaf);
    var els = Array.prototype.slice.call(bodyEl.querySelectorAll('b[data-n]')), t0 = performance.now();
    if (!els.length) return;
    (function step(now) {
      var k = Math.min(1, (now - t0) / 900), e = 1 - Math.pow(1 - k, 3);
      els.forEach(function (el) { el.textContent = fa(Math.round(+el.dataset.n * e)); });
      if (k < 1) cntRaf = requestAnimationFrame(step);
    })(t0);
  }

  /* سطحِ جلوه‌ها: ذخیره در localStorage؛ بدونِ انتخاب، روی گوشی‌های ضعیف خودکار «سبک» */
  function pickFx() {
    var v = LS && LS.get && LS.get('rgm_fx');
    if (v === 'full' || v === 'balanced' || v === 'lite') return v;
    var lowEnd = (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 3;
    return lowEnd ? 'lite' : 'balanced';
  }
  function setFx(v) { FX = v; if (LS && LS.set) LS.set('rgm_fx', v); if (root) root.dataset.fx = v; }

  /* انفجارِ ذرات + موجِ لمس */
  var BURST = { mgr_grant: '#22c55e', gd_unlock: '#22c55e', gd_close: '#38bdf8', gd_release: '#a78bfa', mgr_full: '#f59e0b', gd_lock: '#ef4444', mgr_revoke: '#94a3b8', gd_contain: '#f97316', mgr_directive: '#38bdf8' };
  function burst(x, y, color) {
    if (FX === 'lite' || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
    var box = h('div', { class: 'rgm-burst' });
    for (var i = 0; i < 18; i++) {
      var ang = Math.PI * 2 * i / 18 + Math.random() * .4, dist = 50 + Math.random() * 70, pt = h('i', { class: i % 3 ? 'c' : 'r' });
      pt.style.cssText = 'left:' + x + 'px;top:' + y + 'px;--dx:' + Math.cos(ang) * dist + 'px;--dy:' + Math.sin(ang) * dist + 'px;--r:' + (Math.random() * 540 - 270) + 'deg;--c:' + color + ';animation-delay:' + (Math.random() * 60) + 'ms';
      box.append(pt);
    }
    document.body.append(box); setTimeout(function () { box.remove(); }, 1000);
  }
  function ripple(el, e) {
    var r = el.getBoundingClientRect(), d = Math.max(r.width, r.height) * 1.7, s = document.createElement('span');
    s.className = 'rgm-rip'; s.style.cssText = 'width:' + d + 'px;height:' + d + 'px;left:' + (e.clientX - r.left - d / 2) + 'px;top:' + (e.clientY - r.top - d / 2) + 'px';
    el.append(s); setTimeout(function () { s.remove(); }, 700);
  }
  function onPointer(e) {
    if (!shown) return;
    PT = { x: e.clientX, y: e.clientY };
    if (FX === 'lite') return;
    var t = e.target && e.target.closest && e.target.closest('.rgm-b,.rgm-chip,.rgm-mc,.rgm-nav button,.rgm-sw,.rgm-seg button,.dk,.rgm-tile');
    if (t) ripple(t, e);
  }

  /* ═════════ شبکه ═════════ */
  function load(first) {
    if (loading) return Promise.resolve();
    loading = true;
    return api('/hub/api/rgm/overview' + (first ? '?fresh=1' : '')).then(function (d) { setData(d); }).catch(function (e) {
      if (!D) bodyEl.replaceChildren(empty(e && e.code === 403 ? 'این بخش فقط برای مدیر ارشد است.' : 'اتصال برقرار نشد؛ دوباره امتحان کنید.'));
    }).then(function () { loading = false; }, function () { loading = false; });
  }
  var VOL = { now: 1, now_fa: 1, remaining: 1, elapsed: 1, pct_left: 1, usage: 1, last_round_fa: 1 }, lastSig = '';
  function setData(d) {
    var sig = JSON.stringify(d, function (k, v) { return VOL[k] ? undefined : v; });
    D = d; fetchedAt = Date.now();
    updateHero(); updateNav();
    if (sig === lastSig) return;
    lastSig = sig;
    var ae = document.activeElement;
    if (ae && root.contains(ae) && /^(INPUT|TEXTAREA)$/.test(ae.tagName)) return;
    renderBody(!rendered); rendered = true;
  }
  function act(body, quiet) {
    var px = PT.x, py = PT.y;
    return api('/hub/api/rgm/act', body).then(function (r) {
      if (r && r.overview) setData(r.overview);
      if (!quiet) toast(r && r.message ? String(r.message).split('\n')[0].slice(0, 90) : (r && r.ok ? 'انجام شد' : 'انجام نشد'));
      (r && r.ok ? hx.ok : hx.err)();
      if (r && r.ok && BURST[body.a]) burst(px, py, BURST[body.a]);
      return r;
    }).catch(function (e) { hx.err(); toast(e && e.data && e.data.message ? e.data.message : 'خطا؛ دوباره امتحان کنید.'); return null; });
  }
  function confirmSheet(title, text, label, danger, fn) {
    sheetOpen({ title: title, body: div('', [h('p', { class: 'rgm-sub', style: 'font-size:14px;margin:6px 0 14px', text: text })]), foot: btn(label, danger ? 'd full' : 'p full', function () { Sheet.close(); fn(); }) });
  }

  /* ═════════ نشانِ امنیتیِ سیستم (Emblem) ═════════ */
  var SH = 'M80 8 L140 30 V84 C140 126 112 156 80 172 C48 156 20 126 20 84 V30 Z';
  function buildEmblem() {
    var s = svg('svg', { viewBox: '-14 -6 188 196', class: 'emb' }), df = svg('defs', {});
    var g = svg('linearGradient', { id: 'rgEg', x1: 0, y1: 0, x2: 0, y2: 1 }); g.append(svg('stop', { offset: '0', class: 's0' }), svg('stop', { offset: '1', class: 's1' }));
    var cp = svg('clipPath', { id: 'rgEc' }); cp.append(svg('path', { d: SH })); df.append(g, cp);
    var tk = svg('g', { class: 'emb-ticks' });
    for (var i = 0; i < 36; i++) { var a = i * 10 * Math.PI / 180, r1 = 88, r2 = i % 3 ? 91 : 95; tk.append(svg('line', { x1: 80 + Math.cos(a) * r1, y1: 92 + Math.sin(a) * r1, x2: 80 + Math.cos(a) * r2, y2: 92 + Math.sin(a) * r2 })); }
    var clipG = svg('g', { 'clip-path': 'url(#rgEc)' });
    clipG.append(svg('path', { d: 'M20 48H140M20 78H140M20 108H140M20 138H140M50 8V172M80 8V172M110 8V172', class: 'emb-hex' }), svg('rect', { x: 20, y: -30, width: 120, height: 34, class: 'emb-scan' }));
    s.append(df, tk, svg('path', { d: SH, class: 'emb-rp' }), svg('path', { d: SH, class: 'emb-rp r2' }), svg('path', { d: SH, class: 'emb-fill', fill: 'url(#rgEg)' }), clipG, svg('path', { d: SH, class: 'emb-line', pathLength: 1 }));
    H.embIc = div('emb-ic', []); H.embBadge = div('emb-badge', []);
    return div('rgm-emb', [s, H.embIc, H.embBadge]);
  }

  /* ═════════ هدر + هیرو (یک‌بار ساخته می‌شوند؛ فقط مقدارها به‌روز می‌شوند) ═════════ */
  function state() { return !D ? 'off' : D.guard.locked ? 'lock' : D.mgr.active ? 'on' : 'off'; }
  function remainNow() { if (!D || !D.mgr.timer.active || !D.mgr.timer.timed) return null; return Math.max(0, D.mgr.timer.remaining - (Date.now() - fetchedAt) / 1000); }
  function modeFa(m) { return { off: 'خاموش', watch: 'هشدار', protect: 'هشدار+مهار', full: 'کامل' }[m] || m; }
  function threatLevel() { var m = 0; if (D) D.incidents.forEach(function (i) { if (i.status !== 'closed') m = Math.max(m, i.level); }); return D && D.guard.locked ? 3 : m; }

  function buildHeader() {
    H.live = h('span', { class: 'live', text: 'زنده' });
    hdrEl.replaceChildren(
      h('button', { type: 'button', class: 'rgm-x', 'aria-label': 'بازگشت', onclick: function () { hx.tap(); goHome(); } }, ic('chev')),
      div('ttl', [h('h2', { text: 'مرکزِ فرماندهی' }), div('sub', [sp('رهگشا · نگهبان'), h('i', { class: 'ver', text: 'v' + BUILD })])]),
      h('span', { class: 'lv' }, h('i'), H.live),
      h('button', { type: 'button', class: 'rgm-x ai', 'aria-label': 'گفتگو با رهگشا', onclick: function () { hx.tap(); if (openChat) openChat(); } }, ic('sparkle')));
  }
  function buildHero() {
    var pts = [];
    for (var i = 0; i < 12; i++) pts.push(h('i', { class: 'pt', style: '--x:' + (5 + i * 8) + '%;--d:' + (5 + (i * 7) % 6) + 's;--dl:-' + ((i * 13) % 9) + 's' }));
    var fx = div('rgm-fx', [div('bl b1'), div('bl b2'), div('hexg'), div('haz')].concat(pts));
    H.title = h('h3'); H.desc = h('p'); H.lvd = div('lvd', [h('i'), h('i'), h('i'), sp('', 'lvt')]);
    H.clk = h('b', { class: 'tm' }); H.clkLb = sp('', 'tl'); H.pb = h('i'); H.cap = div('rgm-cap', [div('row', [H.clk, H.clkLb]), div('pb', [H.pb])]);
    H.s1 = h('b'); H.s2 = h('b'); H.s3 = h('b'); H.s4 = h('b');
    function st(v, l) { return div('st', [v, sp(l)]); }
    var strip = div('rgm-strip', [st(H.s1, 'رویدادِ باز'), st(H.s2, 'مهارشده'), st(H.s3, 'دورِ بعد'), st(H.s4, 'مدیرِ آنلاین')]);
    H.cta = div('rgm-cta'); H.dock = div('rgm-dock');
    heroEl.replaceChildren(fx, buildEmblem(), H.title, H.desc, H.lvd, H.cap, strip, H.cta, H.dock);
  }
  function dk(icon, label, fn, cls) { return h('button', { type: 'button', class: 'dk ' + (cls || ''), onclick: function (e) { hx.tap(); fn(e); } }, h('span', { class: 'c' }, ic(icon)), h('small', { text: label })); }
  function updateHero() {
    if (!D || !H.title) return;
    var s = state(), t = D.mgr.timer, g = D.guard, k = D.kpi, rem = remainNow(), lv = threatLevel();
    heroEl.dataset.s = s; heroEl.dataset.lv = lv;
    H.title.textContent = s === 'lock' ? 'قفلِ اضطراری فعال است' : s === 'on' ? 'رهگشا مدیر است' : (k.incidents_open ? 'رویدادِ امنیتیِ باز دارید' : 'سیستم امن است');
    H.desc.textContent = s === 'lock' ? (g.lock_reason || 'نگهبان سیستم را قفل کرد.') : s === 'on' ? (t.timed ? 'مدیریت تا پایانِ مهلت با رهگشاست.' : 'تا اطلاعِ ثانوی مدیریت با رهگشاست.') : (k.incidents_open ? 'نگهبان رویدادهای باز را نشان می‌دهد.' : 'مدیریت دستِ شماست؛ نگهبان بیدار است.');
    H.lvd.children[3].textContent = ['بدونِ تهدید', 'تهدیدِ سطح ۱', 'تهدیدِ سطح ۲', 'تهدیدِ بحرانی'][lv];
    for (var i = 0; i < 3; i++) H.lvd.children[i].className = i < lv ? 'on l' + lv : '';
    H.cap.style.display = t.active ? '' : 'none';
    H.pb.style.transform = 'scaleX(' + (t.active ? (t.timed ? clamp(rem / t.total * 100) / 100 : 1) : 0) + ')';
    H.clkLb.textContent = t.timed ? 'تا پایانِ مهلت' : 'مدتِ مدیریتِ رهگشا';
    H.s1.textContent = fa(k.incidents_open); H.s2.textContent = fa(k.incidents_contained); H.s4.textContent = fa(k.online);
    H.s3.textContent = D.mgr.active ? fa((D.mgr.next_round_fa || '—').split(' ').slice(-1)[0]) : '—';
    H.s1.parentNode.className = 'st' + (k.incidents_open ? ' bad' : '');
    var sig = [s, lv, k.incidents_open].join('|');
    if (sig !== heroSig) {
      heroSig = sig;
      H.embIc.replaceChildren(ic(s === 'lock' ? 'lock' : s === 'on' ? 'bolt' : (k.incidents_open ? 'alert' : 'shield')));
      H.embBadge.textContent = k.incidents_open ? fa(k.incidents_open) : ''; H.embBadge.style.display = k.incidents_open ? '' : 'none';
    }
    var bk = s + (D.mgr.active ? 1 : 0);
    if (bk !== H.bk) {
      H.bk = bk;
      H.cta.replaceChildren(s === 'lock'
        ? btn('رفعِ قفلِ اضطراری', 'ok full big', function () { act({ a: 'gd_unlock' }); }, 'unlock')
        : D.mgr.active
          ? btn('خاموشیِ فوریِ رهگشا', 'ghost full', function () { confirmSheet('خاموشیِ فوریِ رهگشای مدیر', 'مدیریت همین لحظه به شما برمی‌گردد و گزارشِ این دوره در پیوی می‌آید.', 'بله، خاموش کن', true, function () { act({ a: 'mgr_revoke' }); }); }, 'power')
          : btn('بسپار به رهگشا', 'ok full big', grantSheet, 'bolt'));
      var items = [];
      if (D.mgr.active) items.push(dk('brain', 'دورِ فوری', function () { act({ a: 'mgr_round' }); }), dk('clock', 'تمدید', extendSheet));
      items.push(s === 'lock' ? dk('unlock', 'رفعِ قفل', function () { act({ a: 'gd_unlock' }); }, 'ok') : dk('lock', 'قفلِ اضطراری', lockSheet, 'warn'), dk('inbox', 'بکاپ', function () { act({ a: 'gd_backup' }); }), dk('list', 'گزارش', reportSheet));
      H.dock.replaceChildren.apply(H.dock, items);
    }
    tick();
  }
  function tick() {
    if (!D || !H.clk) return;
    var t = D.mgr.timer, rem = remainNow();
    if (t.active) H.clk.textContent = clock(rem != null ? rem : t.elapsed + (Date.now() - fetchedAt) / 1000);
    if (H.live) { var sec = Math.round((Date.now() - fetchedAt) / 1000); H.live.textContent = sec < 4 ? 'زنده' : fa(sec) + ' ثانیه پیش'; }
  }

  /* ═════════ ناوبری: قرصِ بازشونده ═════════ */
  var TABS = [['over', 'نمای کلی', 'pulse'], ['caps', 'اختیارات', 'sliders'], ['guard', 'نگهبان', 'shield'], ['jr', 'ژورنال', 'book'], ['set', 'تنظیمات', 'gear']];
  function buildNav() {
    NAV.btns = {}; NAV.badge = sp('', 'bd'); navEl.replaceChildren();
    TABS.forEach(function (t) {
      var b = h('button', { type: 'button', onclick: function () { if (view !== t[0]) { hx.sel(); view = t[0]; updateNav(); renderBody(true); window.scrollTo(0, 0); } } }, ic(t[2]), h('span', { class: 'lb', text: t[1] }));
      NAV.btns[t[0]] = b; navEl.append(b);
    });
    NAV.btns.guard.append(NAV.badge);
  }
  function updateNav() {
    if (!NAV.btns) return;
    TABS.forEach(function (t) { NAV.btns[t[0]].classList.toggle('on', view === t[0]); });
    if (heroEl) heroEl.dataset.c = view === 'over' ? '0' : '1';
    var n = D ? D.kpi.incidents_open : 0; NAV.badge.textContent = fa(n); NAV.badge.style.display = n ? '' : 'none';
  }
  function renderBody(animate) {
    if (!D) { bodyEl.replaceChildren(skeleton()); return; }
    var y = window.scrollY, fn = { over: bodyOver, caps: bodyCaps, guard: bodyGuard, jr: bodyJournal, set: bodySet }[view];
    animIn = !!animate && FX !== 'lite'; kIdx = 0;
    bodyEl.replaceChildren.apply(bodyEl, fn());
    if (animIn) {
      Array.prototype.forEach.call(bodyEl.children, function (c, i) { if (!c.classList.contains('rgm-bento')) { c.classList.add('rgm-enter'); c.style.setProperty('--i', Math.min(i, 9)); } });
      runCount();
    } else window.scrollTo(0, y);
    animIn = false;
  }

  /* ═════════ ۱) نمای کلی (Bento) ═════════ */
  function bodyOver() {
    var k = D.kpi, sc = k.score == null ? 0 : k.score, col = sc >= 80 ? '#2fb344' : sc >= 55 ? '#f08c00' : '#e5484d', tone = sc >= 80 ? 'ok' : sc >= 55 ? 'warn' : 'bad';
    var tr = D.trend.map(function (x) { return x.score; });
    var hero = h('div', { class: 'rgm-k score ' + tone }, div('gauge', [ring(sc, col, 34, 7, animIn), h('b', { text: fa(sc) })]),
      div('tx', [h('b', { text: 'امتیازِ امنیتِ سیستم' }), h('i', { text: sc >= 80 ? 'وضعیت عالی است.' : sc >= 55 ? 'چند نکته نیاز به توجه دارد.' : 'وضعیت نگران‌کننده است؛ نگهبان را ببینید.' }),
        h('i', { text: 'وضعیتِ ربات: ' + ({ normal: 'عادی', bad: 'احتیاطی', danger: 'خطر', aps: 'APS' }[k.system_status] || k.system_status) })]),
      tr.filter(function (x) { return x != null; }).length > 1 ? div('bg', [spark(tr, col, animIn, 56)]) : null);
    if (animIn) { hero.classList.add('rgm-enter'); hero.style.setProperty('--i', kIdx++); }
    var bento = div('rgm-bento', [hero,
      kpi('رویدادِ باز', k.incidents_open, k.incidents_open ? 'bad' : 'ok', fa(k.incidents_24h) + ' در ۲۴ ساعت', 'alert'), kpi('فردِ مهارشده', k.incidents_contained, k.incidents_contained ? 'warn' : 'ok', null, 'shield'),
      kpi('دورِ ۲۴ ساعت', k.rounds_24h, 'cy', fa(k.rounds_ok_24h) + ' موفق', 'brain'), kpi('مدیرِ آنلاین', k.online, 'cy', 'از ' + fa(k.admins) + ' مدیر', 'users'),
      kpi('غریبه‌ها', k.strangers, k.strangers ? 'warn' : 'ok', null, 'eye'), kpi('در انتظارِ تأیید', k.pending, k.pending ? 'warn' : 'ok', null, 'inbox'),
      kpi('اقدامِ مخرب', k.destructive, k.destructive > 3 ? 'bad' : 'ok', null, 'trash'), kpi('بازیکنِ اخطاری', k.warned, 'warn', null, 'alert'),
      kpi('مسابقه بدونِ نتیجه', k.matches_pending, k.matches_pending ? 'warn' : 'ok', fa(k.matches_today) + ' مسابقه‌ی امروز', 'clock'), kpi('ژورنال', k.journal_total, 'vi', null, 'book')]);
    var out = [bento];
    /* «رهگشا چه فکر می‌کند» */
    var lastRound = D.journal.filter(function (j) { return j.kind === 'round'; })[0];
    out.push(card('آخرین برداشتِ رهگشا', 'brain', [lastRound
      ? div('rgm-think', [div('dots', [h('i'), h('i'), h('i')]), h('p', { text: (lastRound.body || '').replace(/\n+/g, ' ').slice(0, 220) || 'گزارشی ثبت نشده.' }), div('mt', [sp(ago(lastRound.ts)), btn('خواندنِ کامل', 'sm', function () { jSheet(lastRound.id); })])])
      : empty('هنوز دورِ مدیریتی‌ای انجام نشده.')]));
    out.push(queueCard());
    var evs = [];
    D.incidents.slice(0, 5).forEach(function (i) { evs.push({ t: i.ts, k: 'sec', lv: i.level, a: i.title, b: i.actor_name }); });
    D.journal.slice(0, 6).forEach(function (j) { evs.push({ t: j.ts, k: 'ai', ok: j.ok, a: j.title, b: ((j.body || '').split('\n')[0] || '').slice(0, 70) }); });
    evs.sort(function (a, b) { return a.t < b.t ? 1 : -1; });
    out.push(card('رویدادهای زنده', 'clock', evs.length ? [div('rgm-feed', evs.slice(0, 8).map(function (e, i) {
      return div('fd ' + (e.k === 'sec' ? 'sec l' + e.lv : 'ai' + (e.ok === false ? ' bad' : '')) + (i === 0 ? ' live' : ''), [h('span', { class: 'fi' }, ic(e.k === 'sec' ? 'shield' : 'brain')), div('fm', [div('a', [e.a]), e.b ? div('b', [e.b]) : null]), sp(ago(e.t), 'ft')]);
    }))] : [empty('هنوز رویدادی ثبت نشده.')]));
    if (D.risk.length) out.push(card('ریسکِ لحظه‌ایِ مدیران', 'alert', D.risk.map(function (r) { return li(r.replace(/^- /, ''), null); })));
    return out;
  }

  /* صفِ کارِ رهگشا: کارهای عملیاتیِ واقعی که از دیتابیس درمی‌آیند */
  var QICON = { match: '♟️', task: '📌', access: '🔑', admin: '👤', player: '⚠️', tournament: '🏆', ops: '🧩' };
  function queueCard() {
    var q = D.queue || [], open = q.filter(function (t) { return !t.cooling; }), ini = D.mgr.initiative || 'active';
    var kids = q.length ? [div('rgm-queue', q.map(function (t) {
      var ev = div('qe', t.evidence.map(function (e) { return div('', [e]); })), row = div('qt' + (t.cooling ? ' cool' : '') + (t.prio >= 2 ? ' hi' : ''), [
        div('qh', [h('span', { class: 'qi', text: QICON[t.kind] || '•' }), div('qm', [h('b', { text: t.title }), h('small', { text: t.cooling ? 'به‌تازگی پیگیری شد' : (t.prio >= 2 ? 'اولویتِ بالا' : 'اولویتِ عادی') })]), ic('chev')]), ev]);
      row.querySelector('.qh').addEventListener('click', function () { hx.sel(); row.classList.toggle('open'); }); return row;
    }))] : [empty('الان کارِ بازی در صف نیست 🎉')];
    kids.push(h('p', { class: 'rgm-sub', style: 'margin:10px 0 0', text: 'رهگشا در هر دور برای هر مورد اقدام می‌کند یا دلیلِ نکردن را می‌نویسد. سطحِ ابتکار: «' + ({ report: 'گزارش‌دهنده', active: 'فعال', proactive: 'پیش‌قدم' }[ini] || ini) + '» (از تنظیمات عوض می‌شود).' }));
    return card('صفِ کارِ رهگشا', 'list', kids, '', sp(fa(open.length) + ' باز', 'rgm-tag' + (open.length ? ' l1' : ' ok')));
  }

  /* ═════════ ۲) اختیارات (کاشی‌ها) ═════════ */
  function bodyCaps() {
    var m = D.mgr, full = m.full_access, out = [];
    out.push(div('rgm-gold' + (full ? ' on' : ''), [div('gt', [h('b', { text: '👑 دسترسیِ کامل' }), h('small', { text: full ? 'روشن — رهگشا در همه‌ی حوزه‌ها اقدام می‌کند' : 'خاموش — اختیارات به تفکیکِ حوزه' }), h('p', { text: 'سقفِ هر دور: ' + fa(m.limits.writes) + ' اقدام و ' + fa(m.limits.destructive) + ' اقدامِ مخرب. قفل‌های سخت (مثل اقدام علیهِ مدیر ارشد) همیشه برقرارند.' })]),
      sw(full, function (v) { confirmSheet(v ? 'روشن‌کردنِ دسترسیِ کامل' : 'خاموش‌کردنِ دسترسیِ کامل', v ? 'رهگشا در همه‌ی حوزه‌ها می‌تواند اقدام کند.' : 'اختیارات به تنظیمِ تک‌تکِ حوزه‌ها برمی‌گردد.', 'تأیید', v, function () { act({ a: 'mgr_full', enabled: v }); }); })]));
    out.push(card('پیش‌تنظیم', 'sliders', [div('rgm-presets', [['cautious', 'محتاطانه', 'eye', 'فقط خواندن و گزارش'], ['balanced', 'متعادل', 'sliders', 'کارهای روتین + دفاع'], ['full', 'کامل', 'crown', 'همه‌چیز']].map(function (p) {
      return h('button', { type: 'button', class: 'rgm-prs', onclick: function () { hx.sel(); act({ a: 'mgr_preset', preset: p[0] }); } }, h('span', { class: 'pi' }, ic(p[2])), h('b', { text: p[1] }), h('small', { text: p[3] }));
    }))]));
    var q = h('input', { class: 'rgm-in', placeholder: 'جست‌وجوی حوزه…', value: F.capq, oninput: function (e) { F.capq = e.target.value; paint(); } });
    var grid = div('rgm-tiles'), brain = div('rgm-brainlist');
    function paint() {
      var s = F.capq.trim(), cats = D.caps.filter(function (c) { return c.kind === 'cat' && (!s || c.label.indexOf(s) > -1); }), br = D.caps.filter(function (c) { return c.kind === 'brain' && (!s || c.label.indexOf(s) > -1); });
      grid.replaceChildren.apply(grid, cats.length ? cats.map(function (c) {
        var e = emo(c.label), t = h('div', { class: 'rgm-tile' + (c.on ? ' on' : '') }, h('span', { class: 'em', text: e[0] }), h('b', { text: e[1] }), h('small', { text: fa(c.tools) + ' ابزار' }),
          sw(c.on, function (v) { c.on = v; act({ a: 'mgr_caps', keys: [c.key], enabled: v }, true).then(function (r) { if (r) toast(v ? 'روشن شد' : 'خاموش شد'); }); paint(); }));
        t.addEventListener('click', function (ev) { if (!ev.target.closest('.rgm-sw')) toolsSheet(c); }); return t;
      }) : [empty('حوزه‌ای پیدا نشد.')]);
      brain.replaceChildren.apply(brain, br.map(function (c) { return li(c.label, c.desc, sw(c.on, function (v) { c.on = v; act({ a: 'mgr_caps', keys: [c.key], enabled: v }, true); paint(); })); }));
    }
    out.push(card('حوزه‌ها', 'grid', [q, h('div', { style: 'height:10px' }), grid], '', sp(fa(m.caps_on) + '/' + fa(m.caps_all), 'rgm-tag')));
    out.push(card('رفتارِ رهگشا', 'brain', [brain]));
    paint(); return out;
  }
  function toolsSheet(c) {
    sheetOpen({ title: c.label, body: div('', [h('p', { class: 'rgm-sub', text: 'ابزارهایی که رهگشا با روشن‌بودنِ این حوزه می‌تواند صدا بزند:' }), div('rgm-pills', c.tool_names.map(function (n) { return sp(n, 'rgm-tag'); }))]) });
  }

  /* ═════════ ۳) نگهبان ═════════ */
  var MODES = [['watch', 'فقط هشدار', 'eye', 'تهدید را می‌بیند و فوراً خبر می‌دهد؛ خودش اقدامی نمی‌کند.', 1], ['protect', 'هشدار + مهار', 'shield', 'فردِ خصمانه را همان لحظه مهار می‌کند: قطعِ رهگشا، غیرفعال‌کردن، بلاکِ غریبه.', 2], ['full', 'کامل', 'lock', 'مهار + قفلِ اضطراری (APS و خاموشیِ ربات) در تهدیدِ بحرانی + یک دورِ بررسی.', 3]];
  var SENS = [['low', 'کم'], ['medium', 'متوسط'], ['high', 'بالا']];
  function bodyGuard() {
    var g = D.guard, out = [];
    out.push(div('rgm-card glass rgm-lock' + (g.locked ? ' on danger' : ''), [div('big', [div('rp'), div('rp r2'), ic(g.locked ? 'lock' : 'unlock')]), h('h4', { text: g.locked ? 'قفلِ اضطراری روشن است' : 'سیستم آزاد است' }),
      h('p', { text: g.locked ? (g.lock_reason + ' — از ' + g.lock_since_fa + ' توسطِ ' + ({ guardian: 'نگهبان', boss: 'شما', rahgosha: 'رهگشا' }[g.lock_by] || g.lock_by)) : 'قفلِ اضطراری: وضعیتِ APS + خاموشیِ ربات و ورودِ مدیران. مدیر ارشد همیشه آزاد است.' }),
      g.locked ? btn('رفعِ قفل و برگشت به حالتِ قبل', 'ok full', function () { act({ a: 'gd_unlock' }); }, 'unlock') : btn('قفلِ اضطراریِ دستی', 'd full', lockSheet, 'lock')]));
    out.push(radarCard());
    var carousel = div('rgm-snap', MODES.map(function (m) {
      return h('button', { type: 'button', class: 'rgm-mc' + (g.mode === m[0] ? ' on' : ''), onclick: function () { hx.sel(); act({ a: 'gd_config', mode: m[0] }, true); } },
        h('span', { class: 'mi' }, ic(m[2])), h('b', { text: m[1] }), div('bars', [1, 2, 3].map(function (n) { return h('i', { class: n <= m[4] ? 'on' : '' }); })), h('small', { text: m[3] }), g.mode === m[0] ? sp('فعال', 'cur') : null);
    }));
    out.push(card('حالتِ نگهبان', 'shield', [carousel, h('p', { class: 'rgm-sub', style: 'margin:6px 0 0', text: g.eff_mode === g.mode ? 'حالتِ مؤثرِ الان همین است.' : 'حالتِ مؤثرِ الان «' + modeFa(g.eff_mode) + '» است؛ مهار و قفل فقط وقتی اعمال می‌شود که رهگشای مدیر روشن باشد یا «همیشه‌فعال» را بزنید.' })], '', sp(g.enabled ? 'روشن' : 'خاموش', 'rgm-tag ' + (g.enabled ? 'ok' : ''))));
    var th = g.thresholds, si = Math.max(0, SENS.map(function (x) { return x[0]; }).indexOf(g.sens));
    out.push(card('حساسیت', 'radar', [div('rgm-step', [h('i', { class: 'fl', style: 'transform:scaleX(' + (si / 2) + ')' })].concat(SENS.map(function (x, i) { return h('button', { type: 'button', class: i <= si ? 'on' : '', onclick: function () { hx.sel(); act({ a: 'gd_config', sens: x[0] }, true); } }, h('i'), h('span', { text: x[1] })); }))),
      h('p', { class: 'rgm-sub', style: 'margin:12px 0 0', text: 'آستانه‌ی امتیازِ ریسک در ۵ دقیقه: هشدار ' + fa(th.events[0]) + ' • مهار ' + fa(th.events[1]) + ' • قفل ' + fa(th.events[2]) + '. سیلِ درخواست: هشدار ' + fa(th.rate[0]) + ' و مهار ' + fa(th.rate[1]) + ' آپدیت در ۱۰ ثانیه.' })]));
    out.push(card('کلیدها', 'sliders', [
      li('نگهبان روشن باشد', 'خاموش‌کردن یعنی هیچ دیدبانی انجام نمی‌شود.', sw(g.enabled, function (v) { act({ a: 'gd_config', enabled: v }, true); })),
      li('همیشه‌فعال', 'مهار و قفل حتی وقتی رهگشای مدیر خاموش است.', sw(g.always, function (v) { act({ a: 'gd_config', always: v }, true); })),
      li('قفلِ اضطراریِ خودکار', 'در تهدیدِ بحرانی خودش قفل می‌کند.', sw(g.auto_lockdown, function (v) { act({ a: 'gd_config', auto_lockdown: v }, true); })),
      li('آینه در گروه فرماندهی', 'خلاصه‌ی رویدادها در گروه هم ثبت شود.', sw(g.ops_group, function (v) { act({ a: 'gd_config', ops_group: v }, true); }))]));
    out.push(incCard(), labCard());
    return out;
  }
  /* رادارِ تهدید: هر مدیر یک نقطه است؛ هرچه ریسک بیشتر، نزدیک‌تر به مرکز */
  function radarCard() {
    var wrap = div('rgm-radar', []), list = div('rgm-ppl', []);
    function blipPos(p, i) {
      var score = clamp(p.risk * 5 + p.incidents_7d * 14 + (p.contained ? 25 : 0)), r = 112 - score * 0.92, ang = ((p.id * 2654435761) % 360) * Math.PI / 180;
      return { x: 120 + Math.cos(ang) * r, y: 120 + Math.sin(ang) * r, score: score };
    }
    function paint(items) {
      var s = svg('svg', { viewBox: '0 0 240 240', class: 'rd' });
      [112, 78, 44].forEach(function (r) { s.append(svg('circle', { cx: 120, cy: 120, r: r, class: 'ring' })); });
      s.append(svg('path', { d: 'M8 120H232M120 8V232', class: 'axes' }));
      var sweep = svg('g', { class: 'sweep' }); sweep.append(svg('path', { d: 'M120 120 L120 8 A112 112 0 0 1 199 41 Z', class: 'wedge' })); s.append(sweep);
      items.forEach(function (p, i) {
        var q = blipPos(p, i), cls = !p.active ? 'off' : q.score > 60 ? 'hi' : q.score > 25 ? 'mid' : 'lo', g = svg('g', { class: 'blip ' + cls, transform: 'translate(' + q.x.toFixed(1) + ' ' + q.y.toFixed(1) + ')' });
        g.append(svg('circle', { r: 11, class: 'halo' }), svg('circle', { r: 5, class: 'dot' })); g.style.cursor = 'pointer'; g.addEventListener('click', function () { personSheet(p); }); s.append(g);
      });
      s.append(svg('circle', { cx: 120, cy: 120, r: 7, class: 'core' }));
      wrap.replaceChildren(s, div('rgm-rdl', [sp('● کم‌ریسک', 'lo'), sp('● متوسط', 'mid'), sp('● پرریسک', 'hi'), sp('○ مهارشده', 'off')]));
      list.replaceChildren.apply(list, items.length ? items.map(function (p) {
        var rk = clamp(p.risk * 5 + p.incidents_7d * 14), bar = h('div', { class: 'rgm-bar' }, h('i', { style: 'width:100%;transform:scaleX(' + (rk / 100) + ');background:' + (rk > 60 ? 'var(--bad)' : rk > 30 ? 'var(--warn)' : 'var(--ok)') }));
        var r = div('rgm-li pp', [div('m', [div('t', [p.name + (p.active ? '' : ' (غیرفعال)')]), div('s', [roleFa(p.role) + (p.incidents_7d ? ' • ' + fa(p.incidents_7d) + ' رویداد در ۷ روز' : '')]), bar]), ic('chev')]);
        r.style.cursor = 'pointer'; r.addEventListener('click', function () { personSheet(p); }); return r;
      }) : [empty('مدیری پیدا نشد.')]);
    }
    function loadPeople() { return api('/hub/api/rgm/people').then(function (r) { PPL = r.items; paint(PPL); }).catch(function () { wrap.replaceChildren(empty('بارگذاریِ مدیران ناموفق بود.')); }); }
    if (PPL) paint(PPL); else wrap.replaceChildren(div('rgm-skel', [div('sk c')]));
    loadPeople();
    radarCard.reload = loadPeople;
    return card('رادارِ مدیران', 'radar', [h('p', { class: 'rgm-sub', style: 'margin-top:-4px', text: 'هر نقطه یک مدیر است؛ هرچه ریسکش بیشتر، به مرکز نزدیک‌تر. روی نقطه بزنید.' }), wrap, list]);
  }
  function roleFa(r) { return r === 'security_manager' ? 'مسئول انتظامات' : r === 'tournament_manager' ? 'مسئول مسابقات' : (r || 'مدیر'); }
  function personSheet(p) {
    var kids = [div('rgm-pcard', [h('b', { text: p.name }), h('small', { text: roleFa(p.role) + (p.username ? ' • @' + p.username : '') + ' • آخرین فعالیت ' + (p.last_active || '—') }),
      div('rgm-pills', [sp('ریسکِ لحظه‌ای ' + fa(p.risk), 'rgm-tag' + (p.risk > 8 ? ' l3' : '')), sp(fa(p.incidents_7d) + ' رویداد در ۷ روز', 'rgm-tag'), sp(p.active ? 'فعال' : 'غیرفعال', 'rgm-tag' + (p.active ? ' ok' : '')), sp(p.ai_access ? 'دسترسی به رهگشا ✓' : 'بدونِ رهگشا', 'rgm-tag')])])];
    var foot = p.active
      ? btn('مهارِ ' + p.name, 'd full', function () { Sheet.close(); act({ a: 'gd_contain', uid: p.id, reason: 'مهارِ دستی از رادار' }).then(function () { if (radarCard.reload) radarCard.reload(); }); }, 'shield')
      : btn('بازگردانیِ ' + p.name, 'ok full', function () { Sheet.close(); act({ a: 'gd_release', uid: p.id }).then(function () { if (radarCard.reload) radarCard.reload(); }); }, 'reset');
    sheetOpen({ title: 'جزئیاتِ مدیر', body: div('', kids), foot: foot });
  }
  function labCard() {
    var inp = h('input', { class: 'rgm-in', placeholder: 'یک جمله بنویس و ببین نگهبان چه می‌کند…' }), res = div('', []);
    function run() {
      var t = inp.value.trim(); if (!t) return;
      api('/hub/api/rgm/act', { a: 'gd_classify', text: t }).then(function (r) {
        res.replaceChildren(div('rgm-row', [lvTag(r.level), r.level ? null : sp('بی‌خطر', 'rgm-tag ok')].filter(Boolean)), h('p', { class: 'rgm-sub', style: 'margin:8px 0 0', text: r.level ? (r.tags.join(' • ') + ' — ' + (r.level === 1 ? 'فقط هشدار' : r.level === 2 ? 'مهارِ فرد' : 'مهار + قفلِ اضطراری') + ' (در حالتِ مؤثرِ مناسب)') : 'هیچ واکنشی ایجاد نمی‌شود.' }));
      }).catch(function () { toast('خطا'); });
    }
    return card('آزمایشگاهِ تهدید', 'sparkle', [h('p', { class: 'rgm-sub', text: 'بدونِ اجرای هیچ اقدامی، تشخیصِ نگهبان را روی هر جمله امتحان کنید.' }), inp, h('div', { style: 'height:8px' }), btn('بررسی', 'p full', run, 'search'), h('div', { style: 'height:8px' }), res]);
  }
  function wasContained(i) { return i.status === 'contained' || (i.actions || []).some(function (a) { return /غیرفعال|بلاک|قطع/.test(a); }); }
  function incCard() {
    var list = div(''), chips = div('rgm-chips', [['open', 'باز'], ['all', 'همه']].map(function (c) { return h('button', { type: 'button', class: 'rgm-chip' + (F.inc === c[0] ? ' on' : ''), onclick: function () { F.inc = c[0]; renderBody(); } }, c[1]); }));
    function paint(items) { list.replaceChildren.apply(list, items.length ? items.map(incRow) : [empty(F.inc === 'open' ? 'رویدادِ بازی نیست 🎉' : 'رویدادی ثبت نشده.')]); }
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
    return div('rgm-inc lv' + i.level + (i.status === 'closed' ? ' closed' : ''), [div('top', [lvTag(i.level), h('span', { class: 'nm', text: i.actor_name }), sp(i.status === 'closed' ? 'بسته' : cont ? 'مهارشده' : 'باز', 'rgm-tag' + (i.status === 'closed' ? ' ok' : '')), h('i', { style: 'flex:1' }), sp(ago(i.ts), 'rgm-tag')]),
      div('dt', ['#' + fa(i.id) + ' — ' + i.title + (i.detail ? ' — ' + i.detail : '')]), (i.actions || []).length ? div('ac', ['⚙️ ' + i.actions.join(' • ')]) : null, btns.length ? div('btns', btns) : null]);
  }
  function lockSheet() {
    var ta = h('input', { class: 'rgm-in', placeholder: 'دلیل (اختیاری)' });
    sheetOpen({ title: 'قفلِ اضطراری', body: div('', [h('p', { class: 'rgm-sub', style: 'font-size:14px', text: 'وضعیتِ سیستم روی APS می‌رود، ربات برای مدیران خاموش و ورودِ مدیرِ جدید بسته می‌شود. فقط شما آزاد می‌مانید.' }), ta]),
      foot: btn('قفل کن', 'd full', function () { Sheet.close(); act({ a: 'gd_lock', reason: ta.value.trim() || undefined }); }, 'lock') });
  }

  /* ═════════ ۴) ژورنال (خطِ زمانِ گروه‌بندی‌شده با روز) ═════════ */
  var KINDS = [['all', 'همه'], ['round', 'دورها'], ['directive', 'دستورها'], ['caps', 'اختیارات'], ['question', 'پرسش‌ها'], ['grant', 'اعطا'], ['revoke', 'پایان'], ['session_summary', 'گزارش‌ها']];
  var KSTYLE = { round: ['brain', 'cy'], directive: ['pencil', 'bl'], caps: ['sliders', 'vi'], question: ['alert', 'wr'], grant: ['bolt', 'ok'], revoke: ['power', 'gr'], extend: ['clock', 'bl'], session_summary: ['list', 'cy'], announce_cfg: ['chat', 'bl'] };
  function bodyJournal() {
    var chips = div('rgm-chips', KINDS.map(function (k) { return h('button', { type: 'button', class: 'rgm-chip' + (F.journal === k[0] ? ' on' : ''), onclick: function () { F.journal = k[0]; JR = { items: [], more: true, busy: false }; renderBody(); } }, k[1]); }));
    var list = div('rgm-tl2'), more = div('', []);
    function paint() {
      var groups = {}, order = [], today = (D.now_fa || '').split(' ')[0];
      JR.items.forEach(function (j) { var d = (j.ts_fa || '').split(' ')[0]; if (!groups[d]) { groups[d] = []; order.push(d); } groups[d].push(j); });
      var kids = [];
      order.forEach(function (d) { kids.push(div('dayh', [sp(d === today ? 'امروز' : d)])); groups[d].forEach(function (j) { kids.push(jRow(j)); }); });
      list.replaceChildren.apply(list, kids.length ? kids : [JR.busy ? div('rgm-skel', [div('sk c'), div('sk c')]) : empty('ثبتی پیدا نشد.')]);
      more.replaceChildren.apply(more, JR.more && JR.items.length ? [btn('نمایشِ بیشتر', 'full', fetchMore)] : []);
    }
    function fetchMore() {
      if (JR.busy) return; JR.busy = true;
      var before = JR.items.length ? JR.items[JR.items.length - 1].id : '';
      api('/hub/api/rgm/journal?kind=' + F.journal + '&limit=20' + (before ? '&before=' + before : '')).then(function (r) { JR.items = JR.items.concat(r.items); JR.more = r.items.length >= 20; JR.busy = false; paint(); }).catch(function () { JR.busy = false; });
    }
    if (!JR.items.length) { fetchMore(); paint(); } else paint();
    var mem = card('حافظه‌ی رهگشا', 'brain', D.memory.length ? [div('rgm-notes', D.memory.map(function (m) { return div('note', [h('p', { text: m.text }), h('small', { text: m.ts_fa })]); })), btn('پاک‌کردنِ حافظه', 'sm full', function () { confirmSheet('پاک‌کردنِ حافظه', 'یادداشت‌های ماندگارِ رهگشا پاک می‌شود.', 'پاک کن', true, function () { act({ a: 'mgr_memory_clear' }); }); })] : [empty('حافظه خالی است.')]);
    return [card('گزارش', 'list', [btn('«چه کردی؟» — آخرین دوره', 'p full', reportSheet, 'list')]), card('ژورنال', 'book', [chips, list, more]), mem];
  }
  function jRow(j) {
    var st = KSTYLE[j.kind] || ['pulse', 'gr'], meta = (j.tools && j.tools.length ? fa(j.tools.length) + ' ابزار • ' : '') + (j.ok ? '' : 'ناموفق • ') + (j.ts_fa || '').split(' ').slice(1).join(' ');
    var r = div('jr ' + st[1] + (j.ok ? '' : ' bad'), [h('span', { class: 'ji' }, ic(st[0])), div('jm', [div('t', [j.title]), div('s', [(j.body || '').slice(0, 100).replace(/\n/g, ' ') || meta]), div('s m', [meta])]), ic('chev')]);
    r.addEventListener('click', function () { hx.tap(); jSheet(j.id); }); return r;
  }
  function jSheet(id) {
    sheetOpen({ title: 'جزئیاتِ ثبت', body: skeleton() });
    api('/hub/api/rgm/journal/' + id).then(function (r) {
      var it = r.item, kids = [h('p', { class: 'rgm-sub', text: it.ts_fa + ' • ' + it.kind }), h('pre', { class: 'rgm-pre', text: it.body || '—' })];
      if (it.tools.length) kids.push(h('h4', { class: 'rgm-h', style: 'margin-top:14px' }, h('span', { class: 'hico' }, ic('bolt')), sp('کارهایی که انجام شد')), div('', it.tools.map(function (t) { return li(t.tool, (t.result || t.args || '—').slice(0, 220)); })));
      sheetOpen({ title: it.title, body: div('', kids) });
    }).catch(function () { sheetSet(empty('بارگذاری ناموفق بود.')); });
  }
  function reportSheet() {
    sheetOpen({ title: 'گزارشِ دوره', body: skeleton() });
    api('/hub/api/rgm/report?session=' + (D && D.mgr.active ? 'current' : 'last')).then(function (r) {
      sheetOpen({ title: 'رهگشا در این مدت چه کرد؟', body: r.report ? h('pre', { class: 'rgm-pre', text: r.report }) : empty('هنوز دوره‌ای ثبت نشده است.') });
    }).catch(function () { sheetSet(empty('بارگذاری ناموفق بود.')); });
  }

  /* ═════════ ۵) تنظیمات (آکاردئون) ═════════ */
  var TEMPLATES = [['پیگیریِ مسابقات', 'هر مسابقه‌ی بدونِ نتیجه را بعد از یک ساعت پیگیری کن و به مسئولِ مسابقات یادآوری بده.'], ['سخت‌گیریِ امنیتی', 'هیچ مدیر یا درخواستِ دسترسیِ تازه‌ای را بدونِ اجازه‌ی من تأیید نکن؛ هر نشانه‌ی تهدید را فوراً مهار کن.'], ['گزارشِ شبانه', 'هر شب ساعت ۲۲ یک گزارشِ کوتاه از وضعیتِ امنیت و مسابقات برایم بفرست.'], ['نظارت بر مدیران', 'فعالیتِ مدیرها را مرور کن و اگر کسی بیش از حد حذف یا تغییر انجام داد اخطار بده.']];
  function bodySet() {
    var m = D.mgr, out = [], caps = {}; D.caps.forEach(function (c) { caps[c.key] = c.on; });
    var ta = h('textarea', { class: 'rgm-ta', placeholder: 'دستورِ اختصاصی برای رهگشا…', text: m.directive || '' }), cnt = h('small', { class: 'cnt', text: fa((m.directive || '').length) + ' / ۲۰۰۰' });
    ta.addEventListener('input', function () { cnt.textContent = fa(ta.value.length) + ' / ۲۰۰۰'; });
    out.push(acc('dir', 'دستورِ اختصاصی', 'pencil', [h('p', { class: 'rgm-sub', text: 'وظیفه‌ی اجباریِ هر دور؛ بر هر چیز مقدم است. با ذخیره، رهگشا همان لحظه اجرایش می‌کند و برای هر بند وضعیت می‌دهد.' }),
      div('rgm-chips', TEMPLATES.map(function (t) { return h('button', { type: 'button', class: 'rgm-chip', onclick: function () { ta.value = (ta.value ? ta.value.trim() + '\n' : '') + t[1]; ta.dispatchEvent(new Event('input')); } }, '＋ ' + t[0]); })),
      ta, div('rgm-cnt', [cnt]), div('rgm-row', [btn('ذخیره و اجرا', 'p', function () { act({ a: 'mgr_directive', mode: 'set', text: ta.value }); }, 'bolt'), btn('پاک', '', function () { act({ a: 'mgr_directive', mode: 'clear' }); }, 'trash')])], m.directive ? fa(m.directive.length) + ' نویسه' : 'خالی'));
    var ini = m.initiative || 'active';
    out.push(acc('ini', 'ابتکارِ رهگشا', 'bolt', [h('p', { class: 'rgm-sub', text: 'رهگشا فقط وقتی کارِ غیرامنیتی می‌کند که چیزی جلوی چشمش باشد. «صفِ کار» هر دور از دیتابیس ساخته می‌شود (مسابقه‌ی بدونِ نتیجه، وظیفه‌ی معوق، مدیرِ غایب، درخواستِ دسترسیِ معطل، ...). این کلید تعیین می‌کند با آن چه کند.' }),
      div('rgm-mode', [['report', 'گزارش‌دهنده', 'eye', 'فقط می‌بیند و گزارش می‌دهد؛ اقدامِ عملیاتی نمی‌کند.'], ['active', 'فعال', 'bolt', 'موارد صف را خودش پیگیری می‌کند: یادآوری، پیام، وظیفه، تحلیل.'], ['proactive', 'پیش‌قدم', 'sparkle', 'علاوه بر صف، هر دور تا ۳ کارِ ابتکاری هم می‌کند.']].map(function (x) {
        return h('button', { type: 'button', class: 'rgm-mc' + (ini === x[0] ? ' on' : ''), style: 'flex:none;width:100%;margin-bottom:8px', onclick: function () { hx.sel(); act({ a: 'mgr_initiative', level: x[0] }); } }, h('span', { class: 'mi' }, ic(x[2])), h('b', { text: x[1] }), h('small', { text: x[3] }));
      }))], ({ report: 'گزارش‌دهنده', active: 'فعال', proactive: 'پیش‌قدم' })[ini]));
    var iv = [[15, '۱۵د'], [30, '۳۰د'], [60, '۱س'], [120, '۲س'], [180, '۳س'], [360, '۶س'], [720, '۱۲س'], [1440, '۲۴س']];
    var tm = h('input', { class: 'rgm-in', type: 'time', value: m.daily_time, style: 'direction:ltr;text-align:center', onchange: function (e) { act({ a: 'mgr_schedule', daily_time: e.target.value }); } });
    out.push(acc('sch', 'زمان‌بندیِ دورها', 'clock', [h('p', { class: 'rgm-sub', text: 'هرچه کوتاه‌تر، رهگشا فعال‌تر (و مصرفِ هوش مصنوعی بیشتر).' }),
      div('rgm-chips', iv.map(function (x) { return h('button', { type: 'button', class: 'rgm-chip' + (m.interval_min === x[0] ? ' on' : ''), onclick: function () { act({ a: 'mgr_schedule', interval_minutes: x[0] }); } }, x[1]); })),
      li('دورهای خودکار', 'رهگشا خودش و بی‌درخواست دور می‌زند.', sw(!!caps.autonomous_rounds, function (v) { act({ a: 'mgr_schedule', autonomous: v }, true); })),
      li('بررسیِ روزانه‌ی امنیت', 'هر شب در ساعتِ زیر.', sw(!!caps.daily_review, function (v) { act({ a: 'mgr_schedule', daily_review: v }, true); })), tm], 'هر ' + fa(m.interval_min) + ' دقیقه'));
    var an = m.announce, rp = m.report;
    out.push(acc('ann', 'اعلام و گزارش', 'chat', [
      li('اعلامِ شروعِ مدیریت', 'به مدیرها و گروه‌ها خبر بده که رهگشا مدیر است.', sw(an.on, function (v) { act({ a: 'mgr_announce', master: v }, true); })),
      h('div', { style: 'padding:4px 0 8px' }, seg([['all', 'همه‌ی مدیران'], ['none', 'هیچ‌کس']], an.admins === 'none' ? 'none' : 'all', function (v) { act({ a: 'mgr_announce', admins_mode: v }, true); })),
      li('گروهِ فرماندهی', null, sw(an.ops_group, function (v) { act({ a: 'mgr_announce', ops_group: v }, true); })), li('گروهِ اطلاعیه', null, sw(an.ann_group, function (v) { act({ a: 'mgr_announce', announcement_group: v }, true); })),
      li('گزارشِ دورها در پیوی شما', null, sw(rp.boss_pm, function (v) { act({ a: 'mgr_announce', report_boss_pm: v }, true); })), li('گزارشِ دورها در گروهِ فرماندهی', null, sw(rp.ops_group, function (v) { act({ a: 'mgr_announce', report_ops_group: v }, true); }))], an.on ? 'روشن' : 'خاموش'));
    var msg = h('textarea', { class: 'rgm-ta', style: 'min-height:70px', placeholder: 'پیامی که با نامِ رهگشا اعلام شود…' });
    out.push(acc('now', 'اعلامِ فوری', 'sparkle', [msg, h('div', { style: 'height:8px' }), btn('ارسال', 'p full', function () { if (!msg.value.trim()) return; confirmSheet('ارسالِ اعلام', 'پیام برای مدیرانِ تنظیم‌شده فرستاده می‌شود.', 'ارسال', false, function () { act({ a: 'mgr_announce_send', text: msg.value }); msg.value = ''; }); }, 'chat')]));
    out.push(acc('sys', 'کنترلِ سیستم', 'gear', [h('p', { class: 'rgm-sub', text: 'وضعیتِ کلیِ ربات (همان که در «پنل مدیر ارشد» هست).' }),
      seg([['normal', 'عادی'], ['bad', 'احتیاط'], ['danger', 'خطر'], ['aps', 'APS']], D.kpi.system_status, function (v) { confirmSheet('تغییرِ وضعیتِ سیستم', 'وضعیت به «' + v + '» می‌رود و مدیرها تحتِ تأثیر قرار می‌گیرند.', 'تغییر بده', v !== 'normal', function () { act({ a: 'sys_status', status: v }); }); }),
      h('div', { style: 'height:8px' }), li('رهگشا (چتِ هوشمند)', 'خاموش‌شدن یعنی هیچ مدیری با رهگشا گفتگو نمی‌کند.', sw(D.kpi.ai_online, function (v) { act({ a: 'sys_ai_online', on: v }); }))], D.kpi.system_status));
    out.push(acc('fx', 'جلوه‌های بصری', 'sparkle', [h('p', { class: 'rgm-sub', text: 'اگر پنل روی گوشی‌تان سنگین است، «سبک» را بزنید. «متعادل» نشانِ سپر، ورودِ پله‌ای و نمودارها را نگه می‌دارد و فقط حرکت‌های بی‌پایانِ پس‌زمینه را خاموش می‌کند.' }),
      seg([['lite', 'سبک'], ['balanced', 'متعادل'], ['full', 'کامل']], FX, function (v) { setFx(v); renderBody(); })], ({ lite: 'سبک', balanced: 'متعادل', full: 'کامل' })[FX]));
    out.push(acc('use', 'آمارِ استفاده', 'pulse', [div('rgm-ustats', [['کلِ زمانِ مدیریت', dur(m.usage.total)], ['امروز', dur(m.usage.today)], ['۷ روزِ اخیر', dur(m.usage.week)], ['طولانی‌ترین دوره', dur(m.usage.longest)], ['تعدادِ دوره‌ها', fa(m.usage.count) + ' بار'], ['نوبتِ اعطا', fa(m.grant_count)]].map(function (x) { return div('us', [h('b', { text: x[1] }), h('small', { text: x[0] })]); }))]));
    return out;
  }

  /* ═════════ اعطا / تمدید ═════════ */
  function grantSheet() {
    var sel = { mins: 180, forever: false, preset: 'balanced', ann: !!(D && D.mgr.announce.on) };
    var durs = [[30, '۳۰ دقیقه'], [60, '۱ ساعت'], [180, '۳ ساعت'], [360, '۶ ساعت'], [720, '۱۲ ساعت'], [1440, '۱ روز'], [4320, '۳ روز'], [0, 'تا اطلاعِ ثانوی']];
    var ta = h('textarea', { class: 'rgm-ta', style: 'min-height:74px', placeholder: 'دستورِ اختصاصی برای این دوره (اختیاری)', text: (D && D.mgr.directive) || '' }), wrap = div('', []);
    function paint() {
      wrap.replaceChildren(h('p', { class: 'rgm-sub', text: 'مدتِ مدیریت' }), div('rgm-dur', durs.map(function (d) { var on = d[0] === 0 ? sel.forever : (!sel.forever && sel.mins === d[0]); return h('button', { type: 'button', class: 'rgm-chip' + (on ? ' on' : ''), onclick: function () { sel.forever = d[0] === 0; if (d[0]) sel.mins = d[0]; paint(); } }, d[1]); })),
        h('p', { class: 'rgm-sub', text: 'میزانِ اختیار' }), seg([['cautious', 'محتاطانه'], ['balanced', 'متعادل'], ['full', 'کامل']], sel.preset, function (v) { sel.preset = v; paint(); }), h('div', { style: 'height:12px' }),
        h('p', { class: 'rgm-sub', text: 'دستورِ اختصاصی' }), ta, li('اعلامِ شروع به مدیرها', null, sw(sel.ann, function (v) { sel.ann = v; paint(); })));
    }
    paint();
    sheetOpen({ title: 'سپردنِ مدیریت به رهگشا', body: wrap, foot: btn('شروعِ مدیریتِ رهگشا', 'ok full', function () { Sheet.close(); act({ a: 'mgr_grant', minutes: sel.forever ? null : sel.mins, until_revoked: sel.forever, preset: sel.preset, directive: ta.value.trim() || undefined, announce: sel.ann }); }, 'bolt') });
  }
  function extendSheet() {
    var opts = [[30, '+۳۰ دقیقه'], [60, '+۱ ساعت'], [180, '+۳ ساعت'], [720, '+۱۲ ساعت'], [1440, '+۱ روز']];
    sheetOpen({ title: 'تمدیدِ مهلت', body: div('', [h('p', { class: 'rgm-sub', text: 'مهلتِ فعلی را تمدید کنید یا بی‌پایان کنید.' }), div('rgm-dur', opts.map(function (o) { return h('button', { type: 'button', class: 'rgm-chip', onclick: function () { Sheet.close(); act({ a: 'mgr_extend', delta_minutes: o[0] }); } }, o[1]); })), btn('تا اطلاعِ ثانوی', 'full', function () { Sheet.close(); act({ a: 'mgr_extend', until_revoked: true }); }, 'clock')]) });
  }

  /* ═════════ چرخه‌ی زندگی ═════════ */
  function fab(hide) {
    var f = document.getElementById('rg-fab'); if (!f) return;
    if (hide) { fabWas = f.style.display; f.style.display = 'none'; } else f.style.display = fabWas || '';
  }
  function onShow() {
    shown = true; fab(true); load(!D); clearInterval(pollT); clearInterval(tickT);
    pollT = setInterval(function () { if (!document.hidden) load(false); }, 12000); tickT = setInterval(tick, 1000);
  }
  function onHide() { shown = false; fab(false); clearInterval(pollT); clearInterval(tickT); }
  function open(v) { if (v && TABS.some(function (t) { return t[0] === v; })) { view = v; updateNav(); if (D) renderBody(true); } }
  function mount(el, ctx) {
    h = ctx.h; ic = ctx.ic; hx = ctx.hx; tg = ctx.tg; toast = ctx.toast; LS = ctx.LS; api = ctx.api; Sheet = ctx.Sheet; goHome = ctx.goHome; openChat = ctx.openChat;
    root = el; el.replaceChildren(); setFx(pickFx());
    hdrEl = h('header', { class: 'rgm-hdr' }); heroEl = h('section', { class: 'rgm-hero', 'data-s': 'off', 'data-lv': '0' });
    navEl = h('nav', { class: 'rgm-nav', 'aria-label': 'بخش‌های مرکز فرماندهی' }); bodyEl = h('div', { class: 'rgm-body' });
    el.append(hdrEl, heroEl, navEl, bodyEl);
    buildHeader(); buildHero(); buildNav(); updateNav(); renderBody(true);
    document.addEventListener('pointerdown', onPointer, true);
    document.addEventListener('visibilitychange', function () { if (shown && !document.hidden) load(false); });
  }
  window.HubRgm = { mount: mount, onShow: onShow, onHide: onHide, open: open };
})();
