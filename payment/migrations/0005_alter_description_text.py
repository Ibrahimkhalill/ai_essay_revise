# Generated by Django 5.1.6 on 2025-04-24 12:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment', '0004_remove_subscriptionplan_descriptions_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='description',
            name='text',
            field=models.CharField(max_length=500),
        ),
    ]
