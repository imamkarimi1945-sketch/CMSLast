"""
ai_workqueue.py — «صفِ کارِ رهگشا»: کارهای عملیاتیِ واقعی که از دیتابیس درمی‌آیند و در هر دور به رهگشا داده می‌شوند.

چرا؟ تا قبل از این، رهگشای مدیر فقط «آمارِ امنیتی» می‌دید؛ پس هیچ کارِ عملیاتی‌ای (مسابقه‌ی بدونِ نتیجه، وظیفه‌ی عقب‌افتاده،
مدیرِ غایب، درخواستِ دسترسیِ معطل، ...) جلوی چشمش نبود و همیشه می‌نوشت «اقدامی لازم نبود».
اینجا هر کار با «شواهدِ واقعی»، اولویت و ابزارهای مناسب ساخته می‌شود؛ مدل موظف است برای هر مورد اقدام کند یا دلیلِ نکردن را بنویسد.

همه‌ی تولیدکننده‌ها جدا و محافظت‌شده‌اند: خطا در یکی بقیه را خراب نمی‌کند. فقط خواندن؛ هیچ تغییری در دیتابیس نمی‌دهد
(به‌جز یادداشتِ «چه چیزی قبلاً پیشنهاد شد» در mgr_kv تا هر ۳ ساعت یک مورد تکرار نشود).
"""
import hashlib
import json
import logging
from datetime import timedelta

from config import PISHVA_ID

logger = logging.getLogger(__name__)

COOLDOWN_H = {1: 12, 2: 3, 3: 1}      # بعد از پیشنهاد، هر مورد تا این مدت (ساعت) دوباره پیشنهاد نمی‌شود مگر شواهدش عوض شود
INITIATIVE = ("report", "active", "proactive")
INITIATIVE_FA = {"report": "گزارش‌دهنده", "active": "فعال", "proactive": "پیش‌قدم"}
KIND_ICON = {"match": "♟️", "task": "📌", "access": "🔑", "admin": "👤", "player": "⚠️", "tournament": "🏆", "ops": "🧩"}


def _am():
    import ai_manager
    return ai_manager


def _age_h(ts):
    am = _am()
    d = am._pdt(ts)
    if not d:
        return None
    try:
        return max(0.0, (am.now_teh() - d).total_seconds() / 3600)
    except Exception:       # naive/aware نامتجانس
        return None


def _hfa(h):
    return f"{int(h)} ساعت" if h < 48 else f"{int(h // 24)} روز"


def _task(key, prio, kind, title, evidence, tools, hint=""):
    return {"key": key, "prio": prio, "kind": kind, "title": title, "evidence": evidence[:8], "tools": tools, "hint": hint}


# ─────────────── تولیدکننده‌ها ───────────────
async def _stale_matches():
    am = _am()
    rows = await am._rows(
        "SELECT m.id, m.created_at, m.match_date, m.created_by, wp.full_name AS w, bp.full_name AS b, t.name AS tn "
        "FROM matches m LEFT JOIN players wp ON wp.id=m.white_player_id LEFT JOIN players bp ON bp.id=m.black_player_id "
        "LEFT JOIN tournaments t ON t.id=m.tournament_id WHERE m.result IS NULL ORDER BY m.id DESC LIMIT 40")
    ev, old = [], 0
    for r in rows:
        h = _age_h(r["created_at"] or r["match_date"])
        if h is None or h < 3:
            continue
        old = max(old, h)
        ev.append((h, f"#{r['id']}: {r['w'] or '؟'} در برابر {r['b'] or '؟'}" + (f" ({r['tn']})" if r["tn"] else "") + f" — {_hfa(h)} بدونِ نتیجه (ثبت‌کننده {r['created_by']})"))
    if not ev:
        return []
    ev.sort(key=lambda x: -x[0])
    return [_task("matches_stale", 2 if old >= 24 else 1, "match", f"{len(ev)} مسابقه‌ی بدونِ نتیجه (قدیمی‌ترین {_hfa(old)})", [e for _h, e in ev],
                  ["recent_matches", "message_admin", "mgr_note", "mgr_ask_boss"],
                  "به ثبت‌کننده/مسئولِ مسابقات یادآوری بده؛ نتیجه را از خودت نساز. اگر از ۲۴ ساعت گذشته به مدیر ارشد هم خبر بده.")]


