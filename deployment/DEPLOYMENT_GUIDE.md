# دليل رفع وتشغيل متجر Telegram الرقمي

## 1. النتيجة المعمارية

المشروع تطبيق Django يدير قاعدة البيانات ولوحة Django Admin، وبوتين مبنيين على aiogram: بوت للعميل وبوت للإدارة. الطلبات التي تعتمد على مخزون داخلي تُسلَّم داخل المعاملة نفسها. الطلبات التي تعتمد على مزود خارجي تُرسل إلى Celery بعد نجاح معاملة الشراء. لذلك يلزم تشغيل أربعة مكونات في الإنتاج:

1. **خدمة الويب** لتشغيل Django وDjango Admin.
2. **خدمة بوت Telegram** لتشغيل البوتين عبر polling.
3. **عامل Celery** لتنفيذ طلبات المزود الخارجي وإعادة المحاولة.
4. **Redis** كوسيط رسائل لـ Celery.

تحتاج كذلك إلى PostgreSQL موصى به للإنتاج. يمكن استخدام SQLite للتطوير المحلي فقط.

## 2. الخدمات المطلوبة

| المكوّن | هل هو إلزامي؟ | الاستخدام |
| --- | --- | --- |
| Telegram Bot API | نعم | تشغيل بوت العميل وبوت الإدارة |
| PostgreSQL | موصى به بقوة | تخزين المستخدمين والمحفظة والطلبات |
| Redis | نعم مع `fulfillment_type=API` | طابور Celery للطلبات الخلفية |
| مزود المنتجات الخارجي | اختياري | التنفيذ الآلي. الوضع `MOCK` للاختبار فقط |
| نطاق HTTPS | اختياري للوحة الإدارة | الوصول الآمن إلى `/admin/` |

لا تحتاج إلى ربط موصل Manus أو Cloudinary حتى يعمل المشروع على VPS. صور إيصالات التحويل تُرسل عبر Telegram ويُحفظ `file_id` فقط في قاعدة البيانات، ثم يعيد بوت الإدارة عرض الصورة من Telegram. إذا أردت نشره على استضافة خارجية، تحتاج إلى وصول SSH أو حساب الاستضافة بالطريقة الآمنة التي تختارها، وليس إرسال الأسرار داخل المحادثة.

## 3. تجهيز Telegram

أنشئ بوت العميل وبوت الإدارة من [BotFather][1] واحفظ التوكنين منفصلين. أضف بوت الإدارة إلى مجموعة المشرفين، وأضف البوت الذي سيتحقق من الاشتراك إلى القنوات المطلوبة. امنح البوت الصلاحيات اللازمة لقراءة حالة العضوية وإرسال الرسائل.

استخدم معرفات رقمية تبدأ عادةً بـ `-100` للمجموعات والقنوات الخاصة. لا تضع توكنًا حقيقيًا في GitHub أو في رسالة عامة.

## 4. تجهيز Ubuntu

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip postgresql redis-server nginx
sudo systemctl enable --now postgresql redis-server
sudo adduser --system --group --home /var/www/tele_bot telebot
sudo mkdir -p /var/www/tele_bot
sudo chown -R telebot:telebot /var/www/tele_bot
```

أنشئ قاعدة بيانات PostgreSQL:

```bash
sudo -u postgres psql
```

ثم داخل جلسة PostgreSQL:

```sql
CREATE USER telebot_db_user WITH PASSWORD 'ضع_كلمة_مرور_قوية_هنا';
CREATE DATABASE telebot_db OWNER telebot_db_user;
\q
```

## 5. رفع الكود وتثبيت البيئة

```bash
sudo -u telebot -H bash
cd /var/www/tele_bot
git clone https://github.com/eng-duud/tele_bot.git .
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

عند تحديث نسخة موجودة، استخدم `git pull` بعد أخذ نسخة احتياطية من قاعدة البيانات، ثم شغّل الترحيلات من جديد.

## 6. إنشاء ملف البيئة

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

اضبط القيم التالية، وغيّر كل قيمة تجريبية:

