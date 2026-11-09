"""
ai_manager_panel.py — پنلِ «🤖 رهگشای مدیر» (داخلِ پنلِ مدیر ارشد + دکمه‌ی منوی اصلی) و نمای فقط‌خواندنیِ مدیرها.

• صفحه‌ی اصلی «زنده» است: زمان‌سنج، نوارِ باقی‌مانده، ساعتِ دقیقِ خاموشی و آمارِ روشن‌بودن هر ۳۰ ثانیه خودش تازه می‌شود
  (فقط تا ۱۵ دقیقه بعد از آخرین لمس، تا ویرایشِ بی‌پایانِ پیام نداشته باشیم).
• همه‌ی کلیدها فقط برای مدیر ارشد؛ نمای مدیرها (mgrv:view) فقط وقتی «اعلام» روشن و حالتِ مدیر فعال است جواب می‌دهد.
"""
import hashlib
import json
import logging
import re
import time
from datetime import timedelta

from telegram import InlineKeyboardButton as _B, InlineKeyboardMarkup as M
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, MessageHandler, filters

import ai_manager as am
import database as db
from config import PISHVA_ID
from helpers import safe_edit_message_text
from ops_group import bar, fa, h, jfmt, now_teh, spark

logger = logging.getLogger(__name__)

PAGE = 8


def B(label, callback_data=None, style="primary", **kw):
    """همه‌ی دکمه‌های این پنل رنگی‌اند (primary آبی، success سبز، danger قرمز) مثلِ بقیه‌ی ربات؛
    کلیدهای خاموش/روشن با وضعیتشان سبز/قرمز می‌شوند."""
    return _B(label, callback_data=callback_data, style=style, **kw)


def _tog(on: bool) -> str:
    return "success" if on else "danger"


def _hash(text, kb) -> str:
    sig = text + "|" + "|".join(b.text for row in kb.inline_keyboard for b in row)
    return hashlib.md5(sig.encode()).hexdigest()
LIVE_TTL = 15 * 60
_LIVE = {}          # (chat_id, message_id) -> {"t": زمانِ آخرین لمس, "hash": …}

DUR_ON = (("۳۰ دقیقه", 30), ("۱ ساعت", 60), ("۳ ساعت", 180), ("۶ ساعت", 360), ("۱۲ ساعت", 720),
          ("۱ روز", 1440), ("۳ روز", 4320), ("۷ روز", 10080), ("۳۰ روز", 43200))
ADM_MODE = {"all": "همه‌ی مدیران", "none": "هیچ مدیری", "only": "فقط انتخاب‌شده‌ها", "except": "همه به‌جز انتخاب‌شده‌ها"}
_NEXT_MODE = {"all": "except", "except": "only", "only": "none", "none": "all"}


async def _boss_only(q) -> bool:
    if q.from_user.id != PISHVA_ID:
        await q.answer("⛔ فقط مدیر ارشد.", show_alert=True)
        return False
    return True