async def _overdue_tasks():
    am = _am()
    rows = await am._rows("SELECT id, assigned_to, title, assigned_at FROM tasks WHERE status='pending' ORDER BY id DESC LIMIT 30")
    ev = []
    for r in rows:
        h = _age_h(r["assigned_at"])
        if h is not None and h >= 24:
            ev.append((h, f"#{r['id']}: «{r['title']}» برای {r['assigned_to']} — {_hfa(h)} معوق"))
    if not ev:
        return []
    ev.sort(key=lambda x: -x[0])
    return [_task("tasks_overdue", 1, "task", f"{len(ev)} وظیفه‌ی معوق", [e for _h, e in ev], ["message_admin", "assign_task", "mgr_note"],
                  "برای هر وظیفه یک یادآوریِ کوتاه و محترمانه به مسئولش بفرست.")]


async def _pending_access():
    am = _am()
    rows = await am._rows("SELECT id, telegram_id, username, full_name, role, requested_at FROM access_requests WHERE status='pending' ORDER BY id DESC LIMIT 10")
    ev = []
    for r in rows:
        h = _age_h(r["requested_at"])
        if h is None or h >= 0.5:
            ev.append(f"#{r['id']}: {r['full_name'] or '؟'} (@{r['username'] or '—'}، {r['telegram_id']}) برای نقشِ {r['role']}" + (f" — {_hfa(h)} معطل" if h is not None else ""))
    if not ev:
        return []
    return [_task("access_pending", 2, "access", f"{len(ev)} درخواستِ دسترسیِ در انتظار", ev, ["list_access_requests", "mgr_ask_boss"],
                  "تأیید نکن مگر دستورِ اختصاصی صریحاً بگوید. مشکوک‌ها را با دلیل به مدیر ارشد بگو (mgr_ask_boss) و در صورتِ نشانه‌ی جعل رد کن.")]


async def _quiet_admins():
    am = _am()
    rows = await am._rows("SELECT telegram_id, COALESCE(NULLIF(display_name,''), full_name) AS n, last_active FROM admins WHERE is_active=1 AND telegram_id != ?", (PISHVA_ID,))
    ev = []
    for r in rows:
        h = _age_h(r["last_active"])
        if h is not None and h >= 72:
            ev.append((h, f"{r['n']} ({r['telegram_id']}) — {_hfa(h)} بدونِ فعالیت"))
    if not ev:
        return []
    ev.sort(key=lambda x: -x[0])
    return [_task("admins_quiet", 1, "admin", f"{len(ev)} مدیرِ غایب", [e for _h, e in ev], ["review_admins_activity", "message_admin", "mgr_note"],
                  "یک پیامِ احوال‌پرسی/یادآوریِ کوتاه به هر کدام بفرست؛ اخطار نده مگر دستور باشد.")]


async def _warned_players():
    am = _am()
    rows = await am._rows("SELECT id, full_name, warnings FROM players WHERE status='active' AND warnings>=3 ORDER BY warnings DESC LIMIT 8")
    if not rows:
        return []
    return [_task("players_warned", 1, "player", f"{len(rows)} بازیکنِ فعال با ۳ اخطار یا بیشتر", [f"{r['full_name']} — {r['warnings']} اخطار" for r in rows],
                  ["search_player", "mgr_note", "mgr_ask_boss"], "پیشنهادِ تصمیم (تعلیق/گفتگو) را کوتاه به مدیر ارشد بده؛ خودت تعلیق نکن مگر دستور باشد.")]


async def _quiet_tournaments():
    am = _am()
    rows = await am._rows("SELECT t.id, t.name, t.created_at, MAX(m.created_at) AS last FROM tournaments t LEFT JOIN matches m ON m.tournament_id=t.id "
                          "WHERE t.status='active' AND COALESCE(t.is_default,0)=0 GROUP BY t.id, t.name, t.created_at")
    ev = []
    for r in rows:
        age_c = _age_h(r["created_at"])
        h = _age_h(r["last"]) if r["last"] else age_c
        if age_c is not None and age_c >= 24 and (h is None or h >= 24):
            ev.append(f"«{r['name']}» (#{r['id']}) — " + ("هیچ مسابقه‌ای ثبت نشده" if not r["last"] else f"{_hfa(h)} از آخرین مسابقه")) 
    if not ev:
        return []
    return [_task("tournaments_quiet", 1, "tournament", f"{len(ev)} تورنمنتِ فعالِ ساکت", ev, ["analyze_tournament", "message_admin", "mgr_note"],
                  "وضعیت را تحلیل کن و اگر مسئولی دارد یادآوری بده؛ به مدیر ارشد پیشنهادِ بستن/ادامه بده.")]


