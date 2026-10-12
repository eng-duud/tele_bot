from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('fulfillment', '0003_remove_fulfillmenttask_max_attempts'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='fulfillmenttask',
            constraint=models.UniqueConstraint(fields=('order',), name='unique_fulfillment_task_per_order'),
        ),
    ]
