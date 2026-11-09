"""mgr_ctx.py — پرچمِ «الان رهگشای مدیر (جانشین) دارد اقدام می‌کند». بدونِ هیچ وابستگی، تا database و ai_tools بتوانند بی‌چرخه ایمپورتش کنند."""
from contextvars import ContextVar

ACTING = ContextVar("rg_manager_acting", default=False)
LABEL = "🤖[رهگشای مدیر] "
