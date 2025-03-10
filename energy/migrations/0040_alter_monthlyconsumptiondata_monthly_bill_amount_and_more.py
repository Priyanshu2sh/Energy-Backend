# Generated by Django 4.2.10 on 2025-01-16 11:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0039_consumerrequirements_site_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='monthlyconsumptiondata',
            name='monthly_bill_amount',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='monthlyconsumptiondata',
            name='monthly_consumption',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='monthlyconsumptiondata',
            name='off_peak_consumption',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='monthlyconsumptiondata',
            name='peak_consumption',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
