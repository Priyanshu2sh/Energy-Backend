# Generated by Django 4.2.10 on 2025-02-18 10:15

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0076_alter_standardtermssheet_consumer_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='notifications',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='performainvoice',
            name='due_date',
            field=models.DateField(default=datetime.date(2025, 2, 28), verbose_name='Due Date'),
        ),
        migrations.AlterField(
            model_name='standardtermssheet',
            name='consumer_status',
            field=models.CharField(choices=[('Offer Sent', 'Offer Sent'), ('Offer Received', 'Offer Received'), ('Counter Offer Sent', 'Counter Offer Sent'), ('Counter Offer Received', 'Counter Offer Received'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected')], default='Offer Sent', help_text="Status from the consumer's perspective", max_length=100),
        ),
        migrations.AlterField(
            model_name='standardtermssheet',
            name='generator_status',
            field=models.CharField(choices=[('Offer Sent', 'Offer Sent'), ('Offer Received', 'Offer Received'), ('Counter Offer Sent', 'Counter Offer Sent'), ('Counter Offer Received', 'Counter Offer Received'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected')], default='Offer Sent', help_text="Status from the generator's perspective", max_length=100),
        ),
    ]
