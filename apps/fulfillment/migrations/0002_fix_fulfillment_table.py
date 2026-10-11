from django.db import migrations, models


def fix_fulfillment_columns(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        # Check if table exists
        try:
            cursor.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'fulfillment_fulfillmenttask' 
                        AND column_name = 'provider_idempotency_key'
                    ) THEN
                        ALTER TABLE fulfillment_fulfillmenttask ALTER COLUMN provider_idempotency_key DROP NOT NULL;
                        ALTER TABLE fulfillment_fulfillmenttask ALTER COLUMN provider_idempotency_key SET DEFAULT '';
                    ELSE
                        ALTER TABLE fulfillment_fulfillmenttask ADD COLUMN provider_idempotency_key VARCHAR(255) DEFAULT '';
                    END IF;
                END $$;
                """
            )
        except Exception:
            # Fallback for SQLite or when DO blocks are unsupported
            try:
                cursor.execute("ALTER TABLE fulfillment_fulfillmenttask ADD COLUMN provider_idempotency_key VARCHAR(255) DEFAULT '';")
            except Exception:
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('fulfillment', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='fulfillmenttask',
                    name='provider_idempotency_key',
                    field=models.CharField(
                        blank=True,
                        default='',
                        max_length=255,
                        null=True,
                        verbose_name='مفتاح منع تكرار المزود'
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(fix_fulfillment_columns, migrations.RunPython.noop),
            ]
        )
    ]
