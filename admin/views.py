from itertools import chain
from django.conf import settings
from django.shortcuts import get_object_or_404, render
from admin.serializers import ConsumerRequirementsUpdateSerializer, ConsumerSerializer, GeneratorSerializer, GridTariffSerializer, HelpDeskQuerySerializer, MasterTableSerializer, NationalHolidaySerializer, PeakHoursSerializer, RETariffMasterTableSerializer, SubscriptionTypeSerializer
from energy.models import *
from accounts.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q
from django.core.mail import send_mail

import logging

from energy.serializers import ESSPortfolioSerializer, SolarPortfolioSerializer, WindPortfolioSerializer
traceback_logger = logging.getLogger('django')
logger = logging.getLogger('debug_logger') 
# Create your views here.

class Dashboard(APIView):

    def get(self, request):

        demand = ConsumerRequirements.objects.all()
        total_demand = demand.aggregate(total_contracted_demand=Sum('contracted_demand'))
        HT_Commercial = demand.filter(tariff_category='HT Commercial').aggregate(total_contracted_demand=Sum('contracted_demand'))
        HT_Industrial = demand.filter(tariff_category='HT Industrial').aggregate(total_contracted_demand=Sum('contracted_demand'))
        LT_Commercial = demand.filter(tariff_category='LT Commercial').aggregate(total_contracted_demand=Sum('contracted_demand'))
        LT_Industrial = demand.filter(tariff_category='LT Industrial').aggregate(total_contracted_demand=Sum('contracted_demand'))

        solar_projects = SolarPortfolio.objects.all().count()
        wind_projects = WindPortfolio.objects.all().count()
        ess_projects = ESSPortfolio.objects.all().count()
        total_projects = solar_projects + wind_projects + ess_projects

        offers = StandardTermsSheet.objects.all()
        total_offers = offers.count()
        offers_rejected = offers.filter(Q(consumer_status='Rejected') | Q(generator_status='Rejected')).count()
        offers_accepted = offers.filter(Q(consumer_status='Accepted') | Q(generator_status='Accepted')).count()
        offers_pending = offers.filter(~Q(consumer_status__in=['Accepted', 'Rejected', 'Withdrawn']) | ~Q(generator_status__in=['Accepted', 'Rejected', 'Withdrawn'])).count()

        total_consumers = User.objects.filter(user_category='Consumer').count()
        total_generators = User.objects.filter(user_category='Generator').count()

        response_data = {
            "total_demand": total_demand['total_contracted_demand'] or 0,
            "HT_Commercial": HT_Commercial['total_contracted_demand'] or 0,
            "HT_Industrial": HT_Industrial['total_contracted_demand'] or 0,
            "LT_Commercial": LT_Commercial['total_contracted_demand'] or 0,
            "LT_Industrial": LT_Industrial['total_contracted_demand'] or 0,
            "total_projects": total_projects,
            "solar_projects": solar_projects,
            "wind_projects": wind_projects,
            "ess_projects": ess_projects,
            "total_offers": total_offers,
            "offers_rejected": offers_rejected,
            "offers_accepted": offers_accepted,
            "offers_pending": offers_pending,
            "total_consumers": total_consumers,
            "total_generators": total_generators,
        }

        return Response(response_data, status=200)
    

