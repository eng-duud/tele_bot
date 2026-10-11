import uuid
import django.db.models.deletion
from django.db import migrations, models
import apps.support.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupportTicket',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('ticket_number', models.CharField(db_index=True, default=apps.support.models.generate_ticket_number, max_length=50, unique=True, verbose_name='رقم التذكرة')),
                ('subject', models.CharField(blank=True, max_length=255, verbose_name='موضوع التذكرة / المشكلة')),
                ('status', models.CharField(choices=[('OPEN', 'مفتوحة 🟢'), ('ANSWERED', 'تم الرد 💬'), ('CLOSED', 'مغلقة 🔒')], db_index=True, default='OPEN', max_length=20, verbose_name='حالة التذكرة')),
                ('admin_message_id', models.BigIntegerField(blank=True, null=True, verbose_name='معرف رسالة التذكرة في مجموعة الإدارة')),
                ('last_answered_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ آخر رد')),
                ('closed_at', models.DateTimeField(blank=True, null=True, verbose_name='تاريخ الإغلاق')),
                ('last_answered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='answered_tickets', to='users.telegramprofile', verbose_name='آخر رد بواسطة')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='support_tickets', to='users.telegramprofile', verbose_name='العميل')),
            ],
            options={
                'verbose_name': 'تذكرة دعم فني',
                'verbose_name_plural': 'تذاكر الدعم الفني',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='TicketMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('is_from_admin', models.BooleanField(default=False, verbose_name='من الإدارة')),
                ('text', models.TextField(verbose_name='نص الرسالة')),
                ('photo_file_id', models.CharField(blank=True, max_length=255, verbose_name='معرف الصورة في تليجرام')),
                ('document_file_id', models.CharField(blank=True, max_length=255, verbose_name='معرف الملف في تليجرام')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.telegramprofile', verbose_name='المرسل')),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='support.supportticket', verbose_name='التذكرة')),
            ],
            options={
                'verbose_name': 'رسالة دعم فني',
                'verbose_name_plural': 'رسائل الدعم الفني',
                'ordering': ['created_at'],
            },
        ),
    ]
