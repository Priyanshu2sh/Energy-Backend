from rest_framework import serializers
from .models import EnergyProfiles

class EnergyProfilesSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnergyProfiles
        fields = ['user', 'energy_type', 'state', 'capacity', 'unit', 'cod']
