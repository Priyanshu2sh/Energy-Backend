# Generated by Django 5.1.4 on 2025-01-06 11:06

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0028_remove_tariffs_generator_negotiationoffer'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(
            old_name='NegotiationOffer',
            new_name='GeneratorOffer',
        ),
        migrations.RemoveField(
            model_name='generatoroffer',
            name='terms_sheet',
        ),
        migrations.AddField(
            model_name='generatoroffer',
            name='tariff',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='energy.tariffs'),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='NegotiationWindow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_time', models.DateTimeField(default=django.utils.timezone.now)),
                ('end_time', models.DateTimeField()),
                ('terms_sheet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='energy.standardtermssheet')),
            ],
        ),
    ]
