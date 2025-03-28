# Generated by Django 5.1.4 on 2025-01-04 12:52

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0024_notifications'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tariffs',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('offer_tariff', models.FloatField()),
                ('combination', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='energy.combination')),
            ],
        ),
    ]
