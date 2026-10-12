from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='idempotency_key',
            field=models.CharField(blank=True, db_index=True, max_length=180, null=True, unique=True, verbose_name='مفتاح منع تكرار الشراء'),
        ),
    ]
