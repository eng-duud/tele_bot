# 📐 المعمارية وخطة التنفيذ لمنصة التجارة الرقمية عبر تليجرام
## (Customer Bot & Admin Bot with Django Backend)

---

### 1. ملخص القرارات المعمارية المعتمدة
بناءً على تحليلك ومتطلباتك، تم اعتماد التصميم التالي:

1. **النمط المعماري (Architecture)**:
   - **Modular Monolith with Service Layer**:
     مشروع Django موحد، تُدار فيه منطق الأعمال (Business Logic) عبر طبقة خدمات نقية (`apps.*.services`).
     البوتات (Customer Bot & Admin Bot) تعمل كواجهة عرض (Presentation Layer) تستدعي دوال الـ Services مباشرة.
   - البوت لا يتخذ أي قرار مالي أو مخزني بمفرده، بل يعتمد على ما يعيده الـ Backend.

2. **نظام العملات المزدوج (Dual Currency: YER / USD)**:
   - العملة الأساسية للحسابات هي **الريال اليمني (YER)** مع دعم كامل للدولار (**USD**).
   - سعر الصرف ديناميكي في الإعدادات (مثلاً: 1 USD = 550 YER) يمكن تعديله في أي لحظة.
   - العميل يختار العملة المفضلة لعرض الأسعار والمنتجات في حسابه، ويتم الحساب والتحويل تلقائياً.

3. **مجموعة الإدارة والموافقات (Admin Group Workflow)**:
   - إرسال طلبات شحن الرصيد (`PaymentRequest`) والمشاكل الفنية (`OrderIssue`) إلى **مجموعة خاصة بمشرفي النظام والبوت**.
   - معالجة الطلبات عبر أزرار تفاعلية مضمنة (`[✅ موافقة]` / `[❌ رفض]`) مع التحقق من الصلاحيات وتسجيل اسم المشرف وتاريخ التنفيذ فوراً ومنع التكرار (Idempotent).

4. **طرق الدفع الديناميكية (Dynamic Payment Methods)**:
   - لوحة الإدارة تمكّن المشرف من إضافة وتعديل وتفعيل أي طريقة دفع (اسم، أيقونة، رقم حساب/نقطة، تعليمات التحويل، شروط إرفاق صورة الإشعار أو رقم العملية).

5. **المزودون الخارجيون والتسليم التلقائي (External Providers & Async Fulfillment)**:
   - تصميم واجهة مجردة للمزودين (`BaseFulfillmentProvider`).
   - استدعاء المزود الخارجي يتم **خارج الـ Database Transaction** عبر مهام خلفية (Celery/Async Worker).
   - توفير نظام إعادة المحاولة (Exponential Backoff) واسترجاع الرصيد التلقائي (Idempotent Refund) في حال فشل التسليم النهائي.

---

### 2. هيكلية المجلدات والتطبيقات المقترحة (Directory Structure)

```
tele_bot/
├── config/                         # إعدادات المشروع و Celery
│   ├── __init__.py
│   ├── settings.py                 # إعدادات Django و قاعدة البيانات والتليجرام
│   ├── celery.py                   # إعدادات طابور المهام
│   ├── asgi.py
│   ├── wsgi.py
│   └── urls.py
│
├── apps/
│   ├── core/                       # الأدوات العامة، أسعار الصرف، والتشفير
│   │   ├── models.py               # TimeStampedModel, ExchangeRate, SystemSetting
│   │   ├── encryption.py           # دوال تشفير وفك تشفير البيانات الحساسة (Fernet)
│   │   └── services.py             # دوال تحويل العملات وتنسيق الأسعار
│   │
│   ├── users/                      # المستخدمين والملفات الشخصية والأذونات
│   │   ├── models.py               # User, TelegramProfile, AdminRole, AdminPermission
│   │   └── services.py             # تسجيل الدخول، فحص الصلاحيات
│   │
│   ├── wallet/                     # المحفظة المالية وسجل الحركات المحاسبي
│   │   ├── models.py               # Wallet, WalletTransaction (DEPOSIT, PURCHASE, REFUND, ADJUSTMENT)
│   │   └── services.py             # شحن الرصيد، الخصم، الاسترجاع مع الأقفال الذرية
│   │
│   ├── payments/                   # طرق الدفع المخصصة وطلبات الشحن
│   │   ├── models.py               # PaymentMethod (ديناميكي), PaymentRequest
│   │   └── services.py             # إنشاء الطلب، قبول الشحن، رفض الشحن
│   │
│   ├── catalog/                    # التصنيفات والمنتجات والصور
│   │   ├── models.py               # Category (هرمية), Product, ProductImage
│   │   └── services.py             # جلب المنتجات، تصفية الفئات، حساب الأسعار
│   │
│   ├── inventory/                  # أنواع المخزون الأربعة
│   │   ├── models.py               # StockItem (مشفر), RestockSubscription
│   │   └── services.py             # حجز وتخصيص المخزون وإشعارات التوفر
│   │
│   ├── orders/                     # الطلبات والـ State Machine
│   │   ├── models.py               # Order, OrderItem (Snapshot), OrderStatusHistory
│   │   └── services.py             # إنشاء الطلب الذري، تحديث الحالة
│   │
│   ├── fulfillment/                # تنفيذ التسليم والمهام المؤجلة
│   │   ├── models.py               # FulfillmentTask, OrderIssue
│   │   ├── tasks.py                # مهام Celery للتسليم غير المتزامن
│   │   └── services.py             # إدارة عمليات التسليم
│   │
│   ├── providers/                  # مزودو الـ API والـ Adapters
│   │   ├── base.py                 # BaseFulfillmentProvider
│   │   ├── mock_provider.py        # مزود وهمي للاختبار الفوري
│   │   ├── models.py               # ApiProvider, ProviderServiceMapping
│   │   └── services.py             # توجيه الطلب للمزود المناسب
│   │
│   ├── services_app/               # الخدمات الرقمية الثابتة والمخصصة (Custom Quotes)
│   │   ├── models.py               # Service, ServiceRequest, ServiceQuote
│   │   └── services.py             # دورة حياة عروض الأسعار والموافقة
│   │
│   ├── notifications/              # فحص القنوات وبث العمليات الناجحة
│   │   ├── models.py               # RequiredChannel, ChannelLog
│   │   └── services.py             # فحص الاشتراك الفعلي عبر API ونشر الإيصالات
│   │
│   ├── audit/                      # سجل التدقيق وتتبع العمليات الحساسة
│   │   ├── models.py               # AuditLog (المشرف، العملية، الفروقات قبل/بعد)
│   │   └── services.py             # تسجيل العمليات الإدارية
│   │
│   └── telegram_bot/               # محرك بوتات التليجرام (aiogram 3)
│       ├── customer/               # بوت العميل: القوائم، المتجر، الشراء، المحفظة
│       ├── admin/                  # بوت الإدارة: التحكم، المخزون، المنتجات
│       ├── admin_group/            # معالجات رسائل وأزرار مجموعة الإدارة الخاصة
│       ├── common/                 # لوحات المفاتيح (Keyboards), Middlewares, FSM States
│       └── management/commands/    # أوامر تشغيل البوتات (run_customer_bot, run_admin_bot)
│
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── manage.py
```

