from rest_framework import serializers
from accounts.models import User
from energy.models import ConsumerRequirements, ESSPortfolio, GridTariff, HelpDeskQuery, MasterTable, NationalHoliday, PeakHours, RETariffMasterTable, SolarPortfolio, SubscriptionEnrolled, SubscriptionType, WindPortfolio
from energy.models import GeneratorQuotation

class ConsumerSerializer(serializers.ModelSerializer):
    subscription_type = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    duration_in_days = serializers.SerializerMethodField()
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        exclude = ['password']

    def _get_active_subscription(self, obj):
        # Assuming only one active subscription per user
        return obj.subscriptions.filter(status="active").first()

    def get_subscription_type(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.subscription.subscription_type if sub else None

    def get_price(self, obj):
        sub = self._get_active_subscription(obj)
        return str(sub.subscription.price) if sub else None

    def get_duration_in_days(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.subscription.duration_in_days if sub else None

    def get_start_date(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.start_date if sub else None

    def get_end_date(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.end_date if sub else None

    def get_status(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.status if sub else None

class SubscriptionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionType
        fields = '__all__'
        
class GeneratorSerializer(serializers.ModelSerializer):
    subscription_type = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    duration_in_days = serializers.SerializerMethodField()
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        exclude = ['password']

    def _get_active_subscription(self, obj):
        # Assuming only one active subscription per user
        return obj.subscriptions.filter(status="active").first()

    def get_subscription_type(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.subscription.subscription_type if sub else None

    def get_price(self, obj):
        sub = self._get_active_subscription(obj)
        return str(sub.subscription.price) if sub else None

    def get_duration_in_days(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.subscription.duration_in_days if sub else None

    def get_start_date(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.start_date if sub else None

    def get_end_date(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.end_date if sub else None

    def get_status(self, obj):
        sub = self._get_active_subscription(obj)
        return sub.status if sub else None
        
class GeneratorQuotationSerializer(serializers.ModelSerializer):
    consumer = ConsumerSerializer(source="rooftop_quotation.requirement.user", read_only=True)
    generator = GeneratorSerializer(read_only=True)

    class Meta:
        model = GeneratorQuotation
        fields = '__all__'


class ConsumerRequirementsUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumerRequirements
        exclude = ['user', 'state']

class HelpDeskQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpDeskQuery
        fields = '__all__'
        read_only_fields = ['user', 'query', 'date_time']

class MasterTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterTable
        fields = '__all__'


class RETariffMasterTableSerializer(serializers.ModelSerializer):
    class Meta:
        model = RETariffMasterTable
        fields = '__all__'


class GridTariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = GridTariff
        fields = '__all__'


class PeakHoursSerializer(serializers.ModelSerializer):
    peak_hours = serializers.SerializerMethodField()
    off_peak_hours = serializers.SerializerMethodField()

    class Meta:
        model = PeakHours
        fields = '__all__'

    def get_peak_hours(self, obj):
        return obj.calculate_peak_hours()

    def get_off_peak_hours(self, obj):
        return obj.calculate_off_peak_hours()


class NationalHolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = NationalHoliday
        fields = '__all__'

class SolarPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )

    class Meta:
        model = SolarPortfolio
        fields = ['id', 'user', 'state', 'connectivity', 'site_name', 'available_capacity', 'cod',
                  'total_install_capacity', 'hourly_data', 'annual_generation_potential', 'updated', 'banking_available'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'hourly_data': {'required': False},
            'annual_generation_potential': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
            'banking_available': {'required': False},
        }

class WindPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )

    class Meta:
        model = WindPortfolio
        fields = ['id', 'user', 'state', 'connectivity', 'site_name', 'available_capacity', 'cod',
                  'total_install_capacity', 'hourly_data', 'annual_generation_potential', 'updated', 'banking_available'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'hourly_data': {'required': False},
            'annual_generation_potential': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
            'banking_available': {'required': False},
        }
    
class ESSPortfolioSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field='id'  # Map the user field to the email field
    )
    class Meta:
        model = ESSPortfolio
        fields = ['id', 'user', 'state', 'connectivity', 'site_name', 'available_capacity', 'cod',
                  'total_install_capacity', 'efficiency_of_storage', 'efficiency_of_dispatch', 'updated'] 
        extra_kwargs = {
            'total_install_capacity': {'required': False},
            'efficiency_of_storage': {'required': False},
            'efficiency_of_dispatch': {'required': False},
            'updated': {'read_only': True},  # Prevent manual update of this field
        }