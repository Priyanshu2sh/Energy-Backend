from rest_framework import serializers
from accounts.models import User
from energy.models import ConsumerRequirements, GridTariff, HelpDeskQuery, MasterTable, NationalHoliday, PeakHours, RETariffMasterTable, SubscriptionType

class ConsumerSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['id', 'company_representative', 'company', 'email', 'mobile', 'is_active']

class GeneratorSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['id', 'company_representative', 'company', 'email', 'mobile', 'is_active']
        
class SubscriptionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionType
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