---

### 3. تدفق العمليات الحساسة (Critical Flows)

#### أ. تدفق شحن المحفظة (Wallet Deposit Flow):
1. يختار العميل طريقة الدفع المعرفة من لوحة الإدارة.
2. تظهر تعليمات التحويل ورقم الحساب/النقطة.
3. يرسل العميل صورة الإشعار و/أو رقم العملية.
4. يُنشأ سجل `PaymentRequest` بحالة `PENDING`.
5. تُرسل بطاقة تفاعلية فوراً إلى **مجموعة الإدارة الخاصة** بأزرار: `[✅ قبول]` و `[❌ رفض]`.
6. يضغط أحد المشرفين المعتمدين على `[✅ قبول]`:
   - يتم التحقق من الصلاحيات ووجود قفل لمنع التكرار (Idempotency).
   - يتم إيداع المبلغ في `WalletTransaction` ذرياً (`transaction.atomic`).
   - يتم تحديث رسالة القروب باسم المشرف ووقت الاعتماد.
   - يتلقى العميل إشعاراً في محادثته الخاصة بزيادة رصيده مع رصيده الجديد.

#### ب. تدفق شراء المنتج الرقمي (Purchase Flow):
1. يختار العميل المنتج والكمية بالعملة المفضلة له (YER أو USD).
2. عند الضغط على "تأكيد الشراء":
   - يُفتح `transaction.atomic()` مع قفل الصفوف (`select_for_update`) للمحفظة والمخزون.
   - يتم التحقق من الرصيد الحقيقي في قاعدة البيانات ومطابقة السعر مع سعر الصرف اللحظي.
   - حجز عنصر المخزون أو تقليل الكمية.
   - خصم المبلغ من المحفظة وتسجيل `WalletTransaction` من نوع `PURCHASE`.
   - إنشاء الطلب `Order` بحالة `PENDING` أو `PROCESSING`.
   - إتمام المعاملة (`Commit`).
3. بعد الـ Commit مباشرة (`transaction.on_commit`):
   - إرسال مهمة الـ Fulfillment إلى طابور Celery / Background Worker.
   - في حال كان التسليم من المخزون الداخلي (`INDIVIDUAL_ITEMS`): يتم فك تشفير الكود وإرساله للعميل مباشرة وتحديث حالة الطلب إلى `COMPLETED`.
   - في حال كان التسليم عبر مزود API خارجي: يقوم الـ Worker باستدعاء المزود واستلام الكود وتمريره للعميل.
   - نشر إشعار العملية الناجحة في قناة العمليات العامة (مع إخفاء أي بيانات حساسة).

---

### 4. مراحل التنفيذ المباشرة (Step-by-Step Execution Plan)

- **الخطوة 1:** تجهيز ملف `requirements.txt` وإعداد بيئة Django + Celery + aiogram 3.
- **الخطوة 2:** إعداد النواة الأساسية `core` (نظام التشفير Fernet + نماذج العملات وأسعار الصرف الديناميكية).
- **الخطوة 3:** إعداد تطبيق المستخدمين `users` والصلاحيات الإدارية (RBAC).
- **الخطوة 4:** إعداد المحفظة المحاسبية `wallet` والعمليات الذرية المانعة للازدواج المالي.
- **الخطوة 5:** إعداد طرق الدفع الديناميكية `payments` ونظام بطاقات موافقات مجموعة المشرفين.
- **الخطوة 6:** إعداد الكتالوج `catalog` (تصنيفات هرمية + منتجات متعددة العملات) والمخزون `inventory` (الأنواع الأربعة).
- **الخطوة 7:** إعداد الطلبات `orders` ونظام الـ Fulfillment ومزود الـ Mock Provider.
- **الخطوة 8:** بناء واجهات بوت العميل (Customer Bot) مع فحص الاشتراك الإجباري.
- **الخطوة 9:** بناء واجهات بوت الإدارة ومجموعة المشرفين (Admin Bot & Group Handler).
- **الخطوة 10:** قناة العمليات الناجحة ونظام التدقيق (Audit Logs) وتجهيز الاختبارات.
