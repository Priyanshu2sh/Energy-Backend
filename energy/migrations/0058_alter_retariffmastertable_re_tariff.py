# Generated by Django 4.2.10 on 2025-01-24 05:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0057_retariffmastertable_average_savings_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='retariffmastertable',
            name='re_tariff',
            field=models.FloatField(),
        ),
    ]
