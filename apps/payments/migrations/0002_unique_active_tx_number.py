from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='paymentrequest',
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=('PENDING', 'APPROVED'), tx_number__gt=''),
                fields=('tx_number',),
                name='unique_active_payment_tx_number',
            ),
        ),
    ]
