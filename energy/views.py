import ast
import base64
import calendar
from calendar import monthrange
import csv
import io
from itertools import chain
import re
import fitz
from django.shortcuts import get_object_or_404
import pytz
import requests
from accounts.models import User
from accounts.views import JWTAuthentication
from .models import GeneratorHourlyDemand, GeneratorMonthlyConsumption, GeneratorOffer, GridTariff, Industry, NegotiationInvitation, ScadaFile, SolarPortfolio, State, StateTimeSlot, WindPortfolio, ESSPortfolio, ConsumerRequirements, MonthlyConsumptionData, HourlyDemand, Combination, StandardTermsSheet, MatchingIPP, SubscriptionType, SubscriptionEnrolled, Notifications, Tariffs, NegotiationWindow, MasterTable, RETariffMasterTable, PerformaInvoice, SubIndustry
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from rest_framework.serializers import ValidationError
from .serializers import CSVFileSerializer, CreateOrderSerializer, PaymentTransactionSerializer, PerformaInvoiceCreateSerializer, PerformaInvoiceSerializer, ScadaFileSerializer, SolarPortfolioSerializer, StateTimeSlotSerializer, WindPortfolioSerializer, ESSPortfolioSerializer, ConsumerRequirementsSerializer, MonthlyConsumptionDataSerializer, StandardTermsSheetSerializer, SubscriptionTypeSerializer, SubscriptionEnrolledSerializer, NotificationsSerializer, TariffsSerializer
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

# Create your views here.

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

# Get the logged-in user
def get_admin_user(user_id):
        logged_in_user = User.objects.get(id=user_id)
        # Determine the admin user for the logged-in user
        admin_user_id = logged_in_user.parent if logged_in_user.parent else logged_in_user
        # admin_user = User.objects.get(id=admin_user_id)

        return admin_user_id

class StateListAPI(APIView):
    def get(self, request):
        names = list(State.objects.values_list('name', flat=True))
        return Response(names)
        
class IndustryListAPI(APIView): 
    def get(self, request):
        industries = Industry.objects.prefetch_related('sub_industries').all()
        
        industry_data = {
            industry.name: {sub_industry.name for sub_industry in industry.sub_industries.all()}
            for industry in industries
        }

        return Response(industry_data)
    
