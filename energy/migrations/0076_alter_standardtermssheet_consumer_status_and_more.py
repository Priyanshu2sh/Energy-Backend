# Generated by Django 4.2.10 on 2025-02-17 12:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('energy', '0075_alter_industry_name_alter_performainvoice_due_date_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='standardtermssheet',
            name='consumer_status',
            field=models.CharField(choices=[('Offer Sent', 'Offer Sent'), ('Offer Received', 'Offer Received'), ('Counter Offer Sent', 'Counter Offer Sent'), ('Counter Offer Received', 'Counter Offer Received'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected')], default='Counter Offer Sent', help_text="Status from the consumer's perspective", max_length=100),
        ),
        migrations.AlterField(
            model_name='standardtermssheet',
            name='generator_status',
            field=models.CharField(choices=[('Offer Sent', 'Offer Sent'), ('Offer Received', 'Offer Received'), ('Counter Offer Sent', 'Counter Offer Sent'), ('Counter Offer Received', 'Counter Offer Received'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected')], default='Counter Offer Sent', help_text="Status from the generator's perspective", max_length=100),
        ),
    ]
