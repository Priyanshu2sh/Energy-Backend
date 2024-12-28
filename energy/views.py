from django.shortcuts import get_object_or_404
from accounts.models import User
from accounts.views import JWTAuthentication
from .models import GenerationPortfolio, ConsumerRequirements, MonthlyConsumptionData
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import status
from .serializers import GenerationPortfolioSerializer, ConsumerRequirementsSerializer, MonthlyConsumptionDataSerializer
from django.core.mail import send_mail
import random
from django.contrib.auth.hashers import check_password
from django.utils.timezone import now
from datetime import datetime, timedelta
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum


# Create your views here.
class GenerationPortfolioAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
   

    def get(self, request):
        # Fetch all energy profiles
        profiles = GenerationPortfolio.objects.all()
        serializer = GenerationPortfolioSerializer(profiles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Add a new energy profile
        serializer = GenerationPortfolioSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        # Update an existing energy profile (Full update)
        profile = get_object_or_404(GenerationPortfolio, pk=pk)
        serializer = GenerationPortfolioSerializer(profile, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ConsumerRequirementsAPI(APIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
   

    def get(self, request):
        # Fetch all energy profiles
        profiles = ConsumerRequirements.objects.all()
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
   

    def get(self, request):
        # Fetch all energy profiles
        profiles = MonthlyConsumptionData.objects.all()
        serializer = MonthlyConsumptionDataSerializer(profiles, many=True)
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
        state = data.get("state")
        procurement_date = data.get("procurement_date")

        if not state or not procurement_date:
            return Response(
                {"error": "Please provide 'state' and 'procurement_date' parameters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Filter the data
            filtered_data = GenerationPortfolio.objects.filter(
                Q(state=state) & Q(cod__gte=procurement_date)
            ).values("user__username", "state", "capacity")

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
        email = data.get("email")
        user = User.objects.get(email=email)

        try:
            # Get all GenerationPortfolio records for the user
            generation_portfolio = GenerationPortfolio.objects.filter(user=user)

            # Ensure generation portfolio exists
            if not generation_portfolio.exists():
                return Response(
                    {"error": "No generation portfolio records found for the user."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Fetch all states and CODs for the user's generation portfolio
            states = generation_portfolio.values_list("state", flat=True).distinct()
            cod_dates = generation_portfolio.values_list("cod", flat=True)

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