class StateTimeSlotAPI(APIView):
    def get(self, request):
        states = StateTimeSlot.objects.all()
        serializer = StateTimeSlotSerializer(states, many=True)
        return Response(serializer.data)
    
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
                file_content = ContentFile(decoded_file, name=file_name)
                # Validate the file content
                with io.BytesIO(decoded_file) as file_stream:
                    try:
                        # Read the Excel file into a DataFrame, retrieving sheet names
                        xls = pd.ExcelFile(file_stream)
                        if energy_type not in xls.sheet_names:
                            return Response({"error": "Wrong uploaded file: Sheet name does not match energy type."}, 
                                            status=status.HTTP_400_BAD_REQUEST)
                        
                        # Read the Excel file into a DataFrame
                        df = pd.read_excel(file_stream)
                    except Exception as e:
                        return Response({"error": f"Invalid file format: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

                    # Check for the required number of rows
                    current_year = datetime.now().year
                    is_leap_year = (current_year % 4 == 0 and current_year % 100 != 0) or (current_year % 400 == 0)
                    required_rows = 8786 if is_leap_year else 8762

                    # Verify row count
                    if df.shape[0] != required_rows:
                        return Response(
                            {
                                "error": f"Invalid data rows: Expected {required_rows} rows, but got {df.shape[0]}"
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # Add the validated file to the request data
                request.data["hourly_data"] = file_content

            except Exception as e:
                return Response({"error": f"{str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


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
            df = pd.read_excel(scada_file.file, sheet_name="Logger 1", header=7)

            # Extract the required column
            column_name = "Active(I) Total [kWh]\n (1.0.1.29.0.255)"  # Ensure this matches exactly
            if column_name not in df.columns:
                return Response(
                    {"error": "Required column not found in the sheet."},
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

            # Check if the record exists
            instance = MonthlyConsumptionData.objects.filter(
                requirement=requirement, month=month
            ).first()

            if instance:
                # Update the existing record
                serializer = MonthlyConsumptionDataSerializer(instance, data=item)
                if serializer.is_valid():
                    serializer.save()
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Create a new record
                serializer = MonthlyConsumptionDataSerializer(data=item)
                if serializer.is_valid():
                    serializer.save()
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": "Data processed successfully."},
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

        try:
            # Read the CSV content
            file_data = csv_file_content.read().decode('utf-8').splitlines()
            csv_reader = csv.DictReader(file_data)

            # Get the ConsumerRequirement object
            try:
                requirement = ConsumerRequirements.objects.get(id=requirement_id)
            except ConsumerRequirements.DoesNotExist:
                return Response(
                    {"error": "requirement not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Process each row in the CSV file
            for row in csv_reader:
                print(row)
                try:
                    monthly_consumption = MonthlyConsumptionData.objects.get(requirement=requirement, month=row['Month'])
                    
                except MonthlyConsumptionData.DoesNotExist:
                    monthly_consumption = MonthlyConsumptionData()
                    monthly_consumption.requirement=requirement
                    monthly_consumption.month=row['Month']

                monthly_consumption.monthly_consumption=float(row['Monthly Consumption'])
                monthly_consumption.peak_consumption=float(row['Peak Consumption'])
                monthly_consumption.off_peak_consumption=float(row['Off Peak Consumption'])
                monthly_consumption.monthly_bill_amount=float(row['Monthly Bill Amount'])
                monthly_consumption.save()
                
            return Response({'message': 'Success'}, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(str(e))
            return Response(
                {"error": f"An error occurred while processing the file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UploadMonthlyConsumptionBillAPI(APIView):
    def extract_required_data(self, pdf_path):
        """Extract TOD 1, TOD 2, TOD 3, and Current Month Bill from PDF"""
        extracted_text = ""
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                extracted_text += page.get_text("text") + "\n"

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

            # Validate extracted data to ensure TOD values exist
            if extracted_data["TOD 1"] == "Not found" or extracted_data["TOD 2"] == "Not found" or extracted_data["TOD 3"] == "Not found":
                return Response(
                    {"error": "Invalid file format. Required TOD values not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Calculate required values
            peak_consumption = round(float(extracted_data["TOD 1"]))  # TOD 1
            off_peak_consumption = round(float(extracted_data["TOD 3"]))  # TOD 3
            monthly_consumption = round(peak_consumption + round(float(extracted_data["TOD 2"])) + off_peak_consumption, 2)  # TOD 1 + TOD 2 + TOD 3
            monthly_bill_amount = extracted_data["Current Month Bill"]  # Current Month Bill

            # Update instance with extracted data
            instance.peak_consumption = peak_consumption
            instance.off_peak_consumption = off_peak_consumption
            instance.monthly_consumption = monthly_consumption
            instance.monthly_bill_amount = monthly_bill_amount
            instance.save()

        return Response(
            {
                "message": "Bill file uploaded and processed successfully."
            },
            status=status.HTTP_200_OK,
        )

class MatchingIPPAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        try:
            # Fetch the requirement
            requirement = ConsumerRequirements.objects.get(id=pk)

            solar_data = SolarPortfolio.objects.filter(
                cod__lte=requirement.procurement_date
            ).filter(
                Q(state=requirement.state) | Q(connectivity="CTU"),
            ).values("user", "user__username", "state", "available_capacity", "updated")

            wind_data = WindPortfolio.objects.filter(
                cod__lte=requirement.procurement_date
            ).filter(
                Q(state=requirement.state) | Q(connectivity="CTU"),
            ).values("user", "user__username", "state", "available_capacity", "updated")

            ess_data = ESSPortfolio.objects.filter(
                cod__lte=requirement.procurement_date
            ).filter(
                Q(state=requirement.state) | Q(connectivity="CTU"),
            ).values("user", "user__username", "state", "available_capacity", "updated")
        
            print('solar.....', solar_data)
            print('wind.....', wind_data)
            print('ess.....', ess_data)
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
            print('unique data...........')
            print(unique_data)
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
                print(has_not_updated)
                
                if not is_subscribed:
                    print('not subscribed...........')
                    # Send notification to user
                    message = f"Your subscription is inactive. Please subscribe to start receiving and accepting offers."
                    send_notification(user.id, message) 
                elif has_not_updated:
                    print('not updated...........')
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

                    # Update the user's available capacity
                    entry["available_capacity"] = available_capacity
                    filtered_data.append(entry)  # Keep only subscribed users

            sorted_data = sorted(filtered_data, key=lambda x: x["available_capacity"], reverse=True)

            # Get only the top 3 matches
            top_three_matches = sorted_data[:3]
            print('top three matched...........')
            print(top_three_matches)

            # Extract user IDs from the top three matches
            user_ids = [match["user"] for match in top_three_matches]

            # Save the user IDs in MatchingIPP
            matching_ipp, created = MatchingIPP.objects.get_or_create(requirement=requirement)
            matching_ipp.generator_ids = user_ids
            matching_ipp.save()

            # Return the top three matches as the response
            return Response(top_three_matches, status=status.HTTP_200_OK)
        except Exception as e:
            print('error====')
            print(e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MatchingConsumerAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        user = User.objects.get(id=pk)
        user = get_admin_user(pk)

        try:
            # Get all GenerationPortfolio records for the user
            solar_data = SolarPortfolio.objects.filter(user=user)
            wind_data = WindPortfolio.objects.filter(user=user)
            ess_data = ESSPortfolio.objects.filter(user=user)

            # Combine all data
            data = list(chain(solar_data, wind_data, ess_data))

            # Ensure generation portfolio exists
            if not data:
                return Response(
                    {"error": "No generation portfolio records found for the user."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            
            # Separate CTU and non-CTU portfolios
            ctu_portfolios = [p for p in data if p.connectivity == "CTU"]
            non_ctu_portfolios = [p for p in data if p.connectivity != "CTU"]

            # Collect filtering criteria
            states = set(p.state for p in non_ctu_portfolios)
            cod_dates = [p.cod for p in non_ctu_portfolios if p.cod]

            # Get consumer requirements based on filtering logic
            filtered_data = ConsumerRequirements.objects.none()  # Empty queryset initially

            if ctu_portfolios:
                # Match procurement date only for CTU projects
                ctu_cod_dates = [p.cod for p in ctu_portfolios if p.cod]

                ctu_filtered_data = ConsumerRequirements.objects.filter(
                    procurement_date__gte=min(ctu_cod_dates),  # Use earliest COD from CTU projects
                )

                # Merge with existing filter
                filtered_data = filtered_data | ctu_filtered_data

            if states and cod_dates:
                # Match state-wise and COD-wise for non-CTU projects
                state_filtered_data = ConsumerRequirements.objects.filter(
                    state__in=states,
                    procurement_date__gte=min(cod_dates),  # Use earliest COD from non-CTU projects
                )

                # Merge both results (CTU + State-wise matching)
                filtered_data   = filtered_data | state_filtered_data
            
            # Check for subscription and notify consumers without a subscription
            exclude_consumers = []
            exclude_requirements = []
            for requirement in filtered_data:
                
                if not SubscriptionEnrolled.objects.filter(user=requirement.user, status='active').exists():

                    # Add the consumer to the notification list
                    exclude_consumers.append(requirement.user)

                    # Send a notification (customize this part as per your notification system)
                    message = f"Please activate your subscription to access matching services."
                    Notifications.objects.create(
                        user_id=requirement.user.id,
                        message=message,
                    )

                # Exclude users who do not have monthly consumption data for all 12 months
                users_with_complete_consumption = MonthlyConsumptionData.objects.filter(requirement=requirement)
                print('monthly ', len(users_with_complete_consumption))

                # Check if hourly demand data is available for any requirement
                users_with_hourly_demand = HourlyDemand.objects.filter(requirement=requirement)
                print('hourly ', users_with_hourly_demand)

                if len(users_with_complete_consumption) != 12 and not users_with_hourly_demand:

                    # Add the consumer to the notification list
                    exclude_requirements.append(requirement.id)

                    # Send a notification (customize this part as per your notification system)
                    message = f"Please complete your profile to access matching services."
                    Notifications.objects.create(
                        user_id=requirement.user.id,
                        message=message,
                    )


            # Exclude consumers without a subscription from the response
            filtered_data = filtered_data.exclude(user__in=exclude_consumers)
            filtered_data = filtered_data.exclude(id__in=exclude_requirements)

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
            user = get_admin_user(user_id)
            user_id = user.id
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
                
        # Read the specified sheet from the Excel file
        df = pd.read_excel(file_path, sheet_name=sheet)

        # Select only the relevant column (B) and start from the 4th row (index 3)
        df_cleaned = df.iloc[3:, 1].reset_index(drop=True)  # Column B corresponds to index 1

        # Fill NaN values with 0
        profile = df_cleaned.fillna(0).reset_index(drop=True)
                
        return profile
    

    @staticmethod
    def calculate_hourly_demand(consumer_requirement, state="Madhya Pradesh"):
        consumer_demand = HourlyDemand.objects.get(requirement=consumer_requirement)

        # Define the state-specific hours
        state_hours = {
            "Madhya Pradesh": {
                "peak_hours_1": (6, 9),  # 6 AM to 9 AM
                "peak_hours_2": (17, 22),  # 5 PM to 10 PM
                "off_peak_hours": (22, 6),  # 10 PM to 6 AM
            }
        }

        monthly_consumptions = MonthlyConsumptionData.objects.filter(requirement=consumer_requirement)

        # Get state-specific hours
        hours = state_hours[state]
        peak_hours_1 = hours["peak_hours_1"]
        peak_hours_2 = hours["peak_hours_2"]
        off_peak_hours = hours["off_peak_hours"]
        total_hours = 24

        # Calculate total hours for all ranges
        peak_hours_total = (peak_hours_1[1] - peak_hours_1[0]) + (peak_hours_2[1] - peak_hours_2[0])
        off_peak_hours_total = off_peak_hours[1] - off_peak_hours[0]
        normal_hours = total_hours - peak_hours_total - off_peak_hours_total

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

            # Distribute values across the hours of each day
            for day in range(1, days_in_month + 1):
                for hour in range(24):
                    if peak_hours_1[0] <= hour < peak_hours_1[1] or peak_hours_2[0] <= hour < peak_hours_2[1]:
                        all_hourly_data.append(peak_hour_value)
                    elif off_peak_hours[0] <= hour < off_peak_hours[1]:
                        all_hourly_data.append(off_peak_hour_value)
                    else:
                        all_hourly_data.append(normal_hour_value)

        # Update the HourlyDemand model
        consumer_demand.set_hourly_data_from_list(all_hourly_data)
        consumer_demand.save()
        print('-----------all_hourly_data-----------')
        print(all_hourly_data)
        # Return the data in the desired flat format
        return pd.Series(all_hourly_data)

    def post(self, request):
        data = request.data
        optimize_capacity_user = data.get("optimize_capacity_user") #consumer or generator
        user_id = data.get("user_id")
        id = data.get("requirement_id")

        if data.get("re_replacement"):
            re_replacement = int(data.get("re_replacement"))
        else:
            re_replacement = None

        if re_replacement == 0:
            return Response({"message": "No available capacity."}, status=status.HTTP_200_OK)
        

         # Check optimize_capacity value
        if optimize_capacity_user == "Consumer":
            matching_ipps = MatchingIPP.objects.get(requirement=id)
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
                        Q(state=consumer_requirement.state) | Q(connectivity="CTU"),
                        cod__lte=consumer_requirement.procurement_date
                    )
                    wind_data = WindPortfolio.objects.filter(
                        user=generator
                    ).filter(
                        Q(state=consumer_requirement.state) | Q(connectivity="CTU"),
                        cod__lte=consumer_requirement.procurement_date
                    )
                    ess_data = ESSPortfolio.objects.filter(
                        user=generator
                    ).filter(
                        Q(state=consumer_requirement.state) | Q(connectivity="CTU"),
                        cod__lte=consumer_requirement.procurement_date
                    )


                    # separating combinations based on connectivity 
                    solar_data = solar_data.filter(connectivity=connectivity)
                    wind_data = wind_data.filter(connectivity=connectivity)
                    ess_data = ess_data.filter(connectivity=connectivity)

                    solar_project = []
                    wind_project = []
                    ess_project = []
                    print('matched======')
                    print(solar_data)
                    print(wind_data)
                    print(ess_data)
                    print('matched======')

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

                            if not wind.hourly_data:
                                continue

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

                print('===================input data===================')
                print(input_data)
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

                    print('hourly demand=========')
                    print(hourly_demand)
                
                    # 8760 rows should be there if more then remove extra and if less then show error
                    if len(hourly_demand) > 8760:
                        hourly_demand = hourly_demand.iloc[:8760]
                    elif len(hourly_demand) < 8760:
                        padding_length = 8760 - len(hourly_demand)
                        hourly_demand = pd.concat([hourly_demand, pd.Series([0] * padding_length)], ignore_index=True)
                    response_data = optimization_model(input_data, hourly_demand=hourly_demand, re_replacement=re_replacement, valid_combinations=valid_combinations)

                    if response_data != 'The demand cannot be met by the IPPs':
                        for combination_key, details in response_data.items():
                        # Extract user and components from combination_key
                            components = combination_key.split('-')
                            print('components==========')
                            print(components)
                            print('components==========')

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

                            annual_demand_met = (details["Annual Demand Met"] * 24) / 1000000

                            combo = Combination.objects.filter(combination=combination_key, requirement=consumer_requirement, annual_demand_offset=details["Annual Demand Offset"]).first()
                            terms_sheet = StandardTermsSheet.objects.filter(combination=combo).first()

                            terms_sheet_sent = False
                            if combo:
                                terms_sheet_sent = combo.terms_sheet_sent
                            else:
                                # Save to Combination table
                                combo = Combination.objects.get_or_create(
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
                            details["Annual Demand Met"] = (details["Annual Demand Met"] * 24) / 1000000

                           # Update the aggregated response dictionary
                            if combination_key not in aggregated_response:
                                aggregated_response[combination_key] = {
                                    **details,
                                    'OA_cost': OA_cost,
                                    "state": state,
                                    "greatest_cod": greatest_cod,
                                    "terms_sheet_sent": terms_sheet_sent,
                                    "sent_from_you": sent_from_you,
                                    "connectivity": connectivity,
                                    "re_index": re_index,
                                }
                            else:
                                # Merge the details if combination already exists
                                aggregated_response[combination_key].update(details)
                            print('===================aggregated_response===================')
                            print(aggregated_response[combination_key])
                    
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
                return Response({"error": "The demand cannot be made by your projects."}, status=status.HTTP_200_OK)
            print('==============')
            print(aggregated_response)
            print('==============')

            # Extract top 3 records with the smallest "Per Unit Cost"
            top_three_records = sorted(aggregated_response.items(), key=lambda x: x[1]['Per Unit Cost'])[:3]
            # Function to round values to 2 decimal places
            def round_values(record):
                return {key: round(value, 2) if isinstance(value, (int, float)) else value for key, value in record.items()}
            # Round the values for the top 3 records
            top_three_records_rounded = {
                key: round_values(value) for key, value in top_three_records
            }   

            print(top_three_records_rounded)

            return Response(top_three_records_rounded, status=status.HTTP_200_OK)


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
            consumption_data = MonthlyConsumptionData.objects.filter(requirement=pk).values('month', 'monthly_consumption', 'peak_consumption', 'off_peak_consumption', 'monthly_bill_amount')

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
                        "consumption": entry["monthly_consumption"],
                        "peak_consumption": entry["peak_consumption"],
                        "off_peak_consumption": entry["off_peak_consumption"],
                        "monthly_bill_amount": entry["monthly_bill_amount"],
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
                print(len(all_records), '11111111111')

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
                            "state": ast.literal_eval(record.combination.state),
                            "optimal_solar_capacity": round(record.combination.optimal_solar_capacity, 2),
                            "optimal_wind_capacity": round(record.combination.optimal_wind_capacity, 2),
                            "optimal_battery_capacity": round(record.combination.optimal_battery_capacity, 2),
                            "optimal_battery_capacity": round(record.combination.optimal_battery_capacity, 2),
                            "per_unit_cost": round(record.combination.per_unit_cost, 2),
                            "final_cost": round(record.combination.final_cost, 2),
                            # Add more fields as required
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

        if from_whom not in ['Consumer', 'Generator']:
            return Response({"error": "Invalid value for 'from_whom'."}, status=status.HTTP_400_BAD_REQEUST)

        if not requirement_id:
            return Response({"error": "requirement_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
        except ConsumerRequirements.DoesNotExist:
            return Response({"error": "Invalid requirement_id."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            combination = Combination.objects.filter(combination=combination, requirement=requirement).order_by('-id').first()
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

            Tariffs.objects.get_or_create(terms_sheet=termsheet, offer_tariff=termsheet.combination.per_unit_cost)
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

                record.save()
                return Response(
                    {"message": f"Terms sheet {action.lower()} successfully.", "record": StandardTermsSheetSerializer(record).data},
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
    def get(self, request, user_type):
        # Get all subscription types
        subscription_types = SubscriptionType.objects.filter(user_type=user_type)

        # Serialize the subscription types
        serializer = SubscriptionTypeSerializer(subscription_types, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
        
class SubscriptionEnrolledAPIView(APIView):
    def get(self, request, pk):
        try:
            user = get_admin_user(pk)
            pk = user.id
            print(pk)
            subscription = SubscriptionEnrolled.objects.filter(user=pk)
            print(subscription)
            subscription = SubscriptionEnrolled.objects.filter(user=pk).order_by('start_date').first()
            print(subscription)
            data = {
                "id": subscription.id,
                "user": subscription.user.id,
                "subscription_type": subscription.subscription.subscription_type,
                "start_date": subscription.start_date,
                "end_date": subscription.end_date,
                "status": subscription.status,
            }
            print(data)
            return Response(data, status=status.HTTP_200_OK)
        except SubscriptionEnrolled.DoesNotExist:
            return Response({"message": "No subscription found for this user."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



    def post(self, request):
        user = request.data.get('user')
        user = get_admin_user(user)
        user = user.id

        # Check if the user is already enrolled in this subscription
        existing_subscription = SubscriptionEnrolled.objects.filter(user=user, status='active').first()

        # If no existing subscription or it has expired, create a new subscription
        serializer = SubscriptionEnrolledSerializer(instance=existing_subscription, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

def send_notification(user_id, message):
    """
    Ensures notification is created and triggers WebSocket update only for new notifications.
    """
    notification, created = Notifications.objects.get_or_create(
        user_id=user_id,
        message=message,
        defaults={"is_read": False}
    )

    # Only trigger WebSocket update if a new notification was created
    if created:
        unread_count = Notifications.objects.filter(user_id=user_id, is_read=False).count()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user_id}",
            {
                "type": "send_notification",
                "unread_count": unread_count,
            }
        )

    return notification
        
class NotificationsAPI(APIView):
    
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
                f"user_{user_id}",
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
        print(now_time)
        # Calculate the negotiation window start time (tomorrow at 10:00 AM)
        next_day_date = (now_time + timedelta(days=1)).date()
        next_day_10_am = datetime.combine(next_day_date, time(10, 0))
        next_day_10_am_aware = timezone.make_aware(next_day_10_am, timezone=timezone.get_current_timezone())
        # Define the end time for the negotiation window (e.g., 1 hour after start time)
        end_time = next_day_10_am_aware + timedelta(hours=1)
        print(next_day_10_am_aware)
        print(end_time)
        
        # Only consumers can initiate the negotiation
        if user.user_category == 'Generator':
            # Notify the consumer linked in the terms sheet
            try:
                response = MatchingIPPAPI.get(self, request, terms_sheet.combination.requirement.id)
                matching_ipps = response.data

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
                
                # Calculate the execution time (30 min after end_time)
                # execute_at = negotiation_window.end_time + timedelta(minutes=1)
                execute_at = datetime.now() + timedelta(minutes=1)

                # Create a clocked schedule for the specific execution time
                clocked_schedule, created = ClockedSchedule.objects.get_or_create(
                    clocked_time=execute_at
                )
                

                # Create a unique periodic task that runs one time
                task, created = PeriodicTask.objects.get_or_create(
                    name=f'negotiation_reminder_{tariff.id}',  # Unique task name
                    task='energy.tasks.send_negotiation_reminder',  # Celery task function
                    defaults={
                        'args': json.dumps([tariff.id, 1]),  # Pass window ID + attempt count (1st attempt)
                        'one_off': True,  # Runs only once
                        'enabled': True,
                        'clocked': clocked_schedule  # Assign the clocked schedule
                    }
                )

                NegotiationInvitation.objects.create(negotiation_window=negotiation_window,user=terms_sheet.consumer)

                # Notify recipients
                for recipient in matching_ipps:
                    print(recipient, "recipient")
                    if recipient.id == user.id:
                        continue
                    try:
                        recipient_user = User.objects.get(id=recipient['user'])
                        message=(
                            f"Consumer {terms_sheet.consumer} has initiated a negotiation for Terms Sheet {terms_sheet}. "
                            f"The negotiation window will open tomorrow at 10:00 AM. "
                            f"The starting offer tariff being provided is {offer_tariff}."
                        )
                        send_notification(recipient_user.id, message)

                        email_message = (
                            f"Consumer {user.username} has initiated a negotiation for Terms Sheet {terms_sheet}. "
                            f"The negotiation window will open tomorrow at 10:00 AM. "
                            f"The starting offer tariff being provided is {offer_tariff}.\n\n"
                            f"Click here to join the bidding window directly: http://localhost:3001/consumer/transaction-mb/{user.id}-{tariff.id}-{token}"
                        )
                        # Send email with the link
                        send_mail(
                            "Negotiation Invitation",
                            email_message,
                            settings.DEFAULT_FROM_EMAIL,
                            [recipient_user.email],
                            fail_silently=False,
                        )

                        invitation = NegotiationInvitation.objects.create(negotiation_window=negotiation_window, user=recipient_user)
                        print(invitation)
                        print('invited!!!!!!!!!!!!!!')

                    except User.DoesNotExist:
                        continue

                
                GeneratorOffer.objects.get_or_create(generator=user, tariff=tariff)

                message=(
                    f"Generator {user.username} is interested in initiating a negotiation for Terms Sheet {terms_sheet}. "
                    f"The starting offer tariff being provided is {offer_tariff}."
                )
                send_notification(terms_sheet.consumer.id, message) 

                email_message=(
                    f"Generator {user.username} is interested in initiating a negotiation for Terms Sheet {terms_sheet}. "
                    f"The starting offer tariff being provided is {offer_tariff}."
                    f"Click here to join the bidding window directly: http://localhost:3001/consumer/transaction-mb/{user.id}-{tariff.id}-{token}"
                )
                # Send email with the link
                send_mail(
                    "Negotiation Invitation",
                    email_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [recipient_user.email],
                    fail_silently=False,
                )

                #self notification
                message=(
                    f"You have initiated negotiation for Terms Sheet {terms_sheet}. "
                    f"The starting offer tariff being provided is {offer_tariff}."
                )
                send_notification(terms_sheet.consumer.id, message) 

                email_message=(
                    f"You have initiated negotiation for Terms Sheet {terms_sheet}. "
                    f"The starting offer tariff being provided is {offer_tariff}."
                    f"Click here to join the bidding window directly: http://localhost:3001/consumer/transaction-mb/{user.id}-{tariff.id}-{token}"
                )
                # Send email with the link
                send_mail(
                    "Negotiation Invitation",
                    email_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [recipient_user.email],
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

            # Calculate the execution time (30 min after end_time)
            # execute_at = negotiation_window.end_time + timedelta(minutes=1)
            execute_at = datetime.now() + timedelta(minutes=1)

            # Create a clocked schedule for the specific execution time
            clocked_schedule, created = ClockedSchedule.objects.get_or_create(
                clocked_time=execute_at
            )
            

            # Create a unique periodic task that runs one time
            task, created = PeriodicTask.objects.get_or_create(
                name=f'negotiation_reminder_{tariff.id}',  # Unique task name
                task='energy.tasks.send_negotiation_reminder',  # Celery task function
                defaults={
                    'args': json.dumps([tariff.id, 1]),  # Pass window ID + attempt count (1st attempt)
                    'one_off': True,  # Runs only once
                    'enabled': True,
                    'clocked': clocked_schedule  # Assign the clocked schedule
                }
            )

            NegotiationInvitation.objects.create(negotiation_window=negotiation_window,user=user)

            # Notify recipients
            for recipient in recipients:
                try:
                    recipient_user = User.objects.get(id=recipient)
                    message=(
                        f"Consumer {user.username} has initiated a negotiation for Terms Sheet {terms_sheet}. "
                        f"The negotiation window will open tomorrow at 10:00 AM. "
                        f"The starting offer tariff being provided is {offer_tariff}."
                    )
                    send_notification(recipient_user.id, message)

                    email_message = (
                        f"Consumer {user.username} has initiated a negotiation for Terms Sheet {terms_sheet}. "
                        f"The negotiation window will open tomorrow at 10:00 AM. "
                        f"The starting offer tariff being provided is {offer_tariff}.\n\n"
                        f"Click here to join the bidding window directly: http://localhost:3001/consumer/transaction-mb/{user.id}-{tariff.id}-{token}"
                    )
                    # Send email with the link
                    send_mail(
                        "Negotiation Invitation",
                        email_message,
                        settings.DEFAULT_FROM_EMAIL,
                        [recipient_user.email],
                        fail_silently=False,
                    )

                    invitation = NegotiationInvitation.objects.create(negotiation_window=negotiation_window, user=recipient_user)
                    print(invitation)
                    print('invited!!!!!!!!!!!!!!')
                    
                except User.DoesNotExist:
                    continue
                    
            message=(
                f"Generator {user.username} is interested in initiating a negotiation for Terms Sheet {terms_sheet}. "
                f"The starting offer tariff being provided is {offer_tariff}."
            )
            send_notification(terms_sheet.consumer.id, message) 
            email_message=(
                f"Generator {user.username} is interested in initiating a negotiation for Terms Sheet {terms_sheet}. "
                f"The starting offer tariff being provided is {offer_tariff}."
                f"Click here to join the bidding window directly: http://localhost:3001/consumer/transaction-mb/{user.id}-{tariff.id}-{token}"
            )
            # Send email with the link
            send_mail(
                "Negotiation Invitation",
                email_message,
                settings.DEFAULT_FROM_EMAIL,
                [recipient_user.email],
                fail_silently=False,
            )
                    

            return Response({"message": "Negotiation initiated. Notifications sent and negotiation window created."}, status=200)

class NegotiationWindowListAPI(APIView):
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
            response_data.append({
                "window_id": window.id,
                "window_name": window.name,
                "terms_sheet_id": window.terms_sheet.id,
                "tariff_id": tariff.id,
                "offer_tariff": round(tariff.offer_tariff, 2),
                "tariff_status": tariff.window_status,
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
            })


        return Response(response_data, status=status.HTTP_200_OK)

        
class NegotiationWindowStatusView(APIView):
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
    

class AnnualSavingsView(APIView):
    def post(self, request):
        # Common logic for both POST (annual savings calculation) and GET (annual report download)
        re = 3.67  # Initially RE value will be taken from Master Table that is provided by the client.
        requirement_id = request.data.get('requirement_id')
        generator_id = request.data.get('generator_id')
        
        try:
            requirement = ConsumerRequirements.objects.get(id=requirement_id)
            combination = Combination.objects.filter(requirement__industry = requirement.industry, generator=generator_id)
            master_record = MasterTable.objects.get(state=requirement.state)
            record = RETariffMasterTable.objects.filter(industry=requirement.industry).first()

            # Check if there are 10 or more records
            if combination.count() >= 10:
                # Calculate the average
                average_per_unit_cost = combination.aggregate(Avg('per_unit_cost'))['per_unit_cost__avg']
                re = average_per_unit_cost
            elif record:
                re = record.re_tariff
            else:
                re = 4

            # Fetch Grid cost from GridTariff (Assuming tariff_category is fixed or dynamic)
            grid_tariff = GridTariff.objects.get(state=requirement.state, tariff_category=requirement.tariff_category)
            
            if grid_tariff is None:
                return Response({"error": "No grid cost data available for the state"}, status=status.HTTP_404_NOT_FOUND)

            # Fetch the last 10 values (adjust the ordering field if needed)
            last_10_values = Combination.objects.filter(requirement__industry=requirement.industry).order_by('-id')[:10].values_list('annual_demand_offset', flat=True)

            if last_10_values.count() < 10:
                re_replacement = 65
            else:
                moving_average = sum(last_10_values) / len(last_10_values)
                re_replacement = round(moving_average, 2)
            
            # Calculate annual savings
            annual_savings = (grid_tariff.cost - re - master_record.ISTS_charges - master_record.state_charges) * re_replacement * requirement.annual_electricity_consumption * 1000

            # Prepare response data
            response_data = {
                "annual_savings": round(annual_savings, 2),
                "average_savings": record.average_savings,
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
                "ISTS_charges": round(master_record.ISTS_charges, 2),
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
            print(e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
class WhatWeOfferAPI(APIView):
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
            record = RETariffMasterTable.objects.filter(industry = requirement.industry).first()

            last_10_values = Combination.objects.filter(requirement__industry=requirement.industry).order_by('-id')[:10].values_list('annual_demand_offset', flat=True)

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
            annual_savings = (re - master_record.ISTS_charges - master_record.state_charges) * re_replacement * requirement.annual_electricity_consumption * 1000

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
    def get(self, request, user_id):
        try:
            user = get_admin_user(user_id)
            user_id = user.id
            subscription = SubscriptionEnrolled.objects.filter(user=user_id).exists()
            return Response(subscription, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        
class ConsumerDashboardAPI(APIView):
    def get(self, request, user_id):
        user = get_admin_user(user_id)

        total_demands = ConsumerRequirements.objects.filter(user=user).aggregate(total_demands=Sum('contracted_demand'))['total_demands'] or 0
        consumption_units = ConsumerRequirements.objects.filter(user=user).count()
        unique_states_count = ConsumerRequirements.objects.filter(user=user).values('state').distinct().count()
        offers_sent = StandardTermsSheet.objects.filter(consumer=user, from_whom='Consumer').count()
        offers_received = StandardTermsSheet.objects.filter(consumer=user, from_whom='Generator')
        total_received = 0
        for offer in offers_received:
            total_received += offer.combination.optimal_solar_capacity + offer.combination.optimal_wind_capacity + offer.combination.optimal_wind_capacity

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
            'states_covered': states_covered,
            'states': states,
        }

        return Response(response, status=status.HTTP_200_OK)

class GeneratorDashboardAPI(APIView):
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
        data = {
            "amount": amount * 100,
            "currency": currency,
        }
        try:
            order_data = client.order.create(data=data)
            return order_data
        except Exception as e:
            print(str(e))
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
            
            subscription_response = requests.post(
                "http://192.168.1.34:8001/api/energy/subscriptions",
                json=subscription_data
            )

            if subscription_response.status_code == 201:
                return Response(
                    {"message": "Transaction and Subscription Created"},
                    status=status.HTTP_201_CREATED
                )
            else:
                # Debugging: Print response status and content
                print(f"Response Status Code: {subscription_response.status_code}")
                print(f"Response Content: {subscription_response.text}")
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
                    print(serializer.errors)
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
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]

    @staticmethod
    def extract_profile_data(file_path, sheet):
                
        # Read the specified sheet from the Excel file
        df = pd.read_excel(file_path, sheet_name=sheet)

        # Select only the relevant column (B) and start from the 4th row (index 3)
        df_cleaned = df.iloc[3:, 1].reset_index(drop=True)  # Column B corresponds to index 1

        # Fill NaN values with 0
        profile = df_cleaned.fillna(0).reset_index(drop=True)
                
        return profile
    

    @staticmethod
    def calculate_hourly_demand(consumption_name, state="Madhya Pradesh"):
        generator_demand = GeneratorHourlyDemand.objects.get(consumption=consumption_name)

        # Define the state-specific hours
        state_hours = {
            "Madhya Pradesh": {
                "peak_hours_1": (6, 9),  # 6 AM to 9 AM
                "peak_hours_2": (17, 22),  # 5 PM to 10 PM
                "off_peak_hours": (22, 6),  # 10 PM to 6 AM
            }
        }

        monthly_consumptions = GeneratorMonthlyConsumption.objects.filter(name=consumption_name)

        # Get state-specific hours
        hours = state_hours[state]
        peak_hours_1 = hours["peak_hours_1"]
        peak_hours_2 = hours["peak_hours_2"]
        off_peak_hours = hours["off_peak_hours"]
        total_hours = 24

        # Calculate total hours for all ranges
        peak_hours_total = (peak_hours_1[1] - peak_hours_1[0]) + (peak_hours_2[1] - peak_hours_2[0])
        off_peak_hours_total = off_peak_hours[1] - off_peak_hours[0]
        normal_hours = total_hours - peak_hours_total - off_peak_hours_total

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

            # Distribute values across the hours of each day
            for day in range(1, days_in_month + 1):
                for hour in range(24):
                    if peak_hours_1[0] <= hour < peak_hours_1[1] or peak_hours_2[0] <= hour < peak_hours_2[1]:
                        all_hourly_data.append(peak_hour_value)
                    elif off_peak_hours[0] <= hour < off_peak_hours[1]:
                        all_hourly_data.append(off_peak_hour_value)
                    else:
                        all_hourly_data.append(normal_hour_value)

        # Update the HourlyDemand model
        generator_demand.set_hourly_data_from_list(all_hourly_data)
        generator_demand.save()
        print('-----------all_hourly_data-----------')
        print(all_hourly_data)
        # Return the data in the desired flat format
        return pd.Series(all_hourly_data)

    @staticmethod
    def get_next_consumption_name(generator):
        # Count existing records grouped by name
        existing_names = (
            GeneratorMonthlyConsumption.objects.filter(generator=generator)
            .values('name')
            .annotate(month_count=Count('month'))
        )

        # Find the lowest available index
        name_counts = {entry['name']: entry['month_count'] for entry in existing_names}
        
        index = 1
        while f"consumption_{index}" in name_counts and name_counts[f"consumption_{index}"] == 12:
            index += 1

        return f"consumption_{index}"

    def post(self, request):
        data = request.data
        user_id = data.get("user_id")
        csv_file = data.get("csv_file")

        try:
            # Fetch the user
            generator = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "Generator not found."}, status=status.HTTP_404_NOT_FOUND)

        # Handle RE Replacement
        re_replacement = int(data.get("re_replacement")) if data.get("re_replacement") else None
        if re_replacement == 0:
            return Response({"message": "No available capacity."}, status=status.HTTP_200_OK)

        consumption_name = self.get_next_consumption_name(generator)
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

                # Process each row in the CSV file
                for row in csv_reader:
                    monthly_consumption = GeneratorMonthlyConsumption()
                    monthly_consumption.generator=generator
                    monthly_consumption.name = consumption_name
                    monthly_consumption.month=row['Month']
                    monthly_consumption.monthly_consumption=float(row['Monthly Consumption'])
                    monthly_consumption.peak_consumption=float(row['Peak Consumption'])
                    monthly_consumption.off_peak_consumption=float(row['Off Peak Consumption'])
                    monthly_consumption.monthly_bill_amount=float(row['Monthly Bill Amount'])
                    monthly_consumption.save()
            except Exception as e:
                print(e)
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        else:

            for entry in request.data["data"]:
                monthly_consumption = GeneratorMonthlyConsumption()
                monthly_consumption.generator = generator
                monthly_consumption.name = consumption_name
                monthly_consumption.month = entry["month"]
                monthly_consumption.monthly_consumption = entry["monthly_consumption"]
                monthly_consumption.peak_consumption = entry["peak_consumption"]
                monthly_consumption.off_peak_consumption = entry["off_peak_consumption"]
                monthly_consumption.monthly_bill_amount = entry["monthly_bill_amount"]
                monthly_consumption.save()

        try:
            # Initialize final aggregated response
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
                    if not wind.hourly_data:
                        continue
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
            print('===================input data===================')
            print(input_data)
            
            valid_combinations = []  

            print('nnnnnnn')
            print(consumption_name)
            GeneratorHourlyDemand.objects.get_or_create(consumption=consumption_name)
            hourly_demand = GeneratorHourlyDemand.objects.get(consumption=consumption_name)

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
                hourly_demand = self.calculate_hourly_demand(consumption_name)
            print('hourly demand=========')
            print(hourly_demand)
        
            # 8760 rows should be there if more then remove extra and if less then show error
            if len(hourly_demand) > 8760:
                hourly_demand = hourly_demand.iloc[:8760]
            elif len(hourly_demand) < 8760:
                padding_length = 8760 - len(hourly_demand)
                hourly_demand = pd.concat([hourly_demand, pd.Series([0] * padding_length)], ignore_index=True)

            response_data = optimization_model(input_data, hourly_demand=hourly_demand, re_replacement=re_replacement, valid_combinations=valid_combinations)
            
            if response_data == 'The demand cannot be met by the IPPs':
                return Response({"error": "The demand cannot be met by the IPPs."}, status=status.HTTP_200_OK)
            
            for combination_key, details in response_data.items():
            # Extract user and components from combination_key                
                OA_cost = (details["Final Cost"] - details['Per Unit Cost']) / 1000
                details['Per Unit Cost'] = details['Per Unit Cost'] / 1000
                details['Final Cost'] = details['Final Cost'] / 1000
                details["Annual Demand Met"] = (details["Annual Demand Met"] * 24) / 1000000
               # Update the aggregated response dictionary
                if combination_key not in aggregated_response:
                    aggregated_response[combination_key] = {
                        **details,
                        'OA_cost': OA_cost,
                    }
                else:
                    # Merge the details if combination already exists
                    aggregated_response[combination_key].update(details)                
            
            print('==============')
            print(aggregated_response)
            print('==============')

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

        # except Exception as e:
        #     return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)