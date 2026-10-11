#!/bin/bash
# ==============================================================================
# سكربت الإعداد التلقائي لمشروع بوت تيليجرام على خادم DigitalOcean (Ubuntu)
# ==============================================================================
set -e

echo "=========================================================="
echo "🚀 بدء تجهيز خادم DigitalOcean لتشغيل بوت تيليجرام والمتجر..."
echo "=========================================================="

# 1. تحديث النظام وتثبيت الحزم الأساسية
echo "📦 [1/6] تحديث حزم النظام وتثبيت المتطلبات..."
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip redis-server postgresql postgresql-contrib nginx curl gzip

# 2. تفعيل وتشغيل الخدمات
echo "⚙️ [2/6] تشغيل خادم Redis وخادم PostgreSQL..."
sudo systemctl enable --now redis-server
sudo systemctl enable --now postgresql

# 3. إعداد مستخدم ومجلد المشروع
APP_DIR="/var/www/tele_bot"
echo "👤 [3/6] إنشاء مستخدم ومجلد المشروع في ${APP_DIR}..."
if ! id "telebot" &>/dev/null; then
    sudo adduser --system --group --home ${APP_DIR} telebot
fi

sudo mkdir -p ${APP_DIR}
sudo chown -R telebot:telebot ${APP_DIR}

# 4. إعداد البيئة الافتراضية وتثبيت المتطلبات
echo "🐍 [4/6] تجهيز بيئة بايثون وتثبيت المكتبات..."
if [ ! -d "${APP_DIR}/venv" ]; then
    sudo -u telebot python3 -m venv ${APP_DIR}/venv
fi

if [ -f "${APP_DIR}/requirements.txt" ]; then
    sudo -u telebot ${APP_DIR}/venv/bin/pip install --upgrade pip
    sudo -u telebot ${APP_DIR}/venv/bin/pip install -r ${APP_DIR}/requirements.txt
fi

# 5. تثبيت خدمات systemd
echo "🔄 [5/6] ربط خدمات systemd للتشغيل الدائم..."
if [ -d "${APP_DIR}/deployment" ]; then
    sudo cp ${APP_DIR}/deployment/*.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable tele_bot tele_worker tele_web
fi

# 6. جدولة النسخ الاحتياطي التلقائي إلى تيليجرام يومياً الساعة 3 فجراً
echo "📦 [6/6] جدولة النسخ الاحتياطي التلقائي عبر Cron..."
CRON_JOB="0 3 * * * ${APP_DIR}/venv/bin/python ${APP_DIR}/manage.py backup_database > /dev/null 2>&1"
( crontab -u telebot -l 2>/dev/null | grep -Fv "backup_database" ; echo "$CRON_JOB" ) | crontab -u telebot -

echo "=========================================================="
echo "✅ اكتمل التجهيز الأساسي بنجاح!"
echo "📝 الخطوة التالية:"
echo "1. تأكد من ضبط ملف ${APP_DIR}/.env بالبيانات الصحيحة."
echo "2. طبّق الترحيلات: cd ${APP_DIR} && sudo -u telebot venv/bin/python manage.py migrate"
echo "3. شغّل الخدمات: sudo systemctl start tele_bot tele_worker tele_web"
echo "4. افحص الحالة: sudo systemctl status tele_bot"
echo "=========================================================="
