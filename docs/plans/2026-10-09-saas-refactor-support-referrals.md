# SaaS Architecture, Support System & Referral Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform Tele Bot into a fully configurable, white-label SaaS e-commerce platform with dynamic system settings, an integrated customer support ticketing system routed to the Admin Group, a dynamic referral bonus system, fully dynamic mandatory channels, modular admin handlers, and sanitized security credentials.

**Architecture:** 
- Modular Monolith in Django 5 with aiogram 3.
- `SystemSetting` service provides dynamic store configuration (Store Name, Support Username, Referral Bonus in YER, etc.) replacing all static strings.
- Referral engine with unique links (`/start ref_<id>`), automated ledger bonuses upon verified channel subscription.
- Integrated Support Ticket system inside Customer Bot with interactive dispatch & reply cards in the Admin Group.
- Modularization of `apps/telegram_bot/admin/handlers.py` into dedicated domain routers.

**Tech Stack:** Python 3.11+, Django 5, aiogram 3, Celery, Redis, PostgreSQL/SQLite, Fernet Encryption.

---

### Task 1: Security Cleanup & Credential Protection
**Files:**
- Modify: `test_provider.py`
- Modify: `apps/providers/management/commands/setup_vente_provider.py`
- Modify: `.env.example`

**Step 1:** In `test_provider.py` and `setup_vente_provider.py`, remove the hardcoded live API key and load it dynamically from environment variable `VENTE_API_KEY` (or Django `ApiProvider` DB record) with a safe placeholder fallback.
**Step 2:** Update `.env.example` to document `VENTE_API_KEY`.
**Step 3:** Verify no plain-text secret keys remain in the codebase.

---

### Task 2: SaaS Dynamic Settings Engine (`SystemSettingService`)
**Files:**
- Modify: `apps/core/models.py`
- Modify: `apps/core/services.py`
- Modify: `apps/core/admin.py`

**Step 1:** Ensure `SystemSetting` has efficient cached lookup and typed helpers in `SystemSettingService`:
- `get_setting(key: str, default: str = "") -> str`
- `get_int(key: str, default: int = 0) -> int`
- `get_decimal(key: str, default: Decimal = Decimal('0')) -> Decimal`
- `get_bool(key: str, default: bool = False) -> bool`
- `set_setting(key: str, value: str, description: str = "")`
**Step 2:** Prepopulate default settings on first run (Store Name, Support Contact Username, Referral Bonus YER = 50, Referral Enabled = True).
**Step 3:** Register `SystemSetting` with a clean UI in `apps/core/admin.py`.

---

### Task 3: Referral & Affiliate Engine (نظام الإحالات والأرباح)
**Files:**
- Modify: `apps/users/models.py`
- Modify: `apps/users/services.py`
- Modify: `apps/users/admin.py`
- Create: `apps/telegram_bot/customer/handlers/referrals.py`
- Modify: `apps/telegram_bot/customer/handlers/start.py`
- Modify: `apps/telegram_bot/common/keyboards.py`

**Step 1:** Add `referred_by` foreign key, `referral_code`, and `referral_bonus_paid` boolean to `TelegramProfile`.
**Step 2:** In `UserService.get_or_create_user`, accept an optional `referrer_id` to link the invitation.
**Step 3:** Implement `ReferralService`:
- Process referral reward atomically: when user passes channel verification, check `REFERRAL_ENABLED` and credit the referrer's wallet via `WalletService.deposit` with idempotency key.
- Send a Telegram alert to the referrer with their new balance.
**Step 4:** Build the customer UI for referrals:
- Menu button `🤝 نظام الإحالة (كسب الأرباح)`.
- Shows custom referral link `https://t.me/<bot_username>?start=ref_<telegram_id>`.
- Displays total referred friends and total earnings.

---

### Task 4: Dynamic Mandatory Channels Management (قنوات الاشتراك الإجباري)
**Files:**
- Modify: `apps/notifications/services.py`
- Modify: `apps/notifications/models.py`
- Modify: `apps/telegram_bot/admin/handlers/channels.py` (part of refactor)

**Step 1:** Update `ChannelSubscriptionService` to make DB records in `RequiredChannel` the primary source of truth without any hardcoded project defaults or fallback strings.
**Step 2:** Ensure adding and removing channels can be done dynamically from Django Admin and from the Admin Bot.

---

### Task 5: Integrated Support Ticketing System (الدعم الفني المدمج)
**Files:**
- Create: `apps/support/` (or within `apps/notifications/` / `apps/users/`):
  - `apps/support/models.py` (`SupportTicket`, `TicketMessage`)
  - `apps/support/services.py` (`SupportService`)
  - `apps/support/admin.py`
- Modify: `config/settings.py` (register `apps.support`)
- Modify: `apps/telegram_bot/customer/handlers/start.py`
- Create: `apps/telegram_bot/customer/handlers/support.py`
- Modify: `apps/telegram_bot/admin_group/handlers.py`
- Modify: `apps/telegram_bot/common/states.py`

**Step 1:** Model `SupportTicket` (`user`, `status`: OPEN/ANSWERED/CLOSED, `subject`, `admin_message_id`).
**Step 2:** Customer clicks "🎧 الدعم الفني":
- Displays dynamic support username/link configured by Admin in `SystemSetting`.
- Displays inline button `📝 إرسال تذكرة / استفسار للدعم`.
**Step 3:** Customer sends their message / screenshot:
- Ticket is created.
- Formatted card is sent directly to the **Admin Group** with buttons: `[✍️ رد على العميل]` and `[🔒 إغلاق التذكرة]`.
**Step 4:** Admin Group reply handling:
- Admin clicks `[✍️ رد على العميل]` and submits the reply.
- System delivers the reply message to the customer's private chat via Customer Bot with clear branding.
- Updates the ticket status to `ANSWERED`.

---

### Task 6: Refactoring Admin Bot Handlers into Modular Domain Routers
**Files:**
- Deconstruct: `apps/telegram_bot/admin/handlers.py` (2,591 lines) into:
  - `apps/telegram_bot/admin/handlers/__init__.py`
  - `apps/telegram_bot/admin/handlers/dashboard.py`
  - `apps/telegram_bot/admin/handlers/products.py`
  - `apps/telegram_bot/admin/handlers/categories.py`
  - `apps/telegram_bot/admin/handlers/stock.py`
  - `apps/telegram_bot/admin/handlers/payments.py`
  - `apps/telegram_bot/admin/handlers/users.py`
  - `apps/telegram_bot/admin/handlers/settings.py` (with settings for Support username, Referral bonus YER, Store name, Exchange rate)
  - `apps/telegram_bot/admin/handlers/channels.py`
  - `apps/telegram_bot/admin/handlers/providers.py`
  - `apps/telegram_bot/admin/handlers/broadcast.py`
  - `apps/telegram_bot/admin/handlers/issues.py`
- Update: `apps/telegram_bot/management/commands/run_all_bots.py` and `run_admin_bot.py`.

---

### Task 7: Comprehensive Verification & Automated Tests
**Files:**
- Create: `apps/wallet/tests.py` (concurrent deposits, idempotency, referral bonus)
- Create: `apps/support/tests.py` (ticket creation, admin reply dispatch)
- Run Django system check and tests.
- Update `README.md` and `ARCHITECTURE.md` with the new SaaS, Support, and Referral capabilities.