```dotenv
DJANGO_SECRET_KEY=سلسلة_عشوائية_طويلة_وفريدة
DEBUG=False
ALLOWED_HOSTS=your-domain.com,your-server-ip
CSRF_TRUSTED_ORIGINS=https://your-domain.com

USE_POSTGRES=True
DATABASE_URL=postgresql://telebot_db_user:كلمة_المرور@127.0.0.1:5432/telebot_db
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

CUSTOMER_BOT_TOKEN=توكن_بوت_العميل
ADMIN_BOT_TOKEN=توكن_بوت_الإدارة
ADMIN_GROUP_ID=-1001234567890
SUCCESS_CHANNEL_ID=@your_channel
SUPER_ADMIN_TELEGRAM_ID=123456789
REQUIRED_CHANNEL_ID=@your_required_channel
REQUIRED_CHANNEL_URL=https://t.me/your_required_channel
SUCCESS_CHANNEL_URL=https://t.me/your_success_channel

DATA_ENCRYPTION_KEY=مفتاح_Fernet_ثابت
DEFAULT_EXCHANGE_RATE_USD_TO_YER=550.00
BASE_CURRENCY=YER
```

ولّد مفتاح التشفير مرة واحدة فقط:

```bash
venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

احتفظ بهذا المفتاح في مدير أسرار أو نسخة احتياطية مشفرة. **لا تغيّره بعد إدخال مخزون مشفر**؛ تغييره يجعل الأكواد القديمة غير قابلة للفك. الكود الآن يرفض المفتاح المفقود أو غير الصحيح بدل توليد مفتاح عشوائي يؤدي إلى فقدان قابلية قراءة المخزون بعد إعادة التشغيل.

## 7. تهيئة Django

```bash
source /var/www/tele_bot/venv/bin/activate
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

لا تشغّل `makemigrations` على الخادم في النشر العادي. أنشئ الترحيلات أثناء التطوير، راجعها في Git، ثم طبّقها في الإنتاج باستخدام `migrate`.

للاختبار الأولي فقط يمكنك تعبئة بيانات تجريبية:

```bash
python manage.py seed_demo_data
```

لا تستخدم بيانات `MOCK` أو بيانات الدفع التجريبية في متجر حقيقي.

## 8. تشغيل الخدمات عبر systemd

انسخ ملفات الخدمات:

```bash
sudo cp deployment/tele_bot.service /etc/systemd/system/
sudo cp deployment/tele_web.service /etc/systemd/system/
sudo cp deployment/tele_worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tele_web tele_bot tele_worker
```

ملف `tele_worker.service` ضروري لطلبات API. من دونه سيبقى الطلب في حالة `PROCESSING` بعد خصم الرصيد.

```bash
sudo systemctl status tele_web tele_bot tele_worker --no-pager
sudo journalctl -u tele_bot -f
sudo journalctl -u tele_worker -f
sudo journalctl -u tele_web -f
```

إذا استخدمت مستخدم `telebot` كما في هذا الدليل، تأكد من أن المجلد وملف `.env` مملوكان له. لا يُنصح بتشغيل التطبيق كمستخدم `root`.

## 9. إعداد Nginx وHTTPS

وجّه النطاق إلى عنوان الخادم، ثم أنشئ إعداد Nginx:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /static/ {
        alias /var/www/tele_bot/staticfiles/;
    }

    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

فعّل الإعداد ثم أضف HTTPS:

```bash
sudo ln -s /etc/nginx/sites-available/tele_bot /etc/nginx/sites-enabled/tele_bot
sudo nginx -t
sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

بعد تفعيل HTTPS، حدّث `CSRF_TRUSTED_ORIGINS` إلى العنوان الفعلي.

## 10. اختبار القبول بعد الرفع

1. افتح `https://your-domain.com/admin/` وسجّل الدخول.
2. أضف تصنيفًا ومنتجًا تجريبيًا.
3. أضف عنصر مخزون مشفرًا وتحقق من عرض النص الصحيح.
4. أرسل `/start` إلى بوت العميل.
5. اختبر الاشتراك الإجباري وزر التحقق.
6. نفّذ شراءً من المخزون وتحقق من خصم المحفظة وتسليم الكود مرة واحدة.
7. أنشئ منتجًا من نوع `API` مربوطًا بمزود `MOCK`، وتحقق من اكتمال الطلب عبر Celery.
8. أوقف عامل Celery مؤقتًا، أنشئ طلب API، ثم شغّله وتأكد من معالجة الطلب لاحقًا.
9. اختبر فشل المزود وتأكد من تسجيل المحاولات واسترجاع الرصيد بعد استنفادها.
10. راقب عدم ظهور التوكنات أو مفاتيح التشفير في السجلات.

