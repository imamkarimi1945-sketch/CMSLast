"""
hub_rgm.py — «مرکز فرماندهیِ رهگشا» در پنل من (هاب): رهگشای مدیر + نگهبان، با همه‌ی جزئیات و کنترل‌ها.

فقط برای مدیر ارشد (initData امضاشده‌ی تلگرام). مسیرها:
  GET  /hub/api/rgm/mini            ← خلاصه‌ی خیلی سبک برای کارتِ صفحه‌ی خانه
  GET  /hub/api/rgm/overview        ← همه‌چیز: وضعیت، زمان‌سنج، اختیارات، نگهبان، شاخص‌ها، رویدادها، ژورنال، حافظه، روند
  GET  /hub/api/rgm/journal         ← ژورنالِ صفحه‌بندی‌شده (kind, limit, before)
  GET  /hub/api/rgm/journal/{id}    ← متنِ کاملِ یک ثبت + اقدام‌های انجام‌شده
  GET  /hub/api/rgm/incidents       ← رویدادهای امنیتی (status, limit)
  GET  /hub/api/rgm/people          ← مدیران با ریسک/وضعیت برای «مهار/بازگردانی»
  GET  /hub/api/rgm/report          ← «در این مدت چه کردی؟» (session=last|current|id)
  POST /hub/api/rgm/act             ← همه‌ی کارها با یک دروازه: {"a": "...", ...}

هیچ منطقِ تازه‌ای اینجا نیست: همه‌چیز از ai_manager / ai_guardian می‌آید تا ربات و پنل همیشه یک واقعیت را نشان بدهند.
"""
import asyncio
import json
import logging
import time
from datetime import timedelta

from aiohttp import web

import database as db
import hub
import srvctx
from config import PISHVA_ID, ROLE_PISHVA

logger = logging.getLogger(__name__)
routes = web.RouteTableDef()

_OV_CACHE = {"t": 0.0, "v": None}


def _j(data, status=200):
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str))


def _fail(code, message, status=400):
    cls = {400: web.HTTPBadRequest, 403: web.HTTPForbidden, 404: web.HTTPNotFound}.get(status, web.HTTPBadRequest)
    return hub._err(cls, code, message=message)


async def _boss(request):
    is_pishva, _admin, _user = await hub._require_admin(request)
    if not is_pishva:
        raise hub._err(web.HTTPForbidden, "pishva_only")
    try:
        if not srvctx.is_main():
            raise _fail("main_only", "این بخش فقط روی سرورِ اصلی کار می‌کند.", 403)
    except web.HTTPException:
        raise
    except Exception:
        pass


def _dt(v):
    from ops_group import jfmt
    try:
        return jfmt(v) if v else ""
    except Exception:
        return ""


def _iso(v):
    try:
        return v.isoformat(timespec="seconds") if v else None
    except Exception:
        return None


