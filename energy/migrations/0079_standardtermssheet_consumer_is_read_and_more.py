# Generated by Django 4.2.10 on 2025-02-20 05:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0078_alter_performainvoice_due_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='standardtermssheet',
            name='consumer_is_read',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='standardtermssheet',
            name='generator_is_read',
            field=models.BooleanField(default=False),
        ),
    ]