## 11. النسخ الاحتياطي والتحديث

خذ نسخة يومية من PostgreSQL، واحتفظ بنسخة مستقلة من `DATA_ENCRYPTION_KEY`. لا تكفي نسخة قاعدة البيانات وحدها لاستعادة المخزون المشفر إذا فُقد المفتاح.

```bash
sudo -u postgres pg_dump -Fc telebot_db > /var/backups/telebot_$(date +%F).dump
```

عند التحديث:

```bash
sudo systemctl stop tele_bot tele_worker tele_web
sudo -u telebot -H bash -c 'cd /var/www/tele_bot && git pull && source venv/bin/activate && pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput'
sudo systemctl start tele_web tele_worker tele_bot
```

## 12. الإصلاحات المنفذة

تمت إضافة ملف ASGI المفقود، وتشديد الإعدادات الافتراضية بحيث لا يبدأ المشروع على `DEBUG=True` أو `ALLOWED_HOSTS=*`. تم تغيير التشفير من مفتاح عشوائي جديد في كل تشغيل إلى مفتاح Fernet ثابت مطلوب من البيئة. تم ربط طلبات `API` بعامل Celery باستخدام `transaction.on_commit` حتى لا يبدأ التنفيذ قبل تثبيت الخصم والطلب. أضيف رفض صريح لنوع التسليم `FILE` لأنه معلن لكنه غير منفذ بعد. وأضيفت اختبارات انحدار لهذه الحالات.

## 13. الموصلات المطلوبة

لا أحتاج أي موصل داخل Manus للمراجعة أو لتعديل GitHub. للتشغيل الخارجي تحتاج إلى Telegram Bot API، وقاعدة PostgreSQL، وRedis عند استخدام Celery. لا تحتاج إلى Cloudinary لإيصالات التحويل؛ مزود API للمنتجات اختياري. إذا أردت نشره فعليًا، يكفي تحديد نوع الاستضافة؛ أما الأسرار فالأفضل إدخالها مباشرة في لوحة الاستضافة أو مدير الأسرار، وليس إرسالها في المحادثة.

## 14. قيود منع الإزعاج والتلاعب

يتحقق البوت من عضوية المستخدم في كل رسالة أو زر بعد الدخول. إذا خرج المستخدم من أي قناة أو مجموعة إلزامية، يُحجب عنه البوت عند أول تفاعل لاحق. كما أن فشل البوت في قراءة حالة العضوية لا يمنح المستخدم مرورًا تلقائيًا؛ يتم إيقاف الوصول حتى تُصلح صلاحية البوت أو معرف القناة. يجب أن يكون البوت مشرفًا في كل قناة إلزامية حتى يعمل هذا الفحص.

أصبح الضغط السريع على الأزرار محدودًا بثمانية callbacks خلال ثلاث ثوانٍ لكل مستخدم. هذا يمنع النقر المتكرر أو إرسال عدة طلبات بسبب ضغط زر واحد بسرعة، ولا يؤثر على الاستخدام الطبيعي.

طلبات الشحن مقيدة بحيث لا يستطيع المستخدم إنشاء طلب جديد أثناء وجود طلب `PENDING`. وبعد اكتمال الطلبات، يسمح النظام بثلاثة طلبات كحد أقصى خلال عشر دقائق. يتم تطبيق الفحص داخل معاملة وقفل سجل المستخدم حتى لا تتجاوز طلبات متزامنة هذا الحد.

تأكد من أن `ADMIN_GROUP_ID` يشير إلى مجموعة الإدارة الصحيحة، وأن البوت الإداري مشرف فيها. راقب `journalctl -u tele_bot -f` بعد التشغيل؛ أخطاء عدم صلاحية البوت في القنوات ستظهر بوضوح في السجل.

## المراجع

[1]: https://core.telegram.org/bots/tutorial "Telegram Bot API tutorial"
[2]: https://docs.djangoproject.com/en/5.2/howto/deployment/ "Django deployment checklist"
[3]: https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html "Celery Redis broker documentation"
[4]: https://cryptography.io/en/latest/fernet/ "Fernet authenticated encryption documentation"