def _jsonl(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


async def _incidents(status=None, limit=30):
    import ai_guardian as gd
    q, a = "SELECT * FROM mgr_incidents", []
    if status == "open":
        q += " WHERE status IN ('open','contained')"
    elif status in ("closed", "contained"):
        q += " WHERE status=?"
        a.append(status)
    rows = await gd._rows(q + " ORDER BY id DESC LIMIT ?", (*a, max(1, min(100, int(limit)))))
    out = []
    for r in rows:
        out.append({"id": r["id"], "ts": r["ts"], "ts_fa": _dt(am_pdt(r["ts"])), "actor_id": r["actor_id"], "actor_name": r["actor_name"],
                    "level": r["level"], "kind": r["kind"], "title": r["title"], "detail": r["detail"] or "",
                    "actions": _jsonl(r["actions"], []), "status": r["status"], "source": r["source"]})
    return out


def am_pdt(s):
    import ai_manager as am
    return am._pdt(s)


async def _journal(kind=None, limit=20, before=None, full=False):
    import ai_manager as am
    q, a = "SELECT * FROM mgr_journal WHERE 1=1", []
    if kind and kind != "all":
        q += " AND kind=?"
        a.append(kind)
    if before:
        q += " AND id<?"
        a.append(int(before))
    rows = await am._rows(q + " ORDER BY id DESC LIMIT ?", (*a, max(1, min(60, int(limit)))))
    out = []
    for r in rows:
        tools = _jsonl(r["tools"], [])
        out.append({"id": r["id"], "ts": r["ts"], "ts_fa": _dt(am._pdt(r["ts"])), "kind": r["kind"], "trigger": r["trigger"] or "",
                    "title": r["title"], "body": (r["body"] or "")[: (6000 if full else 700)], "ok": bool(r["ok"]),
                    "tools": [{"tool": t.get("tool"), "args": str(t.get("args", ""))[:200], "result": str(t.get("result", ""))[:300]} for t in tools[:40]]})
    return out


async def _queue():
    try:
        import ai_workqueue as wq
        return await wq.build(include_cooling=True)
    except Exception:
        logger.info("rgm overview: queue failed", exc_info=True)
        return []


async def _overview():
    import ai_manager as am
    import ai_guardian as gd
    from ops_group import now_teh
    st = await am.get_state(force=True)
    gs = await gd.get_state(force=True)
    await gd.refresh_fast()
    t, u = am.timer_of(st), await am.usage()
    caps_on = am.eff_caps(st)
    caps = []
    for d in am.capability_defs():
        caps.append({"key": d["key"], "label": d["label"], "kind": d["kind"], "desc": d.get("desc", ""),
                     "tools": len(d.get("tools") or []), "tool_names": (d.get("tools") or [])[:30], "on": bool(caps_on[d["key"]])})
    try:
        _snap, m = await am._snapshot()
    except Exception:
        logger.warning("rgm overview: snapshot failed", exc_info=True)
        m = {}
    now = now_teh()
    since = (now.replace(microsecond=0)).isoformat()
    jr_all = await am._rows("SELECT COUNT(*) AS n FROM mgr_journal")
    rounds24 = await am._rows("SELECT COUNT(*) AS n, SUM(ok) AS ok FROM mgr_journal WHERE kind='round' AND ts>=?",
                              ((now.replace(microsecond=0) - timedelta(hours=24)).isoformat(),))
    inc24 = await gd._rows("SELECT COUNT(*) AS n FROM mgr_incidents WHERE ts>=?",
                           ((now - timedelta(hours=24)).isoformat(timespec="seconds"),))
    inc_open = await gd._rows("SELECT COUNT(*) AS n FROM mgr_incidents WHERE status='open'")
    inc_cont = await gd._rows("SELECT COUNT(*) AS n FROM mgr_incidents WHERE status='contained'")
    mem = await am._rows("SELECT id, ts, kind, text FROM mgr_memory WHERE active=1 ORDER BY id DESC LIMIT 14")
    trend_rows = await am._rows("SELECT ts, data FROM mgr_metrics ORDER BY id DESC LIMIT 24")
    trend = []
    for r in reversed(trend_rows):
        d = _jsonl(r["data"], {})
        trend.append({"ts": r["ts"], "score": d.get("score"), "strangers": d.get("strangers"), "pending": d.get("pending"),
                      "destructive": d.get("destructive"), "incidents_open": d.get("incidents_open", 0)})
    timer = {"active": bool(t.get("active"))}
    if t.get("active"):
        timer.update(timed=bool(t.get("timed")), elapsed=int(t["elapsed"]), start=_iso(t.get("start")), start_fa=_dt(t.get("start")))
        if t.get("timed"):
            timer.update(remaining=int(t["remaining"]), total=int(t["total"]), pct_left=round(t["pct_left"], 1), end=_iso(t["end"]), end_fa=_dt(t["end"]))
    lk = gs["lockdown"]
    ai_online = (await db.get_setting("ai_online", "1")) == "1"
    risk = []
    for line in await gd.risk_rows(8):
        risk.append(line)
    return {
        "ok": True, "now": _iso(now), "now_fa": _dt(now),
        "mgr": {"active": bool(st["active"]), "initiative": st.get("initiative", "active"), "timer": timer, "directive": st["directive"], "full_access": bool(st["full_access"]),
                "interval_min": st["interval_min"], "daily_time": st["daily_time"], "next_round": _iso(am._pdt(st["next_round"])),
                "next_round_fa": _dt(am._pdt(st["next_round"])), "last_round_fa": _dt(am._pdt(st["last_round"])),
                "announce": st["announce"], "report": st["report"], "grant_count": st["grant_count"], "fail_streak": st["fail_streak"],
                "caps_on": sum(1 for c in caps if c["kind"] == "cat" and c["on"]), "caps_all": sum(1 for c in caps if c["kind"] == "cat"),
                "usage": {k: int(v) for k, v in u.items()},
                "limits": dict(zip(("writes", "destructive", "hops"), am.limits(st)))},
        "caps": caps,
        "diag": [{"lvl": l, "text": t} for l, t in await am.diagnose(st)],
        "queue": [{"key": t["key"], "prio": t["prio"], "kind": t["kind"], "title": t["title"], "evidence": t["evidence"], "tools": t["tools"], "cooling": t["cooling"]}
                  for t in await _queue()],
        "guard": {"enabled": gs["enabled"], "mode": gs["mode"], "eff_mode": gd._fast["mode"], "sens": gs["sens"], "always": gs["always"],
                  "auto_undo": gs["auto_undo"], "auto_lockdown": gs["auto_lockdown"], "ops_group": gs["ops_group"],
                  "locked": bool(lk["on"]), "lock_reason": lk.get("reason", ""), "lock_since_fa": _dt(am._pdt(lk.get("since"))), "lock_by": lk.get("by", ""),
                  "thresholds": {"events": gd.EV_TH[gs["sens"]] if gs["sens"] in gd.EV_TH else gd.EV_TH["medium"],
                                 "rate": gd.RATE_TH[gs["sens"]] if gs["sens"] in gd.RATE_TH else gd.RATE_TH["medium"]}},
        "kpi": {"score": m.get("score"), "strangers": m.get("strangers"), "pending": m.get("pending"), "queued": m.get("queued"),
                "blocked": m.get("blocked"), "destructive": m.get("destructive"), "admins": m.get("admins"), "online": m.get("online"),
                "warned": m.get("warned"), "matches_today": m.get("matches_today"), "matches_pending": m.get("matches_pending"),
                "incidents_open": inc_open[0]["n"], "incidents_contained": inc_cont[0]["n"], "incidents_24h": inc24[0]["n"],
                "rounds_24h": rounds24[0]["n"] or 0, "rounds_ok_24h": int(rounds24[0]["ok"] or 0), "journal_total": jr_all[0]["n"],
                "ai_online": ai_online, "system_status": await db.get_setting("system_status", "normal")},
        "incidents": await _incidents(None, 14),
        "risk": risk,
        "journal": await _journal(None, 12),
        "memory": [{"id": r["id"], "ts_fa": _dt(am._pdt(r["ts"])), "kind": r["kind"], "text": r["text"]} for r in mem],
        "trend": trend,
    }


@routes.get("/hub/api/rgm/mini")
async def rgm_mini(request):
    await _boss(request)
    import ai_manager as am
    import ai_guardian as gd
    st = await am.get_state()
    gs = await gd.get_state()
    t = am.timer_of(st)
    opn = await gd._rows("SELECT COUNT(*) AS n FROM mgr_incidents WHERE status IN ('open','contained') AND level>=2")
    return _j({"ok": True, "active": bool(st["active"]), "locked": bool(gs["lockdown"]["on"]), "full": bool(st["full_access"]),
               "open": opn[0]["n"], "mode": gd._fast["mode"],
               "remaining": int(t["remaining"]) if t.get("active") and t.get("timed") else None, "forever": bool(t.get("active") and not t.get("timed"))})


@routes.get("/hub/api/rgm/overview")
async def rgm_overview(request):
    await _boss(request)
    if _OV_CACHE["v"] is not None and time.monotonic() - _OV_CACHE["t"] < 2.5 and not request.query.get("fresh"):
        return _j(_OV_CACHE["v"])
    data = await _overview()
    _OV_CACHE.update(t=time.monotonic(), v=data)
    return _j(data)


@routes.get("/hub/api/rgm/journal")
async def rgm_journal(request):
    await _boss(request)
    q = request.query
    return _j({"ok": True, "items": await _journal(q.get("kind"), q.get("limit", 20), q.get("before"))})


@routes.get("/hub/api/rgm/journal/{id}")
async def rgm_journal_one(request):
    await _boss(request)
    import ai_manager as am
    rows = await am._rows("SELECT * FROM mgr_journal WHERE id=?", (int(request.match_info["id"]),))
    if not rows:
        raise _fail("not_found", "ثبت پیدا نشد.", 404)
    r = rows[0]
    tools = _jsonl(r["tools"], [])
    return _j({"ok": True, "item": {"id": r["id"], "ts_fa": _dt(am._pdt(r["ts"])), "kind": r["kind"], "title": r["title"], "body": r["body"] or "",
                                    "ok": bool(r["ok"]), "tools": [{"tool": t.get("tool"), "args": str(t.get("args", "")), "result": str(t.get("result", ""))} for t in tools]}})


@routes.get("/hub/api/rgm/incidents")
async def rgm_incidents(request):
    await _boss(request)
    return _j({"ok": True, "items": await _incidents(request.query.get("status"), request.query.get("limit", 40))})


@routes.get("/hub/api/rgm/people")
async def rgm_people(request):
    await _boss(request)
    import ai_guardian as gd
    import ai_manager as am
    rows = await gd._rows("SELECT actor_id, MAX(level) AS lv, COUNT(*) AS n FROM mgr_incidents WHERE ts>=? GROUP BY actor_id",
                          ((am.now_teh() - timedelta(days=7)).isoformat(timespec="seconds"),))
    inc = {r["actor_id"]: (r["lv"], r["n"]) for r in rows}
    risk_now = {}
    now = time.monotonic()
    for uid, dq in list(gd._EV.items()):
        risk_now[uid] = sum(x[1] for x in dq if now - x[0] <= gd.EV_WINDOW)
    out = []
    for a in await db.get_all_admins():
        uid = int(a["telegram_id"])
        perms = _jsonl(a["permissions"], {})
        out.append({"id": uid, "name": a["display_name"] or a["full_name"] or str(uid), "username": a["username"] or "", "role": a["role"],
                    "active": bool(a["is_active"]), "warnings": a["warnings"] or 0, "last_active": str(a["last_active"] or "")[:16].replace("T", " "),
                    "ai_access": bool(perms.get("ai_access", True)), "risk": round(risk_now.get(uid, 0), 1),
                    "incidents_7d": inc.get(uid, (0, 0))[1], "max_level": inc.get(uid, (0, 0))[0],
                    "contained": uid in gd._CONTAINED})
    out.sort(key=lambda r: (-r["risk"], -r["incidents_7d"], not r["active"]))
    return _j({"ok": True, "items": out})


@routes.get("/hub/api/rgm/report")
async def rgm_report(request):
    await _boss(request)
    import ai_manager as am
    which = request.query.get("session", "last")
    sid = int(which) if which.isdigit() else None
    if which == "current":
        st = await am.get_state(force=True)
        sid = st.get("session_id")
    d = await am.session_digest(sid)
    ss = await am._rows("SELECT id, started_at, ended_at, end_reason FROM mgr_sessions ORDER BY id DESC LIMIT 12")
    return _j({"ok": True, "report": (d[0] if d else ""), "meta": (d[1] if d else None),
               "sessions": [{"id": r["id"], "start_fa": _dt(am._pdt(r["started_at"])), "end_fa": _dt(am._pdt(r["ended_at"])), "reason": r["end_reason"]} for r in ss]})


def _b(v):
    return bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "yes", "on")


