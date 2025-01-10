import base64
import calendar
from calendar import monthrange
from itertools import chain
import re
from django.shortcuts import get_object_or_404
import pytz
from accounts.models import User
from accounts.views import JWTAuthentication
from .models import GeneratorOffer, GridTariff, SolarPortfolio, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, HourlyDemand, Combination, StandardTermsSheet, MatchingIPP, SubscriptionType, SubscriptionEnrolled, Notifications, Tariffs, NegotiationWindow, MasterTable
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from .serializers import SolarPortfolioSerializer, WindPortfolioSerializer, ESSPortfolioSerializer, ConsumerRequirementsSerializer, MonthlyConsumptionDataSerializer, StandardTermsSheetSerializer, SubscriptionTypeSerializer, SubscriptionEnrolledSerializer, NotificationsSerializer, TariffsSerializer
from django.core.mail import send_mail
import random
from django.contrib.auth.hashers import check_password
from django.utils.timezone import make_aware, now
from datetime import datetime, timedelta, time
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from .aggregated_model.main import optimization_model
from django.core.files.base import ContentFile
import pandas as pd
from itertools import product
from django.utils import timezone

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

            # Get the user associated with the saved data (assuming it's passed in the request)
            user_id = request.data.get('user')  # Assuming user is passed in the request body
            if user_id:
                user = get_object_or_404(User, id=user_id)  # Get the user object

                # Update the user's `is_new_user` field to False after saving the data
                user.is_new_user = False
                user.save()
                # Include energy_type in the response
                response_data = serializer.data
                response_data["energy_type"] = energy_type
            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        # Determine the serializer and model based on `energy_type`
        energy_type = request.data.get("energy_type")
        if not energy_type:
            return Response({"error": "Energy type is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        model = self.get_model(energy_type)
        instance = get_object_or_404(model, pk=pk)
        serializer_class = self.get_serializer_class(energy_type)

        # Handle Base64-encoded file
        file_data = request.data.get("hourly_data")
        if file_data:
            try:
                # Decode Base64 file
                decoded_file = base64.b64decode(file_data)
                # Define a file name (customize as needed)
                file_name = f"hourly_data_{pk}.xlsx"  # Assuming the file is an Excel file
                # Wrap the decoded file into ContentFile
                request.data["hourly_data"] = ContentFile(decoded_file, name=file_name)
            except Exception as e:
                return Response({"error": f"Invalid Base64 file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = serializer_class(instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            response_data = serializer.data
            response_data['energy_type'] = energy_type
            return Response(response_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        # Determine the model based on `energy_type`
        energy_type = request.data.get("energy_type")
        if not energy_type:
            return Response({"error": "Energy type is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        model = self.get_model(energy_type)
        instance = get_object_or_404(model, pk=pk)
        instance.delete()
        return Response({"message": f"{energy_type} portfolio record deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


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

            # Get the user associated with the saved data (assuming it's passed in the request)
            user_id = request.data.get('user')  # Assuming user is passed in the request body
            if user_id:
                user = get_object_or_404(User, id=user_id)  # Get the user object

                # Update the user's `is_new_user` field to False after saving the data
                user.is_new_user = False
                user.save()
                
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        # Update an existing energy profile
        instance = get_object_or_404(ConsumerRequirements, id=pk)
        serializer = ConsumerRequirementsSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        # Delete an energy profile
        instance = get_object_or_404(ConsumerRequirements, id=pk)
        instance.delete()
        return Response({"message": "Profile deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
    
class MonthlyConsumptionDataAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
   

    def get(self, request, pk):
        # Fetch energy profiles
        data = MonthlyConsumptionData.objects.filter(requirement=pk)
        serializer = MonthlyConsumptionDataSerializer(data, many=True)

        # Extract the serialized data
        serialized_data = serializer.data

        # Sort the data by the month field (assuming full month names)
        try:
            sorted_data = sorted(
                serialized_data, 
                key=lambda x: datetime.strptime(x['month'], '%B')
            )
        except KeyError:
            return Response({"error": "Missing 'month' key in data"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"error": "Invalid month format in data"}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(sorted_data, status=status.HTTP_200_OK)

    def post(self, request):
        # Add a new energy profile
        serializer = MonthlyConsumptionDataSerializer(data=request.data, many=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        # Update an existing consumption record
        instance = get_object_or_404(MonthlyConsumptionData, id=pk)
        serializer = MonthlyConsumptionDataSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        # Delete a consumption record
        instance = get_object_or_404(MonthlyConsumptionData, pk=pk)
        instance.delete()
        return Response({"message": "Record deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

class MatchingIPPAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        try:
            # Fetch the requirement
            requirement = ConsumerRequirements.objects.get(id=pk)

            # Filter the data
            # Query SolarPortfolio
            solar_data = SolarPortfolio.objects.filter(
                Q(state=requirement.state) & Q(cod__gte=requirement.procurement_date)
            ).values("user", "user__username", "state", "available_capacity")
        
            # Query WindPortfolio
            wind_data = WindPortfolio.objects.filter(
                Q(state=requirement.state) & Q(cod__gte=requirement.procurement_date)
            ).values("user", "user__username", "state", "available_capacity")
        
            # Query ESSPortfolio
            ess_data = ESSPortfolio.objects.filter(
                Q(state=requirement.state) & Q(cod__gte=requirement.procurement_date)
            ).values("user", "user__username", "state", "available_capacity")
        
            # Combine all data
            combined_data = list(chain(solar_data, wind_data, ess_data))

            # Use a dictionary to store unique users with the highest capacity
            unique_users = {}
            for entry in combined_data:
                user_id = entry["user"]
                if user_id not in unique_users or entry["available_capacity"] > unique_users[user_id]["available_capacity"]:
                    unique_users[user_id] = entry

            # Extract the unique entries and sort by capacity in descending order
            unique_data = list(unique_users.values())
            sorted_data = sorted(unique_data, key=lambda x: x["available_capacity"], reverse=True)

            # Get only the top 3 matches
            top_three_matches = sorted_data[:3]

            # Extract user IDs from the top three matches
            user_ids = [match["user"] for match in top_three_matches]

            # Save the user IDs in MatchingIPP
            matching_ipp, created = MatchingIPP.objects.get_or_create(requirement=requirement)
            matching_ipp.generator_ids = user_ids
            matching_ipp.save()

            # Return the top three matches as the response
            return Response(top_three_matches, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MatchingConsumerAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        user = User.objects.get(id=pk)

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
            )
            
            # Check for subscription and notify consumers without a subscription
            consumers_without_subscription = []
            for requirement in filtered_data:
                
                if not SubscriptionEnrolled.objects.filter(user=requirement.user, status='active').exists():

                    # Add the consumer to the notification list
                    consumers_without_subscription.append(requirement.user)

                    # Send a notification (customize this part as per your notification system)
                    Notifications.objects.create(
                        user=requirement.user,
                        message="Please activate your subscription to access matching services."
                    )

            # Exclude consumers without a subscription from the response
            filtered_data = filtered_data.exclude(user__in=consumers_without_subscription)

            # Annotate and prepare the final response
            response_data = (
                filtered_data.values("id", "user__username", "state", "industry")
                .annotate(total_contracted_demand=Sum("contracted_demand"))
            )

            # Convert QuerySet to a list for JSON response
            return Response(list(response_data), status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PortfolioUpdateStatusView(APIView):

    def get(self, request, user_id):
        try:
            # Fetch records for the given user in all three models
            solar_records = SolarPortfolio.objects.filter(user_id=user_id)
            wind_records = WindPortfolio.objects.filter(user_id=user_id)
            ess_records = ESSPortfolio.objects.filter(user_id=user_id)

            # Combine all records into a single list
            all_records = list(solar_records) + list(wind_records) + list(ess_records)

            # Check if any record is not updated
            all_updated = all(record.updated for record in all_records)

            return Response({
                "user_id": user_id,
                "all_updated": all_updated
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "error": "An error occurred.",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            new_list = []
            
            for id in generator_id:
                generator = User.objects.get(id=id)
                
                if optimize_capacity_user == "consumer":
                    
                    if not SubscriptionEnrolled.objects.filter(user=generator, status='active').exists():
                        message = "You have not subscribed yet. Please subscribe so that you don't miss the perfect matchings."
                        notification = Notifications(user=generator, message=message)
                        notification.save()
                        new_list.append(id)
                        continue


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
                            "max_capacity": solar.available_capacity,
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
                            "max_capacity": wind.available_capacity,
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

            print(input_data)
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

            if new_list != generator_id:

                consumer_demand = HourlyDemand.objects.get(requirement=consumer_requirement)

                # monthly data conversion in hourly data
                if not consumer_demand.bulk_file:
                    hourly_demand = self.calculate_hourly_demand(consumer_requirement)
                    response_data = optimization_model(input_data, hourly_demand=hourly_demand, re_replacement=re_replacement)
                else:
                    consumer_demand_path = consumer_demand.bulk_file.path
                    response_data = optimization_model(input_data, consumer_demand_path=consumer_demand_path, re_replacement=re_replacement)
                
                if response_data == 'The demand cannot be met by the IPPs' and optimize_capacity_user=='consumer':
                    return Response({"response": "The demand cannot be met by the IPPs."}, status=status.HTTP_200_OK)
                if response_data == 'The demand cannot be met by the IPPs' and optimize_capacity_user=='generator':
                    return Response({"response": "The demand cannot be made by your projects."}, status=status.HTTP_200_OK)

                updated_response = {}

                for combination_key, details in response_data.items():
                # Extract user and components from combination_key
                    components = combination_key.split('-')

                    # Safely extract components, ensuring that we have enough elements
                    username = components[0] if len(components) > 0 else None  # Example: 'IPP241'
                    component_1 = components[1] if len(components) > 1 else None  # Example: 'Solar_1' (if present)
                    component_2 = components[2] if len(components) > 2 else None  # Example: 'Wind_1' (if present)
                    component_3 = components[3] if len(components) > 3 else None  # Example: 'ESS_1' (if present)

                    generator = User.objects.get(username=username)

                    solar = wind = ess = None

                    # Helper function to fetch the component and its COD
                    def get_component_and_cod(component_name, generator, portfolio_model):
                        try:
                            portfolio = portfolio_model.objects.get(user=generator, project=component_name)
                            return portfolio, portfolio.cod
                        except portfolio_model.DoesNotExist:
                            return None, None

                    # Fetch solar, wind, and ESS components and their CODs
                    if component_1:
                        if 'Solar' in component_1:
                            solar, solar_cod = get_component_and_cod(component_1, generator, SolarPortfolio)
                        elif 'Wind' in component_1:
                            wind, wind_cod = get_component_and_cod(component_1, generator, WindPortfolio)
                        elif 'ESS' in component_1:
                            ess, ess_cod = get_component_and_cod(component_1, generator, ESSPortfolio)

                    if component_2:
                        if 'Wind' in component_2:
                            wind, wind_cod = get_component_and_cod(component_2, generator, WindPortfolio)
                        elif 'ESS' in component_2:
                            ess, ess_cod = get_component_and_cod(component_2, generator, ESSPortfolio)

                    if component_3:
                        if 'ESS' in component_3:
                            ess, ess_cod = get_component_and_cod(component_3, generator, ESSPortfolio)

                    # Determine the greatest COD
                    cod_dates = [solar_cod if solar else None, wind_cod if wind else None, ess_cod if ess else None]
                    cod_dates = [date for date in cod_dates if date is not None]
                    greatest_cod = max(cod_dates) if cod_dates else None

                    if solar and wind and ess:
                        if solar.available_capacity > wind.available_capacity and solar.available_capacity > ess.available_capacity:
                            state = solar.state
                        elif wind.available_capacity > solar.available_capacity and wind.available_capacity > ess.available_capacity:
                            state = wind.state
                        elif ess.available_capacity > solar.available_capacity and ess.available_capacity > wind.available_capacity:
                            state = ess.state
                    elif solar and wind:
                        state = solar.state if solar.available_capacity > wind.available_capacity else wind.state
                    elif wind and ess:
                        state = wind.state if wind.available_capacity > ess.available_capacity else ess.state
                    elif solar and ess:
                        state = solar.state if solar.available_capacity > ess.available_capacity else ess.state
                    elif solar:
                        state = solar.state
                    elif wind:
                        state = wind.state
                    elif ess:
                        state = ess.state
                    
                    terms_sheet_sent = True
                    combo = Combination.objects.filter(combination=combination_key).first()
                    if combo:
                        terms_sheet_sent = combo.terms_sheet_sent
                        print('terms_sheet_sent====')
                        print('terms_sheet_sent====')
                    else:
                        # Save to Combination table
                        Combination.objects.get_or_create(
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
                        "state": state,
                        "greatest_cod": greatest_cod,
                        "terms_sheet_sent": terms_sheet_sent
                    }
                    print(updated_response)
                    # Extract top 3 records with the smallest "Per Unit Cost"
                    top_three_records = sorted(updated_response.items(), key=lambda x: x[1]['Per Unit Cost'])[:3]

                    # Function to round values to 2 decimal places
                    def round_values(record):
                        return {key: round(value, 2) if isinstance(value, (int, float)) else value for key, value in record.items()}

                    # Round the values for the top 3 records
                    top_three_records_rounded = {
                        key: round_values(value) for key, value in top_three_records
                    }   
                    print(top_three_records_rounded)

                return Response(top_three_records_rounded, status=status.HTTP_200_OK)
            else:
                return Response({"response": "No IPPs matched"}, status=status.HTTP_200_OK)


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
            consumption_data = MonthlyConsumptionData.objects.filter(requirement=pk).values('month', 'monthly_consumption')

            # Check if consumption data exists
            if not consumption_data.exists():
                return Response(
                    {"error": "No consumption data found for the consumer."},
                    status=status.HTTP_404_NOT_FOUND
                )
            # Convert the month data to sorted month names (e.g., "Jan", "Feb", "Mar", ...)
            sorted_data = sorted(consumption_data, key=lambda x: datetime.strptime(x['month'], '%B'))

            # Prepare response with the sorted monthly consumption data
            response_data = {
                "monthly_consumption": [
                    {
                        "month": datetime.strptime(entry["month"], '%B').strftime('%b'),  # Convert to short month name (e.g., Jan, Feb)
                        "consumption": entry["monthly_consumption"]
                    }
                    for entry in sorted_data
                ]
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class StandardTermsSheetAPI(APIView):

    def get(self, request, pk, from_whom):
        if pk and from_whom:
            user = User.objects.get(id=pk)
            try:
                if user.user_category == 'Consumer':
                    if from_whom == 'Consumer':
                        record = StandardTermsSheet.objects.filter(consumer=user, from_whom ='Consumer').first()
                    else:
                        record = StandardTermsSheet.objects.filter(consumer=user, from_whom ='Generator').first()
                else:
                    if request.data.get('from_whom') == 'Consumer':
                        record = StandardTermsSheet.objects.filter(combination__generator=user, from_whom ='Consumer').first()
                    else:
                        record = StandardTermsSheet.objects.filter(combination__generator=user, from_whom ='Generator').first()
                        
                if record is None:
                    return Response({"error": "Record not found."}, status=status.HTTP_404_NOT_FOUND)

                serializer = StandardTermsSheetSerializer(record)
                return Response(serializer.data, status=status.HTTP_200_OK)

            except StandardTermsSheet.DoesNotExist:
                return Response({"error": "Record not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"error": "Please send valid values of user id and category."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        # Extract requirement_id from the request data
        requirement_id = request.data.get("requirement_id")
        from_whom = request.data.get("from_whom")

        if from_whom not in ['Consumer', 'Generator']:
            return Response({"error": "Invalid value for 'from_whom'."}, status=status.HTTP_400_BAD_REQUEST)


        if not requirement_id:
            return Response({"error": "requirement_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        requirement = ConsumerRequirements.objects.get(id=requirement_id)

        if StandardTermsSheet.objects.filter(combination__requirement=requirement, combination__combination=request.data.get('combination')):
            return Response({"error": "The term sheet is already sent to the consumer for this combination."}, status=status.HTTP_400_BAD_REQUEST)

        # Add consumer and combination to the request data
        request_data = request.data.copy()
        request_data["consumer"] = requirement.user.id  # Set consumer ID

        c = Combination.objects.filter(combination=request.data.get('combination')).order_by('-id').first()
        request_data["combination"] = c.id


        serializer = StandardTermsSheetSerializer(data=request_data)
        if serializer.is_valid():
            # Save the termsheet
            termsheet = serializer.save()
            c.terms_sheet_sent = True
            c.save()

            if from_whom == "Consumer":
                Notifications.objects.get_or_create(user=termsheet.combination.generator, message=f'The consumer {termsheet.consumer.username} has sent you a terms sheet.')
            elif from_whom == "Generator":
                Notifications.objects.get_or_create(user=termsheet.consumer, message=f'The generator {termsheet.combination.generator.username} has sent you a terms sheet.')
            else:
                return Response({"error": "Invalid value for 'from_whom'."}, status=status.HTTP_400_BAD_REQUEST)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, user_id, pk):
        try:
            user = User.objects.get(id=user_id)
            record = StandardTermsSheet.objects.get(id=pk)
            action = request.data.get("action")  # Check for an 'action' key in the request payload

            if action in ['Accepted', 'Rejected']:
                record.consumer_status = action
                record.generator_status = action

                record.save()
                return Response(
                    {"message": f"Terms sheet {action.lower()}ed successfully.", "record": StandardTermsSheetSerializer(record).data},
                    status=status.HTTP_200_OK,
                )

            # Check if the update limit has been reached
            if record.count >= 4:
                # Check if a Tariffs record already exists for this StandardTermsSheet
                tariffs_instance = Tariffs.objects.filter(terms_sheet=record).first()

                if tariffs_instance:
                    # Update the existing Tariffs record
                    tariffs_serializer = TariffsSerializer(
                        tariffs_instance, data=request.data, partial=True
                    )
                    if tariffs_serializer.is_valid():
                        tariffs_serializer.save()
                        return Response(
                            {
                                "message": "Update limit reached. Existing Tariff record updated.",
                                "tariff_record": tariffs_serializer.data,
                            },
                            status=status.HTTP_200_OK,
                        )
                    return Response(
                        {"error": "Failed to update Tariff record.", "details": tariffs_serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    # Create a new Tariffs record if none exists
                    tariffs_data = {
                        "terms_sheet": record.id,
                        "offer_tariff": request.data.get("offer_tariff"),
                        "generator": request.data.get("generator"),
                    }
                    tariffs_serializer = TariffsSerializer(data=tariffs_data)
                    if tariffs_serializer.is_valid():
                        tariffs_serializer.save()
                        return Response(
                            {
                                "message": "Update limit reached. New Tariff record created.",
                                "tariff_record": tariffs_serializer.data,
                            },
                            status=status.HTTP_201_CREATED,
                        )
                    return Response(
                        {"error": "Update limit reached, but Tariff creation failed.", "details": tariffs_serializer.errors},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Determine if the user is the consumer or generator
            if user == record.consumer:
                record.consumer_status = 'Pending'
                record.generator_status = 'Negotiated'
            else:  # Assuming the other user is a generator
                record.consumer_status = 'Negotiated'
                record.generator_status = 'Pending'

            # Proceed with updating the StandardTermsSheet record
            serializer = StandardTermsSheetSerializer(record, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                record.count += 1  # Increment the count on successful update
                record.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except StandardTermsSheet.DoesNotExist:
            return Response({"error": "Record not found."}, status=status.HTTP_404_NOT_FOUND)

    
class SubscriptionTypeAPIView(APIView):
    def get(self, request, user_type):
        # Get all subscription types
        subscription_types = SubscriptionType.objects.filter(user_type=user_type)

        # Serialize the subscription types
        serializer = SubscriptionTypeSerializer(subscription_types, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
        
class SubscriptionEnrolledAPIView(APIView):
    def get(self, request, pk):
        subscriptions = SubscriptionEnrolled.objects.filter(user=pk)
        serializer = SubscriptionEnrolledSerializer(subscriptions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        user = request.data.get('user')
        subscription_id = request.data.get('subscription')
        start_date_str = request.data.get('start_date')

        # Convert start_date to a datetime.date object
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"detail": "Invalid start_date format. Expected YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if the user is already enrolled in this subscription
        existing_subscription = SubscriptionEnrolled.objects.filter(user=user, subscription_id=subscription_id).first()

        if existing_subscription:
            if existing_subscription.end_date >= now().date():
                return Response(
                    {"detail": "You have already taken this subscription and it is still active."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                # Update the expired subscription
                existing_subscription.start_date = start_date
                subscription = existing_subscription.subscription
                existing_subscription.end_date = start_date + timedelta(days=subscription.duration_in_days)
                existing_subscription.status = 'active'
                existing_subscription.save()
                return Response(
                    {"detail": "Your subscription has been renewed successfully."},
                    status=status.HTTP_200_OK
                )

        # If no existing subscription or it has expired, create a new subscription
        serializer = SubscriptionEnrolledSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
class NotificationsAPI(APIView):
    
    def get(self, request, user_id):
        try:
            # Fetch notifications based on user_id
            notifications = Notifications.objects.filter(user_id=user_id).order_by('-timestamp')
            
            # Serialize the notifications data
            serializer = NotificationsSerializer(notifications, many=True)
            
            # Return the response with serialized data
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Notifications.DoesNotExist:
            # Handle the case where no notifications are found
            return Response({"message": "No notifications found for this user."}, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            # Handle any other exceptions
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class NegotiateTariffView(APIView):
    def get(self, request, terms_sheet_id):
        try:
            terms_sheet = StandardTermsSheet.objects.get(id=terms_sheet_id)
            serializer = StandardTermsSheetSerializer(terms_sheet)

            Tariffs.objects.get_or_create(terms_sheet=terms_sheet, offer_tariff=terms_sheet.combination.per_unit_cost)
            return Response({
                "terms_sheet": serializer.data,
                "offer_tariff": terms_sheet.combination.per_unit_cost,
            })
        except StandardTermsSheet.DoesNotExist:
            return Response({"error": "Terms Sheet not found."}, status=404)
        
    def post(self, request):
        user_id = request.data.get('user_id')
        terms_sheet_id = request.data.get('terms_sheet_id')

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            terms_sheet = StandardTermsSheet.objects.get(id=terms_sheet_id)
        except StandardTermsSheet.DoesNotExist:
            return Response({"error": "Terms Sheet not found."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Only consumers can initiate the negotiation
        if user.user_category == 'Generator':
            # Notify the consumer linked in the terms sheet
            try:
                updated_tariff = request.data.get("updated_tariff")
                tariff = Tariffs.objects.get(terms_sheet=terms_sheet)
                GeneratorOffer.objects.get_or_create(generator=user, tariff=tariff, updated_tariff=updated_tariff)

                consumer = terms_sheet.combination.consumer
                Notifications.objects.create(
                    user=consumer,
                    message=(
                        f"Generator {user.username} is interested in initiating a negotiation for Terms Sheet {terms_sheet}. "
                        f"The offer tariff being provided is {terms_sheet.combination.per_unit_cost}."
                    )
                )
            except User.DoesNotExist:
                return Response({"error": "Consumer linked to the terms sheet not found."}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"message": "Notification sent to the consumer linked to the terms sheet."}, status=200)
        else:
            # Notify all matching IPPs and the current generator
            matching_ipps = MatchingIPP.objects.get(requirement=terms_sheet.combination.requirement)
            recipients = matching_ipps.generator_ids

            # Get current time in timezone-aware format
            now_time = timezone.now()

            # Calculate the negotiation window start time (tomorrow at 10:00 AM)
            next_day_date = (now_time + timedelta(days=1)).date()
            next_day_10_am = datetime.combine(next_day_date, time(10, 0))
            next_day_10_am_aware = timezone.make_aware(next_day_10_am, timezone=timezone.get_current_timezone())

            # Define the end time for the negotiation window (e.g., 1 hour after start time)
            end_time = next_day_10_am_aware + timedelta(hours=1)

            # Notify recipients
            for recipient in recipients:
                try:
                    recipient_user = User.objects.get(id=recipient)
                    Notifications.objects.create(
                        user=recipient_user,
                        message=(
                            f"Consumer {user.username} has initiated a negotiation for Terms Sheet {terms_sheet}. "
                            f"The negotiation window will open tomorrow at 10:00 AM. "
                            f"The generator involved in this negotiation is {terms_sheet.combination.generator.username}, "
                            f"and the offer tariff being provided is {terms_sheet.combination.per_unit_cost}."
                        )
                    )
                except User.DoesNotExist:
                    continue

            # Create the negotiation window record with date and time
            NegotiationWindow.objects.create(
                terms_sheet=terms_sheet,
                start_time=next_day_10_am_aware,
                end_time=end_time
            )

            return Response({"message": "Negotiation initiated. Notifications sent and negotiation window created."}, status=200)
        
class NegotiationWindowStatusView(APIView):
    def get(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({"message": "no user found"}, status=status.HTTP_404_NOT_FOUND)
        if user.user_category == 'Consumer':
            tariff = Tariffs.objects.filter(terms_sheet__consumer=user).order_by('-id').first()
            if tariff:
                negotiation_window = NegotiationWindow.objects.filter(terms_sheet=tariff.terms_sheet).first()

                if negotiation_window:
                    # Check if the current time is less than the start time
                    current_time = now()
                    if current_time < negotiation_window.start_time:
                        return Response({
                            "status": "error",
                            "message": f"The negotiation window is not yet open. It will open on {negotiation_window.start_time.strftime('%Y-%m-%d at %I:%M %p')}."
                        }, status=status.HTTP_403_FORBIDDEN)
                    elif current_time > negotiation_window.end_time:
                        return Response({
                            "status": "error",
                            "message": f"The negotiation window is closed."
                        }, status=status.HTTP_403_FORBIDDEN)
                    else:
                        return Response({
                            "status": "success",
                            'tariff_id': tariff.id,
                            "message": "Negotiation window is open.",
                        }, status=status.HTTP_200_OK)

                else:
                    return Response({
                        "status": "error",
                        "message": "Negotiation window not found.",
                    }, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "status": "error",
                "message": "Not Eligible.",
            }, status=status.HTTP_400_BAD_REQUEST)

       
        # Fetch the latest notification for the user
        notification = Notifications.objects.filter(user_id=user_id).order_by('-timestamp').first()

        if notification:
            # Check if the message contains the required substring
            if "The negotiation window will open tomorrow at 10:00 AM" in notification.message:
                # Extract the Terms Sheet name from the message using regex
                terms_sheet_pattern = re.compile(r"Terms Sheet (.+?)\. The negotiation window will open tomorrow")
                match = terms_sheet_pattern.search(notification.message)

                if match:
                    terms_sheet_name = match.group(1)

                    # Regex to extract consumer email and requirement
                    pattern = re.compile(r"^(?P<consumer_email>\S+) - Demand for (?P<requirement>.+)$")
                    result = pattern.match(terms_sheet_name)

                    if result:
                        consumer_email = result.group("consumer_email")
                        requirement = result.group("requirement")
                        
                        # Split the string by ' - '
                        values = [value.strip() for value in requirement.split(' - ')]

                        # Extracted values
                        # email = values[0]  # Consumer email
                        state = values[1]  # State
                        industry = values[2]  # Industry
                        contracted_demand = values[3]  # Contracted demand
                        # Extract the numeric part using a regular expression
                        contracted_demand = float(re.search(r"\d+(\.\d+)?", contracted_demand).group())

                        consumer = User.objects.get(email=consumer_email)
                        requirement = ConsumerRequirements.objects.get(user=consumer, state=state, industry=industry, contracted_demand=contracted_demand)
                    else:
                        print("No match found.")

                    # Fetch the NegotiationWindow record based on the extracted Terms Sheet name
                    try:
                        terms_sheet = StandardTermsSheet.objects.get(consumer=consumer, combination__requirement=requirement)
                        tariff = Tariffs.objects.get(terms_sheet=terms_sheet)
                        negotiation_window = NegotiationWindow.objects.filter(terms_sheet=terms_sheet).order_by('-id').first()

                        if negotiation_window:
                            # Check if the current time is less than the start time
                            current_time = now()
                            if current_time < negotiation_window.start_time:
                                return Response({
                                    "status": "error",
                                    "message": f"The negotiation window is not yet open. It will open on {negotiation_window.start_time.strftime('%Y-%m-%d at %I:%M %p')}."
                                }, status=status.HTTP_403_FORBIDDEN)
                            elif current_time > negotiation_window.end_time:
                                return Response({
                                    "status": "error",
                                    "message": f"The negotiation window is closed."
                                }, status=status.HTTP_403_FORBIDDEN)
                            else:
                                return Response({
                                    "status": "success",
                                    'tariff_id': tariff.id,
                                    "message": "Negotiation window is open.",
                                }, status=status.HTTP_200_OK)

                    except StandardTermsSheet.DoesNotExist:
                        return Response({
                            "status": "error",
                            "message": "Terms Sheet not found.",
                        }, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "status": "error",
                "message": "Notification message format is invalid or does not contain the required information.",
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "status": "error",
            "message": "No notification found for the user.",
        }, status=status.HTTP_404_NOT_FOUND)
    

class AnnualSavingsView(APIView):
    def post(self, request):
        re = 3.67  # Fixed RE value for calculationgenera
        requirement_id = request.data.get('requirement_id')
        generator_id = request.data.get('generator_id')
        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
            master_record = MasterTable.objects.get(state=requirement.state)

            # Fetch Grid cost from GridTariff (Assuming tariff_category is fixed or dynamic)
            grid_tariff = GridTariff.objects.get(state=requirement.state, tariff_category=requirement.tariff_category)
            
            if grid_tariff is None:
                return Response({"error": "No grid cost data available for the state"}, status=status.HTTP_404_NOT_FOUND)
            
            # Calculate annual savings
            annual_savings = grid_tariff.cost - (re + master_record.ISTS_charges + master_record.state_charges)
            
            return Response({
                "re_replacement": 65,
                "annual_savings": annual_savings
            }, status=status.HTTP_200_OK)
        
        except MasterTable.DoesNotExist:
            return Response({"error": f"No data available for the state: {requirement.state}"}, status=status.HTTP_404_NOT_FOUND)