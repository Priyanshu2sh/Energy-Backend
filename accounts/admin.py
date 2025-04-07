from django.contrib import admin
from .models import User, GeneratorConsumerMapping
# from django.contrib.auth.admin import UserAdmin
# Register your models here.
admin.site.register(User)
admin.site.register(GeneratorConsumerMapping)