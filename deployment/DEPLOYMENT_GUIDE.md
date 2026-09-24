# 🚀 دليل النشر والتشغيل على الاستضافة والسيرفر (Production Deployment Guide)

تم فحص وتحصين المشروع بالكامل ليكون جاهزاً للرفع المباشر والعمل 24/7 دون توقف أو أخطاء.

---

## 📋 المتطلبات الأساسية على السيرفر (Linux VPS / Ubuntu 22.04 أو 24.04):
- Python 3.10 أو أحدث.
- Git.
- (اختياري) Redis في حال تفعيل مهام Celery الخلفية للمزودين الخارجيين.

---

## 🛠 خطوات التثبيت على السيرفر خطوة بخطوة:

### 1. استنساخ أو رفع المشروع إلى السيرفر:
```bash
# إنشاء مجلد المشروع
sudo mkdir -p /var/www/tele_bot
cd /var/www/tele_bot

# رفع ملفات المشروع أو استنساخها عبر git
# git clone <YOUR_REPO_URL> .
```

### 2. إعداد البيئة الافتراضية وتثبيت المكتبات:
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. إعداد ملف البيئة `.env`:
انسخ ملف `.env` وتأكد من ملء المتغيرات:
```bash
cp .env.example .env
nano .env
```
تأكد من ضبط:
- `DEBUG=False`
- `ALLOWED_HOSTS=your_domain.com,your_server_ip`
- `CSRF_TRUSTED_ORIGINS=https://your_domain.com`
- `CUSTOMER_BOT_TOKEN=...`
- `ADMIN_BOT_TOKEN=...`
- `SUPER_ADMIN_TELEGRAM_ID=...`
- `DATA_ENCRYPTION_KEY=...`
- `DATABASE_URL=...` (قاعدة بيانات Neon السحابية جاهزة ومعدة)

### 4. تطبيق الترحيلات وتجميع الملفات الثابتة:
```bash
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
```

### 5. إنشاء حساب المشرف للوحة التحكم (Django Admin):
```bash
python manage.py createsuperuser
```

---

## ⚙️ تشغيل البوتات كخدمة خلفية دائمة (Systemd Daemon):

لضمان عمل البوتات في الخلفية وإعادة تشغيلها تلقائياً عند إعادة تشغيل السيرفر أو حدوث أي طارئ:

### 1. تثبيت خدمة البوتات:
```bash
sudo cp deployment/tele_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tele_bot
sudo systemctl start tele_bot
```

### 2. التحقق من حالة البوتات ومتابعة السجلات الحية:
```bash
sudo systemctl status tele_bot
# لمتابعة سجلات البوت الحية أولاً بأول:
sudo journalctl -u tele_bot -f
```

### 3. (اختياري) تشغيل لوحة التحكم والويب (Gunicorn):
```bash
sudo cp deployment/tele_web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tele_web
sudo systemctl start tele_web
```

---

## 🛡 ملخص التحصينات التي تمت في هذه الدورية الشاملة:
1. **أمان الإدارة (Admin RBAC Middleware)**:
   - تم تثبيت `AdminAuthMiddleware` على مستوى الـ Dispatcher الأساسي لبوت الإدارة. أي مستخدم غير مصرح له أو يحاول إرسال أي أمر/زر تفاعلي يُمنع في الحال.
2. **منع تجمد وانحباس المستخدم في المحادثة (FSM Traps Unblocked)**:
   - تم دعم أوامر الإلغاء والرجوع (`إلغاء`, `رجوع`, `/cancel`) في كافة مراحل الشحن والشراء والخدمات.
   - تنظيف الـ FSM State تلقائياً بمجرد طلب القائمة الرئيسية أو `/start`.
3. **أمان معالجة نصوص التيليجرام (Markdown Escaping)**:
   - إضافة دالة `escape_md` لمعالجة الرموز الخاصة في أسماء العملاء ومنع توقف إرسال الرسائل.
4. **تفعيل إشعارات التنفيذ الآلي والمشاكل الفنية (Fulfillment Alerts)**:
   - إنشاء `CustomerNotifierService` و `send_order_issue_alert` لدعم تنبيه العميل والإدارة عند اكتمال أو فشل الطلبات مع مهام Celery.
5. **معالجة خطأ تعديل صور الرسائل في التيليجرام (Photo Edit Bug)**:
   - معالجة أزرار العودة للرئيسية بحيث لا تستدعي `edit_text` على رسائل الصور مما كان يسبب خطأ تيليجرام.
