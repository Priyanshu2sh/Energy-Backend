from django.db import models
from django.contrib.auth.models import Group, Permission, AbstractUser, PermissionsMixin, BaseUserManager
from energy.models import State
from django.conf import settings
from django.utils.timezone import now
from datetime import timedelta

# Create your models here.
class UserManager(BaseUserManager):

    def _create_user(self, email, password, is_staff, is_superuser, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        if not password:
            raise ValueError('Password is not provided')
        
        user = self.model(
            email=self.normalize_email(email),
            is_staff=is_staff,
            is_active=True,
            is_superuser=is_superuser,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password, **extra_fields):
        return self._create_user(email, password, False, False, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        user = self._create_user(email, password, True, True, **extra_fields)
        return user


class User(AbstractUser, PermissionsMixin):
    industry_choices = [
    ("Residential", "Residential"),
    ("Commercial", "Commercial"),
    ("Industrial", "Industrial"),
    ("Agriculture", "Agriculture"),
    ("Transportation", "Transportation"),
    ("Healthcare", "Healthcare"),
    ("Telecommunications", "Telecommunications"),
    ("Education", "Education"),
    ("Government & Public Services", "Government & Public Services"),
    ("Entertainment", "Entertainment")
    ]

    user_category_choices = [
    ("Consumer", "Consumer"),
    ("Generator", "Generator"),
    ]
    
    # Adding additional columns
    email = models.EmailField(max_length=254, unique=True)
    name = models.CharField(max_length=254, blank=True, null=True)
    user_category = models.CharField(max_length=255, choices= user_category_choices, blank=True, null=True)
    industry = models.CharField(max_length=255, choices= industry_choices, blank=True, null=True)
    company = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    other_phone = models.CharField(max_length=20, blank=True, null=True)
    city_name = models.CharField(max_length=100, blank=True, null=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)  # Link to the State model
    country = models.CharField(max_length=100, blank=True, null=True)
    pin = models.CharField(max_length=20, blank=True, null=True)
    web = models.URLField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')], blank=True, null=True)
    dob = models.DateField(blank=True, null=True)

    # Define custom related names for groups and user_permissions
    groups = models.ManyToManyField(Group, related_name='custom_user_set', blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name='custom_user_permissions', blank=True)

    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
    
class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        return now() < self.created_at + timedelta(minutes=5)  # OTP valid for 5 minutes
