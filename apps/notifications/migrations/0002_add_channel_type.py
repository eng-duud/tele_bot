from django.db import migrations, models


def add_channel_type_column(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'notifications_requiredchannel' 
                        AND column_name = 'channel_type'
                    ) THEN
                        ALTER TABLE notifications_requiredchannel ADD COLUMN channel_type VARCHAR(30) DEFAULT 'SUBSCRIPTION';
                    END IF;
                    ALTER TABLE notifications_requiredchannel ALTER COLUMN invite_link DROP NOT NULL;
                END $$;
                """
            )
        except Exception:
            try:
                cursor.execute("ALTER TABLE notifications_requiredchannel ADD COLUMN channel_type VARCHAR(30) DEFAULT 'SUBSCRIPTION';")
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='requiredchannel',
                    name='channel_type',
                    field=models.CharField(
                        choices=[
                            ('SUBSCRIPTION', '🔒 اشتراك إجباري للعملاء'),
                            ('SUCCESS', '📢 نشر التفعيلات والعمليات الناجحة'),
                            ('BACKUP', '📦 نسخ احتياطي للبيانات'),
                            ('ALERTS', '🔔 إشعارات الإدارة والمشرفين'),
                        ],
                        db_index=True,
                        default='SUBSCRIPTION',
                        max_length=30,
                        verbose_name='نوع القناة والغرض منها'
                    ),
                ),
                migrations.AlterField(
                    model_name='requiredchannel',
                    name='invite_link',
                    field=models.URLField(blank=True, default='', verbose_name='رابط الدعوة للقناة'),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_channel_type_column, migrations.RunPython.noop),
            ]
        )
    ]
