import calendar
from calendar import monthrange
from itertools import chain
from django.shortcuts import get_object_or_404
from accounts.models import User
from accounts.views import JWTAuthentication
from .models import SolarPortfolio, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, HourlyDemand, Combination, StandardTermsSheet, MatchingIPP
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from .serializers import SolarPortfolioSerializer, WindPortfolioSerializer, ESSPortfolioSerializer, ConsumerRequirementsSerializer, MonthlyConsumptionDataSerializer, StandardTermsSheetSerializer
from django.core.mail import send_mail
import random
from django.contrib.auth.hashers import check_password
from django.utils.timezone import now
from datetime import datetime, timedelta
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from .aggregated_model.main import optimization_model
import pandas as pd
from itertools import product


# Create your views here.
class GenerationPortfolioAPI(APIView):
    def get_serializer_class(self, energy_type):
        """Return the appropriate serializer class based on the energy type."""
        if energy_type == "Solar":
            return SolarPortfolioSerializer
        elif energy_type == "Wind":
            return WindPortfolioSerializer
        elif energy_type == "ESS":
            return ESSPortfolioSerializer

    def get_model(self, energy_type):
        """Return the appropriate model class based on the energy type."""
        if energy_type == "Solar":
            return SolarPortfolio
        elif energy_type == "Wind":
            return WindPortfolio
        elif energy_type == "ESS":
            return ESSPortfolio

    def get(self, request, pk):
        try:
            user = User.objects.get(id=pk)
            # Query all portfolio models
            solar_data = SolarPortfolio.objects.filter(user=user)
            wind_data = WindPortfolio.objects.filter(user=user)
            ess_data = ESSPortfolio.objects.filter(user=user)

            # Combine the queryset data
            combined_data = list(chain(solar_data, wind_data, ess_data))

            # Serialize the combined data
            response_data = {
                "Solar": SolarPortfolioSerializer(solar_data, many=True).data,
                "Wind": WindPortfolioSerializer(wind_data, many=True).data,
                "ESS": ESSPortfolioSerializer(ess_data, many=True).data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        # Determine the serializer and model based on `energy_type`
        energy_type = request.data.get("energy_type")
        if not energy_type:
            return Response({"error": "Energy type is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer_class = self.get_serializer_class(energy_type)
        serializer = serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        # Determine the serializer and model based on `energy_type`
        energy_type = request.data.get("energy_type")
        if not energy_type:
            return Response({"error": "Energy type is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        model = self.get_model(energy_type)
        instance = get_object_or_404(model, pk=pk)
        serializer_class = self.get_serializer_class(energy_type)
        serializer = serializer_class(instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConsumerRequirementsAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
   

    def get(self, request, pk):
        # Fetch energy profiles
        user = User.objects.get(id=pk)
        profiles = ConsumerRequirements.objects.filter(user=user)
        serializer = ConsumerRequirementsSerializer(profiles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Add a new energy profile
        serializer = ConsumerRequirementsSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class MonthlyConsumptionDataAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
   

    def get(self, request, pk):
        # Fetch energy profiles
        data = MonthlyConsumptionData.objects.filter(requirement__user=pk)
        serializer = MonthlyConsumptionDataSerializer(data, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Add a new energy profile
        serializer = MonthlyConsumptionDataSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class MatchingIPPAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        requirement_id = data.get("requirement_id")

        if not requirement_id:
            return Response(
                {"error": "Please provide requirement id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        

        try:
            # Fetch the requirement
            requirement = ConsumerRequirements.objects.get(id=requirement_id)

            # Filter the data
            # Query SolarPortfolio
            solar_data = SolarPortfolio.objects.filter(
                Q(state=requirement.state) & Q(cod__gte=requirement.procurement_date)
            ).values("user", "user__username", "state", "capacity")
        
            # Query WindPortfolio
            wind_data = WindPortfolio.objects.filter(
                Q(state=requirement.state) & Q(cod__gte=requirement.procurement_date)
            ).values("user", "user__username", "state", "capacity")
        
            # Query ESSPortfolio
            ess_data = ESSPortfolio.objects.filter(
                Q(state=requirement.state) & Q(cod__gte=requirement.procurement_date)
            ).values("user", "user__username", "state", "capacity")
        
            # Combine all data
            filtered_data = list(chain(solar_data, wind_data, ess_data))

            # Extract user IDs from the filtered data
            user_ids = set()
            for data_item in filtered_data:
                user_ids.add(data_item["user"])  # Add the user ID to the set to avoid duplicates

            user_ids_list = list(user_ids)
            print(user_ids_list)

            # Save the user IDs in MatchingIPP
            matching_ipp, created = MatchingIPP.objects.get_or_create(requirement=requirement)
            matching_ipp.generator_ids = user_ids_list
            matching_ipp.save()

            # Convert QuerySet to a list for JSON response
            response_data = list(filtered_data)

            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MatchingConsumerAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
    
    def post(self, request):
        data = request.data
        id = data.get("generator_id")
        user = User.objects.get(id=id)

        try:
            # Get all GenerationPortfolio records for the user
            # Query SolarPortfolio
            solar_data = SolarPortfolio.objects.filter(user=user)

            # Query WindPortfolio
            wind_data = WindPortfolio.objects.filter(user=user)

            # Query ESSPortfolio
            ess_data = ESSPortfolio.objects.filter(user=user)

            # Combine all data
            data = list(chain(solar_data, wind_data, ess_data))

            # Ensure generation portfolio exists
            if not (solar_data.exists() or wind_data.exists() or ess_data.exists()):
                return Response(
                    {"error": "No generation portfolio records found for the user."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Combine all states and CODs across all portfolios
            states = (
                solar_data.values_list("state", flat=True)
                .union(wind_data.values_list("state", flat=True))
                .union(ess_data.values_list("state", flat=True))
            )

            cod_dates = (
                solar_data.values_list("cod", flat=True)
                .union(wind_data.values_list("cod", flat=True))
                .union(ess_data.values_list("cod", flat=True))
            )

            # Filter ConsumerRequirements
            filtered_data = (
                ConsumerRequirements.objects.filter(
                    state__in=states,
                    procurement_date__gte=min(cod_dates),  # At least one COD <= procurement_date
                )
                .values("user__username", "state")
                .annotate(total_contracted_demand=Sum("contracted_demand"))
            )

            # Convert QuerySet to a list for JSON response
            response_data = list(filtered_data)

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OptimizeCapacityAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    @staticmethod
    def extract_profile_data(file_path, sheet):
                
        df=pd.read_excel(file_path, sheet_name=sheet)

        df_cleaned = df.drop(df.columns[0], axis=1)

        df_cleaned=df_cleaned[2:].reset_index(drop=True)


        # Set the first row as the column header for solar_df_cleaned
        df_cleaned.columns = df_cleaned.iloc[0]
        df_cleaned = df_cleaned[1:]  # Remove the first row (now the header)

        df_cleaned = df_cleaned.reset_index(drop=True)
        for column in df_cleaned.columns:
            profile = df_cleaned[column].fillna(0).reset_index(drop=True)  # Series of hourly data
                
        return profile
    
    @staticmethod
    
    def calculate_hourly_demand(consumer_requirement, state="MP"):
        consumer_demand = HourlyDemand.objects.get(requirement=consumer_requirement)

        # Define the state-specific hours
        state_hours = {
            "MP": {
                "peak_hours": (10, 14),  # 10 AM to 2 PM
                "off_peak_hours": (20, 24),  # 8 PM to 12 AM
            }
        }

        monthly_consumptions = MonthlyConsumptionData.objects.filter(requirement=consumer_requirement)

        # Get state-specific hours
        hours = state_hours[state]
        peak_hours = hours["peak_hours"]
        off_peak_hours = hours["off_peak_hours"]
        total_hours = 24
        normal_hours = total_hours - (peak_hours[1] - peak_hours[0]) - (off_peak_hours[1] - off_peak_hours[0])

        # Initialize a list to store hourly data
        all_hourly_data = []

        for month_data in monthly_consumptions:
            # Extract month details and convert month name to number
            month_name = month_data.month
            month_number = list(calendar.month_name).index(month_name)
            if month_number == 0:
                raise ValueError(f"Invalid month name: {month_name}")

            # Get the number of days in the month
            days_in_month = monthrange(2025, month_number)[-1]  # Update year dynamically

            # Calculate consumption values
            normal_consumption = month_data.monthly_consumption - (
                month_data.peak_consumption + month_data.off_peak_consumption
            )
            normal_hour_value = normal_consumption / (normal_hours * days_in_month)
            peak_hour_value = month_data.peak_consumption / ((peak_hours[1] - peak_hours[0]) * days_in_month)
            off_peak_hour_value = month_data.off_peak_consumption / ((off_peak_hours[1] - off_peak_hours[0]) * days_in_month)

            # Distribute values across the hours of each day
            for day in range(1, days_in_month + 1):
                for hour in range(24):
                    if peak_hours[0] <= hour < peak_hours[1]:
                        all_hourly_data.append(peak_hour_value)
                    elif off_peak_hours[0] <= hour < off_peak_hours[1]:
                        all_hourly_data.append(off_peak_hour_value)
                    else:
                        all_hourly_data.append(normal_hour_value)

        # Update the HourlyDemand model
        consumer_demand.set_hourly_data_from_list(all_hourly_data)
        consumer_demand.save()

        # Return the data in the desired flat format
        return pd.Series(all_hourly_data)

    def post(self, request):
        data = request.data
        optimize_capacity_user = data.get("optimize_capacity_user") #consumer or generator
        id = data.get("requirement_id")

        if data.get("re_replacement"):
            re_replacement = int(data.get("re_replacement"))
        else:
            re_replacement = None

        if re_replacement == 0:
            return Response({"message": "No available capacity."}, status=status.HTTP_200_OK)
        

         # Check optimize_capacity value
        if optimize_capacity_user == "consumer":
            generator_id = data.get("generator_id")  # Expecting a list of emails
        elif optimize_capacity_user == "generator":
            generator_id = data.get("generator_id")  # Expecting a single email
            generator_id = [generator_id]  # Normalize to a list for consistent processing
        else:
            return Response(
                {"error": "Invalid value for 'optimize_capacity'. Must be 'consumer' or 'generator'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Fetch consumer details
            # consumer = User.objects.get(email=consumer_email)
            consumer_requirement = ConsumerRequirements.objects.get(id=id)

            input_data = {}  # Initialize the final dictionary
            
            for id in generator_id:
                generator = User.objects.get(id=id)

                # Query generator's portfolios
                solar_data = SolarPortfolio.objects.filter(
                    user=generator,
                    state=consumer_requirement.state,
                    cod__lte=consumer_requirement.procurement_date,
                )
                wind_data = WindPortfolio.objects.filter(
                    user=generator,
                    state=consumer_requirement.state,   
                    cod__lte=consumer_requirement.procurement_date,
                )
                ess_data = ESSPortfolio.objects.filter(
                    user=generator,
                    state=consumer_requirement.state,
                    cod__lte=consumer_requirement.procurement_date,
                )

                solar_project = []
                wind_project = []
                ess_project = []

                # Initialize data for the current generator
                input_data[generator.username] = {}

                # Add Solar projects if solar_data exists
                if solar_data.exists():
                    input_data[generator.username]["Solar"] = {}
                    for solar in solar_data:

                        solar_project.append(solar.project)

                        # Extract profile data from file
                        profile_data = self.extract_profile_data(solar.hourly_data.path, 'Solar')

                        input_data[generator.username]["Solar"][solar.project] = {
                            "profile": profile_data,
                            "max_capacity": solar.capacity,
                            "marginal_cost": solar.marginal_cost,
                            "capital_cost": solar.capital_cost,
                        }

                # Add Wind projects if wind_data exists
                if wind_data.exists():
                    input_data[generator.username]["Wind"] = {}
                    for wind in wind_data:

                        wind_project.append(wind.project)

                        # Extract profile data from file
                        profile_data = self.extract_profile_data(wind.hourly_data.path, 'Wind')

                        input_data[generator.username]["Wind"][wind.project] = {
                            "profile": profile_data,
                            "max_capacity": solar.capacity,
                            "marginal_cost": wind.marginal_cost,
                            "capital_cost": wind.capital_cost,
                        }

                # Add ESS projects if ess_data exists
                if ess_data.exists():
                    input_data[generator.username]["ESS"] = {}
                    for ess in ess_data:

                        ess_project.append(ess.project)

                        input_data[generator.username]["ESS"][ess.project] = {
                            "DoD": ess.efficiency_of_dispatch,
                            "efficiency": ess.efficiency_of_dispatch,
                            "marginal_cost": ess.marginal_cost,
                            "capital_cost": ess.capital_cost,
                        }

            # print(input_data)
            # Extract generator name and project lists
            # gen = next(iter(input_data.keys()))
            # solar_projects = list(input_data[gen]['Solar'].keys())
            # wind_projects = list(input_data[gen]['Wind'].keys())
            # ess_projects = list(input_data[gen]['ESS'].keys())
            # # Generate all combinations
            # combinations = [
            #     f"{gen}-{solar}-{wind}-{ess}"
            #     for solar, wind, ess in product(solar_projects, wind_projects, ess_projects)
            # ]
            # print(combinations)
            # for combo in combinations:
            #     combination = Combination.objects.filter(requirement=consumer_requirement, combination=combo).first()
            #     if combination is not None:
            #         # combination = dict(combination)
            #         print("combo= ", combo)
            #         print(True)
            #     else:
            #         print("combo= ", combo)
            #         print(False)
            # return Response(combinations, status=status.HTTP_200_OK)


            consumer_demand = HourlyDemand.objects.get(requirement=consumer_requirement)
            
            # monthly data conversion in hourly data
            if not consumer_demand.bulk_file:
                hourly_demand = self.calculate_hourly_demand(consumer_requirement)
                response_data = optimization_model(input_data, hourly_demand=hourly_demand, re_replacement=re_replacement)
            else:
                consumer_demand_path = consumer_demand.bulk_file.path
                response_data = optimization_model(input_data, consumer_demand_path=consumer_demand_path, re_replacement=re_replacement)
                

            updated_response = {}

            for combination_key, details in response_data.items():
            # Extract user and components from combination_key
                components = combination_key.split('-')
                username = components[0]  # Example: 'IPP585'
                solar_component = components[1]  # Example: 'Solar_1'
                wind_component = components[2]  # Example: 'Wind_1'
                ess_component = components[3]  # Example: 'ESS_1'

                generator = User.objects.get(username=username)

                # Find maximum capacities and corresponding states
                solar = SolarPortfolio.objects.get(user__username=username, project=solar_component)
                wind = WindPortfolio.objects.get(user__username=username, project=wind_component)
                ess = ESSPortfolio.objects.get(user__username=username, project=ess_component)

                if solar.capacity > wind.capacity and solar.capacity > ess.capacity:
                    state = solar.state
                elif wind.capacity > solar.capacity and wind.capacity > ess.capacity:
                    state = wind.state
                elif ess.capacity > solar.capacity and ess.capacity > wind.capacity:
                    state = ess.state


                # Save to Combination table
                Combination.objects.create(
                    requirement=consumer_requirement,
                    generator=generator,
                    combination=combination_key,
                    state=state,
                    optimal_solar_capacity=details["Optimal Solar Capacity (MW)"],
                    optimal_wind_capacity=details["Optimal Wind Capacity (MW)"],
                    optimal_battery_capacity=details["Optimal Battery Capacity (MW)"],
                    per_unit_cost=details["Per Unit Cost"],
                    final_cost=details["Final Cost"],
                    annual_demand_offset=details["Annual Demand Offset"],
                    annual_curtailment=details["Annual Curtailment:"]
                )

                # Update response dictionary
                updated_response[combination_key] = {
                    **details,
                    "state": state
                }
            
            return Response(updated_response, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({"error": "Consumer or generator not found."}, status=status.HTTP_404_NOT_FOUND)

        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Consumer requirements not found."}, status=status.HTTP_404_NOT_FOUND)

        # except Exception as e:
        #     return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class ConsumptionPatternAPI(APIView):
    def get(self, request, pk):
        try:
            
            # Fetch MonthlyConsumptionData for the consumer
            consumption_data = MonthlyConsumptionData.objects.filter(user=pk).values('month', 'monthly_consumption')

            # Check if consumption data exists
            if not consumption_data.exists():
                return Response(
                    {"error": "No consumption data found for the consumer."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Create a response with the monthly consumption data
            response_data = {
                "monthly_consumption": [
                    {
                        "month": entry["month"], 
                        "consumption": entry["monthly_consumption"]
                    } 
                    for entry in consumption_data
                ]
            }


            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class StandardTermsSheetAPI(APIView):
    def get(self, request, pk=None):
        if pk:
            try:
                record = StandardTermsSheet.objects.filter(consumer=pk).first() or StandardTermsSheet.objects.filter(generator=pk).first()
                if record is None:
                    return Response({"error": "Record not found."}, status=status.HTTP_404_NOT_FOUND)
                serializer = StandardTermsSheetSerializer(record)
                return Response(serializer.data, status=status.HTTP_200_OK)
            except StandardTermsSheet.DoesNotExist:
                return Response({"error": "Record not found."}, status=status.HTTP_404_NOT_FOUND)
        records = StandardTermsSheet.objects.all()
        serializer = StandardTermsSheetSerializer(records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = StandardTermsSheetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        try:
            record = StandardTermsSheet.objects.get(pk=pk)
            if record.count >= 4:
                return Response(
                    {"error": "Update limit reached. This record cannot be updated further."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer = StandardTermsSheetSerializer(record, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                record.count += 1  # Increment the count on successful update
                record.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except StandardTermsSheet.DoesNotExist:
            return Response({"error": "Record not found."}, status=status.HTTP_404_NOT_FOUND)
        

