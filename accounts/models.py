from django.db import models
from django.contrib.auth.models import Group, Permission, AbstractUser, PermissionsMixin, BaseUserManager
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
    user_category_choices = [
    ("Consumer", "Consumer"),
    ("Generator", "Generator"),
    ]

    role_choices = [
        ("Admin", "Admin"),
        ("Management", "Management"),
        ("Edit", "Edit"),
        ("View", "View"),
    ]
    
    deleted = models.BooleanField(default=False)
    # Adding additional columns
    email = models.EmailField(max_length=254, unique=True)
    user_category = models.CharField(max_length=255, choices= user_category_choices, blank=True, null=True)
    role = models.CharField(max_length=50, choices=role_choices, blank=True, null=True, default='Admin')  # Role within Consumer category
    company = models.CharField(max_length=255, blank=True, null=True)
    company_representative = models.CharField(max_length=255, blank=True, null=True)
    cin_number = models.CharField(max_length=255, blank=True, null=True)
    designation = models.CharField(max_length=50, blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)
    email_otp = models.CharField(max_length=6, blank=True, null=True)  # Email OTP for Consumer users
    mobile_otp = models.CharField(max_length=6, blank=True, null=True)  # Mobile OTP for Consumer users
    verified_at = models.DateTimeField(blank=True, null=True)  # Verification timestamp
    is_new_user = models.BooleanField(default=True)  # Assume user is new by default
    re_index = models.CharField(max_length=255, blank=True, null=True)
    elite_generator = models.BooleanField(default=False)
    credit_rating = models.CharField(max_length=255, blank=True, null=True)
    credit_rating_proof = models.FileField(upload_to='credit_rating_proofs/', blank=True, null=True)
    last_visited_page = models.CharField(max_length=255, null=True, blank=True)
    selected_requirement_id = models.IntegerField(null=True, blank=True)
    registration_token = models.CharField(max_length=64, blank=True, null=True)  # Token for password setup
    # Self-referential field for hierarchical relationships
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, blank=True, null=True, related_name="children")
    solar_template_downloaded = models.BooleanField(default=True)
    wind_template_downloaded = models.BooleanField(default=True)

    # Define custom related names for groups and user_permissions
    groups = models.ManyToManyField(Group, related_name='custom_user_set', blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name='custom_user_permissions', blank=True)

    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
    
class GeneratorConsumerMapping(models.Model):
    generator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generator_mappings')
    consumer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='consumer_mappings')
    mapped_username = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return f"{self.generator.username} -> {self.mapped_username}"