GENS = (_stale_matches, _overdue_tasks, _pending_access, _quiet_admins, _warned_players, _quiet_tournaments)


# ─────────────── ساخت و حافظه‌ی «قبلاً پیشنهاد شد» ───────────────
async def _seen():
    am = _am()
    r = await am._rows("SELECT v FROM mgr_kv WHERE k='workqueue'")
    try:
        return json.loads(r[0]["v"]) if r else {}
    except Exception:
        return {}


def _sig(t):
    return hashlib.sha1(json.dumps([t["title"], t["evidence"]], ensure_ascii=False).encode()).hexdigest()[:10]


async def build(include_cooling=False):
    """→ فهرستِ کارها (مرتب بر اساسِ اولویت). هر کار فیلدِ cooling دارد: «به‌تازگی پیشنهاد شد و شواهدش عوض نشده»."""
    out = []
    for g in GENS:
        try:
            out += await g()
        except Exception:
            logger.info("workqueue generator %s failed", g.__name__, exc_info=True)
    seen, now = await _seen(), _am().now_teh()
    for t in out:
        s = seen.get(t["key"])
        t["sig"] = _sig(t)
        age = _age_h(s.get("t")) if s else None
        t["cooling"] = bool(s and s.get("sig") == t["sig"] and age is not None and age < COOLDOWN_H.get(t["prio"], 6))
    out.sort(key=lambda t: (-t["prio"], t["key"]))
    return out if include_cooling else [t for t in out if not t["cooling"]]


async def mark_offered(tasks):
    if not tasks:
        return
    am = _am()
    seen = await _seen()
    for t in tasks:
        seen[t["key"]] = {"sig": t.get("sig") or _sig(t), "t": am._iso()}
    await am._exec("INSERT OR REPLACE INTO mgr_kv(k, v) VALUES ('workqueue', ?)", (json.dumps(seen, ensure_ascii=False),))


# ─────────────── متنِ پرامپت ───────────────
def prompt_block(tasks, initiative="active"):
    mode = {
        "report": "سطحِ ابتکار: «گزارش‌دهنده» — موارد را فقط بررسی و گزارش کن؛ اقدامِ عملیاتی نکن (فقط mgr_note/mgr_ask_boss). اقدامِ امنیتیِ قرمز همچنان مجاز است.",
        "active": "سطحِ ابتکار: «فعال» — موارد را خودت پیگیری کن: یادآوری/پیام به مسئول، ثبتِ وظیفه، تحلیل. حذف/ویرایشِ داده فقط با شواهدِ قطعی.",
        "proactive": "سطحِ ابتکار: «پیش‌قدم» — علاوه بر صف، تا ۳ کارِ مفیدِ ابتکاری هم بکن (مثلاً وظیفه/یادآورِ تازه، تحلیلِ تورنمنت، پیشنهادِ بهبود) و دلیلِ هر کدام را بنویس.",
    }.get(initiative, "")
    if not tasks:
        return ("📋 صفِ کار: الان هیچ کارِ عملیاتیِ بازی از دیتابیس درنیامد (یا همه به‌تازگی پیگیری شده‌اند).\n" + mode +
                ("\nچون صف خالی است، ابتکارِ مفید بزن و گزارش بده چه کردی." if initiative == "proactive" else ""))
    lines = []
    for i, t in enumerate(tasks, 1):
        ic = KIND_ICON.get(t["kind"], "•")
        lines.append(f"{i}) {ic} [{'🟠' if t['prio'] >= 2 else '🟡'}] {t['title']}\n   شواهد:\n" + "\n".join(f"     - {e}" for e in t["evidence"]) +
                     f"\n   ابزارهای مناسب: {', '.join(t['tools'])}" + (f"\n   راهنما: {t['hint']}" if t["hint"] else ""))
    return (f"📋 صفِ کارِ واقعی (از دیتابیس؛ {len(tasks)} مورد). {mode}\n" + "\n".join(lines) +
            "\n\nقانونِ صف: برای «هر» مورد یا ابزارِ مناسب را صدا بزن (اقدام) یا در گزارش دلیلِ روشنِ نکردن را بنویس. "
            "نوشتنِ «اقدامی لازم نبود» وقتی صف پر است ممنوع است. نتیجه‌ی ابزار را عیناً گزارش کن.")