def _parse_minutes(text: str):
    t = (text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(m|min|دقیقه|د|h|hr|ساعت|س|d|day|روز|ر)?$", t, re.I)
    if not m:
        return None
    n, u = float(m.group(1)), (m.group(2) or "m").lower()
    mult = 1 if u in ("m", "min", "دقیقه", "د") else (60 if u in ("h", "hr", "ساعت", "س") else 1440)
    return int(n * mult)


def _short(n_min: int) -> str:
    return am.dur_fa(n_min * 60)


# ═══════════════════════ صفحه‌ی اصلی ═══════════════════════
def _caps_summary(st):
    defs = am.capability_defs()
    caps = am.eff_caps(st, defs)
    cats = [d for d in defs if d["kind"] == "cat"]
    return sum(1 for d in cats if caps[d["key"]]), len(cats)


async def render_main():
    st = await am.get_state(force=True)
    t, u = am.timer_of(st), await am.usage()
    on_n, all_n = _caps_summary(st)
    L = ["╔════════════════════════╗", "   🤖 <b>رهگشای مدیر</b>", "╚════════════════════════╝"]
    if t["active"]:
        L.append("🟢 <b>فعال</b> — مدیریت دستِ رهگشاست")
        L += ["", "⏱ <b>زمان‌سنج</b>"]
        if t["timed"]:
            icon = "🔴" if t["remaining"] < 600 else ("🟠" if t["remaining"] < 3600 else "🟢")
            L.append(f"{bar(t['pct_left'], 14)}  <b>{fa(int(t['pct_left']))}٪</b> باقی")
            L.append(f"{icon} باقی‌مانده: <b>{am.dur_fa(t['remaining'])}</b>")
            L.append(f"🔚 خاموشی: <code>{jfmt(t['end'])}</code>")
        else:
            L.append(f"{'▰' * 14}  <b>∞</b>")
            L.append("♾ تا اطلاعِ ثانوی (خودتان خاموش می‌کنید)")
        L.append(f"▶️ شروع: <code>{jfmt(t['start'])}</code> | سپری‌شده: <b>{am.dur_fa(t['elapsed'])}</b>")
    else:
        L += ["⚪️ <b>خاموش</b> — مدیریت دستِ خودِ شماست", "", "برای سپردنِ مدیریت «⚡ روشن‌کردن» را بزنید."]
    L += ["", "📊 <b>آمارِ روشن‌بودن</b>",
          f"امروز {am.dur_fa(u['today'])} | ۷ روز {am.dur_fa(u['week'])}",
          f"کل {am.dur_fa(u['total'])} | {fa(u['count'])} بار | طولانی‌ترین {am.dur_fa(u['longest'])}"]
    if t["active"]:
        nr = am._pdt(st["next_round"])
        lr = am._pdt(st["last_round"])
        L += ["", "🧠 <b>دورهای مدیریتی</b>",
              f"هر {fa(st['interval_min'] // 60)} ساعت | بررسیِ روزانه {fa(st['daily_time'])}",
              f"آخرین: {jfmt(lr) if lr else '—'} | بعدی: {jfmt(nr) if nr else '—'}"]
    L += ["", f"🔐 اختیارات: <b>{fa(on_n)}</b> از {fa(all_n)} حوزه" + ("  👑 <b>دسترسیِ کامل</b>" if st["full_access"] else ""),
          f"📜 دستور: {h(st['directive'][:140]) + ('…' if len(st['directive']) > 140 else '') if st['directive'] else '—'}"]
    a = st["announce"]
    L.append(f"📣 اعلام: <b>{'روشن' if a['on'] else 'خاموش'}</b>" + (f" → {ADM_MODE[a['admins']]}" if a["on"] else " (هیچ‌جا اعلانی نمی‌رود)"))
    L.append(f"\n🕒 <code>{jfmt(now_teh(), '%H:%M:%S')}</code>")
    jn = (await am._rows("SELECT COUNT(*) AS n FROM mgr_journal"))[0]["n"]
    caps_lbl = f"🔐 اختیارات {fa(on_n)}/{fa(all_n)}" + (" 👑" if st["full_access"] else "")
    dir_lbl = "📜 دستور اختصاصی ✅" if st["directive"] else "📜 دستور اختصاصی"
    ann_lbl = "📣 اعلام ✅" if a["on"] else "📣 اعلام ⛔"
    kb = [[B("🛑 خاموشیِ فوری", callback_data="mgr:kill", style="danger") if t["active"]
           else B("⚡ روشن‌کردن", callback_data="mgr:on", style="success")]]
    if t["active"]:
        dur_lbl = f"⏱ مدت/تمدید • {am.short_dur(t['remaining'])}" if t["timed"] else "⏱ مدت/تمدید • ∞"
        nr_ = am._pdt(st["next_round"])
        kb += [[B(dur_lbl, callback_data="mgr:dur", style="danger" if t.get("timed") and t["remaining"] < 600 else "primary"),
                B(caps_lbl, callback_data="mgr:caps:0", style="success" if st["full_access"] else "primary")],
               [B(dir_lbl, callback_data="mgr:dir", style=_tog(bool(st["directive"])) if st["directive"] else "primary"),
                B(ann_lbl, callback_data="mgr:ann", style=_tog(a["on"]))],
               [B("🧠 اجرای دور همین الان" + (f" • بعدی {jfmt(nr_, '%H:%M')}" if nr_ else ""), callback_data="mgr:rn", style="success")]]
    else:
        kb += [[B(dir_lbl, callback_data="mgr:dir", style="success" if st["directive"] else "primary"),
                B(caps_lbl, callback_data="mgr:caps:0", style="success" if st["full_access"] else "primary")],
               [B(ann_lbl, callback_data="mgr:ann", style=_tog(a["on"])),
                B(f"⚙️ برنامه‌ی دورها • هر {fa(st['interval_min'] // 60)}س", callback_data="mgr:sch")]]
    kb.append([B(f"📓 ژورنال ({fa(jn)})", callback_data="mgr:j:0"), B("📋 گزارشِ دوره", callback_data="mgr:rep")])
    if t["active"]:
        kb.append([B("📈 روند و یادداشت‌ها", callback_data="mgr:tr"), B(f"⚙️ دورها • هر {fa(st['interval_min'] // 60)}س", callback_data="mgr:sch")])
    else:
        kb.append([B("📈 روند و یادداشت‌ها", callback_data="mgr:tr")])
    kb.append([B("💬 گفتگو با رهگشا", callback_data="mgr:chat"), B("🔄 بازخوانی", callback_data="mgr:ref")])
    kb.append([B("🔙 پنل مدیر ارشد", callback_data="menu_pishva", style="danger")])
    return "\n".join(L), M(kb)


async def _show_main(q, toast=None):
    text, kb = await render_main()
    await safe_edit_message_text(q, text, reply_markup=kb, parse_mode="HTML")
    msg = q.message
    if msg:
        _LIVE[(msg.chat_id, msg.message_id)] = {"t": time.monotonic(), "hash": _hash(text, kb)}
    if toast:
        await q.answer(toast[:190])


async def refresh_live(bot):
    """از جابِ ۳۰ثانیه‌ای: پنل‌های بازِ اخیر را تازه می‌کند (فقط اگر متن عوض شده)."""
    if not _LIVE:
        return
    now = time.monotonic()
    text, kb = None, None
    for key in list(_LIVE):
        info = _LIVE[key]
        if now - info["t"] > LIVE_TTL:
            _LIVE.pop(key, None)
            continue
        if text is None:
            text, kb = await render_main()
        hsh = _hash(text, kb)
        if hsh == info["hash"]:
            continue
        try:
            await bot.edit_message_text(chat_id=key[0], message_id=key[1], text=text, reply_markup=kb, parse_mode="HTML")
            info["hash"] = hsh
        except Exception as e:
            if "not modified" not in str(e).lower():
                _LIVE.pop(key, None)


async def cmd_a(update, ctx):
    """/A — بازکردنِ سریعِ پنلِ «رهگشای مدیر». فقط مدیر ارشد و فقط در پیوی؛ برای بقیه هیچ واکنشی نیست."""
    m, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not (m and user and chat) or user.id != PISHVA_ID or chat.type != "private":
        return
    ctx.user_data.pop("mgr_wait", None)
    text, kb = await render_main()
    sent = await m.reply_text(text, reply_markup=kb, parse_mode="HTML")
    _LIVE[(sent.chat_id, sent.message_id)] = {"t": time.monotonic(), "hash": _hash(text, kb)}


async def mgr_menu(update, ctx):
    q = update.callback_query
    if not await _boss_only(q):
        return
    await q.answer()
    ctx.user_data.pop("mgr_wait", None)
    await _show_main(q)


# ═══════════════════════ هندلرِ کلیدها ═══════════════════════
def _back(to="mgr:ref"):
    return [B("🔙 رهگشای مدیر", callback_data=to, style="danger")]


async def cb(update, ctx, data=None):
    q = update.callback_query
    if not await _boss_only(q):
        return
    p = (data or q.data or "").split(":")
    act = p[1] if len(p) > 1 else ""
    bot = ctx.bot
    ctx.user_data.pop("mgr_wait", None)

    if act == "ref":
        await _show_main(q, "🔄")
        return

    # ── روشن‌کردن (انتخابِ مدت) ──
    if act == "on":
        st = await am.get_state(force=True)
        a_on = st["announce"]["on"]
        rows = [[B(lbl, callback_data=f"mgr:g:{m}") for lbl, m in DUR_ON[i:i + 3]] for i in range(0, len(DUR_ON), 3)]
        rows.append([B("♾ تا اطلاعِ ثانوی", callback_data="mgr:g:inf"), B("✍️ مدتِ دلخواه", callback_data="mgr:gc")])
        rows.append([B(f"📣 اعلامِ این اعطا: {'✅ روشن' if a_on else '⛔ خاموش'}", callback_data="mgr:annt:on", style=_tog(a_on))])
        rows.append(_back())
        await q.answer()
        await safe_edit_message_text(q, "⚡ <b>سپردنِ مدیریت به رهگشا</b>\nمدت را انتخاب کنید. اختیاراتِ فعلی: "
                                     f"<b>{fa(_caps_summary(st)[0])}</b> حوزه" + ("  👑 کامل" if st["full_access"] else "")
                                     + "\n(اختیارات و دستورِ اختصاصی را می‌توانید قبل/بعد تنظیم کنید.)",
                                     reply_markup=M(rows), parse_mode="HTML")
        return
    if act == "g":
        v = p[2]
        if v == "inf":
            await q.answer()
            await safe_edit_message_text(q, "♾ <b>تا اطلاعِ ثانوی؟</b>\nرهگشا تا وقتی خودتان خاموش نکنید مدیر می‌ماند.",
                                         reply_markup=M([[B("✅ بله، روشن کن", callback_data="mgr:gy:inf", style="success"),
                                                          B("❌ نه", callback_data="mgr:on")]]), parse_mode="HTML")
            return
        ok, msg = await am.grant(bot, int(v), PISHVA_ID)
        await _show_main(q, "✅ روشن شد" if ok else msg)
        return
    if act == "gy":
        ok, msg = await am.grant(bot, None, PISHVA_ID)
        await _show_main(q, "✅ روشن شد" if ok else msg)
        return
    if act in ("gc", "xc"):
        ctx.user_data["mgr_wait"] = "grant" if act == "gc" else "expiry"
        await q.answer()
        await safe_edit_message_text(q, "✍️ مدت را بفرستید: مثل <code>90</code> (دقیقه)، <code>5h</code> یا <code>۵ ساعت</code>، <code>2d</code> یا <code>۲ روز</code>.",
                                     reply_markup=M([_back("mgr:on" if act == "gc" else "mgr:dur")]), parse_mode="HTML")
        return
    if act == "annt":                         # تغییرِ سریعِ کلیدِ اعلام از صفحه‌ی روشن‌کردن
        st = await am.get_state(force=True)
        st["announce"]["on"] = not st["announce"]["on"]
        await am.save_state(st)
        await q.answer("📣 اعلام " + ("روشن" if st["announce"]["on"] else "خاموش"))
        await cb(update, ctx, "mgr:on")
        return
    if act == "kill":
        ok, msg = await am.revoke(bot, "kill", PISHVA_ID)
        await _show_main(q, "🔴 خاموش شد")
        return

    # ── مدت / تمدید ──
    if act == "dur":
        st = await am.get_state(force=True)
        t = am.timer_of(st)
        if not t["active"]:
            await _show_main(q, "خاموش است.")
            return
        rows = [[B("➕ ۱ ساعت", callback_data="mgr:x:60", style="success"), B("➕ ۶ ساعت", callback_data="mgr:x:360", style="success"), B("➕ ۱ روز", callback_data="mgr:x:1440", style="success")],
                [B("➖ ۱ ساعت", callback_data="mgr:x:-60", style="danger"), B("➖ ۶ ساعت", callback_data="mgr:x:-360", style="danger")],
                [B("از همین الان: ۱ ساعت", callback_data="mgr:s:60"), B("۶ ساعت", callback_data="mgr:s:360"), B("۱ روز", callback_data="mgr:s:1440")],
                [B("♾ تا اطلاعِ ثانوی", callback_data="mgr:s:inf"), B("✍️ مدتِ دلخواه", callback_data="mgr:xc")], _back()]
        await q.answer()
        await safe_edit_message_text(q, "⏱ <b>مدت/تمدید</b>\n" + (f"الان: {am.dur_fa(t['remaining'])} باقی (تا {jfmt(t['end'])})" if t["timed"] else "الان: تا اطلاعِ ثانوی")
                                     + "\n➕/➖ به مهلتِ فعلی اضافه/کم می‌کند؛ «از همین الان» مهلت را از نو می‌گذارد.",
                                     reply_markup=M(rows), parse_mode="HTML")
        return
    if act == "x":
        ok, msg = await am.extend(bot, int(p[2]))
        await _show_main(q, "⏳ انجام شد" if ok else msg)
        return
    if act == "s":
        ok, msg = await am.set_expiry(bot, None if p[2] == "inf" else int(p[2]))
        await _show_main(q, "⏳ انجام شد" if ok else msg)
        return

    # ── اختیارات ──
    if act in ("caps", "c", "pre", "full", "fullc", "fulloff"):
        if act == "full":
            await q.answer()
            await safe_edit_message_text(q, "👑 <b>دسترسیِ کامل؟</b>\nهمه‌ی حوزه‌ها روشن می‌شود (مسابقات، بازیکنان، مدیران، امنیت، سیستم، پیام‌رسانی…).\n"
                                         "قفل‌های سخت می‌مانند: رهگشا اختیارِ خودش را تغییر نمی‌دهد، به مدیر ارشد اقدام نمی‌کند، به بیرونی‌ها پیام نمی‌دهد "
                                         "و برای بعدِ از پایانِ مهلت اقدام زمان‌بندی نمی‌کند.",
                                         reply_markup=M([[B("✅ بله، کامل", callback_data="mgr:fullc", style="success"), B("❌ نه", callback_data="mgr:caps:0")]]),
                                         parse_mode="HTML")
            return
        if act == "fullc":
            await am.set_full(True)
            p = ["mgr", "caps", "0"]
        elif act == "fulloff":
            await am.set_full(False)
            p = ["mgr", "caps", "0"]
        elif act == "pre":
            st = await am.get_state(force=True)
            am._apply_preset(st, p[2])
            await am.save_state(st)
            await am.journal("caps", "پیش‌تنظیمِ اختیارات", p[2])
            p = ["mgr", "caps", "0"]
        elif act == "c":
            key, page = p[2], int(p[3])
            st = await am.get_state(force=True)
            cur = am.eff_caps(st).get(key)
            await am.set_caps([key], not cur)
            p = ["mgr", "caps", str(page)]
        page = int(p[2]) if len(p) > 2 else 0
        st = await am.get_state(force=True)
        defs = am.capability_defs()
        caps = am.eff_caps(st, defs)
        pages = (len(defs) + PAGE - 1) // PAGE
        page = max(0, min(page, pages - 1))
        rows = []
        for d in defs[page * PAGE:(page + 1) * PAGE]:
            rows.append([B(("✅ " if caps[d["key"]] else "⛔ ") + d["label"], callback_data=f"mgr:c:{d['key']}:{page}", style=_tog(caps[d["key"]]))])
        nav = []
        if page > 0:
            nav.append(B("◀️", callback_data=f"mgr:caps:{page - 1}"))
        nav.append(B(f"{fa(page + 1)}/{fa(pages)}", callback_data="mgr:ref"))
        if page < pages - 1:
            nav.append(B("▶️", callback_data=f"mgr:caps:{page + 1}"))
        rows.append(nav)
        rows.append([B("🔒 محتاط", callback_data="mgr:pre:cautious"), B("⚖️ متعادل", callback_data="mgr:pre:balanced"),
                     B("👑 خاموش‌کردنِ کامل" if st["full_access"] else "👑 کامل", callback_data="mgr:fulloff" if st["full_access"] else "mgr:full", style="danger" if st["full_access"] else "success")])
        rows.append(_back())
        on_n, all_n = _caps_summary(st)
        await q.answer()
        await safe_edit_message_text(q, f"🔐 <b>اختیارات</b> — {fa(on_n)} از {fa(all_n)} حوزه روشن" + ("  👑 دسترسیِ کامل" if st["full_access"] else "")
                                     + "\nهر کلید یک حوزه است؛ با لمسِ آن خاموش/روشن می‌شود.\n"
                                     "🔒 محتاط = فقط مشاهده و گزارش | ⚖️ متعادل = کارهای معمولِ مدیریت.",
                                     reply_markup=M(rows), parse_mode="HTML")
        return

    # ── دستور اختصاصی ──
    if act == "dir":
        st = await am.get_state(force=True)
        await q.answer()
        await safe_edit_message_text(q, "📜 <b>دستورِ اختصاصیِ رهگشای مدیر</b>\nاین متن «سرلوحه‌ی کارِ» رهگشا در هر دور است و بر بقیه مقدم است.\n\n"
                                     + (f"<blockquote>{h(st['directive'])}</blockquote>" if st["directive"] else "— هنوز دستوری ثبت نشده —"),
                                     reply_markup=M([[B("✏️ جایگزین‌کردن", callback_data="mgr:dirs"), B("➕ افزودن", callback_data="mgr:dira")],
                                                     [B("🗑 پاک‌کردن", callback_data="mgr:dirc", style="danger")], _back()]), parse_mode="HTML")
        return
    if act in ("dirs", "dira"):
        ctx.user_data["mgr_wait"] = "dir_set" if act == "dirs" else "dir_add"
        await q.answer()
        await safe_edit_message_text(q, "✍️ متنِ دستور را در پیامِ بعدی بفرستید.", reply_markup=M([_back("mgr:dir")]), parse_mode="HTML")
        return
    if act == "dirc":
        st = await am.get_state(force=True)
        st["directive"] = ""
        await am.save_state(st)
        await am.journal("directive", "پاک‌شدنِ دستورِ اختصاصی", "")
        await q.answer("🗑 پاک شد")
        await cb(update, ctx, "mgr:dir")
        return

    # ── اعلام ──
    if act in ("ann", "annm", "annmode", "annops", "anngrp", "repboss", "repops"):
        st = await am.get_state(force=True)
        a, r = st["announce"], st["report"]
        if act == "annm":
            a["on"] = not a["on"]
        elif act == "annmode":
            a["admins"] = _NEXT_MODE[a["admins"]]
        elif act == "annops":
            a["ops_group"] = not a["ops_group"]
        elif act == "anngrp":
            a["ann_group"] = not a["ann_group"]
        elif act == "repboss":
            r["boss_pm"] = not r["boss_pm"]
        elif act == "repops":
            r["ops_group"] = not r["ops_group"]
        if act != "ann":
            await am.save_state(st)
            await am.journal("announce_cfg", "تنظیمِ اعلام", f"{a} | {r}")
        await q.answer()
        rows = [[B(f"📣 اعلام: {'✅ روشن' if a['on'] else '⛔ خاموش'}", callback_data="mgr:annm", style="success" if a["on"] else "danger")],
                [B(f"👥 مدیران: {ADM_MODE[a['admins']]}", callback_data="mgr:annmode")]]
        if a["admins"] in ("only", "except"):
            rows.append([B(f"🎯 انتخابِ مدیرها ({fa(len(a['ids']))})", callback_data="mgr:aa:0", style="success" if a['ids'] else "primary")])
        rows += [[B(f"🏛 گروه فرماندهی: {'✔' if a['ops_group'] else '✖'}", callback_data="mgr:annops", style=_tog(a['ops_group'])),
                  B(f"📡 گروه اعلانات: {'✔' if a['ann_group'] else '✖'}", callback_data="mgr:anngrp", style=_tog(a['ann_group']))],
                 [B(f"🧾 گزارشِ دورها ← به من: {'✔' if r['boss_pm'] else '✖'}", callback_data="mgr:repboss", style=_tog(r['boss_pm'])),
                  B(f"← به گروه: {'✔' if r['ops_group'] else '✖'}", callback_data="mgr:repops", style=_tog(r['ops_group']))],
                 [B("📤 ارسالِ اعلامِ وضعیت همین الان", callback_data="mgr:annsend")], _back()]
        await safe_edit_message_text(q, "📣 <b>اعلام</b>\nروشن: موقعِ اعطا/تمدید/پایانِ حالتِ مدیر، به مخاطبانِ زیر خبر می‌رود.\n"
                                     "خاموش: <b>هیچ‌جا هیچ اعلانی نمی‌رود</b>.\n"
                                     "ℹ️ لاگِ اقدام‌های رهگشا همیشه (با برچسبِ «رهگشای مدیر») ثبت می‌شود؛ اعلام فقط خبرِ اعطا/پایان است.\n"
                                     "ℹ️ گزارشِ دورها به گروه فقط وقتی اعلام روشن است ارسال می‌شود.",
                                     reply_markup=M(rows), parse_mode="HTML")
        return
    if act == "aa":
        st = await am.get_state(force=True)
        a = st["announce"]
        if len(p) > 2 and p[2] != "0":
            tid = int(p[2])
            a["ids"] = [x for x in a["ids"] if x != tid] if tid in a["ids"] else a["ids"] + [tid]
            await am.save_state(st)
        adm = [x for x in await db.get_active_admins() if int(x["telegram_id"]) != PISHVA_ID][:20]
        rows = [[B(("✅ " if int(x["telegram_id"]) in a["ids"] else "▫️ ") + (x["display_name"] or x["full_name"] or str(x["telegram_id"])),
                   callback_data=f"mgr:aa:{x['telegram_id']}", style=_tog(int(x['telegram_id']) in a['ids']) if int(x['telegram_id']) in a['ids'] else "primary")] for x in adm]
        rows.append(_back("mgr:ann"))
        await q.answer()
        await safe_edit_message_text(q, f"🎯 <b>انتخابِ مدیرها</b>\nحالت: {ADM_MODE[a['admins']]}\n"
                                     + ("✅ = «فقط به این‌ها» اعلام می‌رسد" if a["admins"] == "only" else "✅ = این‌ها «مستثنی» می‌شوند (اعلام نمی‌گیرند)"),
                                     reply_markup=M(rows), parse_mode="HTML")
        return
    if act == "annsend":
        st = await am.get_state(force=True)
        res = await am.announce(bot, "granted" if st["active"] else "revoked", {"force": True})
        await q.answer(res[:190], show_alert=True)
        return

    # ── برنامه‌ی دورها ──
    if act in ("sch", "schi", "schd", "scha", "schr"):
        st = await am.get_state(force=True)
        if act == "schi":
            st["interval_min"] = int(p[2]) * 60
            st["next_round"] = am._iso(now_teh() + timedelta(minutes=st["interval_min"])) if st["active"] else None
        elif act == "schd":
            st["daily_time"] = f"{p[2][:2]}:{p[2][2:]}"
        elif act == "scha":
            st["caps"]["autonomous_rounds"] = not am.eff_caps(st)["autonomous_rounds"]
        elif act == "schr":
            st["caps"]["daily_review"] = not am.eff_caps(st)["daily_review"]
        if act != "sch":
            await am.save_state(st)
        caps = am.eff_caps(st)
        await q.answer()
        rows = [[B(("✅ " if st["interval_min"] == hh * 60 else "") + f"{fa(hh)} ساعت", callback_data=f"mgr:schi:{hh}", style="success" if st["interval_min"] == hh * 60 else "primary") for hh in (1, 3, 6, 12, 24)],
                [B(("✅ " if st["daily_time"] == t else "") + fa(t), callback_data=f"mgr:schd:{t.replace(':', '')}", style="success" if st["daily_time"] == t else "primary") for t in ("20:00", "21:00", "22:00", "23:00")],
                [B(f"🔄 دورهای خودکار: {'✅' if caps['autonomous_rounds'] else '⛔'}", callback_data="mgr:scha", style=_tog(caps['autonomous_rounds'])),
                 B(f"🛡️ بررسیِ روزانه: {'✅' if caps['daily_review'] else '⛔'}", callback_data="mgr:schr", style=_tog(caps['daily_review']))], _back()]
        await safe_edit_message_text(q, "⚙️ <b>برنامه‌ی دورها</b>\nردیفِ اول: فاصله‌ی دورهای خودکار. ردیفِ دوم: ساعتِ بررسیِ روزانه‌ی امنیت (وقتِ تهران).\n"
                                     "هر دور هزینه‌ی یک اجرای هوش مصنوعی دارد؛ فاصله‌ی بیشتر = هزینه‌ی کمتر.",
                                     reply_markup=M(rows), parse_mode="HTML")
        return

    # ── اجرای دور ──
    if act == "rn":
        st = await am.get_state(force=True)
        if not st["active"]:
            await q.answer("اول رهگشای مدیر را روشن کنید.", show_alert=True)
            return
        await q.answer("⏳ دور شروع شد؛ چند لحظه…")
        final = await am.run_round(bot, "manual")
        st = await am.get_state(force=True)
        await q.message.reply_text("✅ دورِ دستی تمام شد." + ("" if st["report"]["boss_pm"] else "\n\n" + final[:3000]) + "\n(جزئیات: 📓 ژورنال)")
        await _show_main(q)
        return

    # ── ژورنال ──
    if act in ("j", "jd"):
        if act == "jd":
            r = await am._rows("SELECT * FROM mgr_journal WHERE id=?", (int(p[2]),))
            if not r:
                await q.answer("پیدا نشد.", show_alert=True)
                return
            r = r[0]
            tools = ""
            try:
                tl = json.loads(r["tools"] or "[]")
                tools = "\n\n🔧 <b>اقدام‌ها</b>\n" + "\n".join(f"• {h(x['tool'])}: {h(x['result'][:160])}" for x in tl[:15]) if tl else ""
            except Exception:
                pass
            await q.answer()
            await safe_edit_message_text(q, f"📓 <b>{h(r['title'])}</b>\n<code>{jfmt(am._pdt(r['ts']))}</code>\n\n{h((r['body'] or '')[:2800])}{tools}",
                                         reply_markup=M([_back("mgr:j:0")]), parse_mode="HTML")
            return
        page = int(p[2])
        rows_db = await am._rows("SELECT id, ts, kind, title, ok FROM mgr_journal ORDER BY id DESC LIMIT ? OFFSET ?", (6, page * 6))
        icon = {"round": "🧠", "grant": "⚡", "revoke": "🔴", "extend": "⏳", "caps": "🔐", "directive": "📜", "announce_cfg": "📣", "question": "❓"}
        rows = [[B(f"{icon.get(r['kind'], '▫️')}{'' if r['ok'] else '⚠️'} {jfmt(am._pdt(r['ts']), '%m/%d %H:%M')} {r['title'][:28]}", callback_data=f"mgr:jd:{r['id']}")] for r in rows_db]
        nav = ([B("◀️", callback_data=f"mgr:j:{page - 1}")] if page > 0 else []) + ([B("▶️", callback_data=f"mgr:j:{page + 1}")] if len(rows_db) == 6 else [])
        if nav:
            rows.append(nav)
        rows.append(_back())
        await q.answer()
        await safe_edit_message_text(q, "📓 <b>ژورنالِ تصمیم‌ها و اقدام‌ها</b>\nهر ردیف را بزنید تا جزئیات و اقدام‌هایش را ببینید." + ("" if rows_db else "\n\n— خالی —"),
                                     reply_markup=M(rows), parse_mode="HTML")
        return

    # ── روند ──
    if act in ("tr", "trc"):
        if act == "trc":
            await am._exec("UPDATE mgr_memory SET active=0")
        pts = []
        for r in reversed(await am._rows("SELECT data FROM mgr_metrics ORDER BY id DESC LIMIT 14")):
            try:
                pts.append(json.loads(r["data"]))
            except Exception:
                pass
        L = ["📈 <b>روندِ دورها</b>"]
        if len(pts) < 2:
            L.append("هنوز دادّه‌ی کافی نیست؛ بعد از چند دور پر می‌شود.")
        else:
            for k, lab in (("score", "🛡️ امتیازِ امنیت"), ("strangers", "👤 غریبه‌ها"), ("pending", "📥 درخواستِ در انتظار"),
                           ("warned", "⚠️ بازیکنِ دارای اخطار"), ("destructive", "🔥 اقدامِ مخرب")):
                v = [x.get(k, 0) for x in pts]
                L.append(f"{lab}: <code>{spark(v)}</code>  {fa(v[0])} ← {fa(v[-1])}")
        mem = await am._rows("SELECT kind, text FROM mgr_memory WHERE active=1 ORDER BY id DESC LIMIT 8")
        L.append("\n🧠 <b>یادداشت‌های ماندگارِ رهگشا</b>")
        L += [f"• [{h(x['kind'])}] {h(x['text'])}" for x in mem] or ["— هنوز یادداشتی نیست —"]
        await q.answer()
        await safe_edit_message_text(q, "\n".join(L), reply_markup=M([[B("🗑 پاک‌کردنِ یادداشت‌ها", callback_data="mgr:trc", style="danger")], _back()]), parse_mode="HTML")
        return

    # ── گزارشِ دوره ──
    if act == "rep":
        d = await am.session_digest()
        await q.answer()
        body = (d[0] if d else "هنوز هیچ دوره‌ای نبوده.")
        await safe_edit_message_text(q, "📋 <b>گزارشِ آخرین دوره</b>\n<i>(همین را رهگشا هم در چت به یاد دارد)</i>\n\n" + h(body[:3000]),
                                     reply_markup=M([[B("📓 ژورنالِ کامل", callback_data="mgr:j:0")], _back()]), parse_mode="HTML")
        return

    # ── گفتگو ──
    if act == "chat":
        import ai_assistant as aia
        await aia.ai_assistant_open(update, ctx)
        await q.message.reply_text("🤖 با رهگشا درباره‌ی «حالتِ مدیر» حرف بزنید: سپردنِ مدیریت با مدتِ دلخواه، تنظیمِ اختیارات و دستورِ اختصاصی، "
                                   "اعلام برای افرادِ مشخص، مشاوره درباره‌ی این‌که چه چیزی را بسپارید، یا بازخوانیِ ژورنال.")
        return
    await q.answer()


# ═══════════════════════ ورودیِ متنی (دستور اختصاصی / مدتِ دلخواه) ═══════════════════════
async def on_text(update, ctx):
    m, user = update.effective_message, update.effective_user
    if not (m and user and user.id == PISHVA_ID):
        return
    wait = ctx.user_data.get("mgr_wait")
    if not wait:
        return
    text = (m.text or "").strip()
    ctx.user_data.pop("mgr_wait", None)
    if wait in ("dir_set", "dir_add"):
        st = await am.get_state(force=True)
        st["directive"] = (text if wait == "dir_set" else (st["directive"] + "\n" + text).strip())[:2000]
        await am.save_state(st)
        await am.journal("directive", "تغییرِ دستورِ اختصاصی", st["directive"][:500])
        await m.reply_text("✅ دستورِ اختصاصی ثبت شد و از دورِ بعد سرلوحه‌ی کارِ رهگشاست.",
                           reply_markup=M([[B("🤖 رهگشای مدیر", callback_data="mgr_menu")]]))
    elif wait in ("grant", "expiry"):
        mins = _parse_minutes(text)
        if not mins:
            await m.reply_text("❌ نفهمیدم. مثل «90»، «5h» یا «۲ روز» بفرستید.", reply_markup=M([[B("🤖 رهگشای مدیر", callback_data="mgr_menu")]]))
        else:
            st = await am.get_state(force=True)
            if st["active"] or wait == "expiry":
                ok, msg = await am.set_expiry(ctx.bot, mins)
            else:
                ok, msg = await am.grant(ctx.bot, mins, PISHVA_ID)
            await m.reply_text(msg, reply_markup=M([[B("🤖 رهگشای مدیر", callback_data="mgr_menu")]]))
    raise ApplicationHandlerStop


# ═══════════════════════ نمای فقط‌خواندنیِ مدیرها ═══════════════════════
async def admin_view(update, ctx):
    q = update.callback_query
    uid = q.from_user.id
    adm = await db.get_admin(uid)
    if uid != PISHVA_ID and not (adm and adm["is_active"]):
        await q.answer("⛔", show_alert=True)
        return
    st = await am.get_state(force=True)
    if not st["active"] or not st["announce"]["on"]:
        await q.answer("اطلاعاتی برای نمایش نیست.", show_alert=True)
        return
    t = am.timer_of(st)
    defs = am.capability_defs()
    caps = am.eff_caps(st, defs)
    names = [d["label"] for d in defs if d["kind"] == "cat" and caps[d["key"]]]
    L = ["🤖 <b>رهگشا در «حالتِ مدیر»</b>", ""]
    L.append(f"⏳ {h(am._until_text(st))}" + (f" — باقی‌مانده {am.dur_fa(t['remaining'])}" if t.get("timed") else ""))
    L.append("🔐 حوزه‌های اختیار:")
    L += [f"• {h(n)}" for n in names] or ["—"]
    L.append("\nهمه‌ی اقدامات رهگشا با برچسبِ «رهگشای مدیر» در لاگ‌ها ثبت می‌شود. در چت با رهگشا، مجوزهای شما همان مجوزهای خودتان می‌ماند.")
    await q.answer()
    try:
        await q.message.reply_text("\n".join(L), parse_mode="HTML")
    except Exception:
        logger.info("manager admin view failed", exc_info=True)


def register(app):
    app.add_handler(CommandHandler("a", cmd_a, filters=filters.ChatType.PRIVATE), group=-6)
    app.add_handler(CallbackQueryHandler(mgr_menu, pattern=r"^mgr_menu$"))
    app.add_handler(CallbackQueryHandler(cb, pattern=r"^mgr:"))
    app.add_handler(CallbackQueryHandler(admin_view, pattern=r"^mgrv:"))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, on_text), group=-4)
