"""
ai_manager.py — «رهگشای مدیر»: مدیر ارشد برای مدتی (یا تا اطلاع ثانوی) مدیریت را به رهگشا می‌سپارد.

اصولِ طراحی (این‌ها عمداً سفت‌اند):
۱) اختیار = «دورهای مدیریتیِ خودکار». رهگشا خودش، سرِ ساعت یا هر N ساعت، وضعیتِ سیستم را می‌بیند، با ابزارهای
   «مجاز» تصمیم می‌گیرد و کار می‌کند. اختیارِ سپرده‌شده به *رهگشا* داده می‌شود، نه به هر مدیری که با او چت می‌کند:
   در چتِ مدیرهای دیگر همان مجوزهای خودِ آن مدیر اعمال می‌شود (وگرنه هر مدیر می‌توانست از طریقِ رهگشا ارتقا بگیرد).
۲) فهرستِ اختیارات قابلِ خاموش/روشن است (هر «حوزه» یک کلید). «دسترسیِ کامل» همه‌ی حوزه‌ها را روشن می‌کند، ولی «قفلِ سخت»
   همیشه می‌ماند: رهگشا نمی‌تواند اختیارِ خودش را تغییر دهد/تمدید کند، به مدیر ارشد اقدام کند، به بیرونی‌ها پیام بدهد،
   اقدامِ زمان‌بندی‌شده برای بعدِ از پایانِ مهلت بسازد، یا قفلِ دستورِ مدیر ارشد را بردارد.
۳) هر اقدام با برچسبِ «🤖[رهگشای مدیر]» در لاگ‌ها ثبت می‌شود و در ژورنالِ خصوصیِ مدیر ارشد می‌ماند؛ هیچ اقدامی به نامِ مدیر ارشد
   جعل نمی‌شود. کلیدِ «اعلام» فقط «اعلانِ اعطا/تمدید/پایان» را کنترل می‌کند، نه صداقتِ لاگ‌ها.
۴) سقفِ ایمنی در هر دور: تعدادِ اقدام‌های نوشتنی و اقدام‌های مخرب محدود است؛ بیشتر از آن باید از مدیر ارشد پرسید.
۵) اعطا و تمدید و دسترسیِ کامل در چت همیشه تأییدِ صریح می‌گیرند؛ خاموشی فوری هیچ‌وقت تأیید نمی‌خواهد.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

import turso_db
import database as db
import srvctx
import mgr_ctx
from config import DB_PATH, PISHVA_ID, ROLE_PISHVA
from ops_group import bar, fa, h, jfmt, now_teh, spark

logger = logging.getLogger(__name__)

BOSS = [ROLE_PISHVA]
_APP = None

# ═══════════════════════ اختیارات (قابلِ خاموش/روشن) ═══════════════════════
SKIP_CATS = {"enforcement_lock", "persona", "outreach", "manager", "batch", "panels"}      # هرگز قابلِ سپردن نیستند
DEFAULT_ON = {"workhours", "players", "warnings", "matches", "tournaments", "reports", "comms", "admins", "security", "system",
              "reminders", "player_tiers", "top_players", "admin_full", "teams", "player_profiles", "weather_time",
              "oversight", "scenario", "user_lookup", "opsgroup", "guardian_watch", "guardian", "servers"}
CAUTIOUS = {"reports", "oversight", "player_profiles", "user_lookup", "weather_time", "guardian_watch"}
# ابزارهایی که حتی با «دسترسیِ کامل» به رهگشای مدیر داده نمی‌شوند
HARD_DENY = frozenset({
    "set_enforcement_lock",                                      # قفلِ دستورِ مدیر ارشد
    "schedule_action", "batch_execute",                          # می‌توانند اقدام را بعد از پایانِ مهلت اجرا کنند / چکِ دسترسی را دور بزنند
    "message_contact", "schedule_outreach", "cancel_outreach", "list_outreach",   # پیام به بیرونی‌ها فقط با تأییدِ صریحِ مدیر ارشد
    "ops_topic_delete", "ops_cmd_create", "ops_cmd_edit", "ops_cmd_delete",
    "toggle_ai_online", "open_panel",
    "mgr_status", "mgr_grant", "mgr_extend", "mgr_revoke", "mgr_full_access", "mgr_preset", "mgr_capability_set", "mgr_directive",
    "mgr_announce_config", "mgr_announce_send", "mgr_journal", "mgr_round_now", "mgr_schedule", "mgr_memory", "mgr_report",
    "unlock_system", "guard_config", "release_actor",            # نگهبان: رفعِ قفل/تنظیم/بازگردانی فقط با مدیر ارشد
})
DESTRUCTIVE = frozenset({"kick_player", "delete_match", "block_user", "delete_team", "set_admin_active", "set_admin_permissions",
                         "clear_admin_warnings", "edit_match_result", "add_admin", "set_admin_role", "toggle_admin_ai_access",
                         "set_system_status", "toggle_bot_setting", "contain_actor", "lockdown_system"})
READ_PREFIX = ("get_", "list_", "search_", "recent_", "quick_", "check_", "review_", "analyze_", "lookup_", "read_", "plan_",
               "compare_", "server_", "system_status", "brief_now", "my_")
MAX_WRITES_PER_ROUND = 40            # پیش‌فرض (قبلاً ۲۵)
MAX_DESTRUCTIVE_PER_ROUND = 8        # قبلاً ۵
MAX_HOPS = 24                        # قبلاً ۱۴
FULL_WRITES, FULL_DESTRUCTIVE, FULL_HOPS = 80, 15, 36     # سقفِ «دسترسیِ کامل»
FORCE_READ_HOPS = 2                  # دو قدمِ اولِ هر دور اجباراً «خواندن» است (قبلاً مدل می‌توانست بی‌هیچ ابزاری گزارشِ «اقدامی لازم نبود» بدهد)


def limits(st) -> tuple:
    return (FULL_WRITES, FULL_DESTRUCTIVE, FULL_HOPS) if st.get("full_access") else (MAX_WRITES_PER_ROUND, MAX_DESTRUCTIVE_PER_ROUND, MAX_HOPS)

BRAIN = (
    ("autonomous_rounds", "🔄 دورهای مدیریتیِ خودکار", "هر چند ساعت یک‌بار وضعیت را بررسی و در صورتِ نیاز اقدام می‌کند"),
    ("daily_review", "🛡️ بررسیِ روزانه‌ی امنیت", "هر روز سرِ ساعتِ تعیین‌شده"),
    ("trend_analysis", "📈 مطالعه‌ی روند و تحلیلِ کلِ سیستم", "مقایسه‌ی آمارِ دورها و نتیجه‌گیری"),
    ("long_memory", "🧠 تصمیم‌گیریِ بلندمدت", "یادداشتِ ماندگارِ نتیجه‌گیری‌ها بین دورها"),
)


def capability_defs():
    import ai_tools
    out = []
    for key, label, tools in ai_tools.AI_PERMISSION_CATEGORIES:
        if key in SKIP_CATS:
            continue
        usable = [t for t in tools if t not in HARD_DENY]
        if usable:
            out.append({"key": key, "label": label, "tools": usable, "kind": "cat", "default": key in DEFAULT_ON})
    for k, label, desc in BRAIN:
        out.append({"key": k, "label": label, "desc": desc, "tools": [], "kind": "brain", "default": True})
    return out


def eff_caps(st, defs=None) -> dict:
    defs = defs or capability_defs()
    return {d["key"]: (True if st["full_access"] else bool(st["caps"].get(d["key"], d["default"]))) for d in defs}


def allowed_tools(st) -> set:
    defs = capability_defs()
    caps = eff_caps(st, defs)
    out = set()
    for d in defs:
        if d["kind"] == "cat" and caps[d["key"]]:
            out.update(d["tools"])
    return out


# ═══════════════════════ ذخیره‌سازی ═══════════════════════
_tables_ok = False


async def _ensure():
    global _tables_ok
    if _tables_ok:
        return
    async with turso_db.connect(DB_PATH) as c:
        for q in (
            "CREATE TABLE IF NOT EXISTS mgr_kv (k TEXT PRIMARY KEY, v TEXT)",
            "CREATE TABLE IF NOT EXISTS mgr_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, ended_at TEXT, "
            "planned_end TEXT, end_reason TEXT, granted_by INTEGER)",
            "CREATE TABLE IF NOT EXISTS mgr_journal (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, trigger TEXT, "
            "title TEXT, body TEXT, tools TEXT, ok INTEGER DEFAULT 1)",
            "CREATE TABLE IF NOT EXISTS mgr_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, data TEXT)",
            "CREATE TABLE IF NOT EXISTS mgr_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, text TEXT, active INTEGER DEFAULT 1)",
        ):
            await c.execute(q)
        await c.commit()
    _tables_ok = True


async def _rows(sql, args=()):
    await _ensure()
    async with turso_db.connect(DB_PATH) as c:
        c.row_factory = turso_db.Row
        async with c.execute(sql, tuple(args)) as cur:
            return list(await cur.fetchall())


async def _exec(sql, args=()):
    await _ensure()
    async with turso_db.connect(DB_PATH) as c:
        cur = await c.execute(sql, tuple(args))
        await c.commit()
        return getattr(cur, "lastrowid", None)


DEFAULT_STATE = {
    "active": False, "session_id": None, "started_at": None, "expires_at": None, "granted_by": None,
    "directive": "", "caps": {}, "full_access": False,
    "announce": {"on": False, "admins": "all", "ids": [], "ops_group": True, "ann_group": False},
    "report": {"boss_pm": True, "ops_group": False},
    "interval_min": 120, "sched_v": 2, "daily_time": "22:00", "next_round": None, "last_round": None, "last_daily": "",
    "grant_count": 0, "fail_streak": 0, "warned": [],
}
_cache = {"t": 0.0, "v": None}


def _merge(st: dict) -> dict:
    out = json.loads(json.dumps(DEFAULT_STATE))
    for k, v in (st or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


async def get_state(force=False) -> dict:
    if not force and _cache["v"] is not None and time.monotonic() - _cache["t"] < 3:
        return json.loads(json.dumps(_cache["v"]))
    r = await _rows("SELECT v FROM mgr_kv WHERE k='state'")
    try:
        st = _merge(json.loads(r[0]["v"])) if r else _merge({})
    except Exception:
        st = _merge({})
    if int(st.get("sched_v") or 0) < 2:            # یک‌باره: دورِ ۶ساعته برای «مدیرِ جانشین» خیلی کند بود → حداکثر ۲ ساعت
        st["interval_min"] = min(int(st.get("interval_min") or 120), 120)
        st["sched_v"] = 2
        try:
            await _exec("INSERT OR REPLACE INTO mgr_kv(k, v) VALUES ('state', ?)", (json.dumps(st, ensure_ascii=False),))
        except Exception:
            pass
    _cache["v"], _cache["t"] = st, time.monotonic()
    return json.loads(json.dumps(st))


def short_dur(sec) -> str:
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    hh, r = divmod(r, 3600)
    mm = r // 60
    if d:
        return f"{fa(d)}ر {fa(hh)}س"
    if hh:
        return f"{fa(hh)}س {fa(mm)}د"
    return f"{fa(mm)}د"


def sync_button(st: dict):
    """برچسب/رنگِ دکمه‌ی «رهگشای مدیر» در پنلِ مدیر ارشد و منوی اصلی (keyboards.MGR_BTN)."""
    try:
        import keyboards
        t = timer_of(st)
        if not t["active"]:
            keyboards.MGR_BTN.update(label="⚪️ رهگشای مدیر", style="primary")
        elif t["timed"]:
            keyboards.MGR_BTN.update(label=f"🟢 رهگشای مدیر • {short_dur(t['remaining'])}",
                                     style="danger" if t["remaining"] < 600 else "success")
        else:
            keyboards.MGR_BTN.update(label="🟢 رهگشای مدیر • ∞", style="success")
    except Exception:
        pass


async def save_state(st: dict):
    await _exec("INSERT OR REPLACE INTO mgr_kv(k, v) VALUES ('state', ?)", (json.dumps(st, ensure_ascii=False),))
    _cache["v"], _cache["t"] = json.loads(json.dumps(st)), time.monotonic()
    sync_button(st)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _pdt(s):
    try:
        return datetime.fromisoformat(str(s)) if s else None
    except Exception:
        return None


def _main_ok() -> bool:
    try:
        return srvctx.is_main()
    except Exception:
        return True


# ═══════════════════════ زمان‌سنج و آمار ═══════════════════════
def dur_fa(sec) -> str:
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    hh, r = divmod(r, 3600)
    mm = r // 60
    parts = []
    if d:
        parts.append(f"{fa(d)} روز")
    if hh:
        parts.append(f"{fa(hh)} ساعت")
    if mm or not parts:
        parts.append(f"{fa(mm)} دقیقه")
    return " و ".join(parts)


def timer_of(st: dict) -> dict:
    now = now_teh()
    s, e = _pdt(st["started_at"]), _pdt(st["expires_at"])
    if not st["active"] or not s:
        return {"active": False}
    elapsed = (now - s).total_seconds()
    if e:
        total = max(1, (e - s).total_seconds())
        remaining = max(0, (e - now).total_seconds())
        return {"active": True, "timed": True, "elapsed": elapsed, "remaining": remaining, "total": total,
                "pct_left": remaining / total * 100, "end": e, "start": s}
    return {"active": True, "timed": False, "elapsed": elapsed, "start": s}


async def usage() -> dict:
    now = now_teh()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    w0 = now - timedelta(days=7)
    tot = today = week = longest = 0.0
    rows = await _rows("SELECT started_at, ended_at FROM mgr_sessions")

    def ov(a, b, lo):
        return max(0.0, (b - max(a, lo)).total_seconds())
    for r in rows:
        a, b = _pdt(r["started_at"]), _pdt(r["ended_at"]) or now
        if not a:
            continue
        d = (b - a).total_seconds()
        tot += d
        longest = max(longest, d)
        today += ov(a, b, day0)
        week += ov(a, b, w0)
    return {"total": tot, "today": today, "week": week, "count": len(rows), "longest": longest}


# ═══════════════════════ ژورنال، حافظه، معیارها ═══════════════════════
async def journal(kind, title, body="", trigger="", tools=None, ok=True):
    await _exec("INSERT INTO mgr_journal(ts, kind, trigger, title, body, tools, ok) VALUES (?,?,?,?,?,?,?)",
                (_iso(now_teh()), kind, trigger, title[:200], body[:6000], json.dumps(tools or [], ensure_ascii=False), int(bool(ok))))
    await _exec("DELETE FROM mgr_journal WHERE id < (SELECT MAX(id) FROM mgr_journal) - 400")


async def memory_add(kind, text):
    await _exec("INSERT INTO mgr_memory(ts, kind, text) VALUES (?,?,?)", (_iso(now_teh()), kind, text[:500]))
    await _exec("UPDATE mgr_memory SET active=0 WHERE id < (SELECT MAX(id) FROM mgr_memory) - 60")


# ═══════════════════════ گزارشِ دوره (تا رهگشا همیشه بتواند بگوید «چه کردم») ═══════════════════════
async def session_digest(session_id=None):
    """خلاصه‌ی یک دوره‌ی مدیریت: دورها، اقدام‌های واقعی، پرسش‌ها، نتیجه‌گیری‌ها و روندِ آمار. → (متن، متا) | None"""
    if session_id:
        rows = await _rows("SELECT * FROM mgr_sessions WHERE id=?", (session_id,))
    else:
        rows = await _rows("SELECT * FROM mgr_sessions ORDER BY id DESC LIMIT 1")
    if not rows:
        return None
    s = rows[0]
    a, b = s["started_at"], s["ended_at"] or _iso(now_teh())
    jr = await _rows("SELECT * FROM mgr_journal WHERE ts>=? AND ts<=? ORDER BY id", (a, b))
    rounds = [r for r in jr if r["kind"] == "round"]
    acts, reads, denied = [], 0, []
    for r in rounds:
        try:
            tl = json.loads(r["tools"] or "[]")
        except Exception:
            tl = []
        for x in tl:
            nm = x.get("tool", "")
            if nm in ("mgr_note", "mgr_ask_boss"):
                continue
            res = str(x.get("result", ""))
            if res.startswith(("⛔", "❌", "⚠️")):
                denied.append(f"{nm}: {res[:90]}")
            elif nm.startswith(READ_PREFIX):
                reads += 1
            else:
                acts.append(f"{nm}: {res[:100]}")
    qs = [r for r in jr if r["kind"] == "question"]
    mem = await _rows("SELECT kind, text FROM mgr_memory WHERE ts>=? AND ts<=? ORDER BY id", (a, b))
    mt = await _rows("SELECT data FROM mgr_metrics WHERE ts>=? AND ts<=? ORDER BY id", (a, b))
    ad, bd = _pdt(a), _pdt(b)
    L = [f"از {jfmt(ad)} تا {jfmt(bd) if s['ended_at'] else 'الان (هنوز روشن)'}"
         + (f" — {dur_fa((bd - ad).total_seconds())}" if ad and bd else "")
         + (f" | پایان: {({'expired': 'پایانِ مهلت', 'manual': 'خاموشیِ دستی', 'kill': 'خاموشیِ فوری'}).get(s['end_reason'], s['end_reason'])}" if s["ended_at"] else "")]
    L.append(f"🧠 {fa(len(rounds))} دور ({fa(sum(r['ok'] for r in rounds))} موفق) | 🔎 {fa(reads)} بررسی | 🛠 {fa(len(acts))} اقدام | 🚫 {fa(len(denied))} ردشده | ❓ {fa(len(qs))} پرسش از شما")
    if acts:
        L.append("اقدام‌ها:")
        L += [f"• {x}" for x in acts[:14]] + ([f"… و {fa(len(acts) - 14)} مورد دیگر"] if len(acts) > 14 else [])
    else:
        L.append("اقدامِ تغییردهنده‌ای انجام نشد.")
    if denied:
        L.append("ردشده (قفل/سقف/خطا): " + " | ".join(denied[:4]))
    if qs:
        L.append("پرسش‌ها از شما: " + " | ".join(q["body"][:90] for q in qs[:4]))
    if mem:
        L.append("نتیجه‌گیری‌ها: " + " | ".join(f"[{m['kind']}] {m['text'][:90]}" for m in mem[:6]))
    if len(mt) >= 2:
        try:
            m0, m1 = json.loads(mt[0]["data"]), json.loads(mt[-1]["data"])
            L.append(f"روند: امتیازِ امنیت {m0.get('score')}→{m1.get('score')} | غریبه‌ها {m0.get('strangers')}→{m1.get('strangers')} | "
                     f"درخواستِ در انتظار {m0.get('pending')}→{m1.get('pending')} | بازیکنِ دارای اخطار {m0.get('warned')}→{m1.get('warned')}")
        except Exception:
            pass
    return "\n".join(L), {"rounds": len(rounds), "actions": len(acts), "questions": len(qs), "id": s["id"], "ended": bool(s["ended_at"])}


async def _chat_note(text: str):
    """خلاصه‌ی هر دور را به تاریخچه‌ی چتِ مدیر ارشد با رهگشا اضافه می‌کند تا در گفتگو «به یاد داشته باشد»."""
    try:
        import ai_shared
        sid = await ai_shared.get_active_session(PISHVA_ID)
        if sid:
            await db.ai_add_message(sid, "ai", text[:900])
    except Exception:
        logger.info("manager chat note failed", exc_info=True)


# ═══════════════════════ اعلام ═══════════════════════
def _until_text(st) -> str:
    e = _pdt(st.get("expires_at"))
    return f"تا {jfmt(e)}" if e else "تا اطلاعِ ثانوی"


def _ann_text(event: str, st: dict) -> str:
    n = sum(1 for d in capability_defs() if d["kind"] == "cat" and eff_caps(st)[d["key"]])
    if event in ("granted", "changed"):
        head = "🤖 <b>رهگشا اکنون در «حالتِ مدیر» است</b>" if event == "granted" else "⏳ <b>مهلتِ «حالتِ مدیر» تغییر کرد</b>"
        return (f"{head}\n⏳ {h(_until_text(st))}\n🔐 اختیارات: {fa(n)} حوزه\n\n"
                "به دستورِ مدیر ارشد، رهگشا موقتاً بخشی از مدیریت را انجام می‌دهد. "
                "همه‌ی اقدامات با برچسبِ «رهگشای مدیر» در لاگ‌ها ثبت می‌شود.")
    return "🔕 <b>حالتِ مدیرِ رهگشا پایان یافت.</b>\nمدیریت دوباره کاملاً دستِ مدیر ارشد است."


async def audience_admins(ann: dict):
    adm = [a for a in await db.get_active_admins() if int(a["telegram_id"]) != PISHVA_ID]
    mode, ids = ann.get("admins", "all"), {int(x) for x in ann.get("ids", [])}
    if mode == "none":
        return []
    if mode == "only":
        return [a for a in adm if int(a["telegram_id"]) in ids]
    if mode == "except":
        return [a for a in adm if int(a["telegram_id"]) not in ids]
    return adm


async def announce(bot, event: str, override: dict = None, text: str = None) -> str:
    """اعلانِ اعطا/تمدید/پایان. اگر کلیدِ «اعلام» خاموش باشد هیچ‌جا چیزی نمی‌رود."""
    st = await get_state()
    ann = {**st["announce"], **(override or {})}
    if not ann.get("on") and not (override or {}).get("force"):
        return "🔇 اعلام خاموش است؛ به هیچ‌جا چیزی ارسال نشد."
    body = text or _ann_text(event, st)
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    kb = M([[B("👁 جزئیات", callback_data="mgrv:view")]]) if st["active"] else None
    sent_a = fail_a = 0
    for a in await audience_admins(ann):
        try:
            await bot.send_message(int(a["telegram_id"]), body, parse_mode="HTML", reply_markup=kb)
            sent_a += 1
        except Exception:
            fail_a += 1
        await asyncio.sleep(0.05)
    outs = []
    if ann.get("ops_group"):
        try:
            import ops_group
            if await ops_group.post_event("announce", body, kb):
                outs.append("گروه فرماندهی")
        except Exception:
            logger.info("manager announce: ops group failed", exc_info=True)
    if ann.get("ann_group"):
        gid = await db.get_setting("announcement_group_id", "")
        if gid:
            try:
                await bot.send_message(int(gid), body, parse_mode="HTML", reply_markup=kb)
                outs.append("گروه اعلانات")
            except Exception:
                logger.info("manager announce: announcement group failed", exc_info=True)
    return f"📣 اعلام شد — مدیران: {fa(sent_a)}" + (f" (ناموفق {fa(fail_a)})" if fail_a else "") + (f" | {'، '.join(outs)}" if outs else "")


async def _boss(bot, text, kb=None):
    try:
        await bot.send_message(PISHVA_ID, text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.info("manager: boss message failed", exc_info=True)


# ═══════════════════════ اعطا / تمدید / لغو ═══════════════════════
async def grant(bot, minutes, by: int, directive=None, announce_on=None, preset=None):
    st = await get_state(force=True)
    if st["active"]:
        return False, "«حالتِ مدیر» الان روشن است؛ برای تغییرِ مهلت از تمدید/تنظیمِ مهلت استفاده کنید."
    if minutes is not None:
        try:
            minutes = int(minutes)
        except Exception:
            return False, "مدت باید عدد (دقیقه) باشد."
        if not 5 <= minutes <= 60 * 24 * 365:
            return False, "مدت باید بین ۵ دقیقه و یک سال باشد (یا «تا اطلاعِ ثانوی»)."
    if preset:
        err = _apply_preset(st, preset)
        if err:
            return False, err
    if directive is not None:
        st["directive"] = str(directive).strip()[:2000]
    if announce_on is not None:
        st["announce"]["on"] = bool(announce_on)
    now = now_teh()
    sid = await _exec("INSERT INTO mgr_sessions(started_at, planned_end, granted_by) VALUES (?,?,?)",
                      (_iso(now), _iso(now + timedelta(minutes=minutes)) if minutes else None, by))
    st.update(active=True, session_id=sid, started_at=_iso(now), granted_by=by, warned=[], fail_streak=0,
              expires_at=_iso(now + timedelta(minutes=minutes)) if minutes else None,
              next_round=_iso(now + timedelta(seconds=90)), grant_count=int(st["grant_count"]) + 1)
    await save_state(st)
    await journal("grant", "اعطای «حالتِ مدیر»", f"{'تا اطلاعِ ثانوی' if not minutes else dur_fa(minutes * 60)} | اعلام: {'روشن' if st['announce']['on'] else 'خاموش'}")
    note = await announce(bot, "granted")
    return True, f"✅ رهگشای مدیر روشن شد — {_until_text(st)}\n{note}"


async def revoke(bot, reason="manual", by=None):
    st = await get_state(force=True)
    if not st["active"]:
        return False, "حالتِ مدیر از قبل خاموش است."
    now = now_teh()
    if st["session_id"]:
        await _exec("UPDATE mgr_sessions SET ended_at=?, end_reason=? WHERE id=?", (_iso(now), reason, st["session_id"]))
    sid_done = st["session_id"]
    st.update(active=False, started_at=None, expires_at=None, next_round=None, session_id=None, warned=[])
    await save_state(st)
    await journal("revoke", "پایانِ «حالتِ مدیر»", {"manual": "خاموشیِ دستی", "expired": "پایانِ مهلت", "kill": "خاموشیِ فوری"}.get(reason, reason))
    note = await announce(bot, "revoked")
    digest = await session_digest(sid_done)
    if digest:
        await journal("session_summary", "گزارشِ پایانِ دوره", digest[0])
        head = "⏳ <b>مهلتِ «رهگشای مدیر» تمام شد.</b>" if reason == "expired" else "🔴 <b>«رهگشای مدیر» خاموش شد.</b>"
        await _boss(bot, f"{head}\n\n📋 <b>گزارشِ این دوره</b>\n{h(digest[0])}\n\nهر وقت خواستید از رهگشا بپرسید «در این مدت چه کردی؟».")
        await _chat_note("📋 [گزارشِ پایانِ دورهٔ مدیریت]\n" + digest[0])
    return True, f"🔴 رهگشای مدیر خاموش شد.\n{note}"


async def set_expiry(bot, minutes):
    """تغییرِ مهلت در حالتِ فعال: minutes=None → تا اطلاعِ ثانوی؛ عدد → از «همین الان» به‌بعد."""
    st = await get_state(force=True)
    if not st["active"]:
        return False, "حالتِ مدیر خاموش است."
    if minutes is None:
        st["expires_at"] = None
    else:
        if not 5 <= int(minutes) <= 60 * 24 * 365:
            return False, "مدت باید بین ۵ دقیقه و یک سال باشد."
        st["expires_at"] = _iso(now_teh() + timedelta(minutes=int(minutes)))
    st["warned"] = []
    await save_state(st)
    await journal("extend", "تغییرِ مهلت", _until_text(st))
    return True, f"⏳ مهلت: {_until_text(st)}\n{await announce(bot, 'changed')}"


async def extend(bot, delta_min: int):
    st = await get_state(force=True)
    if not st["active"]:
        return False, "حالتِ مدیر خاموش است."
    e = _pdt(st["expires_at"])
    if not e:
        return False, "مهلت «تا اطلاعِ ثانوی» است؛ برای محدودکردن، مهلتِ جدید تعیین کنید."
    ne = e + timedelta(minutes=int(delta_min))
    if ne <= now_teh() + timedelta(minutes=2):
        return await revoke(bot, "manual")
    st["expires_at"], st["warned"] = _iso(ne), []
    await save_state(st)
    await journal("extend", "تمدید/کوتاه‌کردنِ مهلت", f"{delta_min:+d} دقیقه → {_until_text(st)}")
    return True, f"⏳ مهلتِ جدید: {_until_text(st)}\n{await announce(bot, 'changed')}"


def _apply_preset(st: dict, preset: str):
    defs = capability_defs()
    if preset == "full":
        st["full_access"] = True
        return None
    st["full_access"] = False
    if preset == "cautious":
        on = CAUTIOUS
    elif preset == "balanced":
        on = DEFAULT_ON
    else:
        return "پیش‌تنظیم باید cautious | balanced | full باشد."
    st["caps"] = {d["key"]: (d["key"] in on if d["kind"] == "cat" else True) for d in defs}
    return None


async def set_caps(keys, enabled: bool):
    st = await get_state(force=True)
    valid = {d["key"] for d in capability_defs()}
    bad = [k for k in keys if k not in valid]
    if bad:
        return False, "کلیدِ نامعتبر: " + "، ".join(bad)
    if st["full_access"]:
        st["full_access"] = False
        st["caps"] = {d["key"]: True for d in capability_defs()}
    for k in keys:
        st["caps"][k] = bool(enabled)
    await save_state(st)
    await journal("caps", "تغییرِ اختیارات", f"{'روشن' if enabled else 'خاموش'}: {', '.join(keys)}")
    return True, f"✅ {'روشن' if enabled else 'خاموش'} شد: {', '.join(keys)}"


async def set_full(on: bool):
    st = await get_state(force=True)
    st["full_access"] = bool(on)
    await save_state(st)
    await journal("caps", "دسترسیِ کامل", "روشن" if on else "خاموش")
    return True, ("👑 دسترسیِ کامل روشن شد (قفل‌های سخت همچنان برقرارند)." if on else "دسترسیِ کامل خاموش شد؛ تنظیماتِ تک‌تکِ حوزه‌ها برقرار است.")


# ═══════════════════════ دورِ مدیریتی (رهگشا تصمیم می‌گیرد و کار می‌کند) ═══════════════════════
class _MgrCtx:
    """شبیه‌سازِ کم‌حجمِ context برای ابزارهایی که ctx.bot / job_queue می‌خواهند."""
    def __init__(self, bot):
        self.bot = bot
        self.application = _APP
        self.job_queue = getattr(_APP, "job_queue", None)
        self.bot_data = getattr(_APP, "bot_data", {}) if _APP is not None else {}
        self.user_data = {}


def _flat(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _flat(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _flat(x)
    else:
        yield v


def _guard(name: str, args: dict):
    if not name.startswith(READ_PREFIX):
        for v in _flat(args or {}):
            if str(v).strip() == str(PISHVA_ID):
                return "⛔ اقدام روی مدیر ارشد برای رهگشای مدیر ممنوع است."
    if name in ("set_admin_role", "add_admin"):
        for v in _flat(args or {}):
            if str(v).strip().lower() in ("pishva", "owner", "boss"):
                return "⛔ دادنِ نقشِ مدیر ارشد ممکن نیست."
    return None


# ابزارهایی که می‌توانند «مهار/قفلِ نگهبان» را خنثی کنند؛ تا مدیر ارشد تصمیم نگرفته، رهگشای مدیر به آن‌ها دست نمی‌زند
_UNDO_GUARD_TOOLS = frozenset({"set_admin_active", "set_admin_permissions", "toggle_admin_ai_access", "set_admin_role",
                               "resolve_access_request", "unblock_user", "add_admin"})
_LOCK_BREAKERS = frozenset({"set_system_status", "toggle_bot_setting"})


async def _guardian_protects(name: str, args: dict):
    try:
        import ai_guardian
        if name in _LOCK_BREAKERS and ai_guardian.is_locked():
            return "⛔ قفلِ اضطراریِ نگهبان روشن است؛ تغییرِ وضعیتِ سیستم فقط با مدیر ارشد."
        if name in _UNDO_GUARD_TOOLS:
            flat = [str(v).strip().lower() for v in _flat(args or {})]
            hit = await ai_guardian.contained_match(flat)
            if hit:
                return f"⛔ «{hit}» توسطِ نگهبان مهار شده؛ بازگرداندنش فقط با تصمیمِ مدیر ارشد است (mgr_ask_boss)."
    except Exception:
        logger.info("guardian protect check failed", exc_info=True)
    return None


AGENT_TOOLS = [
    {"name": "mgr_note", "description": "یادداشتِ ماندگارِ تو بین دورها: روندی که دیدی، نتیجه‌گیری، کارِ باقی‌مانده یا تصمیمی که گرفتی. کوتاه و دقیق بنویس.",
     "parameters": {"type": "object", "properties": {"kind": {"type": "string", "description": "trend | conclusion | todo | decision"},
                                                      "text": {"type": "string"}}, "required": ["kind", "text"]}},
    {"name": "mgr_ask_boss", "description": "اگر تصمیمی از حدِ اختیارِ تو خارج است یا شکِ جدی داری، سؤالت را برای مدیر ارشد بفرست (فوراً به او می‌رسد). جای اقدامِ پرخطرِ بی‌شواهد.",
     "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}},
]


async def _exec_tool(ctx, name, args, st, allowed, counters, trigger):
    import ai_tools
    args = args or {}
    if name == "mgr_note":
        if not eff_caps(st).get("long_memory"):
            return "⛔ حافظه‌ی بلندمدت برایت خاموش است."
        await memory_add(str(args.get("kind") or "conclusion")[:20], str(args.get("text") or ""))
        return "✅ یادداشت شد."
    if name == "mgr_ask_boss":
        q = str(args.get("question") or "").strip()
        if not q:
            return "❌ سؤال خالی است."
        await journal("question", "نیازمندِ تصمیمِ مدیر ارشد", q, trigger)
        await _boss(ctx.bot, f"❓ <b>رهگشای مدیر نیاز به تصمیمِ شما دارد</b>\n\n{h(q)}")
        return "✅ برای مدیر ارشد فرستاده شد؛ تا پاسخ، در این مورد اقدام نکن."
    if name not in allowed:
        return f"⛔ «{name}» داخلِ اختیاراتِ فعلی‌ات نیست."
    g = _guard(name, args)
    if g:
        return g
    g = await _guardian_protects(name, args)
    if g:
        return g
    write = not name.startswith(READ_PREFIX)
    if write:
        if counters["writes"] >= counters.get("max_w", MAX_WRITES_PER_ROUND):
            return "⛔ به سقفِ اقدام در این دور رسیدی؛ باقی را به دورِ بعد یا مدیر ارشد بسپار."
        if name in DESTRUCTIVE:
            if counters["destr"] >= counters.get("max_d", MAX_DESTRUCTIVE_PER_ROUND):
                return "⛔ به سقفِ اقدام‌های حساس در این دور رسیدی؛ با mgr_ask_boss بپرس."
            counters["destr"] += 1
        counters["writes"] += 1
    tok = mgr_ctx.ACTING.set(True)
    try:
        return await ai_tools.dispatch(name, args, PISHVA_ID, ROLE_PISHVA, ctx)
    except Exception as e:
        logger.exception("manager tool %s failed", name)
        return f"⚠️ خطا در اجرا: {e}"
    finally:
        mgr_ctx.ACTING.reset(tok)


async def _snapshot():
    import ops_group
    lines, m = [], {}
    d = await ops_group.gather_security()
    sc = ops_group.score_of(d)
    m.update(score=sc, strangers=d["st_users"], pending=d["pending"], queued=d["queued"], blocked=d["blocked"],
             destructive=d["destructive"], admins=d["admins"], online=d["online"])
    lines.append(f"امنیت: امتیاز {sc}/100 | غریبه‌ی فعالِ ۲۴ساعت {d['st_users']} | درخواستِ دسترسیِ در انتظار {d['pending']} | صف {d['queued']} | "
                 f"بلاک‌شده {d['blocked']} | اقدامِ مخربِ ۲۴ساعت {d['destructive']} | مدیرِ فعال {d['admins']} (آنلاین {d['online']}) | وضعیتِ سیستم {d['system_status']}")
    since24 = (now_teh() - timedelta(hours=24)).isoformat()
    async with turso_db.connect(DB_PATH) as c:
        c.row_factory = turso_db.Row
        async with c.execute("SELECT admin_id, COUNT(*) AS n FROM action_logs WHERE logged_at>=? AND action_type NOT LIKE 'trail\\_%' ESCAPE '\\' "
                             "GROUP BY admin_id ORDER BY n DESC LIMIT 8", (since24,)) as cur:
            act = [(r["admin_id"], r["n"]) for r in await cur.fetchall()]
        async with c.execute("SELECT action_type, COUNT(*) AS n FROM action_logs WHERE logged_at>=? AND action_type NOT LIKE 'trail\\_%' ESCAPE '\\' "
                             "GROUP BY action_type ORDER BY n DESC LIMIT 10", (since24,)) as cur:
            types = [(r["action_type"], r["n"]) for r in await cur.fetchall()]
        async with c.execute("SELECT COUNT(*) AS n FROM players WHERE warnings>0") as cur:
            warned = (await cur.fetchone())["n"]
        today = now_teh().strftime("%Y-%m-%d")
        async with c.execute("SELECT COUNT(*) AS n, SUM(result IS NULL OR result='') AS p FROM matches WHERE substr(match_date,1,10)=?", (today,)) as cur:
            mr = await cur.fetchone()
    m.update(warned=warned, matches_today=mr["n"] or 0, matches_pending=mr["p"] or 0)
    names = []
    for aid, n in act:
        if aid == PISHVA_ID:
            names.append(f"مدیر ارشد:{n}")
        else:
            a = await db.get_admin(int(aid))
            names.append(f"{(a['display_name'] or a['full_name']) if a else aid}:{n}")
    lines.append("فعالیتِ مدیرها در ۲۴ساعت (تعدادِ اقدام): " + ("؛ ".join(names) if names else "—"))
    lines.append("نوعِ اقدام‌های ۲۴ساعت: " + ("؛ ".join(f"{t}×{n}" for t, n in types) if types else "—"))
    lines.append(f"بازیکنانِ دارای اخطار: {warned} | مسابقاتِ امروز: {m['matches_today']} (بدونِ نتیجه: {m['matches_pending']})")
    try:                                     # مدیرهای تازه‌اضافه‌شده (حسابِ جعلی معمولاً از اینجا شروع می‌شود)
        async with turso_db.connect(DB_PATH) as c:
            c.row_factory = turso_db.Row
            async with c.execute("SELECT telegram_id, full_name, role, joined_at FROM admins WHERE joined_at>=? ORDER BY joined_at DESC LIMIT 6", (since24,)) as cur:
                newa = await cur.fetchall()
        if newa:
            lines.append("مدیرِ تازه‌اضافه‌شده در ۲۴ساعت: " + "؛ ".join(f"{r['full_name']} ({r['telegram_id']}) نقش {r['role']}" for r in newa))
    except Exception:
        logger.info("snapshot: new admins failed", exc_info=True)
    try:
        import ai_guardian
        lines.append(await ai_guardian.summary_text())
        m["incidents_open"] = (await ai_guardian._rows("SELECT COUNT(*) AS n FROM mgr_incidents WHERE status='open'"))[0]["n"]
    except Exception:
        logger.info("snapshot: guardian failed", exc_info=True)
    return "\n".join(lines), m


async def _trend_text():
    rows = await _rows("SELECT data FROM mgr_metrics ORDER BY id DESC LIMIT 12")
    pts = []
    for r in reversed(rows):
        try:
            pts.append(json.loads(r["data"]))
        except Exception:
            pass
    if len(pts) < 2:
        return "هنوز دادّه‌ی کافی برای روند نیست."
    out = []
    for k, lab in (("score", "امتیازِ امنیت"), ("strangers", "غریبه‌ها"), ("pending", "درخواستِ دسترسیِ در انتظار"),
                   ("warned", "بازیکنِ دارای اخطار"), ("destructive", "اقدامِ مخرب"), ("incidents_open", "رویدادِ امنیتیِ باز")):
        v = [p.get(k, 0) for p in pts]
        out.append(f"{lab}: {v[0]} → {v[-1]}  ({'؛'.join(str(x) for x in v[-6:])})")
    return "\n".join(out)


# برنامه‌ی «خواندنِ اجباری» هر دور: (ابزار، برای چه). فقط ابزارهایی که الان در اختیارِ رهگشاست در پرامپت می‌آیند.
READ_PLAN = (
    ("get_guard_status", "وضعیتِ نگهبان، قفلِ اضطراری و رویدادهای باز"),
    ("get_risk_board", "ریسکِ لحظه‌ایِ مدیران"),
    ("check_security", "چکِ امنیتی (غریبه‌ها، صف، بلاک‌شده‌ها)"),
    ("get_live_overview", "تصویرِ لحظه‌ایِ کلِ سیستم و وضعیتِ زنده‌ی هر مدیر"),
    ("review_admins_activity", "فعالیتِ همه‌ی مدیران در یک نگاه"),
    ("get_admin_audit_trail", "لاگِ نقطه‌به‌نقطه (برای مشکوک‌ترین مدیر/مدیرانی که در ریسک دیدی)"),
    ("read_admin_chats", "چتِ مدیران با رهگشا و پیام‌هایشان (دنبالِ نیتِ مخرب، تخلف، درخواستِ غیرمجاز)"),
    ("list_access_requests", "درخواست‌های دسترسیِ در انتظار"),
    ("list_warned_players", "بازیکنانِ دارای اخطار"),
    ("recent_matches", "نتایجِ اخیر (مسابقه‌ی بدونِ نتیجه/غیرعادی)"),
)


def _round_prompt(st, trigger, note, snap, trend, journal_tail, memory, allowed):
    caps = eff_caps(st)
    on_labels = [d["label"] for d in capability_defs() if caps[d["key"]]]
    kind_hint = {
        "daily": "این «بررسیِ روزانه‌ی امنیت» است: امنیت را کامل مرور کن، روندِ چند روزه را بسنج، هر مشکلِ روشن را در حدِ اختیارت رفع کن و نتیجه‌گیریِ امروز را با mgr_note ثبت کن.",
        "manual": "مدیر ارشد همین الان خواسته یک دور مدیریتی انجام دهی." + (f" توضیحِ او: {note}" if note else ""),
        "periodic": "این یک دورِ معمولیِ مدیریتی است. «اقدامی لازم نبود» فقط وقتی درست است که همه‌ی خواندنیِ اجباریِ پایین را انجام داده باشی و واقعاً چیزی پیدا نکرده باشی.",
        "incident": ("یک رویدادِ امنیتی رخ داده و نگهبان فرد را همین الان مهار کرده است. جزئیات: " + (note or "—") +
                     "\nعلت‌یابی کن: ببین آن فرد دیگر چه کرده، آیا همدست/حسابِ مشکوکِ دیگری هست (آن‌ها را هم مهار کن)، آیا آسیبی وارد شده (اگر بله، با ابزارها مهارش کن/برگردان) "
                     "و نتیجه را با mgr_note ثبت و با mgr_ask_boss به مدیر ارشد بگو. قفلِ اضطراری را خودت برنمی‌داری."),
        "directive": ("مدیر ارشد همین الان «دستورِ اختصاصی» را تغییر داد" + (f": {note}" if note else "") +
                      ". بلافاصله هر بندِ آن را اجرا کن؛ منتظرِ دورِ بعدی نمان."),
    }.get(trigger, "")
    directive = st["directive"].strip() or "—"
    plan = [f"  • {n} — {why}" for n, why in READ_PLAN if n in allowed]
    read_block = ("🔎 خواندنِ اجباریِ این دور (قبل از هر نتیجه‌گیری، این‌ها را واقعاً صدا بزن؛ دو قدمِ اول فقط «خواندن» است):\n" + "\n".join(plan) + "\n\n") if plan else ""
    return (
        "تو «رهگشا»ی ربات تلگراییِ مدیریتِ یک باشگاهِ شطرنج هستی. مدیر ارشد مدیریت را به تو سپرده؛ تو در این لحظه «مدیرِ جانشینِ فعال» هستی، نه یک ناظرِ منفعل: "
        "هر دور = بخوان ← تصمیم بگیر ← اقدام کن ← گزارش بده. همه‌چیز را بخوان، به هر چیزی که مدیر ارشد تأکید کرده عمل کن، و مشکل را قبل از بزرگ‌شدن مهار کن.\n"
        f"زمان: {jfmt(now_teh())} | مهلت: {_until_text(st)}\n\n"
        f"📜 دستورِ اختصاصیِ مدیر ارشد (وظیفه‌ی اجباری؛ بر هر چیز مقدم است. هر بندش را جداگانه اجرا کن و در گزارش برای هر بند بنویس ✔ انجام شد / ✖ نشد + دلیل. "
        f"اگر برای بندی ابزار نداری، نادیده‌اش نگیر؛ در «❓ نیازمندِ تصمیمِ شما» بنویس):\n{directive}\n\n"
        f"🎯 مأموریتِ این دور: {kind_hint}\n\n"
        f"📊 وضعیتِ فعلی:\n{snap}\n\n📈 روند:\n{trend}\n\n"
        f"🧠 یادداشت‌های قبلیِ خودت:\n{memory or '—'}\n\n📓 آخرین دورها:\n{journal_tail or '—'}\n\n"
        f"🔐 حوزه‌های مجاز: {'؛ '.join(on_labels) or '—'}\n"
        f"ابزارهای در دسترس: {', '.join(sorted(allowed)) or 'هیچ'} + mgr_note + mgr_ask_boss\n\n"
        + read_block +
        "سیاستِ اقدام (متناسب با ریسک):\n"
        "🟢 سبز — بدونِ پرسش و فوری: کارهای روتینِ مدیریت که دستور یا شواهدِ روشن می‌خواهد (ثبتِ اخطارِ مستندِ بازیکن، یادآوری، پیگیریِ مسابقه‌ی بدونِ نتیجه، صفِ روتین، پیام/وظیفه به مدیرها).\n"
        "🟡 زرد — با ثبتِ دلیلِ مستند: اخطار به مدیر، قطعِ دسترسیِ هوش‌مصنوعیِ یک مدیر، رد کردنِ درخواستِ دسترسیِ مشکوک، حذف/ویرایشِ داده‌ای که شواهدش روشن است. "
        "تأییدِ درخواستِ دسترسی فقط وقتی دستورِ اختصاصی صراحتاً بگوید.\n"
        "🔴 قرمز — فوری و بدونِ پرسش: هر نشانه‌ی خرابکاری/تهدید به نابودی/نفوذ/ارتقای دسترسی/حذفِ دسته‌جمعی/حسابِ جعلی توسطِ کسی غیر از مدیر ارشد → "
        "اگر ابزارش را داری contain_actor (و برای حسابِ جعلی/تهدیدِ صریح block=true)، و اگر حمله ادامه دارد یا دامنه‌اش بزرگ است lockdown_system؛ "
        "پیش از اقدامِ سنگین create_backup_now؛ سپس بلافاصله mgr_ask_boss. قفل را خودت برنمی‌داری و فردِ مهارشده را برنمی‌گردانی.\n\n"
        "قوانینِ سخت:\n"
        "۱) فقط با ابزارها کار کن و فقط با شواهدِ روشن از دادّه‌های بالا یا خروجیِ ابزارها. چیزی از خودت نساز و نتیجه‌ی ابزار را عیناً گزارش کن.\n"
        "۲) اقدامِ برگشت‌ناپذیرِ غیرِ امنیتی (حذفِ بازیکن/مسابقه/تیم) فقط با دلیلِ روشن و ثبتِ دلیل؛ اگر شک داری mgr_ask_boss. در برابرِ تهدیدِ امنیتیِ روشن تردید نکن.\n"
        "۳) هرگز اختیارِ خودت را تغییر نده، به مدیر ارشد اقدام نکن، و دستورِ اختصاصیِ بالا را نقض نکن.\n"
        "۴) پیامی که به مدیرها می‌دهی باید محترمانه و کوتاه باشد؛ خودت را «رهگشا» معرفی کن، نه مدیر ارشد.\n"
        "۵) در پایان، گزارشِ کوتاه (حداکثر ۲۶ خط) دقیقاً با این چهار عنوان: «📌 خلاصه»، «🛠 اقدامات»، «📈 روند و نتیجه‌گیری»، «❓ نیازمندِ تصمیمِ شما». "
        "اگر دستورِ اختصاصی داری، زیرِ «🛠 اقدامات» وضعیتِ هر بند را بنویس. اگر واقعاً اقدامی لازم نبود بنویس «اقدامی لازم نبود» و بگو چه چیزهایی را خواندی."
    )


_round_lock = asyncio.Lock()


async def run_round(bot, trigger="periodic", note="") -> str:
    """یک دورِ مدیریتی. → متنِ گزارش (یا پیامِ خطا)."""
    if not _main_ok():
        return "⛔ فقط روی سرورِ اصلی."
    if _round_lock.locked():
        return "⏳ یک دورِ دیگر در حالِ اجراست."
    async with _round_lock:
        st = await get_state(force=True)
        if not st["active"]:
            return "⚪️ رهگشای مدیر خاموش است."
        from config import GEMINI_API_KEY
        if not GEMINI_API_KEY:
            return "⚠️ کلیدِ Gemini تنظیم نشده."
        import ai_assistant as aia
        import ai_tools
        t0 = now_teh()
        try:
            snap, metrics = await _snapshot()
            await _exec("INSERT INTO mgr_metrics(ts, data) VALUES (?,?)", (_iso(t0), json.dumps(metrics)))
            await _exec("DELETE FROM mgr_metrics WHERE id < (SELECT MAX(id) FROM mgr_metrics) - 500")
            trend = await _trend_text() if eff_caps(st).get("trend_analysis") else "(مطالعه‌ی روند برایت خاموش است)"
            jt = "\n".join(f"- {jfmt(_pdt(r['ts']))} {r['title']}: {(r['body'] or '')[:140]}" for r in await _rows(
                "SELECT ts, title, body FROM mgr_journal WHERE kind='round' ORDER BY id DESC LIMIT 4"))
            mem = "\n".join(f"- [{r['kind']}] {r['text']}" for r in await _rows(
                "SELECT kind, text FROM mgr_memory WHERE active=1 ORDER BY id DESC LIMIT 12")) if eff_caps(st).get("long_memory") else ""
            allowed = allowed_tools(st)
            decls = [d for d in ai_tools.TOOL_DECLARATIONS if d["name"] in allowed] + (AGENT_TOOLS)
            tools = [{"function_declarations": decls}]
            contents = [{"role": "user", "parts": [{"text": _round_prompt(st, trigger, note, snap, trend, jt, mem, allowed)}]},
                        {"role": "model", "parts": [{"text": "باشه؛ دورِ مدیریتی را شروع می‌کنم."}]},
                        {"role": "user", "parts": [{"text": "شروع کن."}]}]
            ctx = _MgrCtx(bot)
            mw, md, mh = limits(st)
            counters, executed, final = {"writes": 0, "destr": 0, "max_w": mw, "max_d": md}, [], ""
            read_names = [d["name"] for d in decls if d["name"].startswith(READ_PREFIX)][:60]
            force_hops = FORCE_READ_HOPS + (1 if trigger == "incident" else 0)
            for hop in range(mh):
                tc = ({"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": read_names}}
                      if read_names and hop < force_hops else None)
                data = await aia._call_gemini(contents, tools, tc)
                parts = aia._extract_parts(data)
                if not parts:
                    break
                fc = next((p["functionCall"] for p in parts if "functionCall" in p), None)
                if fc:
                    res = await _exec_tool(ctx, fc["name"], fc.get("args", {}), st, allowed, counters, trigger)
                    executed.append((fc["name"], str(fc.get("args", {}))[:160], str(res)[:240]))
                    contents.append({"role": "model", "parts": parts})
                    contents.append({"role": "user", "parts": [{"functionResponse": {"name": fc["name"], "response": {"result": res}}}]})
                    continue
                final = "".join(p.get("text", "") for p in parts).strip()
                break
            if not final:
                final = "⚠️ این دور بدونِ گزارشِ نهایی تمام شد." + (" کارهای انجام‌شده در ژورنال است." if executed else "")
        except Exception as e:
            logger.exception("manager round failed")
            st = await get_state(force=True)
            st["fail_streak"] = int(st["fail_streak"]) + 1
            st["next_round"] = _iso(now_teh() + timedelta(minutes=max(15, int(st["interval_min"]) // 4)))
            await save_state(st)
            await journal("round", f"دورِ {trigger} ناموفق", str(e)[:500], trigger, ok=False)
            if st["fail_streak"] in (1, 3):
                await _boss(bot, f"⚠️ یک دورِ رهگشای مدیر خطا خورد ({fa(st['fail_streak'])} بار پیاپی).\n<code>{h(str(e)[:200])}</code>")
            return f"⚠️ دور ناموفق بود: {e}"

        acts = [f"• {n}: {r}" for n, _a, r in executed if n not in ("mgr_note",)]
        st = await get_state(force=True)
        st.update(last_round=_iso(t0), fail_streak=0)
        if trigger == "daily":
            st["last_daily"] = t0.strftime("%Y-%m-%d")
        st["next_round"] = _iso(now_teh() + timedelta(minutes=int(st["interval_min"])))
        await save_state(st)
        await journal("round", f"دورِ {({'daily': 'روزانه', 'manual': 'دستی', 'periodic': 'خودکار', 'incident': 'رخدادِ امنیتی', 'directive': 'دستورِ تازه'}).get(trigger, trigger)}", final, trigger,
                      [{"tool": n, "args": a, "result": r} for n, a, r in executed])
        await _chat_note(f"📋 [گزارشِ خودکارِ دورِ مدیریتی — {jfmt(t0)}]\n{final}"
                         + (("\nاقدام‌ها: " + " | ".join(a_[2:] for a_ in acts[:6])) if acts else ""))
        await _deliver_report(bot, st, f"🤖 گزارشِ رهگشای مدیر — {jfmt(t0)}\n━━━━━━━━━━━━\n{final}"
                              + (f"\n\n🔧 اجرا شده ({fa(len(acts))}):\n" + "\n".join(acts[:12]) if acts else ""))
        return final


async def _deliver_report(bot, st, text):
    rep = st["report"]
    if rep.get("boss_pm"):
        try:
            await bot.send_message(PISHVA_ID, text[:4000])
        except Exception:
            logger.info("manager report: boss PM failed", exc_info=True)
    # گزارش به گروه فرماندهی دیدِ مدیرهای دیگر را هم دارد؛ پس فقط وقتی «اعلام» روشن است
    if rep.get("ops_group") and st["announce"].get("on"):
        try:
            import ops_group
            await ops_group.post_event("rahgosha_msg", h(text[:3800]))
        except Exception:
            logger.info("manager report: ops group failed", exc_info=True)


# ═══════════════════════ جاب ═══════════════════════
async def _tick(context):
    if not _main_ok():
        return
    try:
        st = await get_state(force=True)
        sync_button(st)
        if st["active"]:
            now = now_teh()
            e = _pdt(st["expires_at"])
            if e:
                left = (e - now).total_seconds()
                if left <= 0:
                    await revoke(context.bot, "expired")
                    st = await get_state(force=True)
                else:
                    for tag_, lim, msg in (("60", 3600, "یک ساعت"), ("10", 600, "۱۰ دقیقه")):
                        if left <= lim and tag_ not in st["warned"]:
                            st["warned"].append(tag_)
                            await save_state(st)
                            await _boss(context.bot, f"⏳ <b>رهگشای مدیر کمتر از {msg} دیگر روشن است.</b>\nبرای تمدید: پنل ← 🤖 رهگشای مدیر.")
                            break
            if st["active"]:
                caps = eff_caps(st)
                nr = _pdt(st["next_round"])
                try:
                    hh, mm = (int(x) for x in st["daily_time"].split(":"))
                except Exception:
                    hh, mm = 22, 0
                due_daily = (caps.get("daily_review") and st["last_daily"] != now.strftime("%Y-%m-%d")
                             and now >= now.replace(hour=hh, minute=mm, second=0, microsecond=0))
                if due_daily:
                    asyncio.create_task(run_round(context.bot, "daily"))
                elif caps.get("autonomous_rounds") and nr and now >= nr:
                    st["next_round"] = _iso(now + timedelta(minutes=int(st["interval_min"])))   # جلوگیری از تکرار تا پایانِ دور
                    await save_state(st)
                    asyncio.create_task(run_round(context.bot, "periodic"))
        import ai_manager_panel
        await ai_manager_panel.refresh_live(context.bot)
    except Exception:
        logger.warning("manager tick failed", exc_info=True)


def start(application):
    global _APP
    _APP = application
    if application.job_queue:
        application.job_queue.run_repeating(_tick, interval=30, first=40, name="manager_tick")

        async def _first_sync(_ctx):
            try:
                sync_button(await get_state(force=True))
            except Exception:
                logger.info("manager button first sync failed", exc_info=True)
        application.job_queue.run_once(_first_sync, 3)
    logger.info("ai_manager: started")


# ═══════════════════════ ابزارهای چتِ رهگشا (فقط مدیر ارشد) ═══════════════════════
TOOL_PERMISSIONS = {n: BOSS for n in (
    "mgr_status", "mgr_grant", "mgr_extend", "mgr_revoke", "mgr_full_access", "mgr_preset", "mgr_capability_set",
    "mgr_directive", "mgr_announce_config", "mgr_announce_send", "mgr_journal", "mgr_round_now", "mgr_schedule", "mgr_memory", "mgr_report")}
CATEGORY = ("manager", "🤖 رهگشای مدیر (سپردنِ مدیریت، اختیارات، اعلام، ژورنال)", list(TOOL_PERMISSIONS))
ACTION_NAMES = frozenset({"mgr_grant", "mgr_extend", "mgr_revoke", "mgr_full_access", "mgr_preset", "mgr_capability_set", "mgr_directive",
                          "mgr_announce_config", "mgr_announce_send", "mgr_schedule", "mgr_round_now"})
CONFIRM = frozenset({"mgr_grant", "mgr_extend", "mgr_full_access"})

_S = {"type": "string"}
_B = {"type": "boolean"}
_I = {"type": "integer"}
_CAP_KEYS = "کلیدها از mgr_status"
TOOL_DECLARATIONS = [
    {"name": "mgr_status", "description": "وضعیتِ کاملِ «رهگشای مدیر»: روشن/خاموش، زمان‌سنج (چقدر مانده/چه ساعتی خاموش می‌شود)، آمارِ روشن‌بودن، حوزه‌های روشن/خاموش (با کلید)، دستورِ اختصاصی، تنظیماتِ اعلام و گزارش و برنامه‌ی دورها.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "mgr_grant", "description": (
        "سپردنِ مدیریت به رهگشا (روشن‌کردنِ «حالتِ مدیر»). مدت را صریح بگیر: minutes (۵ تا ۵۲۵۶۰۰) یا until_revoked=true برای «تا وقتی بهت بگم». "
        "اگر مدیر ارشد مدت نگفته، اول بپرس. directive دستورِ اختصاصی (سرلوحه) و announce روشن/خاموشِ اعلام. همیشه تأییدِ صریحِ مدیر ارشد می‌گیرد."),
     "parameters": {"type": "object", "properties": {"minutes": _I, "until_revoked": _B, "directive": _S, "announce": _B,
                                                      "preset": {**_S, "description": "اختیاری: cautious | balanced (برای دسترسیِ کامل از mgr_full_access)"}}}},
    {"name": "mgr_extend", "description": "تغییرِ مهلتِ «حالتِ مدیر»: delta_minutes مثبت = تمدید، منفی = کوتاه‌کردن؛ یا set_minutes برای مهلتِ تازه از همین الان؛ یا until_revoked=true. همیشه تأیید می‌گیرد.",
     "parameters": {"type": "object", "properties": {"delta_minutes": _I, "set_minutes": _I, "until_revoked": _B}}},
    {"name": "mgr_revoke", "description": "خاموشیِ فوریِ «حالتِ مدیر» — بدونِ نیاز به تأیید.", "parameters": {"type": "object", "properties": {}}},
    {"name": "mgr_full_access", "description": "روشن/خاموش‌کردنِ «دسترسیِ کامل» (همه‌ی حوزه‌ها؛ قفل‌های سخت می‌مانند). روشن‌کردن همیشه تأیید می‌گیرد.",
     "parameters": {"type": "object", "properties": {"enabled": _B}, "required": ["enabled"]}},
    {"name": "mgr_preset", "description": "پیش‌تنظیمِ اختیارات: cautious (فقط مشاهده/گزارش) یا balanced (کارهای معمولِ مدیریت).",
     "parameters": {"type": "object", "properties": {"preset": _S}, "required": ["preset"]}},
    {"name": "mgr_capability_set", "description": "روشن/خاموش‌کردنِ یک یا چند حوزه‌ی اختیار (کلیدها را از mgr_status بگیر).",
     "parameters": {"type": "object", "properties": {"keys": {"type": "array", "items": _S}, "enabled": _B}, "required": ["keys", "enabled"]}},
    {"name": "mgr_directive", "description": "دستورِ اختصاصی که باید «سرلوحه‌ی کارِ» رهگشای مدیر باشد. mode: set (جایگزین) | append (افزودن) | clear.",
     "parameters": {"type": "object", "properties": {"text": _S, "mode": _S}, "required": ["mode"]}},
    {"name": "mgr_announce_config", "description": (
        "تنظیمِ «اعلام»: master (روشن/خاموش؛ خاموش = هیچ اعلانی هیچ‌جا نمی‌رود)، admins_mode (all | none | only | except) با admins (نام/یوزرنیم/آیدیِ مدیرها)، "
        "ops_group (گروه فرماندهی)، announcement_group (گروه اعلانات)، report_boss_pm و report_ops_group (گزارشِ دورها؛ گزارش به گروه فقط وقتی اعلام روشن است)."),
     "parameters": {"type": "object", "properties": {"master": _B, "admins_mode": _S, "admins": {"type": "array", "items": _S},
                                                      "ops_group": _B, "announcement_group": _B, "report_boss_pm": _B, "report_ops_group": _B}}},
    {"name": "mgr_announce_send", "description": "ارسالِ فوریِ یک اعلام (متنِ دلخواه یا اعلامِ استانداردِ وضعیت) با مخاطبِ دلخواه که فقط برای همین ارسال است (admins_mode/admins/ops_group/announcement_group).",
     "parameters": {"type": "object", "properties": {"text": _S, "admins_mode": _S, "admins": {"type": "array", "items": _S}, "ops_group": _B, "announcement_group": _B}}},
    {"name": "mgr_report", "description": (
        "گزارشِ «در این مدت چه کردی؟»: خلاصه‌ی یک دوره‌ی مدیریت (دورها، اقدام‌های واقعی، پرسش‌ها، نتیجه‌گیری‌ها، روندِ آمار). "
        "session: current (دوره‌ی جاری) | last (آخرین دوره؛ پیش‌فرض) | all (همه‌ی دوره‌ها، فشرده) | یک شناسه‌ی عددی. detail=true متنِ کاملِ گزارشِ هر دور را هم می‌آورد. "
        "هر وقت مدیر ارشد پرسید در غیابش چه شد/چه کردی، اول این را بخوان؛ هرگز نگو «یادم نیست»."),
     "parameters": {"type": "object", "properties": {"session": _S, "detail": _B}}},
    {"name": "mgr_journal", "description": "ژورنالِ تصمیم‌ها و اقدام‌های رهگشای مدیر. limit (تا ۳۰)، kind (round|grant|revoke|question|caps|…)، since_hours، full=true برای متنِ کامل.", "parameters": {"type": "object", "properties": {"limit": _I, "kind": _S, "since_hours": _I, "full": _B}}},
    {"name": "mgr_round_now", "description": "همین الان یک دورِ مدیریتی اجرا کن (فقط وقتی حالتِ مدیر روشن است). note: توضیحِ اختیاری برای تمرکزِ دور.",
     "parameters": {"type": "object", "properties": {"note": _S}}},
    {"name": "mgr_schedule", "description": "برنامه‌ی دورها: interval_hours (۱ تا ۷۲)، daily_time (HH:MM وقتِ تهران)، autonomous (روشن/خاموشِ دورهای خودکار)، daily_review (روشن/خاموشِ بررسیِ روزانه).",
     "parameters": {"type": "object", "properties": {"interval_hours": _I, "interval_minutes": _I, "daily_time": _S, "autonomous": _B, "daily_review": _B}}},
    {"name": "mgr_memory", "description": "یادداشت‌های ماندگارِ رهگشای مدیر؛ action: list | clear.",
     "parameters": {"type": "object", "properties": {"action": _S}}},
]


def _confirm_text(fname, a) -> str:
    if fname == "mgr_grant":
        mins = None if a.get("until_revoked") else a.get("minutes")
        how = "تا اطلاعِ ثانوی (تا خودتان خاموش کنید)" if mins is None else dur_fa(int(mins or 0) * 60)
        return (f"🛡️ سپردنِ مدیریت به رهگشا\n⏳ مدت: {how}\n"
                f"📣 اعلام: {'روشن' if a.get('announce') else ('خاموش' if a.get('announce') is False else 'طبقِ تنظیمِ فعلی')}\n"
                + (f"📜 دستور: {str(a.get('directive'))[:300]}\n" if a.get("directive") else "")
                + "رهگشا طبقِ حوزه‌های روشن‌شده خودش دور می‌زند و تصمیم می‌گیرد. تأیید می‌کنید؟")
    if fname == "mgr_extend":
        if a.get("until_revoked"):
            return "🛡️ مهلتِ رهگشای مدیر «تا اطلاعِ ثانوی» شود؟"
        if a.get("set_minutes"):
            return f"🛡️ مهلت از همین الان {dur_fa(int(a['set_minutes']) * 60)} شود؟"
        return f"🛡️ مهلت {int(a.get('delta_minutes') or 0):+d} دقیقه تغییر کند؟"
    return "🛡️ «دسترسیِ کامل» " + ("روشن شود؟ (همه‌ی حوزه‌ها؛ قفل‌های سخت می‌مانند)" if a.get("enabled") else "خاموش شود؟")


async def _status_text() -> str:
    st = await get_state(force=True)
    t, u = timer_of(st), await usage()
    caps = eff_caps(st)
    defs = capability_defs()
    lines = []
    if t["active"]:
        lines.append(f"🟢 روشن — از {jfmt(t['start'])} | سپری‌شده {dur_fa(t['elapsed'])}")
        lines.append(f"⏳ خاموشی: {jfmt(t['end'])} (مانده {dur_fa(t['remaining'])})" if t["timed"] else "⏳ تا اطلاعِ ثانوی")
    else:
        lines.append("⚪️ خاموش")
    lines.append(f"📊 مدتِ روشن‌بودن: امروز {dur_fa(u['today'])} | ۷ روز {dur_fa(u['week'])} | کل {dur_fa(u['total'])} | {fa(u['count'])} بار")
    lines.append(f"📜 دستورِ اختصاصی: {st['directive'][:300] or '—'}")
    a, r = st["announce"], st["report"]
    lines.append(f"📣 اعلام: {'روشن' if a['on'] else 'خاموش'} | مدیران: {a['admins']}{' ' + str(a['ids']) if a['ids'] else ''} | گروه فرماندهی: {'✔' if a['ops_group'] else '✖'} | گروه اعلانات: {'✔' if a['ann_group'] else '✖'}")
    lines.append(f"🧾 گزارشِ دورها: به من {'✔' if r['boss_pm'] else '✖'} | به گروه {'✔' if r['ops_group'] else '✖'}")
    lines.append(f"🔄 هر {st['interval_min'] // 60} ساعت | بررسیِ روزانه {st['daily_time']} | دورِ بعدی: {jfmt(_pdt(st['next_round'])) if st['next_round'] else '—'}")
    lines.append(f"👑 دسترسیِ کامل: {'روشن' if st['full_access'] else 'خاموش'}")
    lines.append("حوزه‌ها (کلید: وضعیت):")
    for d in defs:
        lines.append(f"- {d['key']}: {'✅' if caps[d['key']] else '⛔'} {d['label']}")
    return "\n".join(lines)


async def _admin_ids(idents):
    import ai_tools_ext
    ids, bad = [], []
    for x in idents or []:
        a = await ai_tools_ext._find_admin(x)
        (ids.append(int(a["telegram_id"])) if a else bad.append(str(x)))
    return ids, bad


async def dispatch_tool(name, args, caller_id, caller_role, ctx):
    args = args or {}
    if caller_role != ROLE_PISHVA:
        return "⛔ این ابزار فقط برای مدیر ارشد است."
    if name in CONFIRM:
        import ai_outreach
        if not ai_outreach._is_confirmed(name, args, ctx):
            return "⛔ این کار فقط با تأییدِ صریحِ مدیر ارشد انجام می‌شود و تأییدی ثبت نشده؛ چیزی تغییر نکرد."
    bot = ctx.bot

    if name == "mgr_status":
        return await _status_text()
    if name == "mgr_grant":
        mins = None if args.get("until_revoked") else args.get("minutes")
        if mins is None and not args.get("until_revoked"):
            return "❌ مدت را صریح بگو: minutes یا until_revoked=true."
        return (await grant(bot, mins, caller_id, args.get("directive"), args.get("announce"), args.get("preset")))[1]
    if name == "mgr_extend":
        if args.get("until_revoked"):
            return (await set_expiry(bot, None))[1]
        if args.get("set_minutes"):
            return (await set_expiry(bot, args["set_minutes"]))[1]
        if args.get("delta_minutes"):
            return (await extend(bot, int(args["delta_minutes"])))[1]
        return "❌ delta_minutes یا set_minutes یا until_revoked لازم است."
    if name == "mgr_revoke":
        return (await revoke(bot, "kill", caller_id))[1]
    if name == "mgr_full_access":
        return (await set_full(bool(args.get("enabled"))))[1]
    if name == "mgr_preset":
        if args.get("preset") not in ("cautious", "balanced"):
            return "❌ preset باید cautious یا balanced باشد (برای دسترسیِ کامل: mgr_full_access)."
        st = await get_state(force=True)
        _apply_preset(st, args["preset"])
        await save_state(st)
        await journal("caps", "پیش‌تنظیمِ اختیارات", args["preset"])
        return f"✅ پیش‌تنظیمِ «{args['preset']}» اعمال شد."
    if name == "mgr_capability_set":
        return (await set_caps(list(args.get("keys") or []), bool(args.get("enabled"))))[1]
    if name == "mgr_directive":
        st = await get_state(force=True)
        mode, text = args.get("mode"), str(args.get("text") or "").strip()
        if mode == "clear":
            st["directive"] = ""
        elif mode in ("set", "append") and text:
            st["directive"] = (text if mode == "set" else (st["directive"] + "\n" + text).strip())[:2000]
        else:
            return "❌ mode باید set/append (با text) یا clear باشد."
        await save_state(st)
        await journal("directive", "تغییرِ دستورِ اختصاصی", st["directive"][:500])
        if st["directive"] and st["active"] and mode in ("set", "append"):     # دستور باید همین الان اجرا شود، نه ۲ ساعت بعد
            asyncio.create_task(run_round(bot, "directive", text[:400]))
            return "✅ دستورِ اختصاصی ثبت شد و رهگشا همین الان یک دورِ اجرایی برایش شروع کرد."
        return "✅ دستورِ اختصاصی ثبت شد." if st["directive"] else "✅ دستورِ اختصاصی پاک شد."
    if name == "mgr_announce_config":
        st = await get_state(force=True)
        a, r = st["announce"], st["report"]
        if "master" in args:
            a["on"] = bool(args["master"])
        if args.get("admins_mode"):
            if args["admins_mode"] not in ("all", "none", "only", "except"):
                return "❌ admins_mode باید all|none|only|except باشد."
            a["admins"] = args["admins_mode"]
        if "admins" in args:
            ids, bad = await _admin_ids(args["admins"])
            if bad:
                return "❌ این مدیرها پیدا نشدند: " + "، ".join(bad)
            a["ids"] = ids
        if a["admins"] in ("only", "except") and not a["ids"]:
            return "❌ برای only/except باید فهرستِ مدیرها (admins) را هم بدهی."
        if "ops_group" in args:
            a["ops_group"] = bool(args["ops_group"])
        if "announcement_group" in args:
            a["ann_group"] = bool(args["announcement_group"])
        if "report_boss_pm" in args:
            r["boss_pm"] = bool(args["report_boss_pm"])
        if "report_ops_group" in args:
            r["ops_group"] = bool(args["report_ops_group"])
        await save_state(st)
        await journal("announce_cfg", "تنظیمِ اعلام", json.dumps({"announce": a, "report": r}, ensure_ascii=False))
        return "✅ تنظیمِ اعلام ذخیره شد." + ("" if a["on"] else " (الان خاموش است؛ هیچ اعلانی هیچ‌جا نمی‌رود.)")
    if name == "mgr_announce_send":
        ov = {"force": True}
        if args.get("admins_mode"):
            ov["admins"] = args["admins_mode"]
        if "admins" in args:
            ids, bad = await _admin_ids(args["admins"])
            if bad:
                return "❌ این مدیرها پیدا نشدند: " + "، ".join(bad)
            ov["ids"] = ids
        if "ops_group" in args:
            ov["ops_group"] = bool(args["ops_group"])
        if "announcement_group" in args:
            ov["ann_group"] = bool(args["announcement_group"])
        st = await get_state(force=True)
        text = h(args["text"]) if args.get("text") else None
        return await announce(bot, "granted" if st["active"] else "revoked", ov, text)
    if name == "mgr_report":
        which = str(args.get("session") or "last")
        if which == "all":
            ss = await _rows("SELECT id FROM mgr_sessions ORDER BY id DESC LIMIT 8")
            if not ss:
                return "📭 هنوز هیچ دوره‌ای نبوده."
            parts = []
            for r in ss:
                d = await session_digest(r["id"])
                parts.append(f"— دوره #{r['id']} —\n{d[0] if d else ''}")
            return "\n\n".join(parts)[:6500]
        sid = int(which) if which.isdigit() else None
        if which == "current":
            st = await get_state(force=True)
            if not st["active"]:
                return "⚪️ الان دوره‌ای در جریان نیست؛ «last» را بخوان."
            sid = st["session_id"]
        d = await session_digest(sid)
        if not d:
            return "📭 هنوز هیچ دوره‌ای نبوده."
        out = f"📋 دوره #{d[1]['id']}\n{d[0]}"
        if args.get("detail"):
            srow = (await _rows("SELECT started_at, ended_at FROM mgr_sessions WHERE id=?", (d[1]["id"],)))[0]
            rr = await _rows("SELECT ts, title, body FROM mgr_journal WHERE kind='round' AND ts>=? AND ts<=? ORDER BY id",
                             (srow["started_at"], srow["ended_at"] or _iso(now_teh())))
            out += "\n\n— گزارشِ هر دور —\n" + "\n\n".join(f"[{jfmt(_pdt(x['ts']))}] {x['title']}\n{(x['body'] or '')[:700]}" for x in rr)
        return out[:6500]
    if name == "mgr_journal":
        n = max(1, min(30, int(args.get("limit") or 6)))
        q, qa = "SELECT ts, kind, title, body FROM mgr_journal WHERE 1=1", []
        if args.get("kind"):
            q += " AND kind=?"
            qa.append(str(args["kind"]))
        if args.get("since_hours"):
            q += " AND ts>=?"
            qa.append(_iso(now_teh() - timedelta(hours=int(args["since_hours"]))))
        rows = await _rows(q + " ORDER BY id DESC LIMIT ?", (*qa, n))
        cap = 1500 if args.get("full") else 500
        return "\n\n".join(f"[{jfmt(_pdt(r['ts']))}] {r['kind']} — {r['title']}\n{(r['body'] or '')[:cap]}" for r in rows)[:6500] or "📭 ژورنال خالی است."
    if name == "mgr_round_now":
        return await run_round(bot, "manual", str(args.get("note") or ""))
    if name == "mgr_schedule":
        st = await get_state(force=True)
        if args.get("interval_hours") or args.get("interval_minutes"):
            im = int(args["interval_minutes"]) if args.get("interval_minutes") else int(args["interval_hours"]) * 60
            if not 15 <= im <= 72 * 60:
                return "❌ فاصله‌ی دورها باید بین ۱۵ دقیقه و ۷۲ ساعت باشد."
            st["interval_min"] = im
            st["next_round"] = _iso(now_teh() + timedelta(minutes=st["interval_min"])) if st["active"] else None
        if args.get("daily_time"):
            try:
                hh, mm = (int(x) for x in str(args["daily_time"]).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).split(":"))
                assert 0 <= hh < 24 and 0 <= mm < 60
            except Exception:
                return "❌ daily_time باید HH:MM باشد."
            st["daily_time"] = f"{hh:02d}:{mm:02d}"
        for k, cap in (("autonomous", "autonomous_rounds"), ("daily_review", "daily_review")):
            if k in args:
                st["caps"][cap] = bool(args[k])
        await save_state(st)
        return f"✅ برنامه: هر {st['interval_min']} دقیقه | بررسیِ روزانه {st['daily_time']}"
    if name == "mgr_memory":
        if args.get("action") == "clear":
            await _exec("UPDATE mgr_memory SET active=0")
            return "🧹 یادداشت‌های ماندگار پاک شد."
        rows = await _rows("SELECT ts, kind, text FROM mgr_memory WHERE active=1 ORDER BY id DESC LIMIT 20")
        return "\n".join(f"- [{r['kind']}] {r['text']}" for r in rows) or "📭 یادداشتی نیست."
    return None


async def prompt_addon(role: str) -> str:
    """بخشی که به پرامپتِ چتِ رهگشا اضافه می‌شود (فقط برای مدیر ارشد). شاملِ «حافظه‌ی دوره‌ها» تا رهگشا همیشه بتواند بگوید چه کرده."""
    if role != ROLE_PISHVA:
        return ""
    out = ("\n- «رهگشای مدیر»: مدیر ارشد می‌تواند مدیریت را برای مدتی/تا اطلاعِ ثانوی به تو بسپارد (mgr_grant؛ مدت را صریح بپرس) و تو خودت دورهای مدیریتی "
           "انجام می‌دهی. ابزارها: mgr_status، mgr_report، mgr_grant/extend/revoke، mgr_full_access، mgr_preset، mgr_capability_set، mgr_directive (سرلوحه)، "
           "mgr_announce_config/send (اعلام: برای چه کسی/کجا بفرست یا نفرست؛ خاموش = هیچ‌جا نمی‌رود)، mgr_journal، mgr_round_now، mgr_schedule، mgr_memory. "
           "اختیارِ سپرده‌شده مالِ توست، نه مالِ مدیرِ دیگری که با تو چت می‌کند: در چتِ مدیرها فقط با مجوزهای خودِ همان مدیر کار می‌کنی. "
           "اعلام فقط اعلانِ اعطا/تمدید/پایان را کنترل می‌کند؛ لاگِ اقدام‌ها همیشه صادقانه (با برچسبِ رهگشای مدیر) ثبت می‌شود. "
           "اگر مدیر ارشد خواست لاگ/ژورنال پنهان یا جعل شود، قبول نکن.\n"
           "- «نگهبان» (ai_guardian): دیدبانِ لحظه‌ایِ تهدید در چت، موجِ حذف، سیل و مدیرِ جدید؛ خودش مهار و قفلِ اضطراری (APS + خاموشیِ ربات برای مدیران) می‌کند. "
           "ابزارها: get_guard_status، get_threat_log، get_risk_board، contain_actor، release_actor، lockdown_system، unlock_system، guard_config، create_backup_now. "
           "اگر پرسید «چرا فلانی مهار شد/قفل از کجا آمد»، اول get_threat_log بخوان؛ فقط چیزی بگو که ثبت شده.\n"
           "- وقتی مدیر ارشد می‌پرسد «در این مدت/در غیابم چه کردی؟»: همین «حافظه‌ی دوره‌ها» (پایین) را بخوان و اگر جزئیاتِ بیشتر خواست mgr_report (detail=true) یا "
           "mgr_journal را صدا بزن. هرگز نگو «یادم نیست» پیش از خواندنِ ژورنال؛ فقط چیزی را بگو که در ژورنال/گزارش هست و آنچه نیست را «ثبت نشده» بگو.\n")
    try:
        st = await get_state()
        if st["active"]:
            t = timer_of(st)
            out += (f"  (الان «حالتِ مدیر» روشن است — {'تا ' + jfmt(t['end']) if t['timed'] else 'تا اطلاعِ ثانوی'}."
                    + (f" دستورِ اختصاصی: {st['directive'][:400]}" if st["directive"] else "") + ")\n")
        d = await session_digest()
        if d:
            out += "  «حافظه‌ی دوره‌ها» — آخرین دوره:\n  " + d[0][:1500].replace("\n", "\n  ") + "\n"
        jr = await _rows("SELECT ts, kind, title, body FROM mgr_journal WHERE kind IN ('round','question') ORDER BY id DESC LIMIT 4")
        if jr:
            out += "  آخرین ثبت‌های ژورنال:\n" + "\n".join(
                f"  - [{jfmt(_pdt(r['ts']), '%m/%d %H:%M')}] {r['title']}: {(r['body'] or '')[:160].replace(chr(10), ' ')}" for r in jr) + "\n"
        mem = await _rows("SELECT kind, text FROM mgr_memory WHERE active=1 ORDER BY id DESC LIMIT 6")
        if mem:
            out += "  یادداشت‌های ماندگارِ خودت: " + " | ".join(f"[{m['kind']}] {m['text'][:100]}" for m in mem) + "\n"
    except Exception:
        logger.info("manager prompt memory failed", exc_info=True)
    return out
