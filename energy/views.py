import ast
import base64
import calendar
from calendar import monthrange
from collections import defaultdict
import csv
import io
from itertools import chain
import re
import statistics
import fitz
from django.shortcuts import get_object_or_404
import pytz
import requests
from accounts.models import GeneratorConsumerMapping, User
from accounts.views import JWTAuthentication
from .models import CapacitySizingCombination, GeneratorDemand, GeneratorHourlyDemand, GeneratorMonthlyConsumption, GeneratorOffer, GridTariff, Industry, NationalHoliday, NegotiationInvitation, PeakHours, ScadaFile, SolarPortfolio, State, StateTimeSlot, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, HourlyDemand, Combination, StandardTermsSheet, MatchingIPP, SubscriptionType, SubscriptionEnrolled, Notifications, Tariffs, NegotiationWindow, MasterTable, RETariffMasterTable, PerformaInvoice, SubIndustry
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from rest_framework.serializers import ValidationError
from .serializers import CSVFileSerializer, CapacitySizingCombinationSerializer, CreateOrderSerializer, OfflinePaymentSerializer, PaymentTransactionSerializer, PerformaInvoiceCreateSerializer, PerformaInvoiceSerializer, ScadaFileSerializer, SolarPortfolioSerializer, StateTimeSlotSerializer, WindPortfolioSerializer, ESSPortfolioSerializer, ConsumerRequirementsSerializer, MonthlyConsumptionDataSerializer, StandardTermsSheetSerializer, SubscriptionTypeSerializer, SubscriptionEnrolledSerializer, NotificationsSerializer, TariffsSerializer
from django.core.mail import send_mail
import random
from django.contrib.auth.hashers import check_password
from django.utils.timezone import make_aware, now
from datetime import datetime, timedelta, time, date
from rest_framework.permissions import IsAuthenticated
from .permissions import IsAuthenticatedOrInternal
from django.db.models import Q, Sum
from django.db.models import OuterRef, Exists
from .aggregated_model.main import optimization_model
from django.core.files.base import ContentFile
import pandas as pd
from itertools import product
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
import razorpay
from django.db.models import Avg
from django.utils.timezone import localtime
from django.conf import settings
from django.db.models import Count, Q
import secrets
from django_celery_beat.models import PeriodicTask, ClockedSchedule, CrontabSchedule
import json
import logging
import traceback
import chardet
from decimal import Decimal

# Get the logger that is configured in the settings
import logging
traceback_logger = logging.getLogger('django')

logger = logging.getLogger('debug_logger')  # Use the new debug logger

# Create your views here.

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

# Get the logged-in user
def get_admin_user(user_id):
        logged_in_user = User.objects.get(id=user_id)
        # Determine the admin user for the logged-in user
        admin_user_id = logged_in_user.parent if logged_in_user.parent else logged_in_user
        # admin_user = User.objects.get(id=admin_user_id)
        return admin_user_id

def generate_unique_username():
    """Generate a unique consumer username in the format CONxxxx"""
    while True:
        new_id = f"CUD{random.randint(1000, 9999)}"
        if not GeneratorConsumerMapping.objects.filter(mapped_username=new_id).exists():
            return new_id

def get_mapped_username(generator, consumer):
    """Get or create a unique username mapping for the generator-consumer pair"""
    mapping, created = GeneratorConsumerMapping.objects.get_or_create(
        generator=generator, consumer=consumer,
        defaults={'mapped_username': generate_unique_username()}
    )
    return mapping.mapped_username


class StateListAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        names = list(State.objects.values_list('name', flat=True))
        return Response(names)
        
class IndustryListAPI(APIView): 
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        industries = Industry.objects.prefetch_related('sub_industries').all()
        
        industry_data = {
            industry.name: {sub_industry.name for sub_industry in industry.sub_industries.all()}
            for industry in industries
        }

        return Response(industry_data)
    
class StateTimeSlotAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        states = StateTimeSlot.objects.all()
        serializer = StateTimeSlotSerializer(states, many=True)
        return Response(serializer.data)
    
class GenerationPortfolioAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

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
            user = get_admin_user(pk)
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
                "solar_template_downloaded": user.solar_template_downloaded,
                "wind_template_downloaded": user.wind_template_downloaded
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        # Determine the serializer and model based on `energy_type`
        energy_type = request.data.get("energy_type")
        if not energy_type:
            return Response({"error": "Energy type is required."}, status=status.HTTP_400_BAD_REQUEST)

        user_id = request.data.get("user")
        user = get_admin_user(user_id)
        request.data['user'] = user.id
        
        serializer_class = self.get_serializer_class(energy_type)
        serializer = serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()

            # Get the user associated with the saved data (assuming it's passed in the request)
            user_id = request.data.get('user')  # Assuming user is passed in the request body
            if user_id:
                user = get_object_or_404(User, id=user_id)  # Get the user object
                user = get_admin_user(user_id)

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
        updated = request.data.get("updated")
        if not energy_type:
            return Response({"error": "Energy type is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        model = self.get_model(energy_type)
        instance = get_object_or_404(model, pk=pk)
        serializer_class = self.get_serializer_class(energy_type)

        # If updated is explicitly False, update only that field and return
        if updated == "False":
            instance.updated = False
            instance.save()
            return Response({"message": "Updated flag set to false successfully.", "updated": instance.updated}, status=status.HTTP_200_OK)


        # Handle Base64-encoded file
        file_data = request.data.get("hourly_data")
        message = None
        if file_data:
            try:
                # Decode Base64 file
                decoded_file = base64.b64decode(file_data)

                # Check if it's a valid Excel file (magic header: PK\x03\x04)
                if not decoded_file.startswith(b"PK"):
                    return Response({"error": "Uploaded file is not a valid Excel file."}, status=status.HTTP_400_BAD_REQUEST)

                # Define a file name (customize as needed)
                file_name = f"hourly_data_{pk}.xlsx"  # Assuming the file is an Excel file
                # Wrap the decoded file into ContentFile
                file_content = ContentFile(decoded_file, name=file_name)
                # Validate the file content
                with io.BytesIO(decoded_file) as file_stream:
                    try:
                        # Read the Excel file into a DataFrame
                        df = pd.read_excel(file_stream)

                        # Check if the expected column exists
                        expected_column = "Expected Generation(MWh)"
                        if expected_column not in df.columns:
                            return Response(
                                {"error": f"Missing required column: '{expected_column}'."},
                                status=status.HTTP_400_BAD_REQUEST
                            )

                        # Check for missing values in the required column
                        if df[expected_column].isnull().any():
                            return Response(
                                {"error": f"Column '{expected_column}' contains missing or empty values."},
                                status=status.HTTP_400_BAD_REQUEST
                            )

                        # Convert only the second column to float (keeping NaN values)
                        df.iloc[:, 1] = pd.to_numeric(df.iloc[:, 1], errors='coerce')
                    except Exception as e:
                        return Response({"error": f"Invalid file format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

                    # Check for the required number of rows
                    current_year = datetime.now().year
                    # is_leap_year = (current_year % 4 == 0 and current_year % 100 != 0) or (current_year % 400 == 0)
                    required_rows = 8760
                    logger.debug(f'shape= {df.shape[0]}')
                    logger.debug(f'df= {df.head(20)}')

                    # Verify row count
                    if df.shape[0] != required_rows:
                        return Response(
                            {
                                "error": f"Invalid data rows: Expected {required_rows} rows, but got {df.shape[0]}"
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                
                # Get the maximum value from the second column (ignoring NaNs)
                max_value = df.iloc[:, 1].max(skipna=True)

                # Get available capacity
                available_capacity = float(request.data.get("available_capacity"))  # Ensure `available_capacity` exists in the model

                
                # Check if max_value exceeds 80% of available_capacity
                if float(max_value) < (0.8 * available_capacity):
                    message = f"Uploaded data is below 80% of available capacity. Max value: {max_value}, Threshold: {0.8 * available_capacity}"

                # Add the validated file to the request data
                request.data["hourly_data"] = file_content

            except Exception as e:
                tb = traceback.format_exc()  # Get the full traceback
                traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
                return Response({"error": f"{str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = serializer_class(instance, data=request.data)
        if serializer.is_valid():
            serializer.save()
            response_data = serializer.data
            response_data['energy_type'] = energy_type
            response_data['message'] = message
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
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
   

    def get(self, request, pk):
        # Fetch energy profiles
        user = User.objects.get(id=pk)
        user = get_admin_user(pk)
        profiles = ConsumerRequirements.objects.filter(user=user)
        serializer = ConsumerRequirementsSerializer(profiles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Add a new energy profile
        user_id = request.data.get("user")
        user = get_admin_user(user_id)
        request.data["user"] = user.id
        
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

class ScadaFileAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, requirement_id):
        try:
            scada_file = ScadaFile.objects.get(requirement_id=requirement_id)
            serializer = ScadaFileSerializer(scada_file)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ScadaFile.DoesNotExist:
            return Response(
                {"error": "SCADA file not found for this requirement."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def post(self, request, requirement_id):
        # Validate the requirement
        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
        except ConsumerRequirements.DoesNotExist:
            return Response(
                {"error": "Requirement does not exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Handle Base64-encoded file
        file_data = request.data.get("file")
        if not file_data:
            return Response(
                {"error": "No file provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Decode the Base64 file
            decoded_file = base64.b64decode(file_data)
            file_name = f"scada_file_{requirement_id}.xlsx"
            scada_file_content = ContentFile(decoded_file, name=file_name)
        except Exception as e:
            return Response(
                {"error": f"Invalid Base64 file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if a file already exists
        scada_file, created = ScadaFile.objects.get_or_create(requirement=requirement)
        
        # File did not exist; save the new file
        scada_file.file = scada_file_content
        scada_file.save()

        # Process the Excel file
        try:
            # Read the Excel file and validate the sheet
            xls = pd.ExcelFile(scada_file.file)
            if "Logger 1" not in xls.sheet_names:
                return Response(
                    {"error": "Sheet 'Logger 1' not found in the uploaded Excel file."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        
            df = pd.read_excel(scada_file.file, sheet_name="Logger 1", header=7)

            # Extract the required column
            column_name = "Active(I) Total [kWh]\n (1.0.1.29.0.255)"  # Ensure this matches exactly
            if column_name not in df.columns:
                return Response(
                    {"error": f"Required column '{column_name}' not found in the sheet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Clean and check for sufficient data
            valid_data = df[column_name].dropna()
            if valid_data.empty:
                return Response(
                    {"error": f"The column '{column_name}' contains no valid data."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Convert 15-min interval data to hourly by summing every 4 rows
            hourly_data = df[column_name].dropna().astype(float).groupby(df.index // 4).sum()

            # Round values to 2 decimal places
            hourly_data = hourly_data.round(2)

            # Convert list of floats into a comma-separated string
            hourly_demand_str = ','.join(map(str, hourly_data.tolist()))

            # Save hourly demand in the model
            hourly_demand, _ = HourlyDemand.objects.update_or_create(
                requirement=requirement,
            )
            hourly_demand.hourly_demand = hourly_demand_str  # Store as a single string
            hourly_demand.save()

            serializer = ScadaFileSerializer(scada_file)
            return Response(
                {"data": serializer.data},
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )
        
        except Exception as e:
            return Response(
                {"error": f"Error processing file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


    def delete(self, request, requirement_id):
        try:
            scada_file = ScadaFile.objects.get(requirement_id=requirement_id)
            scada_file.delete()
            return Response(
                {"message": "SCADA file deleted successfully."},
                status=status.HTTP_200_OK,
            )
        except ScadaFile.DoesNotExist:
            return Response(
                {"error": "SCADA file not found for this requirement."},
                status=status.HTTP_404_NOT_FOUND,
            )
    
class MonthlyConsumptionDataAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
   

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
        # Iterate over the input data
        for item in request.data:
            requirement = item.get("requirement")
            month = item.get("month")

            # Validate requirement and month presence
            if not requirement or not month:
                return Response(
                    {"error": "Both 'requirement' and 'month' are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                consumer_requirement = ConsumerRequirements.objects.get(id=requirement)
            except ConsumerRequirements.DoesNotExist:
                return Response(
                    {"error": "Invalid requirement ID."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check if the record exists
            instance = MonthlyConsumptionData.objects.filter(
                requirement=requirement, month=month
            ).first()

            if instance:
                # Update the existing record
                serializer = MonthlyConsumptionDataSerializer(instance, data=item, partial=True)
            else:
                # Create a new record
                serializer = MonthlyConsumptionDataSerializer(data=item)

            if serializer.is_valid():
                saved_instance = serializer.save()

                # Check if any of the tracked fields are null
                fields_to_check = ['monthly_consumption', 'peak_consumption', 'off_peak_consumption']
                has_null = any(getattr(saved_instance, field) is None for field in fields_to_check)

            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if not has_null:
            # Call the calculate_hourly_demand method
            OptimizeCapacityAPI.calculate_hourly_demand(consumer_requirement, consumer_requirement.state)

        return Response(
            {"message": "Data processed successfully.", "fields_updated": not has_null},
            status=status.HTTP_200_OK,
        )
    
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

class CSVFileAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        requirement_id = request.data.get("requirement_id")
        csv_file = request.data.get("csv_file")

        if not csv_file or not requirement_id:
            return Response(
                {"error": "Requirement ID and CSV file are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Decode the Base64 file
            decoded_file = base64.b64decode(csv_file)
            file_name = f"csv_file_{requirement_id}.csv"
            csv_file_content = ContentFile(decoded_file, name=file_name)
        except Exception as e:
            return Response(
                {"error": f"Invalid Base64 file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        REQUIRED_HEADERS = {
            "Month",
            "Monthly Consumption (MWh)",
            "Peak Consumption (MWh)",
            "Off Peak Consumption (MWh)",
            "Monthly Bill Amount (INR cr)",
        }

        EXPECTED_MONTHS = {
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        }

        try:
            # Read the CSV content
            raw_data = csv_file_content.read()
            if not raw_data.strip():
                return Response(
                    {"error": "Uploaded file is empty."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            result = chardet.detect(raw_data)
            encoding = result['encoding']

            # Decode the content with detected encoding
            file_data = raw_data.decode(encoding, errors='replace').splitlines()
            
            # Handle the case where no lines are found
            if not file_data:
                return Response(
                    {"error": "No data found in file."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            csv_reader = csv.DictReader(file_data)

            # Validate required headers
            file_headers = set(h.strip() for h in csv_reader.fieldnames if h)
            if not REQUIRED_HEADERS.issubset(file_headers):
                missing_headers = REQUIRED_HEADERS - file_headers
                return Response(
                    {"error": f"Missing required column(s): {', '.join(missing_headers)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the ConsumerRequirement object
            try:
                requirement = ConsumerRequirements.objects.get(id=requirement_id)
            except ConsumerRequirements.DoesNotExist:
                return Response(
                    {"error": "requirement not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Process each row in the CSV file
            found_months = set()
            row_found = False
            for row in csv_reader:
                row_found = True
                # Clean column names (remove extra spaces and non-breaking spaces)
                row = {key.strip(): value.strip().replace('\xa0', '').replace(',', '') for key, value in row.items()}
                month = row['Month']
                found_months.add(month)

                try:
                    monthly_consumption = MonthlyConsumptionData.objects.get(requirement=requirement, month=row['Month'])
                except MonthlyConsumptionData.DoesNotExist:
                    monthly_consumption = MonthlyConsumptionData()
                    monthly_consumption.requirement=requirement
                    monthly_consumption.month=row['Month']

                monthly_consumption.monthly_consumption=float(row['Monthly Consumption (MWh)'].replace(',', ''))
                monthly_consumption.peak_consumption=float(row['Peak Consumption (MWh)'].replace(',', ''))
                monthly_consumption.off_peak_consumption=float(row['Off Peak Consumption (MWh)'].replace(',', ''))
                monthly_consumption.monthly_bill_amount=float(row['Monthly Bill Amount (INR cr)'].replace(',', ''))
                monthly_consumption.save()

            # check if any required fields are null
            incomplete_months = MonthlyConsumptionData.objects.filter(
                requirement=requirement
            ).filter(
                Q(monthly_consumption__isnull=True) |
                Q(peak_consumption__isnull=True) |
                Q(off_peak_consumption__isnull=True)
            ).values_list('month', flat=True)

            fields_updated = True
            if not incomplete_months:
                # Call the calculate_hourly_demand method
                OptimizeCapacityAPI.calculate_hourly_demand(requirement, requirement.state)
            else:
                fields_updated = False

            if not row_found:
                return Response(
                    {"error": "CSV file contains headers but no data rows."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            missing_months = EXPECTED_MONTHS - found_months
            if missing_months:
                return Response(
                    {"error": f"Data missing for month(s): {', '.join(missing_months)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
                
            return Response({'message': 'Success', 'fields_updated': fields_updated, 'Note': 'Missing required values in monthly data.'}, status=status.HTTP_201_CREATED)

        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response(
                {"error": f"An error occurred while processing the file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UploadMonthlyConsumptionBillAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def extract_required_data(self, pdf_path):
        """Extract TOD 1, TOD 2, TOD 3, and Current Month Bill from PDF"""
        extracted_text = ""
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                extracted_text += page.get_text("text") + "\n"

            if not extracted_text.strip():
                return {"error": "No readable text found in the PDF file."}

            # Use regex to extract required values
            tod1 = re.search(r"TOD1\s*:\s*([\d,.]+)", extracted_text)
            tod2 = re.search(r"TOD2\s*:\s*([\d,.]+)", extracted_text)
            tod3 = re.search(r"TOD3\s*:\s*([\d,.]+)", extracted_text)
            current_bill = re.search(r"CURRENT MONTH BILL\s*([\d,.]+)", extracted_text)

            return {
                "TOD 1": tod1.group(1) if tod1 else "Not found",
                "TOD 2": tod2.group(1) if tod2 else "Not found",
                "TOD 3": tod3.group(1) if tod3 else "Not found",
                "Current Month Bill": current_bill.group(1) if current_bill else "Not found"
            }
        except Exception as e:
            return {"error": f"Error extracting text: {str(e)}"}
        
    def post(self, request):
        # Extract data from the request
        requirement_id = request.data.get("requirement")
        month = request.data.get("month")
        file_data = request.data.get("bill_file")

        # Validate requirement, month, and file presence
        if not requirement_id or not month or not file_data:
            return Response(
                {"error": "All fields ('requirement', 'month', and 'bill_file') are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get the requirement instance
        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Invalid requirement ID."}, status=status.HTTP_400_BAD_REQUEST)

        # Handle Base64-encoded file and save it in the model first
        try:
            decoded_file = base64.b64decode(file_data)

            # Check if it's a PDF by magic number (starts with "%PDF")
            if not decoded_file.startswith(b"%PDF"):
                return Response(
                    {"error": "Uploaded file is not a valid PDF."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            file_name = f"bill_{requirement_id}_{month}.pdf"
            bill_file = ContentFile(decoded_file, name=file_name)
        except Exception as e:
            return Response(
                {"error": f"Invalid Base64 file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create or update a new record and save the bill file first
        instance, created = MonthlyConsumptionData.objects.update_or_create(
            requirement=requirement, month=month,
            defaults={"bill": bill_file}  # Save only the bill file first
        )

        # Extract required data from the saved file path
        if instance.bill:
            extracted_data = self.extract_required_data(instance.bill.path)

            if "error" in extracted_data:
                return Response({"error": extracted_data["error"]}, status=status.HTTP_400_BAD_REQUEST)

            # Validate extracted data to ensure TOD values exist
            if extracted_data["TOD 1"] == "Not found" or extracted_data["TOD 2"] == "Not found" or extracted_data["TOD 3"] == "Not found":
                return Response(
                    {"error": "Invalid file format. Required TOD values not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                # Calculate required values
                peak_consumption = round(float(extracted_data["TOD 1"]) / 1000)  # TOD 1
                off_peak_consumption = round(float(extracted_data["TOD 3"]) / 1000)  # TOD 3
                monthly_consumption = round(peak_consumption + round(float(extracted_data["TOD 2"]) / 1000) + off_peak_consumption, 2)  # TOD 1 + TOD 2 + TOD 3
                monthly_bill_amount = extracted_data["Current Month Bill"]  # Current Month Bill

                # Update instance with extracted data
                instance.peak_consumption = peak_consumption
                instance.off_peak_consumption = off_peak_consumption
                instance.monthly_consumption = monthly_consumption
                instance.monthly_bill_amount = monthly_bill_amount
                instance.save()
                # OptimizeCapacityAPI.calculate_hourly_demand(requirement)

            except Exception as e:
                return Response(
                    {"error": f"Error processing extracted data: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(
            {
                "message": "Bill file uploaded and processed successfully."
            },
            status=status.HTTP_200_OK,
        )

class MatchingIPPAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        try:
            # Fetch the requirement
            requirement = ConsumerRequirements.objects.get(id=pk)

            accepted_tariff = Tariffs.objects.filter(
                terms_sheet__combination__requirement=requirement,
                window_status='Accepted'
            ).first()

            if accepted_tariff:
                return Response({"message": "Accepted tariff found."}, status=status.HTTP_200_OK)

            solar_data = SolarPortfolio.objects.filter(
                Q(state=requirement.state) | Q(connectivity="CTU"),
            ).values("user", "user__username", "state", "available_capacity", "updated")

            wind_data = WindPortfolio.objects.filter(
                Q(state=requirement.state) | Q(connectivity="CTU"),
            ).values("user", "user__username", "state", "available_capacity", "updated")

            ess_data = ESSPortfolio.objects.filter(
                Q(state=requirement.state) | Q(connectivity="CTU"),
            ).values("user", "user__username", "state", "available_capacity", "updated")
        
            
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
            
            # Check if users have an active subscription
            filtered_data = []
            for entry in unique_data:
                user_id = entry["user"]
                user = User.objects.get(id=user_id)

                is_subscribed = SubscriptionEnrolled.objects.filter(user=user_id, status='active').exists()

                # Check if any of the user's portfolios have been updated in the last 30 days
                has_not_updated = (
                    SolarPortfolio.objects.filter(user=user_id, updated=False).exists() or
                    WindPortfolio.objects.filter(user=user_id, updated=False).exists() or
                    ESSPortfolio.objects.filter(user=user_id, updated=False).exists()
                )
                
                if not is_subscribed:
                    
                    # Send notification to user
                    message = f"Your subscription is inactive. Please subscribe to start receiving and accepting offers."
                    send_notification(user.id, message) 
                elif has_not_updated:
                    
                    # Send notification for outdated portfolio
                    message = f"Your portfolios are not updated yet. Please update them to start receiving and accepting offers."
                    send_notification(user.id, message) 
                else:
                    # Sum available capacity for all portfolios of this user
                    available_capacity = (
                        SolarPortfolio.objects.filter(user=user_id).aggregate(Sum("available_capacity"))["available_capacity__sum"] or 0
                    ) + (
                        WindPortfolio.objects.filter(user=user_id).aggregate(Sum("available_capacity"))["available_capacity__sum"] or 0
                    ) + (
                        ESSPortfolio.objects.filter(user=user_id).aggregate(Sum("available_capacity"))["available_capacity__sum"] or 0
                    )

                    # Sum installed capacity for all portfolios of this user
                    installed_capacity = (
                        SolarPortfolio.objects.filter(user=user_id).aggregate(Sum("total_install_capacity"))["total_install_capacity__sum"] or 0
                    ) + (
                        WindPortfolio.objects.filter(user=user_id).aggregate(Sum("total_install_capacity"))["total_install_capacity__sum"] or 0
                    ) + (
                        ESSPortfolio.objects.filter(user=user_id).aggregate(Sum("total_install_capacity"))["total_install_capacity__sum"] or 0
                    )

                    # Fetch portfolio details per user
                    solar_portfolios = SolarPortfolio.objects.filter(user=user_id).values("state", "connectivity", "total_install_capacity", "available_capacity")
                    wind_portfolios = WindPortfolio.objects.filter(user=user_id).values("state", "connectivity", "total_install_capacity", "available_capacity")
                    ess_portfolios = ESSPortfolio.objects.filter(user=user_id).values("state", "connectivity", "total_install_capacity", "available_capacity")

                    # Update the user's available capacity
                    entry["available_capacity"] = available_capacity
                    entry["installed_capacity"] = installed_capacity
                    entry["solar"] = list(solar_portfolios)
                    entry["wind"] = list(wind_portfolios)
                    entry["ess"] = list(ess_portfolios)

                    filtered_data.append(entry)  # Keep only subscribed users

            sorted_data = sorted(filtered_data, key=lambda x: x["available_capacity"], reverse=True)

            # Get only the top 3 matches
            top_three_matches = sorted_data[:3]
            

            # Extract user IDs from the top three matches
            user_ids = [match["user"] for match in top_three_matches]

            # Save the user IDs in MatchingIPP
            matching_ipp, created = MatchingIPP.objects.get_or_create(requirement=requirement)
            matching_ipp.generator_ids = user_ids
            matching_ipp.save()

            if top_three_matches:
                # Return the top three matches as the response
                return Response(top_three_matches, status=status.HTTP_200_OK)
            else:
                return Response({"message": "No matching IPP found."}, status=status.HTTP_200_OK)
        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MatchingConsumerAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):

        try:
            user = User.objects.get(id=pk)
            user = get_admin_user(pk)
            # Get all GenerationPortfolio records for the user
            solar_data = SolarPortfolio.objects.filter(user=user)
            wind_data = WindPortfolio.objects.filter(user=user)
            ess_data = ESSPortfolio.objects.filter(user=user)

            # Combine all data
            data = list(chain(solar_data, wind_data, ess_data))
            logger.debug(data)

            # Ensure generation portfolio exists
            if not data:
                return Response(
                    {"error": "No generation portfolio records found for the user."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            
            # Separate CTU and non-CTU portfolios
            ctu_portfolios = [p for p in data if p.connectivity == "CTU"]
            non_ctu_portfolios = [p for p in data if p.connectivity != "CTU"]
            logger.debug(f'ctu=== {ctu_portfolios}')
            logger.debug(f'non ctu=== {non_ctu_portfolios}')

            # Collect filtering criteria
            states = set(p.state for p in non_ctu_portfolios)
            cod_dates = [p.cod for p in non_ctu_portfolios if p.cod]

            # Get consumer requirements based on filtering logic
            filtered_data = ConsumerRequirements.objects.none()  # Empty queryset initially

            if ctu_portfolios:
                ctu_filtered_data = ConsumerRequirements.objects.all()

                logger.debug('ctu filtered data:')
                logger.debug(ctu_filtered_data)

                # Merge with existing filter
                filtered_data = filtered_data | ctu_filtered_data

            if states and cod_dates:
                # Match state-wise and COD-wise for non-CTU projects
                state_filtered_data = ConsumerRequirements.objects.filter(
                    state__in=states
                )
                logger.debug('state filtered data:')
                logger.debug(state_filtered_data)

                # Merge both results (CTU + State-wise matching)
                filtered_data   = filtered_data | state_filtered_data
                logger.debug(filtered_data)

            # Subquery to find if any related Tariff has window_status='Accepted' via this chain
            accepted_tariff_qs = Tariffs.objects.filter(
                terms_sheet__combination__requirement=OuterRef('pk'),
                window_status='Accepted'
            )

            # Annotate and exclude consumer requirements linked to accepted tariffs
            filtered_data = filtered_data.annotate(
                has_accepted_tariff=Exists(accepted_tariff_qs)
            ).filter(
                has_accepted_tariff=False
            )

            logger.debug('final filtered data after removing accepted ones:')
            logger.debug(filtered_data)
            
            # Check for subscription and notify consumers without a subscription
            exclude_consumers = []
            exclude_requirements = []
            for requirement in filtered_data:
                
                if not SubscriptionEnrolled.objects.filter(user=requirement.user, status='active').exists():

                    # Add the consumer to the notification list
                    exclude_consumers.append(requirement.user)

                    # Send a notification (customize this part as per your notification system)
                    message = f"Please activate your subscription to access matching services."
                    send_notification(requirement.user.id, message)

                # Exclude users who do not have monthly consumption data for all 12 months
                users_with_complete_consumption = MonthlyConsumptionData.objects.filter(requirement=requirement)
                
                # Check if hourly demand data is available for any requirement
                users_with_hourly_demand = HourlyDemand.objects.filter(requirement=requirement)
                
                if len(users_with_complete_consumption) != 12 and not users_with_hourly_demand:

                    # Add the consumer to the notification list
                    exclude_requirements.append(requirement.id)

                    # Send a notification (customize this part as per your notification system)
                    message = f"Please complete your profile to access matching services."
                    send_notification(requirement.user.id, message)


            # Exclude consumers without a subscription from the response
            filtered_data = filtered_data.exclude(user__in=exclude_consumers)
            filtered_data = filtered_data.exclude(id__in=exclude_requirements)

            # Annotate before mapping to group by consumer
            annotated_data = (
                filtered_data
                .values("id", "user__username", "state", "sub_industry", "industry", "voltage_level")
                .annotate(total_contracted_demand=Sum("contracted_demand"))
            )

            # Map usernames per generator
            response_data = []

            # Assuming 'current_generator' is the generator making the request
            for item in annotated_data:
                id = item["id"]
                consumer = User.objects.get(username=item["user__username"])  # Get the consumer instance
                
                # Map the consumer username specific to the generator
                mapped_username = get_mapped_username(user, consumer)

                # Append the result with the mapped username
                response_data.append({
                    "id": id,
                    "user__username": mapped_username,   # Mapped consumer username
                    "state": item["state"],
                    "industry": item["industry"],
                    "sub_industry": item["sub_industry"],
                    "voltage_level": item["voltage_level"],
                    "total_contracted_demand": item["total_contracted_demand"]
                })
                
            if response_data == []:
                return Response({"message": "No matching consumers found."}, status=status.HTTP_404_NOT_FOUND)          


            # Convert QuerySet to a list for JSON response
            return Response(list(response_data), status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PortfolioUpdateStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = get_admin_user(user_id)
            # user_id = user.id
            # Fetch records for the given user in all three models
            solar_records = SolarPortfolio.objects.filter(user__id=user.id)
            wind_records = WindPortfolio.objects.filter(user__id=user.id)
            ess_records = ESSPortfolio.objects.filter(user__id=user.id)

            # Combine all records into a single list
            all_records = list(solar_records) + list(wind_records) + list(ess_records)

            # Check if any record is not updated
            all_updated = all(record.updated for record in all_records)
            logger.debug(all_updated)

            return Response({
                "user_id": user.id,
                "all_updated": all_updated
            }, status=status.HTTP_200_OK)

        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({
                "error": "An error occurred.",
                "details": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BankingCharges(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    @staticmethod
    def calculate_monthly_slot_generation(profile, state):
        """
        Calculates monthly generation totals split into:
        - Peak Slot 1
        - Peak Slot 2
        - Off-Peak
        - Normal
        using 8760-hour profile and state's PeakHours.
        """
        # Load PeakHours config
        try:
            peak_config = PeakHours.objects.get(state__name=state)
        except PeakHours.DoesNotExist:
            raise ValueError(f"No PeakHours defined for state: {state}")

        # Step 1: Build datetime range for the year (non-leap year)
        base_date = datetime(datetime.now().year, 1, 1)
        datetimes = [base_date + timedelta(hours=i) for i in range(8760)]
        
        df = pd.DataFrame({
            "datetime": datetimes,
            "generation": profile
        })

        df["month"] = df["datetime"].dt.month
        df["time"] = df["datetime"].dt.time

        # Helper to check if a time falls in a given slot
        def in_slot(t, start, end):
            if not start or not end:
                return False
            if start <= end:
                return start <= t < end
            else:
                return t >= start or t < end  # spans midnight

        # Classify time slot
        def classify_slot(t):
            if in_slot(t, peak_config.peak_start_1, peak_config.peak_end_1):
                return "peak_1"
            elif in_slot(t, peak_config.peak_start_2, peak_config.peak_end_2):
                return "peak_2"
            elif in_slot(t, peak_config.off_peak_start, peak_config.off_peak_end):
                return "off_peak"
            else:
                return "normal"

        df["slot"] = df["time"].apply(classify_slot)

        # Aggregate month-wise
        monthly_data = defaultdict(lambda: {"peak_1": 0.0, "peak_2": 0.0, "off_peak": 0.0, "normal": 0.0})

        for _, row in df.iterrows():
            m = row["month"]
            slot = row["slot"]
            monthly_data[m][slot] += row["generation"]

        # Round results
        result = {
            month: {k: round(v, 2) for k, v in slots.items()}
            for month, slots in monthly_data.items()
        }

        return result

    @staticmethod
    def banking_price_calculations(final_monthly_dict, generation_monthly, capacity, master_data, per_unit_cost):

        adjusted_dict = {}
        for month in final_monthly_dict:
            # Get corresponding data
            final_data = final_monthly_dict.get(month, {})
            solar_data = generation_monthly.get(month, {})
            adjusted_dict[month] = {}
            banked = 0
            not_met = 0
            for key in ['peak_1', 'peak_2', 'normal', 'off_peak']:
                final_value = final_data.get(key, 0)
                solar_value = solar_data.get(key, 0)
                # Subtract solar from actual and multiply
                adjusted_value = round(final_value - (solar_value * capacity) - banked, 2)

                logger.debug(f'======={key}=======')
                logger.debug(f'banked: {banked}')
                logger.debug(f'not_met: {not_met}')
                logger.debug(f'adjusted_value: {adjusted_value}')
                logger.debug('--------------------------------')
                if key == 'off_peak':
                    banked = 0
                while True:
                    # if the demand is not met
                    if adjusted_value > 0:
                        if banked == 0:
                            not_met += adjusted_value
                            break
                        else:
                            adjusted_value -= banked
                    # extra generation
                    else:
                        banked = abs(adjusted_value) * (1 - (master_data.banking_charges/100))
                        adjusted_dict[month]['curtailment'] = abs(adjusted_value)
                        break

                adjusted_dict[month][key] = adjusted_value
                adjusted_dict[month]['not_met'] = not_met

        # ✅ Result:
        logger.debug(f'adjusted values: {adjusted_dict}')
        total_unmet = sum(month_data.get("not_met", 0) for month_data in adjusted_dict.values())
        logger.debug(f"Total unmet: {total_unmet}")

        # curtailment
        curtailment = sum(month_data.get("curtailment", 0) for month_data in adjusted_dict.values())
        logger.debug(f"Curtailment: {curtailment}")

        total_demand = 0
        for month_data in final_monthly_dict.values():
            total_demand += sum(month_data.values())
        logger.debug(f"Total Demand: {total_demand}")

        demand_met = total_demand - total_unmet
        total_generation = 0
        for month_data in generation_monthly.values():
            total_generation += sum(month_data.values())
        logger.debug(f"Total Generation: {total_generation}")

        re_replacement = 1 - (total_unmet / total_demand)
        logger.debug(f"Re Replacement: {re_replacement}")

        generation_price = capacity * total_generation * per_unit_cost * 1000
        logger.debug(f"Generation Price: {generation_price}")

        banking_price = round(generation_price / demand_met, 2) # INR/MWh
        logger.debug(f"Banking Price: {banking_price}")

        return {
            "total_unmet": total_unmet,
            "curtailment": curtailment,
            "total_demand": total_demand,
            "demand_met": demand_met,
            "total_generation": total_generation,
            "re_replacement": re_replacement * 100,
            "generation_price": generation_price,
            "banking_price": banking_price
        }

    def post(self, request):
        data = request.data  # JSON body

        requirement = data.get("requirement")
        solar_id = data.get("solar_id")
        wind_id = data.get("wind_id")
        numeric_hourly_demand = data.get("numeric_hourly_demand")
        per_unit_cost = data.get("per_unit_cost")
        logger.debug(f'Per unit cost------------- {per_unit_cost}')

        try:
            requirement = ConsumerRequirements.objects.get(id=requirement)
            master_data = MasterTable.objects.get(state=requirement.state)
            monthly_consumption = MonthlyConsumptionData.objects.filter(requirement=requirement)
            peak_config = PeakHours.objects.get(state__name=requirement.state)
            solar = SolarPortfolio.objects.get(id=solar_id) if solar_id else None
            wind = WindPortfolio.objects.get(id=wind_id) if wind_id else None

            solar_monthly = {}
            wind_monthly = {}

            if solar:
                available_capacity_solar = solar.available_capacity
                profile = OptimizeCapacityAPI.extract_profile_data(solar.hourly_data.path)
                state = solar.state
                s_project = solar.project
                solar_ipp = solar.user.username
                solar_monthly = self.calculate_monthly_slot_generation(profile, state)
                logger.debug(f'Solar monthly data: {solar_monthly}')
                
            if wind:
                available_capacity_wind = wind.available_capacity
                profile = OptimizeCapacityAPI.extract_profile_data(wind.hourly_data.path)
                state = wind.state
                w_project = wind.project
                wind_ipp = wind.user.username
                wind_monthly = self.calculate_monthly_slot_generation(profile, state)
                logger.debug(f'Wind monthly data: {wind_monthly}')

            final_monthly_dict = {}
            if peak_config.peak_start_1 and peak_config.peak_end_1 and peak_config.peak_start_2 and peak_config.peak_end_2:
                
                peak_1_hours = peak_config.peak_end_1.hour - peak_config.peak_start_1.hour
                peak_2_hours = peak_config.peak_end_2.hour - peak_config.peak_start_2.hour
                total_peak_hours = peak_1_hours + peak_2_hours

                for month_data in monthly_consumption:
                    # Get month number from name
                    month_number = list(calendar.month_name).index(month_data.month)
                    if month_number == 0:
                        continue  # skip invalid month

                    days_in_month = monthrange(2025, month_number)[1]
                    total_peak_consumption = month_data.peak_consumption

                    # Split peak consumption
                    peak_1_consumption = round((peak_1_hours / total_peak_hours) * total_peak_consumption, 2)
                    peak_2_consumption = round((peak_2_hours / total_peak_hours) * total_peak_consumption, 2)

                    off_peak_value = month_data.off_peak_consumption

                    normal_value = round(
                        month_data.monthly_consumption - (total_peak_consumption + off_peak_value), 2
                    )

                    # Save to dictionary
                    final_monthly_dict[month_number] = {
                        'peak_1': peak_1_consumption,
                        'peak_2': peak_2_consumption,
                        'off_peak': off_peak_value,
                        'normal': normal_value
                    }
            

            # final_monthly_dict = {1: {'peak_1': 135.718, 'peak_2': 0, 'off_peak': 135.718, 'normal': 157.561}, 2: {'peak_1': 142.975, 'peak_2': 0, 'off_peak': 142.975, 'normal': 162.059}, 3: {'peak_1': 135.531, 'peak_2': 0, 'off_peak': 135.531, 'normal': 150.038}, 4: {'peak_1': 142.832, 'peak_2': 0, 'off_peak': 142.832, 'normal': 165.669}, 5: {'peak_1': 154.122, 'peak_2': 0, 'off_peak': 154.122, 'normal': 181.509}, 6: {'peak_1': 147.186, 'peak_2': 0, 'off_peak': 147.186, 'normal': 172.573}, 7: {'peak_1': 159.819, 'peak_2': 0, 'off_peak': 159.819, 'normal': 195.103}, 8: {'peak_1': 154.073, 'peak_2': 0, 'off_peak': 154.073, 'normal': 185.739}, 9: {'peak_1': 152.705, 'peak_2': 0, 'off_peak': 152.705, 'normal': 181.539}, 10: {'peak_1': 113.608, 'peak_2': 0, 'off_peak': 113.608, 'normal': 108.177}, 11: {'peak_1': 110.183, 'peak_2': 0, 'off_peak': 110.183, 'normal': 97.058}, 12: {'peak_1': 112.441, 'peak_2': 0, 'off_peak': 112.441, 'normal': 108.886}}

            # solar_monthly = {1: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 2: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 3: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 4: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 5: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 6: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 7: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 8: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 9: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 10: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 11: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}, 12: {'peak_1': 3, 'peak_2': 0, 'off_peak': 0, 'normal': 10}}

            results_solar = None
            if solar:
                logger.debug(f'final_monthly_dict: {final_monthly_dict}')
                logger.debug(f'solar_monthly: {solar_monthly}')
                low = 1
                high = available_capacity_solar
                precision = 0.01
                max_iterations = 100
                for _ in range(max_iterations):
                    mid = (low + high) / 2
                    logger.debug(f'solar capacity---- {mid}')
                    results_solar = self.banking_price_calculations(final_monthly_dict, solar_monthly, mid, master_data, per_unit_cost)
                    current_re = results_solar["re_replacement"]

                    if abs(current_re - 65) < precision:
                        break
                    elif current_re < 65:
                        low = mid
                    else:
                        high = mid
                results_solar['combination'] = f'{solar_ipp}-{s_project}'
                results_solar['s_capacity'] = mid
                results_solar['w_capacity'] = 0
                results_solar['b_capacity'] = 0


            results_wind = None
            if wind:
                logger.debug(f'final_monthly_dict: {final_monthly_dict}')
                logger.debug(f'wind_monthly: {wind_monthly}')
                low = 1
                high = available_capacity_wind
                precision = 0.01
                max_iterations = 100
                for _ in range(max_iterations):
                    mid = (low + high) / 2
                    logger.debug(f'wind capacity---- {mid}')
                    results_wind = self.banking_price_calculations(final_monthly_dict, wind_monthly, mid, master_data, per_unit_cost)
                    current_re = results_solar["re_replacement"]

                    if abs(current_re - 65) < precision:
                        break
                    elif current_re < 65:
                        low = mid
                    else:
                        high = mid
                results_wind['combination'] = f'{wind_ipp}-{w_project}'
                results_wind['s_capacity'] = 0
                results_wind['w_capacity'] = mid
                results_wind['b_capacity'] = 0


            final_response = {
                "solar": results_solar,
                "wind": results_wind
            }

            return Response(final_response, status=status.HTTP_200_OK)

        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class OptimizeCapacityAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @staticmethod
    def extract_profile_data(file_path):
                
        # Read the specified sheet from the Excel file
        df = pd.read_excel(file_path)
        logger.debug('df')
        logger.debug(df)

        df_cleaned = df.iloc[0:, 1].reset_index(drop=True)
        logger.debug('df cleaned')
        logger.debug(df_cleaned)


        # Fill NaN values with 0
        profile = df_cleaned.fillna(0).reset_index(drop=True)
        logger.debug('Profile:')
        logger.debug(profile)
                
        return profile
    

    @staticmethod
    def calculate_hourly_demand(consumer_requirement, state="Maharashtra"):
        consumer_demand = HourlyDemand.objects.get(requirement=consumer_requirement)

        # # Define the state-specific hours
        # state_hours = {
        #     "Madhya Pradesh": {
        #         "peak_hours_1": (6, 9),  # 6 AM to 9 AM
        #         "peak_hours_2": (17, 22),  # 5 PM to 10 PM
        #         "off_peak_hours": (22, 6),  # 10 PM to 6 AM
        #     }
        # }
        hours = PeakHours.objects.filter(state__name=state).first()
        if not hours:
            return Response({"error": f"No peak hours data found for state {state}."}, status=status.HTTP_404_NOT_FOUND)

        monthly_consumptions = MonthlyConsumptionData.objects.filter(requirement=consumer_requirement)

        # Get state-specific hours
        # Get state-specific peak and off-peak hours
        peak_hours_1 = (hours.peak_start_1.hour, hours.peak_end_1.hour)
        peak_hours_2 = (hours.peak_start_2.hour, hours.peak_end_2.hour) if hours.peak_start_2 and hours.peak_end_2 else (0, 0)
        off_peak_hours = (hours.off_peak_start.hour, hours.off_peak_end.hour) if hours.off_peak_start and hours.off_peak_end else (0, 0)
        logger.debug(peak_hours_1)
        logger.debug(peak_hours_2)
        logger.debug(off_peak_hours)


        # Calculate total hours for all ranges
        total_hours = 24
        peak_hours_total = hours.calculate_peak_hours()
        off_peak_hours_total = hours.calculate_off_peak_hours()
        normal_hours = total_hours - peak_hours_total - off_peak_hours_total
        logger.debug(f'normal_hours = {total_hours} - {peak_hours_total} - {off_peak_hours_total}')
        logger.debug(f'Total peak hours: {peak_hours_total}')
        logger.debug(f'Total off peak hours: {off_peak_hours_total}')
        logger.debug(f'Normal hours: {normal_hours}')

        # Initialize a list to store hourly data
        all_hourly_data = []

        logger.debug("not entered....")
        print(monthly_consumptions)
        for month_data in monthly_consumptions:
            logger.debug("entered....")
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
            normal_hour_value = round(normal_consumption / (normal_hours * days_in_month), 3)
            peak_hour_value = round(month_data.peak_consumption / ((peak_hours_total) * days_in_month), 3)
            # Calculate off-peak hour value safely
            if off_peak_hours_total > 0:
                off_peak_hour_value = round(month_data.off_peak_consumption / ((off_peak_hours_total) * days_in_month), 3)
            else:
                off_peak_hour_value = 0
                logger.debug(f'Off-peak hours not defined or zero for state {state}. Skipping off-peak consumption division.')

            logger.debug(f'normal_consumption = month_data.monthly_consumption - (month_data.peak_consumption + month_data.off_peak_consumption)')
            logger.debug(f'normal_consumption = {month_data.monthly_consumption} - ({month_data.peak_consumption} + {month_data.off_peak_consumption}) = {normal_consumption}')
            logger.debug(f'Normal hour value: {normal_hour_value}')
            logger.debug(f'Peak hour value: {peak_hour_value}')
            logger.debug(f'Off peak hour value: {off_peak_hour_value}')

            # Distribute values across the hours of each day
            for day in range(1, days_in_month + 1):
                for hour in range(24):
                    if hour == 24:
                        hour = 0
                    # Peak hours condition
                    if peak_hours_1[0] <= hour < peak_hours_1[1] or peak_hours_2[0] <= hour < peak_hours_2[1]:
                        all_hourly_data.append(peak_hour_value)
                    # Off-peak hours condition (split into two cases)
                    elif off_peak_hours_total > 0 and (off_peak_hours[0] <= hour < 24) or (0 <= hour < off_peak_hours[1]):
                        all_hourly_data.append(off_peak_hour_value)
                    # Normal hours condition
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
        user_id = data.get("user_id")
        id = data.get("requirement_id")
        if data.get("re_replacement"):
            re_replacement = int(data.get("re_replacement"))
        elif data.get("re_replacement") == 0:
            return Response({"error": "No available capacity."}, status=status.HTTP_200_OK)
        else:
            re_replacement = None
        

         # Check optimize_capacity value
        if optimize_capacity_user == "Consumer":
            try:
                matching_ipps = MatchingIPP.objects.get(requirement=id)
            except MatchingIPP.DoesNotExist:
                return Response({"error": "Failed to fetch IPP, Please select requirement and try again."}, status=status.HTTP_404_NOT_FOUND)
            generator_id = matching_ipps.generator_ids
        elif optimize_capacity_user == "Generator":
            generator_id = [user_id]  # Normalize to a list for consistent processing
        else:
            return Response(
                {"error": "Invalid value for 'optimize_capacity'. Must be 'consumer' or 'generator'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Fetch consumer details
            # consumer = User.objects.get(email=consumer_email)
            consumer_requirement = ConsumerRequirements.objects.get(id=id)
            grid_tariff = GridTariff.objects.get(state=consumer_requirement.state, tariff_category=consumer_requirement.tariff_category)
            master_record = MasterTable.objects.get(state=consumer_requirement.state)
            record = RETariffMasterTable.objects.filter(industry=consumer_requirement.sub_industry).first()
            # Initialize final aggregated response
            aggregated_response = {}

            # Define the three states of connectivity
            connectivity_states = ["CTU", "STU", "Discom"]

            # Loop over each connectivity state
            for connectivity in connectivity_states:
                input_data = {}  # Initialize the final dictionary
                new_list = []
            
                for id in generator_id:
                    generator = User.objects.get(id=id)
                    last_10_combinations = Combination.objects.filter(requirement__sub_industry = consumer_requirement.sub_industry, generator=generator).order_by('-id')[:10]
                    # Check if there are 10 or more records
                    if last_10_combinations.count() >= 10:
                        # Calculate the average
                        average_per_unit_cost = last_10_combinations.aggregate(Avg('per_unit_cost'))['per_unit_cost__avg']
                        re = round(average_per_unit_cost/2)
                    elif record:
                        re = record.re_tariff
                    else:
                        re = 4

                    if optimize_capacity_user == "consumer":

                        if not SubscriptionEnrolled.objects.filter(user=generator, status='active').exists():
                            message = "You have not subscribed yet. Please subscribe so that you don't miss the perfect matchings."
                            send_notification(generator.id, message)
                            new_list.append(id)
                            continue


                    # Query generator's portfolios
                    solar_data = SolarPortfolio.objects.filter(
                        user=generator
                    ).filter(
                        Q(state=consumer_requirement.state) | Q(connectivity="CTU")
                    )
                    wind_data = WindPortfolio.objects.filter(
                        user=generator
                    ).filter(
                        Q(state=consumer_requirement.state) | Q(connectivity="CTU")
                    )
                    ess_data = ESSPortfolio.objects.filter(
                        user=generator
                    ).filter(
                        Q(state=consumer_requirement.state) | Q(connectivity="CTU")
                    )

                    logger.debug('Before connectivity filtering:')
                    logger.debug(f'solar_data: {solar_data}')
                    logger.debug(f'wind_data: {wind_data}') 
                    logger.debug(f'ess_data: {ess_data}')
                    
                    # separating combinations based on connectivity 
                    solar_data = solar_data.filter(connectivity=connectivity)
                    wind_data = wind_data.filter(connectivity=connectivity)
                    ess_data = ess_data.filter(connectivity=connectivity)

                    logger.debug('After connectivity filtering:')
                    logger.debug(f'solar_data: {solar_data}')
                    logger.debug(f'wind_data: {wind_data}') 
                    logger.debug(f'ess_data: {ess_data}')

                    portfolios = list(chain(solar_data, wind_data, ess_data))

                    include_ISTS = False
                    for p in portfolios:
                        if p.connectivity == "CTU":
                            include_ISTS = True
                            break
                        elif p.state == consumer_requirement.state:
                            include_ISTS = False
                            break

                    if not portfolios:
                        include_ISTS = True

                    ISTS_charges = master_record.ISTS_charges if include_ISTS else 0
                    logger.debug(f'Including ISTS charges: {include_ISTS}, charges: {ISTS_charges}')
                    logger.debug(f'Including state charges: {master_record.state_charges}')

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

                            if not solar.hourly_data:
                                continue

                            # Extract profile data from file
                            profile_data = self.extract_profile_data(solar.hourly_data.path)

                            # Divide all rows by 5
                            profile_data = profile_data / solar.available_capacity # model algorithm considering profile for per MW so that's why we are dividing profile by available capacity

                            input_data[generator.username]["Solar"][solar.project] = {
                                "profile": profile_data,
                                "max_capacity": solar.available_capacity,
                                "marginal_cost": solar.expected_tariff * 1000,
                                "capital_cost": solar.capital_cost,
                            }

                    # Add Wind projects if wind_data exists
                    if wind_data.exists():
                        input_data[generator.username]["Wind"] = {}
                        for wind in wind_data:

                            wind_project.append(wind.project)

                            if not wind.hourly_data:
                                continue

                            # Extract profile data from file
                            profile_data = self.extract_profile_data(wind.hourly_data.path)

                            # Divide all rows by 5
                            profile_data = profile_data / wind.available_capacity # model algorithm considering profile for per MW so that's why we are dividing profile by available capacity
                            
                            input_data[generator.username]["Wind"][wind.project] = {
                                "profile": profile_data,
                                "max_capacity": wind.available_capacity,
                                "marginal_cost": wind.expected_tariff * 1000,
                                "capital_cost": wind.capital_cost,
                            }
                    logger.debug(f'wind_input_data: {input_data}')

                    # Add ESS projects if ess_data exists
                    if ess_data.exists():
                        input_data[generator.username]["ESS"] = {}
                        for ess in ess_data:

                            ess_project.append(ess.project)

                            input_data[generator.username]["ESS"][ess.project] = {
                                "DoD": ess.efficiency_of_dispatch,
                                "efficiency": ess.efficiency_of_dispatch,
                                "marginal_cost": ess.expected_tariff * 1000,
                                "capital_cost": ess.capital_cost,
                            }

                # Extract generator name and project lists
                # gen = next(iter(input_data.keys()))
                # solar_projects = list(input_data[gen]['Solar'].keys()) if 'Solar' in input_data[gen] else []
                # wind_projects = list(input_data[gen]['Wind'].keys()) if 'Wind' in input_data[gen] else []
                # ess_projects = list(input_data[gen]['ESS'].keys()) if 'ESS' in input_data[gen] else []

                # Ensure at least one valid project list is available
                # if not (solar_projects or wind_projects or ess_projects):
                #     return Response({"error": "No valid projects found in input data"}, status=status.HTTP_400_BAD_REQUEST)

                # Handle missing project types by using ["None"] as a placeholder
                # combinations = [
                #     "-".join(filter(None, [gen, solar, wind, ess]))  # Removes empty parts
                #     for solar, wind, ess in product(
                #         solar_projects if solar_projects else [None], 
                #         wind_projects if wind_projects else [None], 
                #         ess_projects if ess_projects else [None]
                #     )
                # ]

                # print('c ', combinations)
                valid_combinations = []  
                # for combo in combinations:
                #     combination = Combination.objects.filter(requirement=consumer_requirement, combination=combo).first()
                #     if combination is not None:
                #         # combination = dict(combination)
                #         valid_combinations.append(combo)

                if new_list != generator_id:

                    HourlyDemand.objects.get_or_create(requirement=consumer_requirement)
                    hourly_demand_instance = HourlyDemand.objects.get(requirement=consumer_requirement)

                    if hourly_demand_instance and hourly_demand_instance.hourly_demand is not None:
                        # Split the comma-separated string into a list of values
                        hourly_demand_list = hourly_demand_instance.hourly_demand.split(',')
                        # Convert list to a Pandas Series (ensures it has an index)
                        hourly_demand_series = pd.Series(hourly_demand_list)
                        # Convert all values to numeric (float), coercing errors to NaN
                        numeric_hourly_demand = pd.to_numeric(hourly_demand_series, errors='coerce')
                        # Print the numeric Series with index numbers
                    else:
                        # monthly data conversion in hourly data
                        numeric_hourly_demand = self.calculate_hourly_demand(consumer_requirement, consumer_requirement.state)

                    
                    logger.debug('Hourly Demand:')
                    logger.debug(numeric_hourly_demand)
                    # 8760 rows should be there if more then remove extra and if less then show error
                    if len(numeric_hourly_demand) > 8760:
                        hourly_demand = hourly_demand.iloc[:8760]
                    elif len(numeric_hourly_demand) < 8760:
                        padding_length = 8760 - len(numeric_hourly_demand)
                        numeric_hourly_demand = pd.concat([numeric_hourly_demand, pd.Series([0] * padding_length)], ignore_index=True)
                    
                    logger.debug(f'length: {len(numeric_hourly_demand)}')
                    logger.debug(re_replacement)
                    logger.debug(input_data)
                    response_data = optimization_model(input_data, hourly_demand=numeric_hourly_demand, re_replacement=re_replacement, valid_combinations=valid_combinations, OA_cost=(ISTS_charges + master_record.state_charges)*1000)
                    logger.debug(response_data)

                    # if response_data != 'The demand cannot be met by the IPPs':
                    if not response_data.get('error'):
                        for combination_key, details in response_data.items():
                        # Extract user and components from combination_key
                            components = combination_key.split('-')
                            

                            # Safely extract components, ensuring that we have enough elements
                            username = components[0] if len(components) > 0 else None  # Example: 'IPP241'
                            component_1 = components[1] if len(components) > 1 else None  # Example: 'Solar_1' (if present)
                            component_2 = components[2] if len(components) > 2 else None  # Example: 'Wind_1' (if present)
                            component_3 = components[3] if len(components) > 3 else None  # Example: 'ESS_1' (if present)

                            generator = User.objects.get(username=username)
                            logger.debug(f'generator: {generator.username}')

                            solar = wind = ess = None
                            solar_state = wind_state = ess_state = None

                            # Helper function to fetch the component and its COD
                            def get_component_and_cod(component_name, generator, portfolio_model):
                                try:
                                    portfolio = portfolio_model.objects.get(user=generator, project=component_name)
                                    return portfolio, portfolio.cod, portfolio.state, portfolio.site_name, portfolio.capital_cost
                                except portfolio_model.DoesNotExist:
                                    return None, None, None, None, None

                            # Fetch solar, wind, and ESS components and their CODs
                            if component_1:
                                logger.debug('component 1')
                                if 'Solar' in component_1:
                                    solar, solar_cod, solar_state, solar_site, solar_capital_cost = get_component_and_cod(component_1, generator, SolarPortfolio)
                                elif 'Wind' in component_1:
                                    wind, wind_cod, wind_state, wind_site, wind_capital_cost = get_component_and_cod(component_1, generator, WindPortfolio)
                                elif 'ESS' in component_1:
                                    ess, ess_cod, ess_state, ess_site, ess_capital_cost = get_component_and_cod(component_1, generator, ESSPortfolio)

                            if component_2:
                                logger.debug('component 2')
                                if 'Wind' in component_2:
                                    wind, wind_cod, wind_state, wind_site, wind_capital_cost = get_component_and_cod(component_2, generator, WindPortfolio)
                                elif 'ESS' in component_2:
                                    ess, ess_cod, ess_state, ess_site, ess_capital_cost = get_component_and_cod(component_2, generator, ESSPortfolio)

                            if component_3:
                                logger.debug('component 3')
                                if 'ESS' in component_3:
                                    ess, ess_cod, ess_state, ess_site, ess_capital_cost = get_component_and_cod(component_3, generator, ESSPortfolio)

                            # Determine the greatest COD
                            cod_dates = [solar_cod if solar else None, wind_cod if wind else None, ess_cod if ess else None]
                            cod_dates = [date for date in cod_dates if date is not None]
                            greatest_cod = max(cod_dates) if cod_dates else None

                            if solar:
                                logger.debug(f'ssss: {solar.connectivity} {solar.banking_available} {solar.user.username}')
                            else:
                                logger.debug('nooooo solar')

                            if wind:
                                logger.debug(f'ssss: {wind.connectivity} {wind.banking_available} {wind.user.username}')
                            else:
                                logger.debug('nooooo wind')

                            # Prepare query parameters for the GET request
                            banking_data = {
                                "requirement": consumer_requirement.id,
                                "numeric_hourly_demand": list(numeric_hourly_demand),
                                "solar_id": solar.id if solar and solar.connectivity == 'STU' and solar.banking_available else None,
                                "wind_id": wind.id if wind and wind.connectivity == 'STU' and wind.banking_available else None,
                                "per_unit_cost": round(details["Per Unit Cost"] / 1000, 2)
                            }
                            
                            # Forward token received from frontend
                            auth_header = request.META.get('HTTP_AUTHORIZATION')  # 'Bearer <token>'
                            headers = {
                                "Authorization": auth_header,
                                "Content-Type": "application/json"
                            }
                            if settings.ENVIRONMENT == 'local':
                                logger.debug('Local environment detected')
                                url="http://127.0.0.1:8000/api/energy/banking-charges"
                            else:
                                url="https://ext.exgglobal.com/api/api/energy/banking-charges"

                            logger.debug(f'Banking Data: {banking_data}')
                            logger.debug('not entered in condition..............')
                            if any([banking_data["solar_id"], banking_data["wind_id"]]):
                                logger.debug('entered in condition..............')
                                try:
                                    banking_response = requests.post(
                                        url=url,
                                        json=banking_data,
                                        # headers=headers
                                    )
                                    if banking_response.status_code == 200:
                                        banking_result = banking_response.json()
                                        logger.debug(f"BankingCharges result for {combination_key}: {banking_result}")
                                        solar_data = banking_result['solar'] if banking_result['solar'] else None
                                        wind_data = banking_result['wind'] if banking_result['wind'] else None
                                        for i in range(2):
                                            if i == 0 and solar_data:
                                                data = solar_data
                                                state = solar.state
                                                site_name = solar.site_name
                                                cod = solar.cod
                                                capital_cost_solar = solar.capital_cost
                                                capital_cost_wind = 0
                                                capital_cost_ess = 0
                                            elif i == 1 and wind_data:
                                                data = wind_data
                                                state = wind.state
                                                site_name = wind.site_name
                                                cod = wind.cod
                                                capital_cost_solar = 0
                                                capital_cost_wind = wind.capital_cost
                                                capital_cost_ess = 0

                                            combo = Combination.objects.filter(combination=data['combination'], requirement=consumer_requirement, annual_demand_offset=round(data["re_replacement"], 0)).first()
                                            terms_sheet = StandardTermsSheet.objects.filter(combination=combo).first()

                                            terms_sheet_sent = False
                                            if combo:
                                                terms_sheet_sent = combo.terms_sheet_sent
                                            else:
                                                banking_price = round(data["banking_price"] / 1000, 2)
                                                # Save to Combination table
                                                combo, created = Combination.objects.get_or_create(
                                                    requirement=consumer_requirement,
                                                    generator=generator,
                                                    re_replacement=round(data["re_replacement"], 0),
                                                    combination=data['combination'],
                                                    state=state,
                                                    optimal_solar_capacity=round(data["s_capacity"], 2),
                                                    optimal_wind_capacity=round(data["w_capacity"], 2),
                                                    optimal_battery_capacity=round(data["b_capacity"], 2),
                                                    per_unit_cost=banking_price,
                                                    final_cost=banking_price + master_record.state_charges,
                                                    annual_demand_offset=round(data["re_replacement"], 0),
                                                    annual_demand_met=data['demand_met'],
                                                    annual_curtailment=data['curtailment'],
                                                    banking_available=True
                                                )

                                            sent_from_you = False
                                            if terms_sheet:
                                                if terms_sheet.from_whom == optimize_capacity_user:
                                                    sent_from_you = True
                                                else:
                                                    sent_from_you = False

                                            re_index = generator.re_index
                                            if re_index is None:
                                                re_index = 0

                                            if optimize_capacity_user == "Consumer":
                                                mapped_username = consumer_requirement.user.username
                                            else:
                                                # Map the consumer username specific to the generator
                                                mapped_username = get_mapped_username(generator, consumer_requirement.user)

                                            if data['combination'] not in aggregated_response:
                                                aggregated_response[data['combination']] = {
                                                    **data,
                                                    'Per Unit Cost': combo.per_unit_cost,
                                                    'Final Cost': combo.final_cost,
                                                    'OA_cost': ISTS_charges + master_record.state_charges,
                                                    'ISTS_charges': ISTS_charges,
                                                    'state_charges': master_record.state_charges,
                                                    "state": state,
                                                    "site_names": site_name,
                                                    "greatest_cod": cod,
                                                    "terms_sheet_sent": terms_sheet_sent,
                                                    "sent_from_you": sent_from_you,
                                                    "connectivity": "STU",
                                                    "re_index": re_index,
                                                    "elite_generator": generator.elite_generator,
                                                    "per_unit_savings": grid_tariff.cost - combo.per_unit_cost - ISTS_charges - master_record.state_charges,
                                                    "capital_cost_solar": capital_cost_solar,
                                                    "capital_cost_wind": capital_cost_wind,
                                                    "capital_cost_ess": capital_cost_ess,
                                                    "banking_available": True,
                                                    "downloadable": {
                                                        "consumer": mapped_username,
                                                        "generator": generator.username,
                                                        "consumer_state": consumer_requirement.state,
                                                        "generator_state": combo.state,
                                                        "cod": combo.state,
                                                        # "term_of_ppa": record.term_of_ppa,
                                                        # "lock_in_period": record.lock_in_period,
                                                        "minimum_generation_obligation": round(combo.annual_demand_met * 0.8, 2),
                                                        "voltage_level_of_generation": combo.requirement.voltage_level,
                                                        # "tariff_finalized": offer_tariff.offer_tariff,
                                                        # "payment_security_day": record.payment_security_day,
                                                        "solar": combo.optimal_solar_capacity,
                                                        "wind": combo.optimal_wind_capacity,
                                                        "ess": combo.optimal_battery_capacity,
                                                    }
                                                }
                                    else:
                                        logger.error(f"BankingCharges API failed: {banking_response.content}")
                                except Exception as e:
                                    tb = traceback.format_exc()  # Get the full traceback
                                    traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
                                    logger.error(f"Error calling BankingCharges API: {e}")



                            # Map each portfolio to its state
                            state = {}
                            if solar:
                                state[solar.project] = solar_state
                            if wind:
                                state[wind.project] = wind_state
                            if ess:
                                state[ess.project] = ess_state

                            # Map each portfolio to its site name
                            site_names = {}
                            if solar:
                                site_names[solar.project] = solar_site
                            if wind:
                                site_names[wind.project] = wind_site
                            if ess:
                                site_names[ess.project] = ess_site

                            # Initialize capital costs
                            capital_cost_solar = solar.capital_cost if solar else 0
                            capital_cost_wind = wind.capital_cost if wind else 0
                            capital_cost_ess = ess.capital_cost if ess else 0

                            annual_demand_met = (details["Annual Demand Met"]) / 1000
                            logger.debug(f'combination_key:::::: {combination_key}')
                            logger.debug(f'consumer_requirement:::::: {consumer_requirement}')
                            logger.debug(f'Annual Demand Offset:::::: {details["Annual Demand Offset"]}')
                            combo = Combination.objects.filter(combination=combination_key, requirement=consumer_requirement, annual_demand_offset=details["Annual Demand Offset"]).first()
                            terms_sheet = StandardTermsSheet.objects.filter(combination=combo).first()

                            terms_sheet_sent = False
                            if combo:
                                terms_sheet_sent = combo.terms_sheet_sent
                            else:
                                # Save to Combination table
                                combo, created = Combination.objects.get_or_create(
                                    requirement=consumer_requirement,
                                    generator=generator,
                                    re_replacement=re_replacement if re_replacement else 65,
                                    combination=combination_key,
                                    state=state,
                                    optimal_solar_capacity=details["Optimal Solar Capacity (MW)"],
                                    optimal_wind_capacity=details["Optimal Wind Capacity (MW)"],
                                    optimal_battery_capacity=details["Optimal Battery Capacity (MW)"],
                                    per_unit_cost=details["Per Unit Cost"]/1000,
                                    final_cost=details['Final Cost'] / 1000,
                                    annual_demand_offset=details["Annual Demand Offset"],
                                    annual_demand_met=annual_demand_met,
                                    annual_curtailment=details["Annual Curtailment"]
                                )

                            sent_from_you = False
                            if terms_sheet:
                                if terms_sheet.from_whom == optimize_capacity_user:
                                    sent_from_you = True
                                else:
                                    sent_from_you = False

                            re_index = generator.re_index

                            if re_index is None:
                                re_index = 0

                            OA_cost = (details["Final Cost"] - details['Per Unit Cost']) / 1000
                            details['Per Unit Cost'] = details['Per Unit Cost'] / 1000
                            details['Final Cost'] = details['Final Cost'] / 1000
                            details["Annual Demand Met"] = (details["Annual Demand Met"]) / 1000
                            logger.debug('=============')
                            logger.debug(f'{grid_tariff.cost} - {re} - {ISTS_charges} - {master_record.state_charges}')
                            logger.debug('=============')

                            if optimize_capacity_user == "Consumer":
                                mapped_username = consumer_requirement.user.username
                            else:
                                # Map the consumer username specific to the generator
                                mapped_username = get_mapped_username(generator, consumer_requirement.user)
                            # Update the aggregated response dictionary
                            if combination_key not in aggregated_response:
                                aggregated_response[combination_key] = {
                                    **details,
                                    'OA_cost': ISTS_charges + master_record.state_charges,
                                    'ISTS_charges': ISTS_charges,
                                    'state_charges': master_record.state_charges,
                                    "state": state,
                                    "site_names": site_names,
                                    "greatest_cod": greatest_cod,
                                    "terms_sheet_sent": terms_sheet_sent,
                                    "sent_from_you": sent_from_you,
                                    "connectivity": connectivity,
                                    "re_index": re_index,
                                    "elite_generator": generator.elite_generator,
                                    "per_unit_savings": grid_tariff.cost - details['Per Unit Cost'] - ISTS_charges - master_record.state_charges,
                                    "capital_cost_solar": capital_cost_solar,
                                    "capital_cost_wind": capital_cost_wind,
                                    "capital_cost_ess": capital_cost_ess,
                                    "downloadable": {
                                        "consumer": mapped_username,
                                        "generator": generator.username,
                                        "consumer_state": consumer_requirement.state,
                                        "generator_state": combo.state,
                                        "cod": combo.state,
                                        # "term_of_ppa": record.term_of_ppa,
                                        # "lock_in_period": record.lock_in_period,
                                        "minimum_generation_obligation": round(combo.annual_demand_met * 0.8, 2),
                                        "voltage_level_of_generation": combo.requirement.voltage_level,
                                        # "tariff_finalized": offer_tariff.offer_tariff,
                                        # "payment_security_day": record.payment_security_day,
                                        "solar": round(combo.optimal_solar_capacity, 2),
                                        "wind": round(combo.optimal_wind_capacity, 2),
                                        "ess": round(combo.optimal_battery_capacity, 2),
                                    }
                                }
                            else:
                                # Merge the details if combination already exists
                                aggregated_response[combination_key].update(details)
                            
                    
                    # Handle missing valid_combinations that are not in response_data
            #         for combination_key in valid_combinations:
            #             if combination_key not in aggregated_response:
            #                 # Fetch data from the database
            #                 combo = Combination.objects.filter(combination=combination_key, requirement=consumer_requirement).first()
                            
            #                 if combo:
            #                     terms_sheet = StandardTermsSheet.objects.filter(combination=combo).first()
            #                     terms_sheet_sent = combo.terms_sheet_sent if combo else False
            #                     sent_from_you = terms_sheet.from_whom == optimize_capacity_user if terms_sheet else False
            #                     generator = combo.generator
            #                     re_index = generator.re_index if generator.re_index is not None else 0
                                
            #                     aggregated_response[combination_key] = {
            #                         "Optimal Solar Capacity (MW)": combo.optimal_solar_capacity,
            #                         "Optimal Wind Capacity (MW)": combo.optimal_wind_capacity,
            #                         "Optimal Battery Capacity (MW)": combo.optimal_battery_capacity,
            #                         "Per Unit Cost": combo.per_unit_cost,
            #                         "Final Cost": combo.final_cost,
            #                         "Annual Demand Offset": combo.annual_demand_offset,
            #                         "Annual Demand Met": combo.annual_demand_met,
            #                         "Annual Curtailment": combo.annual_curtailment,
            #                         "OA_cost": (combo.final_cost - combo.per_unit_cost),
            #                         "state": combo.state,
            #                         "greatest_cod": None,  # Since we don’t recalculate it here
            #                         "terms_sheet_sent": terms_sheet_sent,
            #                         "sent_from_you": sent_from_you,
            #                         "connectivity": connectivity,
            #                         "re_index": re_index,
            #                     }

            #         # Print the final aggregated response
            #         print('rrrrrrrrrr')
            #         print(aggregated_response)

            #     else:
            #         return Response({"response": "No IPPs matched"}, status=status.HTTP_200_OK)

            # if not aggregated_response and len(valid_combinations) != 0:
            #     if combination_key not in aggregated_response:
            #         aggregated_response[combination_key] = {
            #             **details,
            #             'OA_cost': OA_cost,
            #             "state": state,
            #             "greatest_cod": greatest_cod,
            #             "terms_sheet_sent": terms_sheet_sent,
            #             "sent_from_you": sent_from_you,
            #             "connectivity": connectivity,
            #             "re_index": re_index,
            #         }
            #     else:
            #         # Merge the details if combination already exists
            #         aggregated_response[combination_key].update(details)
            if not aggregated_response and optimize_capacity_user=='Consumer':
                return Response({"error": "The demand cannot be met by the IPPs."}, status=status.HTTP_200_OK)
            elif not aggregated_response and optimize_capacity_user=='Generator':
                return Response({"error": "The demand cannot be met by your projects."}, status=status.HTTP_200_OK)
            

            # Extract top 3 records with the smallest "Per Unit Cost"
            top_three_records = sorted(aggregated_response.items(), key=lambda x: x[1]['Per Unit Cost'])[:3]
            # Function to round values to 2 decimal places
            def round_values(record):
                return {key: round(value, 2) if isinstance(value, (int, float)) else value for key, value in record.items()}
            # Round the values for the top 3 records
            top_three_records_rounded = {
                key: round_values(value) for key, value in top_three_records
            }   

            return Response(top_three_records_rounded, status=status.HTTP_200_OK)


        except User.DoesNotExist:
            return Response({"error": "Consumer or generator not found."}, status=status.HTTP_404_NOT_FOUND)

        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Consumer requirements not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e), "Traceback": tb}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class ConsumptionPatternAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, user_id):
        try:
            
            # Fetch MonthlyConsumptionData for the consumer
            consumption_data = MonthlyConsumptionData.objects.filter(requirement=pk).values('month', 'monthly_consumption', 'peak_consumption', 'off_peak_consumption', 'monthly_bill_amount')

            user = User.objects.get(id=user_id)

            # Check if consumption data exists
            if not consumption_data.exists():
                return Response(
                    {"error": "No consumption data found for the consumer."},
                    status=status.HTTP_404_NOT_FOUND
                )
            # Convert the month data to sorted month names (e.g., "Jan", "Feb", "Mar", ...)
            sorted_data = sorted(consumption_data, key=lambda x: datetime.strptime(x['month'], '%B'))

            consumption = MonthlyConsumptionData.objects.filter(requirement=pk).first()
            consumer = consumption.requirement.user

            if user.user_category == 'Generator':
                username = get_mapped_username(user, consumer)
            else:
                username = consumer.username

            # Extract relevant consumer details
            consumer_details = {
                "username": username,
                "credit_rating": consumer.credit_rating,
                "state": consumption.requirement.state,
                "tariff_category": consumption.requirement.tariff_category,
                "voltage_level": consumption.requirement.voltage_level,
                "contracted_demand": consumption.requirement.contracted_demand,
                "industry": consumption.requirement.industry
            }

            # Prepare response with the sorted monthly consumption data
            response_data = {
                "consumer_details": consumer_details,
                "monthly_consumption": [
                    {
                        "month": datetime.strptime(entry["month"], '%B').strftime('%b'),  # Convert to short month name (e.g., Jan, Feb)
                        "consumption": entry["monthly_consumption"],
                        "peak_consumption": entry["peak_consumption"],
                        "off_peak_consumption": entry["off_peak_consumption"],
                        "monthly_bill_amount": entry["monthly_bill_amount"],
                    }
                    for entry in sorted_data
                ]
            }

            return Response(response_data, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class StandardTermsSheetAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if pk:
            user = User.objects.get(id=pk)
            user = get_admin_user(pk)
            try:
                if user.user_category == 'Consumer':
                    records_from_consumer = StandardTermsSheet.objects.filter(consumer=user, from_whom ='Consumer')
                    records_from_generator = StandardTermsSheet.objects.filter(consumer=user, from_whom ='Generator')
                    StandardTermsSheet.objects.filter(consumer=user, consumer_is_read=False).update(consumer_is_read=True)
                else:
                    records_from_consumer = StandardTermsSheet.objects.filter(combination__generator=user, from_whom ='Consumer')
                    records_from_generator = StandardTermsSheet.objects.filter(combination__generator=user, from_whom ='Generator')
                    StandardTermsSheet.objects.filter(combination__generator=user, generator_is_read=False).update(generator_is_read=True)
                        
                # Combine the two record sets
                all_records = records_from_consumer | records_from_generator
                

                if not all_records.exists():
                    return Response({"error": "No Record found."}, status=status.HTTP_404_NOT_FOUND)


                # Serialize all records
                data = []
                for record in all_records:
                    serialized_record = StandardTermsSheetSerializer(record).data
                    offer_tariff = Tariffs.objects.get(terms_sheet=record)
                    serialized_record['offer_tariff'] = round(offer_tariff.offer_tariff, 2)
                    serialized_record['re_index'] = user.re_index
                    # Check if combination and requirement exist
                    if hasattr(record, 'combination') and hasattr(record.combination, 'requirement'):
                        req = record.combination.requirement
                        serialized_record['requirement'] = {
                            "rq_id": req.id,
                            "rq_state": req.state,
                            "rq_site": req.consumption_unit,
                            "rq_industry": req.industry,
                            "rq_contracted_demand": req.contracted_demand,
                            "rq_tariff_category": req.tariff_category,
                            "rq_voltage_level": req.voltage_level,
                            "rq_procurement_date": req.procurement_date,
                        }

                    # Add combination details manually
                    if hasattr(record, 'combination') and record.combination:
                        serialized_record['combination'] = {
                            "combination": record.combination.combination,
                            "re_replacement": record.combination.re_replacement,
                            "state": record.combination.state,
                            "optimal_solar_capacity": round(record.combination.optimal_solar_capacity, 2),
                            "optimal_wind_capacity": round(record.combination.optimal_wind_capacity, 2),
                            "optimal_battery_capacity": round(record.combination.optimal_battery_capacity, 2),
                            "re_capacity": round(record.combination.optimal_solar_capacity + record.combination.optimal_wind_capacity + record.combination.optimal_battery_capacity, 2),
                            "per_unit_cost": round(record.combination.per_unit_cost, 2),
                            "final_cost": round(record.combination.final_cost, 2),
                            # Add more fields as required
                        }

                    mapped_username = get_mapped_username(record.combination.generator, record.consumer)
                    if hasattr(record, 'combination') and record.combination:
                        serialized_record['downloadable'] = {
                            "consumer": mapped_username,
                            "generator": record.combination.generator.username,
                            "consumer_state": record.combination.requirement.state,
                            "generator_state": record.combination.state,
                            "cod": record.combination.state,
                            "term_of_ppa": record.term_of_ppa,
                            "lock_in_period": record.lock_in_period,
                            "minimum_generation_obligation": round(record.combination.annual_demand_met * 0.8, 2),
                            "voltage_level_of_generation": record.combination.requirement.voltage_level,
                            "tariff_finalized": offer_tariff.offer_tariff,
                            "payment_security_day": record.payment_security_day,
                            "solar": record.combination.optimal_solar_capacity,
                            "wind": record.combination.optimal_wind_capacity,
                            "ess": record.combination.optimal_battery_capacity,
                            "late_payment_surcharge": record.late_payment_surcharge,
                        }

                    transaction_window = NegotiationWindow.objects.filter(terms_sheet=record.id).first()
                    if transaction_window:
                        serialized_record['transaction_window_date'] = transaction_window.start_time
                    else:
                        serialized_record['transaction_window_date'] = None

                    data.append(serialized_record)

                    
                    
                    # Notify the WebSocket group to update the unread count
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"user_{pk}", {"type": "mark_terms_sheet_read"}
                    )
                
                return Response(data, status=status.HTTP_200_OK)

            except StandardTermsSheet.DoesNotExist:
                return Response({"error": "Record not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({"error": "Please send valid values of user id and category."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        # Extract requirement_id from the request data
        from_whom = request.data.get("from_whom")
        requirement_id = request.data.get("requirement_id")
        combination = request.data.get('combination')
        re_replacement = request.data.get('re_replacement')
        offer_tariff = request.data.get('offer_tariff')
        solar = request.data.get('solar_capacity')
        wind = request.data.get('wind_capacity')
        ess = request.data.get('ess_capacity')
        logger.debug(f'{solar}, {wind}, {ess}')

        if from_whom not in ['Consumer', 'Generator']:
            return Response({"error": "Invalid value for 'from_whom'."}, status=status.HTTP_400_BAD_REQEUST)

        if not requirement_id:
            return Response({"error": "requirement_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Invalid requirement_id."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            combination = Combination.objects.filter(combination=combination, re_replacement=re_replacement, requirement=requirement).order_by('-id').first()
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

       

        # Check if a term sheet for the same requirement and combination already exists
        existing_termsheet = StandardTermsSheet.objects.filter(combination=combination).first()

        if existing_termsheet and existing_termsheet.from_whom == 'Generator' and from_whom == 'Consumer':
            return Response({"error": "The term sheet is already sent by the generator for this combination."}, status=status.HTTP_400_BAD_REQUEST)
        elif existing_termsheet and existing_termsheet.from_whom == 'Generator' and from_whom == 'Generator':
            return Response({"error": "The term sheet is already sent by you for this combination."}, status=status.HTTP_400_BAD_REQUEST)
        elif existing_termsheet and existing_termsheet.from_whom == 'Consumer' and from_whom == 'Generator':
            return Response({"error": "The term sheet is already sent by the consumer for this combination."}, status=status.HTTP_400_BAD_REQUEST)
        elif existing_termsheet and existing_termsheet.from_whom == 'Consumer' and from_whom == 'Consumer':
            return Response({"error": "The term sheet is already sent by you for this combination."}, status=status.HTTP_400_BAD_REQUEST)

        # Add consumer and combination to the request data
        request_data = request.data.copy()
        request_data["consumer"] = requirement.user.id  # Set consumer ID

        request_data["combination"] = combination.id

        if from_whom == 'Consumer':
            request_data["generator_status"] = 'Offer Received'
        elif from_whom == 'Generator':
            request_data["consumer_status"] = 'Offer Received'
            combination.optimal_solar_capacity = solar
            combination.optimal_wind_capacity = wind
            combination.optimal_battery_capacity = ess
            combination.save()


        serializer = StandardTermsSheetSerializer(data=request_data)
        if serializer.is_valid():
            # Save the termsheet
            termsheet = serializer.save()
            combination.terms_sheet_sent = True
            combination.save()

            if from_whom == "Consumer":
                send_notification(termsheet.combination.generator.id, f'The consumer {termsheet.consumer.username} has sent you a terms sheet.')
            elif from_whom == "Generator":
                send_notification(termsheet.consumer.id, f'The generator {termsheet.combination.generator.username} has sent you a terms sheet.')
            else:
                return Response({"error": "Invalid value for 'from_whom'."}, status=status.HTTP_400_BAD_REQUEST)

            if from_whom == 'Consumer':
                Tariffs.objects.get_or_create(terms_sheet=termsheet, offer_tariff=termsheet.combination.per_unit_cost)
            else:
                Tariffs.objects.get_or_create(terms_sheet=termsheet, offer_tariff=offer_tariff)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, user_id, pk):
        try:
            user = User.objects.get(id=user_id)
            user = get_admin_user(user_id)
            record = StandardTermsSheet.objects.get(id=pk)
            action = request.data.get("action")  # Check for an 'action' key in the request payload

            if action in ['Accepted', 'Rejected']:
                record.consumer_status = action
                record.generator_status = action
                if action == 'Rejected':
                    record.combination.terms_sheet_sent = False

                record.save()
                return Response(
                    {"message": f"Terms sheet {action.lower()} successfully.", "record": StandardTermsSheetSerializer(record).data},
                    status=status.HTTP_200_OK,
                )
            
            # ✅ Handle Withdraw Action
            if action == 'Withdraw':
                # Only allow withdraw if status is not already accepted/rejected
                if record.consumer_status in ['Accepted', 'Rejected'] or record.generator_status in ['Accepted', 'Rejected']:
                    return Response(
                        {"error": "Cannot withdraw an offer that has already been accepted or rejected."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                record.consumer_status = 'Withdrawn'
                record.generator_status = 'Withdrawn'
                record.save()
                return Response(
                    {"message": "Terms sheet offer withdrawn successfully.", "record": StandardTermsSheetSerializer(record).data},
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
                record.consumer_status = 'Counter Offer Sent'
                record.generator_status = 'Counter Offer Received'
            else:  # Assuming the other user is a generator
                record.consumer_status = 'Counter Offer Received'
                record.generator_status = 'Counter Offer Sent'

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
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_type):
        # Get all subscription types
        subscription_types = SubscriptionType.objects.filter(user_type=user_type)

        # Serialize the subscription types
        serializer = SubscriptionTypeSerializer(subscription_types, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
        
class SubscriptionEnrolledAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticatedOrInternal]

    def get(self, request, pk):
        try:
            user = get_admin_user(pk)
            pk = user.id
            
            subscription = SubscriptionEnrolled.objects.filter(user=pk)
            
            subscription = SubscriptionEnrolled.objects.get(user=pk, status='active')
            
            data = {
                "id": subscription.id,
                "user": subscription.user.id,
                "subscription_type": subscription.subscription.subscription_type,
                "start_date": subscription.start_date,
                "end_date": subscription.end_date,
                "status": subscription.status,
            }
            
            return Response(data, status=status.HTTP_200_OK)
        except SubscriptionEnrolled.DoesNotExist:
            return Response({"message": "No subscription found for this user."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



    def post(self, request):
        user = request.data.get('user')
        user = get_admin_user(user)
        user_id = user.id

        subscription = request.data.get('subscription')
        try:
            subscription_obj = SubscriptionType.objects.get(id=subscription)
        except SubscriptionType.DoesNotExist:
            return Response({"error": "Invalid subscription ID."}, status=status.HTTP_400_BAD_REQUEST)

        today = date.today()

        # Get user's latest subscription
        existing_subscription = SubscriptionEnrolled.objects.filter(user=user_id).order_by('-end_date').first()

        if existing_subscription:
            # Prevent taking FREE again
            if subscription_obj.subscription_type == 'FREE':
                previously_taken_free = SubscriptionEnrolled.objects.filter(
                    user=user_id,
                    subscription__subscription_type='FREE'
                ).exists()

                if previously_taken_free:
                    return Response(
                        {"error": "You can take the FREE subscription only once."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # If an active subscription exists
            if existing_subscription.end_date >= today:
                # If upgrading from FREE to LITE/PRO, expire old and create new
                if existing_subscription.subscription.subscription_type == 'FREE' and subscription_obj.subscription_type in ['LITE', 'PRO']:
                    existing_subscription.status = 'expired'
                    existing_subscription.save()
                else:
                    return Response(
                        {"error": "You already have an active subscription."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # Expire old subscription if it's not active
                existing_subscription.status = 'expired'
                existing_subscription.save()

        # Ensure correct user is passed to serializer
        data = request.data.copy()
        data['user'] = user_id

        # Create new subscription with start date as today
        serializer = SubscriptionEnrolledSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def send_notification(user_id, message):
    """
    Ensures notification is created and triggers WebSocket update only for new notifications.
    """
    notification = Notifications.objects.create(user_id=user_id, message=message)

    unread_count = Notifications.objects.filter(user_id=user_id, is_read=False).count()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"notifications_{user_id}",
        {
            "type": "send_unread_count",
            "unread_count": unread_count,
        }
    )

    return notification
        
class NotificationsAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = get_admin_user(user_id)
            user_id = user.id
            # Fetch notifications based on user_id
            notifications = Notifications.objects.filter(user_id=user_id).order_by('-timestamp')
            # Serialize the notifications data
            serializer = NotificationsSerializer(notifications, many=True)

            # Mark notifications as read
            Notifications.objects.filter(user_id=user_id, is_read=False).update(is_read=True)

            # Send real-time update to WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"notifications_{user_id}",
                {
                    "type": "mark_notifications_read",
                    "unread_count": 0,
                }
            )
            
            # Return the response with serialized data
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Notifications.DoesNotExist:
            # Handle the case where no notifications are found
            return Response({"message": "No notifications found for this user."}, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            # Handle any other exceptions
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class NegotiateTariffView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

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
        offer_tariff = request.data.get('offer_tariff')
        terms_sheet_id = request.data.get('terms_sheet_id')
        token = secrets.token_hex(16)

        try:
            user = User.objects.get(id=user_id)
            user = get_admin_user(user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            terms_sheet = StandardTermsSheet.objects.get(id=terms_sheet_id)
        except StandardTermsSheet.DoesNotExist:
            return Response({"error": "Terms Sheet not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Get current time in timezone-aware format
        now_time = timezone.now()

        tz = timezone.get_current_timezone()
        start_date = timezone.now().date() + timedelta(weeks=1)

        while True:
            # Skip Saturdays and Sundays
            if start_date.weekday() in [5, 6]:
                start_date += timedelta(days=1)
                continue
            # Skip National Holidays
            if NationalHoliday.objects.filter(date=start_date).exists():
                start_date += timedelta(days=1)
                continue
            break

        # Return 10 AM of that day (aware datetime)
        next_day_10_am = datetime.combine(start_date, time(10, 0))
        next_day_10_am_aware = timezone.make_aware(next_day_10_am, timezone=tz)
        end_time = next_day_10_am_aware + timedelta(hours=1)
        
        
        # Only consumers can initiate the negotiation
        if user.user_category == 'Generator':
            # Notify the consumer linked in the terms sheet
            try:
                matching_ipps = MatchingIPP.objects.get(requirement=terms_sheet.combination.requirement)
                recipients = matching_ipps.generator_ids
                logger.debug(f'rrrrrrrr {recipients}')
                # Create the negotiation window record with date and time
                negotiation_window = NegotiationWindow.objects.create(
                    terms_sheet=terms_sheet,
                    start_time=next_day_10_am_aware,
                    end_time=end_time
                )

                # updated_tariff = request.data.get("updated_tariff")
                Tariffs.objects.get_or_create(terms_sheet=terms_sheet)
                tariff = Tariffs.objects.get(terms_sheet=terms_sheet)
                tariff.offer_tariff = offer_tariff
                tariff.save()
                
                GeneratorOffer.objects.get_or_create(generator=user, tariff=tariff, updated_tariff=offer_tariff)

                NegotiationInvitation.objects.create(negotiation_window=negotiation_window,user=terms_sheet.consumer)
                NegotiationInvitation.objects.create(negotiation_window=negotiation_window,user=user)

                # Notify recipients
                for recipient in recipients:
                    logger.debug(f'========== {recipient}')
                    if recipient == user.id:
                        logger.debug(f'========== generator {recipient}')
                        continue
                    try:
                        logger.debug(f'==========hhhhhhh')
                        recipient_user = User.objects.get(id=recipient)
                        # Map the consumer username specific to the generator
                        mapped_username = get_mapped_username(user, terms_sheet.consumer)
                        message=(
                            f"Consumer {mapped_username} has initiated a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh."
                            f"The negotiation window will open tomorrow at 10:00 AM. "
                            f"The starting offer tariff being provided is {offer_tariff} INR/kWh."
                        )
                        send_notification(recipient_user.id, message)

                        logger.debug(f'==========ssssssssss')
                        email_message = (
                            f"Consumer {mapped_username} has initiated a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh. "
                            f"The negotiation window will open tomorrow at 10:00 AM. "
                            f"The starting offer tariff being provided is {offer_tariff} INR/kWh.\n\n"
                            f"Click here to join the bidding window directly: https://ext.exgglobal.com/consumer/transaction-mb/{recipient_user.id}-{tariff.id}-{token}"
                        )
                        # Send email with the link
                        send_mail(
                            "Negotiation Invitation",
                            email_message,
                            f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                            [recipient_user.email],
                            fail_silently=False,
                        )

                        logger.debug(f'==========iiiiiiiiii')
                        invitation = NegotiationInvitation.objects.create(negotiation_window=negotiation_window, user=recipient_user)
                        logger.debug(f'========== {invitation}')

                    except User.DoesNotExist:
                        continue

                
                # GeneratorOffer.objects.get_or_create(generator=user, tariff=tariff)

                message=(
                    f"Generator {user.username} is interested in initiating a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh. "
                    f"The starting offer tariff being provided is {offer_tariff} INR/kWh."
                )
                logger.debug(f'consumer message:  {message}')
                send_notification(terms_sheet.consumer.id, message) 

                email_message=(
                    f"Generator {user.username} is interested in initiating a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh. "
                    f"The starting offer tariff being provided is {offer_tariff} INR/kWh. "
                    f"Click here to join the bidding window directly: https://ext.exgglobal.com/consumer/transaction-mb/{terms_sheet.consumer.id}-{tariff.id}-{token}"
                )
                logger.debug(f'consumer email message:  {email_message}')
                # Send email with the link
                send_mail(
                    "Negotiation Invitation",
                    email_message,
                    f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                    [terms_sheet.consumer.email],
                    fail_silently=False,
                )

                #self notification
                message=(
                    f"You have initiated negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh. "
                    f"The starting offer tariff being provided is {offer_tariff} INR/kWh."
                )
                logger.debug(f'user message:  {message}')
                send_notification(user.id, message)

                email_message=(
                    f"You have initiated negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh. "
                    f"The starting offer tariff being provided is {offer_tariff} INR/kWh. "
                    f"Click here to join the bidding window directly: https://ext.exgglobal.com/consumer/transaction-mb/{user.id}-{tariff.id}-{token}"
                )
                logger.debug(f'user email message:  {email_message}')
                # Send email with the link
                send_mail(
                    "Negotiation Invitation",
                    email_message,
                    f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                    [user.email],
                    fail_silently=False,
                )

            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            return Response({"message": "Notification sent to the consumer linked to the terms sheet and also initiated the negotiation window."}, status=200)
        else:
            
            # Notify all matching IPPs and the current generator
            matching_ipps = MatchingIPP.objects.get(requirement=terms_sheet.combination.requirement)
            recipients = matching_ipps.generator_ids

            # Create the negotiation window record with date and time
            negotiation_window = NegotiationWindow.objects.create(
                terms_sheet=terms_sheet,
                start_time=next_day_10_am_aware,
                end_time=end_time
            )
            
            Tariffs.objects.get_or_create(terms_sheet=terms_sheet)
            tariff = Tariffs.objects.get(terms_sheet=terms_sheet)
            tariff.offer_tariff = offer_tariff
            tariff.save()

            GeneratorOffer.objects.get_or_create(generator=negotiation_window.terms_sheet.combination.generator, tariff=tariff, updated_tariff=offer_tariff)

            NegotiationInvitation.objects.create(negotiation_window=negotiation_window,user=user)

            # Notify recipients
            for recipient in recipients:
                try:
                    recipient_user = User.objects.get(id=recipient)
                    # Map the consumer username specific to the generator
                    mapped_username = get_mapped_username(recipient_user, user)
                    message=(
                        f"Consumer {mapped_username} has initiated a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh."
                        f"The negotiation window will open tomorrow at 10:00 AM. "
                        f"The starting offer tariff being provided is {offer_tariff}."
                    )
                    send_notification(recipient_user.id, message)

                    email_message = (
                        f"Consumer {mapped_username} has initiated a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh."
                        f"The negotiation window will open tomorrow at 10:00 AM. "
                        f"The starting offer tariff being provided is {offer_tariff}.\n\n"
                        f"Click here to join the bidding window directly: https://ext.exgglobal.com/consumer/transaction-mb/{recipient_user.id}-{tariff.id}-{token}"
                    )
                    # Send email with the link
                    send_mail(
                        "Negotiation Invitation",
                        email_message,
                        f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                        [recipient_user.email],
                        fail_silently=False,
                    )

                    invitation = NegotiationInvitation.objects.create(negotiation_window=negotiation_window, user=recipient_user)
                    
                    
                except User.DoesNotExist:
                    continue
                    
            message=(
                f"You have initiated a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh."
                f"The starting offer tariff being provided is {offer_tariff}."
            )
            send_notification(user.id, message) 
            email_message=(
                f"You have initiated a negotiation window for Terms Sheet Demand for - {terms_sheet.combination.requirement.state} - {terms_sheet.combination.requirement.industry} - {terms_sheet.combination.requirement.sub_industry} - {terms_sheet.combination.requirement.consumption_unit} - {terms_sheet.combination.requirement.contracted_demand} kWh."
                f"The starting offer tariff being provided is {offer_tariff}."
                f"Click here to join the bidding window directly: https://ext.exgglobal.com/consumer/transaction-mb/{user.id}-{tariff.id}-{token}"
            )
            # Send email with the link
            send_mail(
                "Negotiation Invitation",
                email_message,
                f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                [user.email],
                fail_silently=False,
            )
                    

            return Response({"message": "Negotiation initiated. Notifications sent and negotiation window created."}, status=200)

class NegotiationWindowListAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        user = get_admin_user(user_id)
        user_id = user.id
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({"message": "no user found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if the user has any invitations
        invitations = NegotiationInvitation.objects.filter(user=user)

        if not invitations.exists():
            return Response({"message": "No invitations found for this user."}, status=status.HTTP_404_NOT_FOUND)

        # Get the associated negotiation windows from the invitations
        negotiation_windows = NegotiationWindow.objects.filter(id__in=invitations.values_list('negotiation_window_id', flat=True))


        # Prepare the response data
        response_data = []
        for window in negotiation_windows:
            tariff = Tariffs.objects.get(terms_sheet=window.terms_sheet.id)
            combination = Combination.objects.get(id=window.terms_sheet.combination.id)
            mapped_username = get_mapped_username(window.terms_sheet.combination.generator, window.terms_sheet.consumer)
            response_data.append({
                "generator_id": window.terms_sheet.combination.generator.id,
                "window_id": window.id,
                "window_name": window.name,
                "window_created_date": window.created_date,
                "terms_sheet_id": window.terms_sheet.id,
                "tariff_id": tariff.id,
                "offer_tariff": round(tariff.offer_tariff, 2),
                "tariff_status": "Upcoming" if window.start_time > timezone.now() else tariff.window_status,
                "start_time": localtime(window.start_time).strftime('%Y-%m-%d %H:%M:%S'),
                "end_time": localtime(window.end_time).strftime('%Y-%m-%d %H:%M:%S'),
                "t_consumer": window.terms_sheet.consumer.id,
                "t_combination": window.terms_sheet.combination.id,
                "t_term_of_ppa": window.terms_sheet.term_of_ppa,
                "t_lock_in_period": window.terms_sheet.lock_in_period,
                "t_commencement_of_supply": window.terms_sheet.commencement_of_supply,
                "t_contracted_energy": window.terms_sheet.contracted_energy,
                "t_minimum_supply_obligation": window.terms_sheet.minimum_supply_obligation,
                "t_payment_security_day": window.terms_sheet.payment_security_day,
                "t_payment_security_type": window.terms_sheet.payment_security_type,
                "rq_state": window.terms_sheet.combination.requirement.state,
                "rq_industry": window.terms_sheet.combination.requirement.industry,
                "rq_contracted_demand": window.terms_sheet.combination.requirement.contracted_demand,
                "rq_tariff_category": window.terms_sheet.combination.requirement.tariff_category,
                "rq_voltage_level": window.terms_sheet.combination.requirement.voltage_level,
                "rq_procurement_date": window.terms_sheet.combination.requirement.procurement_date,
                "rq_consumption_unit": window.terms_sheet.combination.requirement.consumption_unit,
                "rq_annual_electricity_consumption": window.terms_sheet.combination.requirement.annual_electricity_consumption,
                "c_optimal_solar_capacity": round(combination.optimal_solar_capacity, 2),
                "c_optimal_wind_capacity": round(combination.optimal_wind_capacity, 2),
                "c_optimal_battery_capacity": round(combination.optimal_battery_capacity, 2),
                "downloadable": {
                    "consumer": mapped_username,
                    "generator": window.terms_sheet.combination.generator.username,
                    "consumer_state": window.terms_sheet.combination.requirement.state,
                    "generator_state": window.terms_sheet.combination.state,
                    "cod": window.terms_sheet.combination.state,
                    "term_of_ppa": window.terms_sheet.term_of_ppa,
                    "lock_in_period": window.terms_sheet.lock_in_period,
                    "minimum_generation_obligation": round(window.terms_sheet.combination.annual_demand_met * 0.8, 2),
                    "voltage_level_of_generation": window.terms_sheet.combination.requirement.voltage_level,
                    "tariff_finalized": tariff.offer_tariff,
                    "payment_security_day": window.terms_sheet.payment_security_day,
                    "solar": window.terms_sheet.combination.optimal_solar_capacity,
                    "wind": window.terms_sheet.combination.optimal_wind_capacity,
                    "ess": window.terms_sheet.combination.optimal_battery_capacity,
                    "late_payment_surcharge": window.terms_sheet.late_payment_surcharge,
                }
            })


        return Response(response_data, status=status.HTTP_200_OK)

        
class NegotiationWindowStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id, window_id):
        user = get_admin_user(user_id)
        user_id = user.id
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({"message": "no user found"}, status=status.HTTP_404_NOT_FOUND)

        negotiation_window = NegotiationWindow.objects.filter(id=window_id).first()
        tariff = Tariffs.objects.filter(terms_sheet=negotiation_window.terms_sheet).first()

        if not tariff:
            return Response({"message": "no tariff found"}, status=status.HTTP_404_NOT_FOUND)
        

        if negotiation_window:
            # Check if the current time is less than the start time
            current_time = now()
            if current_time < negotiation_window.start_time:
                return Response({
                    "status": "error",
                    "message": f"The negotiation window is not yet open. It will open on {localtime(negotiation_window.start_time).strftime('%Y-%m-%d at %I:%M %p')}."
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
    
    def put(self, request):
        user_id = request.data.get('user_id')
        window_id = request.data.get('window_id')
        new_date_str = request.data.get('date')  # Expecting format 'YYYY-MM-DD'

        if not (user_id and window_id and new_date_str):
            return Response({"error": "Missing required parameters."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Allow only consumers
        if user.user_category != 'Consumer':  # Adjust this if user_type is stored differently
            return Response({"error": "Only consumers can update the negotiation window date."}, status=status.HTTP_403_FORBIDDEN)

        try:
            negotiation_window = NegotiationWindow.objects.get(id=window_id)
        except NegotiationWindow.DoesNotExist:
            return Response({"error": "Negotiation window not found."}, status=status.HTTP_400_BAD_REQUEST)

        today = datetime.now().date()
        old_start_date = negotiation_window.start_time.date()

        # Don't allow change if the old date is today's date
        if old_start_date == today:
            return Response({"error": "You cannot change the date if it's already today's date."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Parse new date
            new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        # Preserve time parts, only change date
        negotiation_window.start_time = make_aware(datetime.combine(new_date, negotiation_window.start_time.time()))
        negotiation_window.end_time = make_aware(datetime.combine(new_date, negotiation_window.end_time.time()))
        negotiation_window.save()

        # Notify matching IPPsA and Generator
        try:
            terms_sheet = negotiation_window.terms_sheet
            requirement = terms_sheet.combination.requirement
            generator = terms_sheet.combination.generator
            matching_ipps = MatchingIPP.objects.get(requirement=requirement)

            state = requirement.state
            industry = requirement.industry
            sub_industry = requirement.sub_industry
            consumption_unit = requirement.consumption_unit
            demand = requirement.contracted_demand
            date_msg = new_date.strftime("%d %B %Y")
            time_msg = negotiation_window.start_time.strftime("%I:%M %p")

            message = (
                f"Negotiation window date has been updated by consumer {user.username} for Terms Sheet Demand - "
                f"{state}, {industry}, {sub_industry}, {consumption_unit}, {demand} kWh. "
                f"The new window timing is on {date_msg} at {time_msg}."
            )

            # Notify generator
            send_notification(generator.id, message)
            send_mail(
                "Negotiation Window Date Updated",
                message,
                f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                [generator.email],
                fail_silently=False,
            )

            # Notify all IPPsA participants
            for ippsa_id in matching_ipps.generator_ids:
                if ippsa_id == user.id:
                    continue
                try:
                    ippsa_user = User.objects.get(id=ippsa_id)
                    send_notification(ippsa_user.id, message)
                    send_mail(
                        "Negotiation Window Date Updated",
                        message,
                        f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                        [ippsa_user.email],
                        fail_silently=False,
                    )
                except User.DoesNotExist:
                    continue

            # Notify the consumer themselves for confirmation
            send_notification(user.id, message)
            send_mail(
                "Negotiation Window Date Updated",
                message,
                f"EXG Global <{settings.DEFAULT_FROM_EMAIL}>",
                [user.email],
                fail_silently=False,
            )

        except Exception as e:
            return Response({"error": f"Update successful, but notification failed: {str(e)}"}, status=500)

        return Response({"message": "Window date updated and notifications sent successfully."}, status=200)


class AnnualSavingsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Common logic for both POST (annual savings calculation) and GET (annual report download)
        re = 3.67  # Initially RE value will be taken from Master Table that is provided by the client.
        requirement_id = request.data.get('requirement_id')
        generator_id = request.data.get('generator_id')
        average_savings = 0
        logger.debug(f'generator_id = {generator_id}')
        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
            combination = Combination.objects.filter(requirement__sub_industry = requirement.sub_industry, generator=generator_id)
            master_record = MasterTable.objects.get(state=requirement.state)
            record = RETariffMasterTable.objects.filter(industry=requirement.sub_industry).first()

            # Check if there are 10 or more records
            if combination.count() >= 10:
                # Calculate the average
                average_per_unit_cost = combination.aggregate(Avg('per_unit_cost'))['per_unit_cost__avg']
                re = round(average_per_unit_cost/2)
            elif record:
                re = record.re_tariff
            else:
                re = 4

            # Fetch Grid cost from GridTariff (Assuming tariff_category is fixed or dynamic)
            grid_tariff = GridTariff.objects.get(state=requirement.state, tariff_category=requirement.tariff_category)
            
            if grid_tariff is None:
                return Response({"error": "No grid cost data available for the state"}, status=status.HTTP_404_NOT_FOUND)

            # Fetch the last 10 values (adjust the ordering field if needed)
            last_10_values = Combination.objects.filter(requirement__sub_industry=requirement.sub_industry).order_by('-id')[:10].values_list('annual_demand_offset', flat=True)

            if last_10_values.count() < 10:
                re_replacement = 65
            else:
                moving_average = sum(last_10_values) / len(last_10_values)
                re_replacement = round(moving_average, 2)

            # --- START OF ISTS Charges Logic ---

            portfolios = list(SolarPortfolio.objects.filter(
                Q(state=requirement.state) | Q(connectivity="CTU")
            ).values("state", "connectivity"))

            portfolios += list(WindPortfolio.objects.filter(
                Q(state=requirement.state) | Q(connectivity="CTU")
            ).values("state", "connectivity"))

            portfolios += list(ESSPortfolio.objects.filter(
                Q(state=requirement.state) | Q(connectivity="CTU")
            ).values("state", "connectivity"))

            include_ISTS = False
            for p in portfolios:
                if p["connectivity"] == "CTU":
                    include_ISTS = True
                    break
                elif p["state"] == requirement.state:
                    include_ISTS = False
                    break

            # Fallback in case no portfolio matched (safe default)
            if not portfolios:
                include_ISTS = True

            ISTS_charges = master_record.ISTS_charges if include_ISTS else 0

            # --- END OF ISTS Charges Logic ---
            
            # Calculate annual savings
            annual_savings = (grid_tariff.cost - re - ISTS_charges - master_record.state_charges) * round(re_replacement/100, 2) * requirement.annual_electricity_consumption * 1000
            logger.debug(f'annual_savings = ({grid_tariff.cost} - {re} - {ISTS_charges} - {master_record.state_charges}) * {round(re_replacement/100, 2)} * {requirement.annual_electricity_consumption} * 1000 = {annual_savings}')
            logger.debug(round(annual_savings, 2))

            # Prepare response data
            response_data = {
                "annual_savings": round(annual_savings, 2),
                "average_savings": record.average_savings*requirement.contracted_demand if record else average_savings,
                "re_replacement": re_replacement,
                "state": requirement.state,
                "procurement_date": requirement.procurement_date,
                # For the report download, prepare the full report data
                "consumer_company_name": requirement.user.company,
                "consumption_unit_name": requirement.consumption_unit,
                "connected_voltage": requirement.voltage_level,
                "tariff_category": requirement.tariff_category,
                "annual_electricity_consumption": round(requirement.annual_electricity_consumption, 2),
                "contracted_demand": round(requirement.contracted_demand, 2),
                "electricity_tariff": round(grid_tariff.cost, 2),
                "potential_re_tariff": round(re, 2),
                "ISTS_charges": round(ISTS_charges, 2),
                "state_charges": round(master_record.state_charges, 2),
                "per_unit_savings_potential": round(grid_tariff.cost - re - master_record.ISTS_charges - master_record.state_charges, 2),
                "potential_re_replacement": round(re_replacement, 2),
                "total_savings": round(annual_savings / 10000000, 2),
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        except MasterTable.DoesNotExist:
            return Response({"error": f"No data available for the state: {requirement.state}"}, status=status.HTTP_404_NOT_FOUND)
        
        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Requirement not found"}, status=status.HTTP_404_NOT_FOUND)

        except RETariffMasterTable.DoesNotExist:
            return Response({"error": "Tariff record not found for the given industry"}, status=status.HTTP_404_NOT_FOUND)

        except GridTariff.DoesNotExist:
            return Response({"error": "Grid tariff data not found for the state"}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
class WhatWeOfferAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Total number of users with 'Generator' category
        consumer_count = User.objects.filter(user_category='Consumer').count()

        total_contracted_demand = ConsumerRequirements.objects.aggregate(total_contracted_demand=Sum('contracted_demand'))['total_contracted_demand'] or 0

        # Total number of portfolios
        total_solar_portfolios = SolarPortfolio.objects.count()
        total_wind_portfolios = WindPortfolio.objects.count()
        total_ess_portfolios = ESSPortfolio.objects.count()
        total_portfolios = total_solar_portfolios + total_wind_portfolios + total_ess_portfolios

        # Sum of available capacities from all portfolios
        solar_capacity = SolarPortfolio.objects.aggregate(total_capacity=Sum('available_capacity'))['total_capacity'] or 0
        wind_capacity = WindPortfolio.objects.aggregate(total_capacity=Sum('available_capacity'))['total_capacity'] or 0
        ess_capacity = ESSPortfolio.objects.aggregate(total_capacity=Sum('available_capacity'))['total_capacity'] or 0
        total_available_capacity = solar_capacity + wind_capacity + ess_capacity

        # Count of unique states across all portfolios
        solar_states = SolarPortfolio.objects.values_list('state', flat=True)
        wind_states = WindPortfolio.objects.values_list('state', flat=True)
        ess_states = ESSPortfolio.objects.values_list('state', flat=True)
        unique_states = set(solar_states).union(set(wind_states), set(ess_states))
        unique_state_count = len(unique_states)

        requirements = ConsumerRequirements.objects.all()

        # Total amount consumers saved annually
        amount_saved_annually = 0
        for requirement in requirements:
            master_record = MasterTable.objects.filter(state=requirement.state).first()
            grid_tariff = GridTariff.objects.filter(state=requirement.state, tariff_category=requirement.tariff_category).first()
            record = RETariffMasterTable.objects.filter(industry = requirement.sub_industry).first()

            last_10_values = Combination.objects.filter(requirement__sub_industry=requirement.sub_industry).order_by('-id')[:10].values_list('annual_demand_offset', flat=True)

            if last_10_values.count() < 10:
                re_replacement = 65
            else:
                moving_average = sum(last_10_values) / len(last_10_values)
                re_replacement = round(moving_average, 2)

            if grid_tariff is None or master_record is None:
                continue
            
            # Initially RE value will be taken from Master Table that is provided by the client.
            if record:
                re = record.re_tariff
            else:
                re = 4
            
            # Calculate annual savings
            annual_savings = (re - master_record.ISTS_charges - master_record.state_charges) * round(re_replacement/100) * requirement.annual_electricity_consumption * 1000

            amount_saved_annually += annual_savings

        # Return the calculated data as a response
        return Response({
            'consumer_count': consumer_count,
            'total_portfolios': total_portfolios,
            'total_contracted_demand': total_contracted_demand,
            'total_available_capacity': total_available_capacity,
            'unique_state_count': unique_state_count,
            'amount_saved_annually': amount_saved_annually
        })

class LastVisitedPageAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_id = request.data.get('user_id')
        last_visited_page = request.data.get('last_visited_page') or None
        selected_requirement_id = request.data.get('selected_requirement_id') or None

        try:
            user = User.objects.get(id=user_id)
            user.last_visited_page = last_visited_page
            user.selected_requirement_id = selected_requirement_id
            user.save()
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'Success'}, status=status.HTTP_200_OK)

class CheckSubscriptionAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = get_admin_user(user_id)
            user_id = user.id
            subscription = SubscriptionEnrolled.objects.filter(user=user_id).exists()
            return Response(subscription, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        
class ConsumerDashboardAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        user = get_admin_user(user_id)

        total_demands = ConsumerRequirements.objects.filter(user=user).aggregate(total_demands=Sum('contracted_demand'))['total_demands'] or 0
        consumption_units = ConsumerRequirements.objects.filter(user=user).count()
        unique_states_count = ConsumerRequirements.objects.filter(user=user).values('state').distinct().count()
        offers_sent = StandardTermsSheet.objects.filter(consumer=user, from_whom='Consumer').count()
        offers_received = StandardTermsSheet.objects.filter(consumer=user, from_whom='Generator')
        total_received = 0
        for offer in offers_received:
            total_received += offer.combination.optimal_solar_capacity + offer.combination.optimal_wind_capacity + offer.combination.optimal_battery_capacity


        # Total number of portfolios
        total_solar_portfolios = SolarPortfolio.objects.count()
        total_wind_portfolios = WindPortfolio.objects.count()
        total_ess_portfolios = ESSPortfolio.objects.count()
        total_portfolios = total_solar_portfolios + total_wind_portfolios + total_ess_portfolios

        # Sum of available capacities from all portfolios
        solar_capacity = SolarPortfolio.objects.aggregate(total_capacity=Sum('available_capacity'))['total_capacity'] or 0
        wind_capacity = WindPortfolio.objects.aggregate(total_capacity=Sum('available_capacity'))['total_capacity'] or 0
        ess_capacity = ESSPortfolio.objects.aggregate(total_capacity=Sum('available_capacity'))['total_capacity'] or 0
        total_available_capacity = solar_capacity + wind_capacity + ess_capacity

        # Count of unique states across all portfolios
        solar_states = SolarPortfolio.objects.values_list('state', flat=True)
        wind_states = WindPortfolio.objects.values_list('state', flat=True)
        ess_states = ESSPortfolio.objects.values_list('state', flat=True)
        unique_states = set(solar_states).union(set(wind_states), set(ess_states))
        states_covered = len(unique_states)
        states = unique_states

        response = {
            'total_demands': total_demands,
            'consumption_units': consumption_units,
            'unique_states_count': unique_states_count,
            'offers_sent': offers_sent,
            'offers_received': total_received,
            'transactions_done': 0,
            'total_portfolios': total_portfolios,
            'total_available_capacity': total_available_capacity,
            'solar_capacity': solar_capacity,
            'wind_capacity': wind_capacity,
            'ess_capacity': ess_capacity,
            'states_covered': states_covered,
            'states': states,
        }

        return Response(response, status=status.HTTP_200_OK)

class GeneratorDashboardAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        user = get_admin_user(user_id)

        
        energy_offered = StandardTermsSheet.objects.filter(combination__generator=user, from_whom='Generator')
        total_solar_energy_offered = energy_offered.aggregate(total_solar_energy=Sum('combination__optimal_solar_capacity'))['total_solar_energy'] or 0
        total_wind_energy_offered = energy_offered.aggregate(total_wind_energy=Sum('combination__optimal_wind_capacity'))['total_wind_energy'] or 0
        total_ess_energy_offered = energy_offered.aggregate(total_ess_energy=Sum('combination__optimal_battery_capacity'))['total_ess_energy'] or 0
        

        offers_received = StandardTermsSheet.objects.filter(combination__generator=user, from_whom='Generator')
        total_offer_received = offers_received.aggregate(total_contracted_demand=Sum('combination__requirement__contracted_demand'))['total_contracted_demand'] or 0

        solar_portfolios = SolarPortfolio.objects.filter(user=user).count()
        wind_portfolios = WindPortfolio.objects.filter(user=user).count()
        ess_portfolios = ESSPortfolio.objects.filter(user=user).count()

        consumer_count = User.objects.filter(user_category='Consumer').count()

        total_contracted_demand = ConsumerRequirements.objects.aggregate(total_contracted_demand=Sum('contracted_demand'))['total_contracted_demand'] or 0
        
        # Count of unique states across all portfolios
        solar_states = SolarPortfolio.objects.values_list('state', flat=True)
        wind_states = WindPortfolio.objects.values_list('state', flat=True)
        ess_states = ESSPortfolio.objects.values_list('state', flat=True)
        unique_states = set(solar_states).union(set(wind_states), set(ess_states))
        unique_state_count = len(unique_states)
        states = unique_states

        response = {
            'total_energy_sold': 0,
            'total_solar_energy_offered': round(total_solar_energy_offered, 2),
            'total_wind_energy_offered': round(total_wind_energy_offered, 2),
            'total_ess_energy_offered': round(total_ess_energy_offered, 2),
            'total_offer_received': round(total_offer_received, 2),
            'transactions_done': 0,
            'solar_portfolios': solar_portfolios,
            'wind_portfolios': wind_portfolios,
            'ess_portfolios': ess_portfolios,
            'total_consumers': consumer_count,
            'total_contracted_demand': total_contracted_demand,
            'unique_state_count': unique_state_count,
            'states': states,
            
        }

        return Response(response, status=status.HTTP_200_OK)

class RazorpayClient():

    def create_order(self, amount, currency):
        if amount > 500000:
            raise ValidationError({"message": "Maximum allowed amount is ₹5,00,000."})

        data = {
            "amount": amount * 100,
            "currency": currency,
        }
        try:
            order_data = client.order.create(data=data)
            return order_data
        except Exception as e:
            
            raise ValidationError(
                {
                    "message": e
                }
            )
        
    def verify_payment(self, razorpay_order_id, razorpay_payment_id, razorpay_signature):
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
        except Exception as e:
            raise ValidationError({
                "message": e
            })
        
rz_client = RazorpayClient()

class CreateOrderAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        create_order_serializer = CreateOrderSerializer(
            data = request.data
        )
        if create_order_serializer.is_valid():
            order_response = rz_client.create_order(
                amount = create_order_serializer.validated_data.get("amount"),
                currency = create_order_serializer.validated_data.get("currency")
            )
            response = {
                "message": "order created",
                "data": order_response
            }
            return Response(response, status=status.HTTP_201_CREATED)
        else:
            response = {
                "error": create_order_serializer.errors
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)
        
class PaymentTransactionAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        subscription = request.data['subscription']
        invoice = request.data['invoice']
        payment_transaction_serializer = PaymentTransactionSerializer(
            data = request.data
        )
        if payment_transaction_serializer.is_valid():
            rz_client.verify_payment(
                razorpay_order_id=payment_transaction_serializer.validated_data.get("order_id"),
                razorpay_payment_id=payment_transaction_serializer.validated_data.get("payment_id"),
                razorpay_signature=payment_transaction_serializer.validated_data.get("signature")
            )
            payment_transaction_serializer.save()

            invoice = PerformaInvoice.objects.get(id=invoice)
            invoice.payment_status = 'Paid'
            invoice.save()

            # Call Subscription API to create a subscription
            subscription_data = {
                "user": invoice.user.id,
                "subscription": subscription,
                "start_date": str(datetime.today().date())
            }
            
            # Forward token received from frontend
            auth_header = request.META.get('HTTP_AUTHORIZATION')  # 'Bearer <token>'
            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json"
            }
            if settings.ENVIRONMENT == 'local':
                subscription_response = requests.post(
                    "http://127.0.0.1:8000/api/energy/subscriptions",
                    json=subscription_data,
                    headers=headers
                )
            else:
                subscription_response = requests.post(
                    "https://ext.exgglobal.com/api/api/energy/subscriptions",
                    json=subscription_data,
                    headers=headers
                )

            if subscription_response.status_code == 201:
                return Response(
                    {"message": "Transaction and Subscription Created"},
                    status=status.HTTP_201_CREATED
                )
            else:
                # Debugging: Print response status and content
                try:
                    response_json = subscription_response.json()
                except requests.exceptions.JSONDecodeError:
                    response_json = {"error": "Invalid JSON response", "content": subscription_response.text}

                return Response(
                    {"message": "Transaction Created but Subscription Failed", "error": response_json},
                    status=400
                )
            
        else:
            response = {
                "error": payment_transaction_serializer.errors
            }
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

class PerformaInvoiceAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = get_admin_user(user_id)
            user_id = user.id
            instance = PerformaInvoice.objects.filter(user=user_id)
            serializer = PerformaInvoiceSerializer(instance, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except PerformaInvoice.DoesNotExist:
            return Response({'message': 'Not Found'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, user_id):
        try:
            # Extract and validate data from the request
            company_name = request.data.get('company_name')
            company_address = request.data.get('company_address')
            gst_number = request.data.get('gst_number')
            subscription_id = request.data.get('subscription')

            # Validate required fields
            if not all([company_name, company_address, gst_number, subscription_id]):
                return Response(
                    {'error': 'Missing required fields'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if a PerformaInvoice already exists for the user
            user = get_admin_user(user_id)
            user_id = user.id

            # Check if an invoice already exists for the same user and subscription
            performa_invoice = PerformaInvoice.objects.filter(user=user_id, subscription=subscription_id).first()

            if performa_invoice:
                # Update the existing invoice
                performa_invoice.company_name = company_name
                performa_invoice.company_address = company_address
                performa_invoice.gst_number = gst_number
                performa_invoice.save()

                message = "Performa Invoice updated successfully"
            else:
                # Create a new invoice if none exists
                serializer = PerformaInvoiceCreateSerializer(data={
                    'user': user_id,
                    'company_name': company_name,
                    'company_address': company_address,
                    'gst_number': gst_number,
                    'subscription': subscription_id
                })

                if serializer.is_valid():
                    performa_invoice = serializer.save()
                    message = "Performa Invoice created successfully"
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Serialize the invoice (updated or newly created)
            serializer = PerformaInvoiceSerializer(performa_invoice)

            return Response(
                {'message': message, 'data': serializer.data},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TemplateDownloadedAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_id = request.data.get('user_id')
        solar_template_downloaded = request.data.get('solar_template_downloaded') or False
        wind_template_downloaded = request.data.get('wind_template_downloaded') or False

        try:
            user = get_admin_user(user_id)
            user_id = user.id
            user = User.objects.get(id=user_id)
            user.solar_template_downloaded = solar_template_downloaded
            user.wind_template_downloaded = wind_template_downloaded
            user.save()
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'message': 'Success'}, status=status.HTTP_200_OK)

class CapacitySizingAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @staticmethod
    def extract_profile_data(file_path):
                
        # Read the specified sheet from the Excel file
        df = pd.read_excel(file_path)

        # Select only the relevant column (B) and start from the 4th row (index 3)
        df_cleaned = df.iloc[1:, 1].reset_index(drop=True)  # Column B corresponds to index 1

        # Fill NaN values with 0
        profile = df_cleaned.fillna(0).reset_index(drop=True)
                
        return profile
    
    @staticmethod
    def calculate_annual_hourly_demand(generator_demand):
        from datetime import datetime, timedelta

        # Extract the relevant times
        morning_start = generator_demand.morning_peak_hours_start.hour
        morning_end = generator_demand.morning_peak_hours_end.hour
        evening_start = generator_demand.evening_peak_hours_start.hour
        evening_end = generator_demand.evening_peak_hours_end.hour

        # Handle wrap-around cases like (22 to 2 AM)
        def hour_range(start, end):
            if end > start:
                return list(range(start, end))
            else:  # wraps around midnight
                return list(range(start, 24)) + list(range(0, end))

        morning_peak_hours = hour_range(morning_start, morning_end)
        evening_peak_hours = hour_range(evening_start, evening_end)
        peak_hours_set = set(morning_peak_hours + evening_peak_hours)

        total_hours_in_year = 365 * 24  # You may check if leap year if needed
        morning_peak_hours_count = len(morning_peak_hours) * 365
        evening_peak_hours_count = len(evening_peak_hours) * 365
        peak_total_hours = morning_peak_hours_count + evening_peak_hours_count
        normal_hours_count = total_hours_in_year - peak_total_hours

        # Calculate consumption values
        annual_peak_consumption = generator_demand.annual_morning_peak_hours_consumption or 0
        annual_evening_consumption = generator_demand.annual_evening_peak_hours_consumption or 0
        annual_total_consumption = generator_demand.annual_consumption or 0

        annual_normal_consumption = annual_total_consumption - (annual_peak_consumption + annual_evening_consumption)

        # Per hour values
        morning_hour_value = annual_peak_consumption / morning_peak_hours_count if morning_peak_hours_count else 0
        evening_hour_value = annual_evening_consumption / evening_peak_hours_count if evening_peak_hours_count else 0
        normal_hour_value = annual_normal_consumption / normal_hours_count if normal_hours_count else 0

        # Generate hourly data
        hourly_data = []
        for day in range(365):
            for hour in range(24):
                if hour in morning_peak_hours:
                    hourly_data.append(round(morning_hour_value, 3))
                elif hour in evening_peak_hours:
                    hourly_data.append(round(evening_hour_value, 3))
                else:
                    hourly_data.append(round(normal_hour_value, 3))

        return pd.Series(hourly_data)


    def post(self, request):
        data = request.data
        user_id = data.get("user_id")
        csv_file = data.get("csv_file")
        curtailment_selling_price = data.get("curtailment_selling_price")
        sell_curtailment_percentage = data.get("sell_curtailment_percentage")
        annual_curtailment_limit = data.get("annual_curtailment_limit")

        try:
            # Fetch the user
            generator = User.objects.get(id=user_id)
            generator = get_admin_user(user_id)
        except User.DoesNotExist:
            return Response({"error": "Generator not found."}, status=status.HTTP_404_NOT_FOUND)

        # Handle RE Replacement
        re_replacement = int(data.get("re_replacement")) if data.get("re_replacement") else None
        if re_replacement == 0:
            return Response({"message": "No available capacity."}, status=status.HTTP_200_OK)
        
        if csv_file:
            try:
                # Decode the Base64 file
                decoded_file = base64.b64decode(csv_file)
                file_name = f"csv_file_{generator}.csv"
                csv_file_content = ContentFile(decoded_file, name=file_name)
            except Exception as e:
                return Response({"error": f"Invalid Base64 file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                # Read the CSV content
                file_data = csv_file_content.read().decode('utf-8').splitlines()
                csv_reader = csv.DictReader(file_data)

                # Validate CSV format
                rows = list(csv_reader)
                if len(rows) != 8760:
                    return Response({"error": "The CSV must contain exactly 8760 rows."}, status=status.HTTP_400_BAD_REQUEST)

                # Extract 'Expected Demand' values
                hourly_values = [row['Expected Demand(MWh)'] for row in rows]

                # Convert to a comma-separated string
                hourly_demand_str = ','.join(hourly_values)

                # Save the data in one record
                obj, created = GeneratorHourlyDemand.objects.get_or_create(
                    generator=generator,
                    defaults={"hourly_demand": hourly_demand_str}
                )

                if not created:
                    obj.hourly_demand = hourly_demand_str
                    obj.save()
                    
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            def parse_time_string(time_str):
                return datetime.strptime(time_str, "%H:%M:%S").time() if time_str else None

            annual_consumption = data.get("annual_consumption")
            contracted_demand = data.get("contracted_demand")
            morning_peak_hours_start = parse_time_string(data.get("morning_peak_hours_start"))
            morning_peak_hours_end = parse_time_string(data.get("morning_peak_hours_end"))
            annual_morning_peak_hours_consumption = data.get("annual_morning_peak_hours_consumption")
            evening_peak_hours_start = parse_time_string(data.get("evening_peak_hours_start"))
            evening_peak_hours_end = parse_time_string(data.get("evening_peak_hours_end"))
            annual_evening_peak_hours_consumption = data.get("annual_evening_peak_hours_consumption")
            peak_hours_availability_requirement = data.get("peak_hours_availability_requirement")

            generator_demand = GeneratorDemand.objects.filter(generator=generator).first()
            if generator_demand:
                generator_demand.annual_consumption = annual_consumption
                generator_demand.contracted_demand = contracted_demand
                generator_demand.morning_peak_hours_start = morning_peak_hours_start
                generator_demand.morning_peak_hours_end = morning_peak_hours_end
                generator_demand.annual_morning_peak_hours_consumption = annual_morning_peak_hours_consumption
                generator_demand.evening_peak_hours_start = evening_peak_hours_start
                generator_demand.evening_peak_hours_end = evening_peak_hours_end
                generator_demand.annual_evening_peak_hours_consumption = annual_evening_peak_hours_consumption
                generator_demand.peak_hours_availability_requirement = peak_hours_availability_requirement
                generator_demand.save()
            else:
                generator_demand = GeneratorDemand(
                    generator=generator,
                    annual_consumption=annual_consumption,
                    contracted_demand=contracted_demand,
                    morning_peak_hours_start=morning_peak_hours_start,
                    morning_peak_hours_end=morning_peak_hours_end,
                    annual_morning_peak_hours_consumption=annual_morning_peak_hours_consumption,
                    evening_peak_hours_start=evening_peak_hours_start,
                    evening_peak_hours_end=evening_peak_hours_end,
                    annual_evening_peak_hours_consumption=annual_evening_peak_hours_consumption,
                    peak_hours_availability_requirement=peak_hours_availability_requirement
                )
                generator_demand.save()
            numeric_hourly_demand = self.calculate_annual_hourly_demand(generator_demand)

            df = pd.DataFrame({
                'Index': numeric_hourly_demand.index,
                'Demand': numeric_hourly_demand.values
            })

            # Export to Excel
            # df.to_excel('hourly_demand.xlsx', index=False, engine='openpyxl')
            # print(f"Excel file 'hourly_demand.xlsx' created successfully with {len(numeric_hourly_demand)} rows.")
            # print('---------------------numeric_hourly_demand---------------------')
            # print(numeric_hourly_demand)

            hourly_demand = GeneratorHourlyDemand.objects.filter(generator=generator).first()
            if not hourly_demand:
                hourly_demand = GeneratorHourlyDemand(generator=generator)
            hourly_demand.hourly_demand = None
            hourly_demand.set_hourly_data_from_list(numeric_hourly_demand)
            hourly_demand.save()

        try:
            # Initialize final aggregated response
            # grid_tariff = GridTariff.objects.get(state=consumer_requirement.state, tariff_category=consumer_requirement.tariff_category)
            # master_record = MasterTable.objects.get(state=consumer_requirement.state)
            # record = RETariffMasterTable.objects.filter(industry=consumer_requirement.industry).first()
            aggregated_response = {}
            input_data = {}  # Initialize the final dictionary
            
            # Fetch the user
            generator = User.objects.get(id=user_id)

            # Extract Portfolio IDs
            solar_portfolio_ids = data.get("solar_portfolio", [])
            wind_portfolio_ids = data.get("wind_portfolio", [])
            ess_portfolio_ids = data.get("ess_portfolio", [])

            # Query generator's portfolios
            solar_data = SolarPortfolio.objects.filter(id__in=solar_portfolio_ids)
            wind_data = WindPortfolio.objects.filter(id__in=wind_portfolio_ids)
            ess_data = ESSPortfolio.objects.filter(id__in=ess_portfolio_ids)

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
                    if not solar.hourly_data:
                        continue
                    # Extract profile data from file
                    profile_data = self.extract_profile_data(solar.hourly_data.path)
                    # Divide all rows by 5
                    profile_data = profile_data / solar.available_capacity # model algorithm considering profile for per MW so that's why we are dividing profile by available capacity 
                    input_data[generator.username]["Solar"][solar.project] = {
                        "profile": profile_data,
                        "max_capacity": solar.available_capacity,
                        "marginal_cost": solar.expected_tariff * 1000,
                        "capital_cost": solar.capital_cost,
                    }
            # Add Wind projects if wind_data exists
            if wind_data.exists():
                input_data[generator.username]["Wind"] = {}
                for wind in wind_data:
                    wind_project.append(wind.project)
                    if not wind.hourly_data:
                        continue
                    # Extract profile data from file
                    profile_data = self.extract_profile_data(wind.hourly_data.path)
                    # Divide all rows by 5
                    profile_data = profile_data / wind.available_capacity # model algorithm considering profile for per MW so that's why we are dividing profile by available capacity
                    input_data[generator.username]["Wind"][wind.project] = {
                        "profile": profile_data,
                        "max_capacity": wind.available_capacity,
                        "marginal_cost": wind.expected_tariff * 1000,
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
                        "marginal_cost": ess.expected_tariff * 1000,
                        "capital_cost": ess.capital_cost,
                    }
            
            
            valid_combinations = []  

            hourly_demand = GeneratorHourlyDemand.objects.get(generator=generator)

            hourly_demand_list = hourly_demand.hourly_demand.split(',')
            hourly_demand_series = pd.Series(hourly_demand_list)
            hourly_demand = pd.to_numeric(hourly_demand_series, errors='coerce')
        
            # 8760 rows should be there if more then remove extra and if less then show error
            if len(hourly_demand) > 8760:
                hourly_demand = hourly_demand.iloc[:8760]
            elif len(hourly_demand) < 8760:
                padding_length = 8760 - len(hourly_demand)
                hourly_demand = pd.concat([hourly_demand, pd.Series([0] * padding_length)], ignore_index=True)

            response_data = optimization_model(input_data, hourly_demand=hourly_demand, re_replacement=re_replacement, valid_combinations=valid_combinations, curtailment_selling_price=curtailment_selling_price, sell_curtailment_percentage=sell_curtailment_percentage, annual_curtailment_limit=annual_curtailment_limit)
            logger.debug(f'capacity sizing output: {response_data}')
            # if response_data == 'The demand cannot be met by the IPPs':
            if response_data.get('error'):
                return Response({"error": "The demand cannot be met by the IPPs."}, status=status.HTTP_200_OK)
            
            for combination_key, details in response_data.items():
            # Extract user and components from combination_key                
                OA_cost = (details["Final Cost"] - details['Per Unit Cost']) / 1000
                details['Per Unit Cost'] = details['Per Unit Cost'] / 1000
                details['Final Cost'] = details['Final Cost'] / 1000
                details["Annual Demand Met"] = (details["Annual Demand Met"]) / 1000
               # Update the aggregated response dictionary
                if combination_key not in aggregated_response:
                    aggregated_response[combination_key] = {
                        **details,
                        'OA_cost': OA_cost,
                    }
                else:
                    # Merge the details if combination already exists
                    aggregated_response[combination_key].update(details)                
            

            # Extract top 3 records with the smallest "Per Unit Cost"
            records = sorted(aggregated_response.items(), key=lambda x: x[1]['Per Unit Cost'])
            # Function to round values to 2 decimal places
            def round_values(record):
                return {key: round(value, 2) if isinstance(value, (int, float)) else value for key, value in record.items()}
            # Round the values for the top 3 records
            records_rounded = {
                key: round_values(value) for key, value in records
            }


            return Response(records_rounded, status=status.HTTP_200_OK)


        except User.DoesNotExist:
            return Response({"error": "Generator not found."}, status=status.HTTP_404_NOT_FOUND)

        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Consumer requirements not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e), "Traceback": tb}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SensitivityAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @staticmethod
    def extract_profile_data(file_path):
                
        # Read the specified sheet from the Excel file
        df = pd.read_excel(file_path)
        logger.debug('df')
        logger.debug(df)

        df_cleaned = df.iloc[1:, 1].reset_index(drop=True)
        logger.debug('df cleaned')
        logger.debug(df)


        # Fill NaN values with 0
        profile = df_cleaned.fillna(0).reset_index(drop=True)
        logger.debug('Profile:')
        logger.debug(profile)
                
        return profile
    

    @staticmethod
    def calculate_hourly_demand(consumer_requirement, state="Maharashtra"):
        consumer_demand = HourlyDemand.objects.get(requirement=consumer_requirement)

        # # Define the state-specific hours
        # state_hours = {
        #     "Madhya Pradesh": {
        #         "peak_hours_1": (6, 9),  # 6 AM to 9 AM
        #         "peak_hours_2": (17, 22),  # 5 PM to 10 PM
        #         "off_peak_hours": (22, 6),  # 10 PM to 6 AM
        #     }
        # }
        hours = PeakHours.objects.filter(state__name=state).first()
        if not hours:
            return Response({"error": f"No peak hours data found for state {state}."}, status=status.HTTP_404_NOT_FOUND)

        monthly_consumptions = MonthlyConsumptionData.objects.filter(requirement=consumer_requirement)

        # Get state-specific hours
        # Get state-specific peak and off-peak hours
        peak_hours_1 = (hours.peak_start_1.hour, hours.peak_end_1.hour)
        peak_hours_2 = (hours.peak_start_2.hour, hours.peak_end_2.hour) if hours.peak_start_2 and hours.peak_end_2 else (0, 0)
        off_peak_hours = (hours.off_peak_start.hour, hours.off_peak_end.hour) if hours.off_peak_start and hours.off_peak_end else (0, 0)
        logger.debug(peak_hours_1)
        logger.debug(peak_hours_2)
        logger.debug(off_peak_hours)


        # Calculate total hours for all ranges
        total_hours = 24
        peak_hours_total = hours.calculate_peak_hours()
        off_peak_hours_total = hours.calculate_off_peak_hours()
        normal_hours = total_hours - peak_hours_total - off_peak_hours_total
        logger.debug(f'normal_hours = {total_hours} - {peak_hours_total} - {off_peak_hours_total}')
        logger.debug(f'Total peak hours: {peak_hours_total}')
        logger.debug(f'Total off peak hours: {off_peak_hours_total}')
        logger.debug(f'Normal hours: {normal_hours}')

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
            normal_hour_value = round(normal_consumption / (normal_hours * days_in_month), 3)
            peak_hour_value = round(month_data.peak_consumption / ((peak_hours_total) * days_in_month), 3)
            off_peak_hour_value = round(month_data.off_peak_consumption / ((off_peak_hours_total) * days_in_month), 3)

            logger.debug(f'normal_consumption = month_data.monthly_consumption - (month_data.peak_consumption + month_data.off_peak_consumption)')
            logger.debug(f'normal_consumption = {month_data.monthly_consumption} - ({month_data.peak_consumption} + {month_data.off_peak_consumption}) = {normal_consumption}')
            logger.debug(f'Normal hour value: {normal_hour_value}')
            logger.debug(f'Peak hour value: {peak_hour_value}')
            logger.debug(f'Off peak hour value: {off_peak_hour_value}')

            # Distribute values across the hours of each day
            for day in range(1, days_in_month + 1):
                for hour in range(24):
                    if hour == 24:
                        hour = 0
                    # Peak hours condition
                    if peak_hours_1[0] <= hour < peak_hours_1[1] or peak_hours_2[0] <= hour < peak_hours_2[1]:
                        all_hourly_data.append(peak_hour_value)
                    # Off-peak hours condition (split into two cases)
                    elif (off_peak_hours[0] <= hour < 24) or (0 <= hour < off_peak_hours[1]):
                        all_hourly_data.append(off_peak_hour_value)
                    # Normal hours condition
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
        combinations = data.get("combinations")
        
        try:
            # Fetch consumer details
            consumer_requirement = ConsumerRequirements.objects.get(id=id)
            grid_tariff = GridTariff.objects.get(state=consumer_requirement.state, tariff_category=consumer_requirement.tariff_category)
            master_record = MasterTable.objects.get(state=consumer_requirement.state)
            record = RETariffMasterTable.objects.filter(industry=consumer_requirement.industry).first()
            # Initialize final aggregated response
            aggregated_response = {}

            if not combinations:
                logger.error("No combinations provided.")
                return Response({"error": "No combinations provided."}, status=400)

            for combination in combinations:
                input_data = {}  # Initialize the final dictionary
                new_list = []
                
                match = re.match(r'^(IPP\d+)(?:-(.+))?$', combination)

                if not match:
                    continue

                ipp_id = match.group(1)  # First part (IPP ID)
                components = match.group(2).split('-') if match.group(2) else []  # Remaining parts
                # Normalize component types from the list (extract just 'Solar', 'Wind', etc.)
                component_types = {comp.split('_')[0].lower():comp for comp in components}
                logger.debug(component_types)

                generator = User.objects.get(username=ipp_id)
                last_10_combinations = Combination.objects.filter(requirement__industry = consumer_requirement.industry, generator=generator).order_by('-id')[:10]
                # Check if there are 10 or more records
                if last_10_combinations.count() >= 10:
                    # Calculate the average
                    average_per_unit_cost = last_10_combinations.aggregate(Avg('per_unit_cost'))['per_unit_cost__avg']
                    ree = round(average_per_unit_cost/2)
                elif record:
                    ree = record.re_tariff
                else:
                    ree = 4 #this is re but conflicting with re function so used as ree

                # Query generator's portfolios
                solar_data = SolarPortfolio.objects.filter(user=generator, project=component_types['solar']) if 'solar' in component_types else None
                wind_data = WindPortfolio.objects.filter(user=generator, project=component_types['wind']) if 'wind' in component_types else None
                ess_data = ESSPortfolio.objects.filter(user=generator, project=component_types['ess']) if 'ess' in component_types else None

                portfolios = list(chain(*(d for d in [solar_data, wind_data, ess_data] if d is not None)))

                include_ISTS = False
                for p in portfolios:
                    if p.connectivity == "CTU":
                        include_ISTS = True
                        break
                    elif p.state == consumer_requirement.state:
                        include_ISTS = False
                        break

                if not portfolios:
                    include_ISTS = True

                ISTS_charges = master_record.ISTS_charges if include_ISTS else 0

                logger.debug(f'solar_data: {solar_data}')
                logger.debug(f'wind_data: {wind_data}')
                logger.debug(f'ess_data: {ess_data}')

                solar = solar_data.first() if solar_data else None
                wind = wind_data.first() if wind_data else None
                ess = ess_data.first() if ess_data else None

                if (solar and solar.connectivity == 'CTU') or \
                    (wind and wind.connectivity == 'CTU') or \
                    (ess and ess.connectivity == 'CTU'):

                    connectivity = 'CTU'
                else:
                    connectivity = 'STU'
                    
                solar_project = []
                wind_project = []
                ess_project = []
                    
                # Initialize data for the current generator
                input_data[generator.username] = {}

                # Add Solar projects if solar_data exists
                if solar_data:
                    if solar_data.exists():
                        input_data[generator.username]["Solar"] = {}
                        for solar in solar_data:

                            solar_project.append(solar.project)

                            if not solar.hourly_data:
                                continue

                            # Extract profile data from file
                            profile_data = self.extract_profile_data(solar.hourly_data.path)
                            # Divide all rows by 5
                            profile_data = profile_data / solar.available_capacity # model algorithm considering profile for per MW so that's why we are dividing profile by available capacity
                            input_data[generator.username]["Solar"][solar.project] = {
                                "profile": profile_data,
                                "max_capacity": solar.available_capacity,
                                "marginal_cost": solar.expected_tariff * 1000,
                                "capital_cost": solar.capital_cost,
                            }

                # Add Wind projects if wind_data exists
                if wind_data:
                    if wind_data.exists():
                        input_data[generator.username]["Wind"] = {}
                        for wind in wind_data:

                            wind_project.append(wind.project)

                            if not wind.hourly_data:
                                continue

                            # Extract profile data from file
                            profile_data = self.extract_profile_data(wind.hourly_data.path)
                            # Divide all rows by 5
                            profile_data = profile_data / wind.available_capacity # model algorithm considering profile for per MW so that's why we are dividing profile by available capacity

                            input_data[generator.username]["Wind"][wind.project] = {
                                "profile": profile_data,
                                "max_capacity": wind.available_capacity,
                                "marginal_cost": wind.expected_tariff * 1000,
                                "capital_cost": wind.capital_cost,
                            }

                # Add ESS projects if ess_data exists
                if ess_data:
                    if ess_data.exists():
                        input_data[generator.username]["ESS"] = {}
                        for ess in ess_data:

                            ess_project.append(ess.project)

                            input_data[generator.username]["ESS"][ess.project] = {
                                "DoD": ess.efficiency_of_dispatch,
                                "efficiency": ess.efficiency_of_dispatch,
                                "marginal_cost": ess.expected_tariff * 1000,
                                "capital_cost": ess.capital_cost,
                            }

            valid_combinations = []

            if new_list != generator.id:

                HourlyDemand.objects.get_or_create(requirement=consumer_requirement)
                hourly_demand = HourlyDemand.objects.get(requirement=consumer_requirement)

                if hourly_demand and hourly_demand.hourly_demand is not None:
                    # Split the comma-separated string into a list of values
                    hourly_demand_list = hourly_demand.hourly_demand.split(',')
                    # Convert list to a Pandas Series (ensures it has an index)
                    hourly_demand_series = pd.Series(hourly_demand_list)
                    # Convert all values to numeric (float), coercing errors to NaN
                    hourly_demand = pd.to_numeric(hourly_demand_series, errors='coerce')
                    # Print the numeric Series with index numbers
                else:
                    # monthly data conversion in hourly data
                    hourly_demand = self.calculate_hourly_demand(consumer_requirement)
                
                # 8760 rows should be there if more then remove extra and if less then show error
                if len(hourly_demand) > 8760:
                    hourly_demand = hourly_demand.iloc[:8760]
                elif len(hourly_demand) < 8760:
                    padding_length = 8760 - len(hourly_demand)
                    hourly_demand = pd.concat([hourly_demand, pd.Series([0] * padding_length)], ignore_index=True)
                    
                logger.debug(f'length: {len(hourly_demand)}')
                re_replacement = 25
                for i in range(1, 11):
                    if i == 7:
                        re_replacement = 80
                    elif i == 8:
                        re_replacement = 85
                    elif i == 9:
                        re_replacement = 90
                    elif i == 10:
                        re_replacement = 95
                            
                    logger.debug(re_replacement)
                    logger.debug(input_data)
                    response_data = optimization_model(input_data, hourly_demand=hourly_demand, re_replacement=re_replacement, valid_combinations=valid_combinations, OA_cost=(ISTS_charges + master_record.state_charges)*1000)

                    logger.debug('***********')
                    logger.debug(f'response_data: {response_data}')

                    # if response_data != 'The demand cannot be met by the IPPs':
                    if not response_data.get('error'):
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
                            solar_state = wind_state = ess_state = None

                            # Helper function to fetch the component and its COD
                            def get_component_and_cod(component_name, generator, portfolio_model):
                                try:
                                    portfolio = portfolio_model.objects.get(user=generator, project=component_name)
                                    return portfolio, portfolio.cod, portfolio.state
                                except portfolio_model.DoesNotExist:
                                    return None, None, None

                            # Fetch solar, wind, and ESS components and their CODs
                            if component_1:
                                if 'Solar' in component_1:
                                    solar, solar_cod, solar_state  = get_component_and_cod(component_1, generator, SolarPortfolio)
                                elif 'Wind' in component_1:
                                    wind, wind_cod, wind_state  = get_component_and_cod(component_1, generator, WindPortfolio)
                                elif 'ESS' in component_1:
                                    ess, ess_cod, ess_state  = get_component_and_cod(component_1, generator, ESSPortfolio)

                            if component_2:
                                if 'Wind' in component_2:
                                    wind, wind_cod, wind_state  = get_component_and_cod(component_2, generator, WindPortfolio)
                                elif 'ESS' in component_2:
                                    ess, ess_cod, ess_state  = get_component_and_cod(component_2, generator, ESSPortfolio)

                            if component_3:
                                if 'ESS' in component_3:
                                    ess, ess_cod, ess_state  = get_component_and_cod(component_3, generator, ESSPortfolio)

                            # Determine the greatest COD
                            cod_dates = [solar_cod if solar else None, wind_cod if wind else None, ess_cod if ess else None]
                            cod_dates = [date for date in cod_dates if date is not None]
                            greatest_cod = max(cod_dates) if cod_dates else None

                            # Map each portfolio to its state
                            state = {}
                            if solar:
                                state[solar.project] = solar_state
                            if wind:
                                state[wind.project] = wind_state
                            if ess:
                                state[ess.project] = ess_state

                            annual_demand_met = (details["Annual Demand Met"]) / 1000

                            combo = Combination.objects.filter(combination=combination_key, requirement=consumer_requirement, annual_demand_offset=details["Annual Demand Offset"]).first()
                            terms_sheet = StandardTermsSheet.objects.filter(combination=combo).first()

                            terms_sheet_sent = False
                            if combo:
                                terms_sheet_sent = combo.terms_sheet_sent
                            else:
                                # Save to Combination table
                                combo, created = Combination.objects.get_or_create(
                                    requirement=consumer_requirement,
                                    generator=generator,
                                    re_replacement=re_replacement if re_replacement else 65,
                                    combination=combination_key,
                                    state=state,
                                    optimal_solar_capacity=details["Optimal Solar Capacity (MW)"],
                                    optimal_wind_capacity=details["Optimal Wind Capacity (MW)"],
                                    optimal_battery_capacity=details["Optimal Battery Capacity (MW)"],
                                    per_unit_cost=details["Per Unit Cost"]/1000,
                                    final_cost=details['Final Cost'] / 1000,
                                    annual_demand_offset=details["Annual Demand Offset"],
                                    annual_demand_met=annual_demand_met,
                                    annual_curtailment=details["Annual Curtailment"],
                                    connectivity=connectivity
                                )

                            sent_from_you = False
                            if terms_sheet:
                                if terms_sheet.from_whom == optimize_capacity_user:
                                    sent_from_you = True
                                else:
                                    sent_from_you = False

                            re_index = generator.re_index

                            if re_index is None:
                                re_index = 0

                            OA_cost = (details["Final Cost"] - details['Per Unit Cost']) / 1000
                            details['Per Unit Cost'] = details['Per Unit Cost'] / 1000
                            details['Final Cost'] = details['Final Cost'] / 1000
                            details["Annual Demand Met"] = (details["Annual Demand Met"]) / 1000

                            # Update the aggregated response dictionary
                            if combination_key not in aggregated_response:
                                aggregated_response[combination_key] = {}
                            aggregated_response[combination_key][re_replacement] = {
                                **details,
                                'OA_cost': ISTS_charges + master_record.state_charges,
                                'ISTS_charges': ISTS_charges,
                                'state_charges': master_record.state_charges,
                                "state": state,
                                "greatest_cod": greatest_cod,
                                "terms_sheet_sent": terms_sheet_sent,
                                "sent_from_you": sent_from_you,
                                "connectivity": connectivity,
                                "re_index": re_index,
                                "re_replacement": re_replacement,
                                "per_unit_savings": grid_tariff.cost - details['Per Unit Cost'] - ISTS_charges - master_record.state_charges,
                            }
                    else:
                        print('newwwwwwww')
                        combi_parts = [
                            response_data.get('ipp'),
                            response_data.get('solar'),
                            response_data.get('wind'),
                            response_data.get('ess')
                        ]

                        # Remove None values
                        filtered_parts = [str(part) for part in combi_parts if part is not None]

                        # Join with underscore
                        combi = "_".join(filtered_parts)
                        print(combi)
                        if combi not in aggregated_response:
                            aggregated_response[combi] = {}
                        aggregated_response[combi][re_replacement] = "The demand cannot be met"

                    re_replacement += 10        
                            
            if not aggregated_response and optimize_capacity_user=='Consumer':
                return Response({"error": "The demand cannot be met by the IPPs."}, status=status.HTTP_200_OK)
            elif not aggregated_response and optimize_capacity_user=='Generator':
                return Response({"error": "The demand cannot be made by your projects."}, status=status.HTTP_200_OK)
            

            # Extract top 3 records with the smallest "Per Unit Cost"
            # top_three_records = sorted(aggregated_response.items(), key=lambda x: x[1]['Per Unit Cost'])[:3]
            # Function to round values to 2 decimal places
            def round_nested_output(data, precision=2):
                for outer_key, inner_dict in data.items():
                    for re_key, value in inner_dict.items():
                        # Skip if value is not a dictionary (e.g., a string)
                        if not isinstance(value, dict):
                            continue
                        
                        for k, v in value.items():
                            if isinstance(v, (int, float)):
                                value[k] = round(v, precision)
                            elif isinstance(v, dict):
                                # If it's another dict (like 'state'), leave it unchanged
                                continue
                            # Leave datetime, bool, and other non-number values as-is
                return data

            rounded_data = round_nested_output(aggregated_response, precision=2)



            return Response(rounded_data, status=status.HTTP_200_OK)


        except User.DoesNotExist:
            return Response({"error": "Consumer or generator not found."}, status=status.HTTP_404_NOT_FOUND)

        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Consumer requirements not found."}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            tb = traceback.format_exc()  # Get the full traceback
            traceback_logger.error(f"Exception: {str(e)}\nTraceback:\n{tb}")  # Log error with traceback
            return Response({"error": str(e), "Traceback": tb}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CapacitySizingCombinationAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user = get_admin_user(user_id)
            combinations = CapacitySizingCombination.objects.filter(generator=user).order_by('-id')
            serializer = CapacitySizingCombinationSerializer(combinations, many=True)
            return Response(serializer.data)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        user = request.data.get('generator')
        user = get_admin_user(user)
        data = request.data.copy()
        data['generator'] = user.id
        serializer = CapacitySizingCombinationSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class HolidayListAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dates = list(NationalHoliday.objects.values_list('date', flat=True))
        return Response(dates)
    
class OfflinePaymentAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OfflinePaymentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Offline Payment Submitted Successfully"}, status=status.HTTP_201_CREATED)
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

class DemandSummaryAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user = get_admin_user(user_id)

            demand = GeneratorHourlyDemand.objects.filter(generator=user).first()

            if not demand:
                return Response({"error": "Demand data not found."}, status=status.HTTP_404_NOT_FOUND)

            hourly_data = demand.get_hourly_data_as_list()

            if not hourly_data:
                return Response({"error": "Hourly demand data is empty."}, status=status.HTTP_404_NOT_FOUND)

            return Response({
                "generator": str(demand.generator),
                "total": round(sum(hourly_data), 2),
                "highest": round(max(hourly_data), 2),
                "lowest": round(min(hourly_data), 2),
                "average": round(statistics.mean(hourly_data), 2)
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