class Consumer(APIView):

    def get(self, request):
        # filter only users with user_category = 'Consumer'
        consumers = User.objects.filter(user_category='Consumer', is_active=True)
        serializer = ConsumerSerializer(consumers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        consumer = User.objects.filter(pk=pk).first()
        if not consumer:
            return Response({"error": "Consumer not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ConsumerSerializer(consumer, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        consumer = User.objects.filter(pk=pk).first()
        if not consumer:
            return Response({"error": "Consumer not found."}, status=status.HTTP_404_NOT_FOUND)

        consumer.is_active = False
        consumer.deleted = True
        consumer.save()
        return Response({"detail": "Consumer deleted."}, status=status.HTTP_200_OK)


class Generator(APIView):

    def get(self, request):
        # filter only users with user_category = 'Consumer'
        generators = User.objects.filter(user_category='Generator', is_active=True)
        serializer = GeneratorSerializer(generators, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        generator = User.objects.filter(pk=pk).first()
        if not generator:
            return Response({"error": "Generator not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = GeneratorSerializer(generator, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        generator = User.objects.filter(pk=pk).first()
        if not generator:
            return Response({"error": "Generator not found."}, status=status.HTTP_404_NOT_FOUND)

        generator.is_active = False
        generator.deleted = True
        generator.save()
        return Response({"detail": "Generator deleted."}, status=status.HTTP_200_OK)


class OnlineSubscriptions(APIView):
    def get(self, request):
        # Get all online payments
        online_payments = PaymentTransaction.objects.all()

        # Get all related users and subscriptions from the invoices
        invoice_users = online_payments.values_list('invoice__user', flat=True)
        invoice_subscriptions = online_payments.values_list('invoice__subscription', flat=True)

        # Filter enrolled subscriptions
        enrolled = SubscriptionEnrolled.objects.filter(
            user_id__in=invoice_users,
            subscription_id__in=invoice_subscriptions
        ).select_related('user', 'subscription')  # company only if separate model

        data = []
        for e in enrolled:
            data.append({
                "user_category": e.user.user_category,
                "user_name": e.user.company_representative,
                "company_name": e.user.company,
                "subscription_type": e.subscription.subscription_type,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "status": "Active" if e.status == "active" else "Inactive"
            })

        return Response(data)


class OfflineSubscriptions(APIView):
    def get(self, request):
        offline_payments = OfflinePayment.objects.select_related('invoice', 'invoice__user', 'invoice__subscription')
        data = []

        for payment in offline_payments:
            user = payment.invoice.user
            subscription_type = payment.invoice.subscription

            # Get the matching enrolled subscription (if any)
            enrolled = SubscriptionEnrolled.objects.filter(
                user=user,
                subscription=subscription_type
            ).select_related('user', 'subscription').first()

            if enrolled:
                data.append({
                    "id": payment.id,
                    "user_category": user.user_category,
                    "user_name": user.company_representative,
                    "company_name": user.company,
                    "subscription_type": subscription_type.subscription_type,
                    "start_date": enrolled.start_date,
                    "end_date": enrolled.end_date,
                    "transaction_id": payment.transaction_id,
                    "payment_date": payment.payment_date,
                    "payment_mode": payment.payment_mode,
                    "payment_status": payment.status,
                    "status": "Active" if enrolled.status == "active" else "Inactive"
                })

        return Response(data)
    
    def put(self, request, pk):
        payment = get_object_or_404(OfflinePayment, pk=pk)
        new_status = request.data.get("status")

        if new_status not in ["Pending", "Approved", "Rejected"]:
            return Response(
                {"error": "Invalid status value."},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment.status = new_status
        payment.save()

        if payment.status == 'Approved':
            subscription_enrolled = SubscriptionEnrolled(user=payment.invoice.user, subscription=payment.invoice.subscription, start_date=date.today(), end_date=date.today() + timedelta(payment.invoice.subscription.duration_in_days))
            subscription_enrolled.save()
            return Response(
                {"message": "Payment status updated and subscription activated successfully.", "new_status": payment.status},
                status=status.HTTP_200_OK
            )
        
        return Response(
            {"message": "Payment status updated successfully.", "new_status": payment.status},
            status=status.HTTP_200_OK
        )


class SubscriptionPlans(APIView):

    def get(self, request):
        subscription_plans = SubscriptionType.objects.all()
        serializer = SubscriptionTypeSerializer(subscription_plans, many=True)
        return Response(serializer.data)

    def put(self, request, pk):
        subscription_plan = get_object_or_404(SubscriptionType, pk=pk)
        serializer = SubscriptionTypeSerializer(subscription_plan, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        subscription_plan = get_object_or_404(SubscriptionType, pk=pk)
        subscription_plan.delete()
        return Response({"message": "Subscription plan deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
    
class DemandData(APIView):

    def get(self, request):

        requirements = ConsumerRequirements.objects.all()

        demand_data = []
        for requirement in requirements:

            monthly_consumption_data = []
            monthly_consumption = MonthlyConsumptionData.objects.filter(requirement=requirement)
            for data in monthly_consumption:
                monthly_consumption_data.append({
                    "id": data.id,
                    "month": data.month,
                    "monthly_consumption": data.monthly_consumption,
                    "peak_consumption": data.peak_consumption,
                    "off_peak_consumption": data.off_peak_consumption,
                    "monthly_bill_amount": data.monthly_bill_amount
                })

            demand_data.append({
                "id": requirement.id,
                "username": requirement.user.username,
                "state": requirement.state,
                "industry": requirement.industry,
                "sub_industry": requirement.sub_industry,
                "contracted_demand": requirement.contracted_demand,
                "tariff_category": requirement.tariff_category,
                "voltage_level": requirement.voltage_level,
                "procurement_date": requirement.procurement_date,
                "consumption_unit": requirement.consumption_unit,
                "annual_electricity_consumption": requirement.annual_electricity_consumption,
                "roof_area": requirement.roof_area,
                "solar_rooftop_capacity": requirement.solar_rooftop_capacity,
                "location": requirement.location,
                "latitude": requirement.latitude,
                "monthly_consumption_data": monthly_consumption_data
            })

        return Response(demand_data, status=status.HTTP_200_OK)
    
    def put(self, request, pk):

        requirement = ConsumerRequirements.objects.filter(pk=pk).first()
        if not requirement:
            return Response({"error": "Requirement not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ConsumerRequirementsUpdateSerializer(requirement, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()

            # Update monthly consumption data
            monthly_data_list = request.data.get('monthly_consumption_data', [])
            for item in monthly_data_list:
                monthly_id = item.get('id')
                if not monthly_id:
                    continue

                monthly_instance = MonthlyConsumptionData.objects.filter(id=monthly_id, requirement=requirement).first()
                if monthly_instance:
                    monthly_instance.monthly_consumption = item.get('monthly_consumption', monthly_instance.monthly_consumption)
                    monthly_instance.peak_consumption = item.get('peak_consumption', monthly_instance.peak_consumption)
                    monthly_instance.off_peak_consumption = item.get('off_peak_consumption', monthly_instance.off_peak_consumption)
                    monthly_instance.monthly_bill_amount = item.get('monthly_bill_amount', monthly_instance.monthly_bill_amount)
                    monthly_instance.save()
                
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GenerationData(APIView):

    def get(self, request):
        try:
            solar_data = SolarPortfolio.objects.all()
            wind_data = WindPortfolio.objects.all()
            ess_data = ESSPortfolio.objects.all()

            # Combine the queryset data
            combined_data = list(chain(solar_data, wind_data, ess_data))

            # Serialize the combined data
            response_data = {
                "Solar": SolarPortfolioSerializer(solar_data, many=True).data,
                "Wind": WindPortfolioSerializer(wind_data, many=True).data,
                "ESS": ESSPortfolioSerializer(ess_data, many=True).data
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class HelpDeskQueryAPI(APIView):

    def get(self, request):
        queries = HelpDeskQuery.objects.all().order_by('-date')
        response_data = []
        for query in queries:
            response_data.append({
                'user': query.user.id, 
                'user_category': query.user.user_category,
                'company': query.user.company,
                'company_representative': query.user.company_representative,
                'query': query.query,
                'date': query.date,
                'status': query.status,
            })

        return Response(response_data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        query = get_object_or_404(HelpDeskQuery, pk=pk)
        serializer = HelpDeskQuerySerializer(query, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class SendNotificationAPI(APIView):
    
    def post(self, request):
        user_id = request.data.get('user_id')
        message = request.data.get('message')
        send_type = request.data.get('send_type')  # 'notification' or 'email'
        user_category = request.data.get('user_category')  # Only required if user_id is 'all'
        title = request.data.get('title')  # Only required if send_type is 'email'

        if not user_id or not message or not send_type:
            return Response({"error": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        # Determine target users
        if user_id == 'all':
            if not user_category:
                return Response({"error": "User category is required when user_id is 'all'."}, status=status.HTTP_400_BAD_REQUEST)
            users = User.objects.filter(user_category=user_category)
        else:
            try:
                user = User.objects.get(id=user_id)
                users = [user]
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Send notifications or emails
        for user in users:
            if send_type == 'notification':
                Notifications.objects.create(user=user, message=message)
            elif send_type == 'email':
                if not title:
                    return Response({"error": "Title is required for sending emails."}, status=status.HTTP_400_BAD_REQUEST)
                send_mail(
                    subject=title,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False
                )
            else:
                return Response({"error": "Invalid send_type. Use 'notification' or 'email'."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"success": True, "sent_to": len(users)}, status=status.HTTP_200_OK)

class MasterTableAPI(APIView):
    def get(self, request):
        records = MasterTable.objects.all()
        serializer = MasterTableSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = MasterTableSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(MasterTable, pk=pk)
        serializer = MasterTableSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(MasterTable, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class RETariffAPI(APIView):
    def get(self, request):
        records = RETariffMasterTable.objects.all()
        serializer = RETariffMasterTableSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = RETariffMasterTableSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(RETariffMasterTable, pk=pk)
        serializer = RETariffMasterTableSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(RETariffMasterTable, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class GridTariffAPI(APIView):
    def get(self, request):
        records = GridTariff.objects.all()
        serializer = GridTariffSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = GridTariffSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(GridTariff, pk=pk)
        serializer = GridTariffSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(GridTariff, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class PeakHoursAPI(APIView):
    def get(self, request):
        records = PeakHours.objects.all()
        response_data = []
        for i in records:
            response_data.append({
                "state": i.state.id,
                "name": i.state.name,
                "peak_start_1": i.peak_start_1,
                "peak_end_1": i.peak_end_1,
                "peak_start_2": i.peak_start_2,
                "peak_end_1": i.peak_end_2,
                "off_peak_start": i.off_peak_start,
                "off_peak_end": i.off_peak_end,
            })
        return Response(response_data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PeakHoursSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(PeakHours, pk=pk)
        serializer = PeakHoursSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(PeakHours, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)


class NationalHolidayAPI(APIView):
    def get(self, request):
        holidays = NationalHoliday.objects.all()
        serializer = NationalHolidaySerializer(holidays, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = NationalHolidaySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        obj = get_object_or_404(NationalHoliday, pk=pk)
        serializer = NationalHolidaySerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        obj = get_object_or_404(NationalHoliday, pk=pk)
        obj.delete()
        return Response({'message': "Record deleted successfully."}, status=status.HTTP_200_OK)