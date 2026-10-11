import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramprofile',
            name='referred_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='referrals',
                to='users.telegramprofile',
                verbose_name='تمت دعوته بواسطة',
            ),
        ),
        migrations.AddField(
            model_name='telegramprofile',
            name='referral_bonus_paid',
            field=models.BooleanField(
                default=False,
                verbose_name='تم دفع مكافأة الإحالة للداعي',
            ),
        ),
    ]