@routes.post("/hub/api/rgm/act")
async def rgm_act(request):
    await _boss(request)
    import ai_manager as am
    import ai_guardian as gd
    try:
        b = await request.json()
    except Exception:
        b = {}
    if not isinstance(b, dict):
        b = {}
    a = str(b.get("a") or "")
    bot = hub._BOT
    ctx = am._MgrCtx(bot)
    res = None
    ok = True

    async def tool(name, args):
        return await am.dispatch_tool(name, args, PISHVA_ID, ROLE_PISHVA, ctx)

    try:
        # ───────── رهگشای مدیر ─────────
        if a == "mgr_grant":
            mins = None if _b(b.get("until_revoked")) else int(b.get("minutes") or 0)
            if mins is None and not _b(b.get("until_revoked")):
                raise _fail("bad_request", "مدت را مشخص کنید.")
            preset = b.get("preset") if b.get("preset") in ("cautious", "balanced", "full") else None
            ann = b.get("announce")
            good, res = await am.grant(bot, mins, PISHVA_ID, b.get("directive"), (_b(ann) if ann is not None else None), preset)
            ok = good
        elif a == "mgr_revoke":
            good, res = await am.revoke(bot, "kill", PISHVA_ID)
            ok = good
        elif a == "mgr_extend":
            if _b(b.get("until_revoked")):
                good, res = await am.set_expiry(bot, None)
            elif b.get("set_minutes"):
                good, res = await am.set_expiry(bot, int(b["set_minutes"]))
            elif b.get("delta_minutes"):
                good, res = await am.extend(bot, int(b["delta_minutes"]))
            else:
                raise _fail("bad_request", "مقدارِ تمدید لازم است.")
            ok = good
        elif a == "mgr_full":
            _good, res = await am.set_full(_b(b.get("enabled")))
        elif a == "mgr_preset":
            if b.get("preset") == "full":
                _good, res = await am.set_full(True)
            else:
                res = await tool("mgr_preset", {"preset": b.get("preset")})
        elif a == "mgr_caps":
            keys = [str(k) for k in (b.get("keys") or [])]
            _good, res = await am.set_caps(keys, _b(b.get("enabled")))
            ok = _good
        elif a == "mgr_directive":
            res = await tool("mgr_directive", {"mode": b.get("mode"), "text": b.get("text")})
        elif a == "mgr_announce":
            args = {k: b[k] for k in ("master", "admins_mode", "admins", "ops_group", "announcement_group", "report_boss_pm", "report_ops_group") if k in b}
            res = await tool("mgr_announce_config", args)
        elif a == "mgr_announce_send":
            res = await tool("mgr_announce_send", {k: b[k] for k in ("text", "admins_mode", "admins", "ops_group", "announcement_group") if k in b})
        elif a == "mgr_schedule":
            res = await tool("mgr_schedule", {k: b[k] for k in ("interval_minutes", "interval_hours", "daily_time", "autonomous", "daily_review") if k in b})
        elif a == "mgr_initiative":
            res = await tool("mgr_initiative", {"level": b.get("level")})
        elif a == "mgr_round":
            asyncio.create_task(am.run_round(bot, "manual", str(b.get("note") or "")[:300]))
            res = "🧠 یک دورِ مدیریتی شروع شد؛ نتیجه در ژورنال و پیوی شما می‌آید."
        elif a == "mgr_memory_clear":
            res = await tool("mgr_memory", {"action": "clear"})
        # ───────── نگهبان ─────────
        elif a == "gd_config":
            gs = await gd.get_state(force=True)
            ch = []
            if b.get("mode") in gd.MODES:
                gs["mode"] = b["mode"]; ch.append("mode")
            if b.get("sens") in gd.SENS:
                gs["sens"] = b["sens"]; ch.append("sens")
            for k in ("always", "auto_undo", "auto_lockdown", "enabled", "ops_group"):
                if k in b:
                    gs[k] = _b(b[k]); ch.append(k)
            if not ch:
                raise _fail("bad_request", "تنظیمِ معتبری نیامد.")
            await gd.save_state(gs)
            res = "✅ تنظیمِ نگهبان ذخیره شد."
        elif a == "gd_lock":
            ok, res = await gd.lockdown(bot, str(b.get("reason") or "قفلِ اضطراریِ دستیِ مدیر ارشد از پنل")[:250], by="boss")
        elif a == "gd_unlock":
            ok, res = await gd.unlock(bot, "boss-panel")
        elif a in ("gd_contain", "gd_release", "gd_undo"):
            uid = int(b.get("uid"))
            if uid == PISHVA_ID:
                raise _fail("forbidden", "اقدام روی مدیر ارشد ممنوع است.", 403)
            if a == "gd_contain":
                steps = await gd.contain(bot, uid, str(b.get("reason") or "مهارِ دستی از پنل")[:200], block=_b(b.get("block")))
            elif a == "gd_release":
                steps = await gd.release(uid)
            else:
                from ops_group import now_teh
                rev, skp = await db.undo_admin_actions(uid, now_teh().strftime("%Y-%m-%d"))
                await db.log_action(PISHVA_ID, "guardian_undo", f"🛡️ خنثی‌سازیِ اقدام‌های {uid}: {len(rev)} مورد", uid)
                steps = [f"{len(rev)} اقدام برگشت", f"{len(skp)} مورد قابلِ بازگشت نبود"]
            if b.get("incident"):
                await gd._exec("UPDATE mgr_incidents SET status=? WHERE id=?",
                               ("contained" if a == "gd_contain" else "closed", int(b["incident"])))
            res = "\n".join(steps)
        elif a == "gd_close":
            await gd._exec("UPDATE mgr_incidents SET status='closed', closed_at=? WHERE id=?", (gd._iso(), int(b.get("id"))))
            res = "✅ بسته شد."
        elif a == "gd_closeall":
            await gd._exec("UPDATE mgr_incidents SET status='closed', closed_at=? WHERE status IN ('open','contained')", (gd._iso(),))
            res = "✅ همه‌ی رویدادها بسته شد."
        elif a == "gd_backup":
            try:
                import backup_utils
                await backup_utils.send_backup(bot, PISHVA_ID, "all", "excel")
                res = "💾 بکاپِ کامل در پیوی شما فرستاده شد."
            except Exception as e:
                ok, res = False, f"بکاپ ناموفق بود: {e}"
        elif a == "gd_classify":
            lvl, tags = gd.classify(str(b.get("text") or ""))
            _OV_CACHE["v"] = None
            return _j({"ok": True, "level": lvl, "tags": tags, "label": gd.LVL_FA.get(lvl, "بی‌خطر")})
        elif a == "sys_status":
            status = str(b.get("status") or "")
            if status not in ("normal", "bad", "danger", "aps"):
                raise _fail("bad_request", "وضعیتِ نامعتبر.")
            await db.set_setting("system_status", status)
            await db.log_action(PISHVA_ID, "set_status", f"تغییر وضعیت به: {status} (پنلِ رهگشا)")
            res = f"✅ وضعیتِ سیستم: {status}"
        elif a == "sys_ai_online":
            await db.set_setting("ai_online", "1" if _b(b.get("on")) else "0")
            await db.log_action(PISHVA_ID, "toggle_ai_online", str(_b(b.get("on"))))
            res = "✅ رهگشا " + ("روشن" if _b(b.get("on")) else "خاموش") + " شد."
        else:
            raise _fail("bad_request", "عملیات ناشناخته.")
    except web.HTTPException:
        raise
    except Exception as e:
        logger.exception("rgm act %s failed", a)
        return _j({"ok": False, "error": "failed", "message": f"خطا: {e}"}, 500)
    _OV_CACHE["v"] = None
    try:
        await gd.refresh_fast()
    except Exception:
        pass
    return _j({"ok": bool(ok), "message": str(res or ""), "overview": await _overview()})
