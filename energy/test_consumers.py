import json
from datetime import datetime, time
import re
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync, sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from django.utils.timezone import localtime

from .models import GeneratorOffer, Notifications, StandardTermsSheet, Tariffs

User = get_user_model()


class TestNegotiationWindowConsumer(AsyncWebsocketConsumer):
    ALLOWED_START_TIME = time(10, 0)
    ALLOWED_END_TIME = time(20, 0)

    async def connect(self):
        """Handles WebSocket connection.
        - Checks if the current time is within the allowed negotiation window.
        - Retrieves user_id and tariff_id from the query string.
        - Adds the channel to a WebSocket group.
        - Sends previous offers to the user.
        """
        current_time = datetime.now().time()
        
        self.user_id = self.get_query_param('user_id')
        self.tariff_id = self.get_query_param('tariff_id')

        if not self.user_id or not self.tariff_id:
            await self.close()
            return
        
        user = await self.get_user(self.user_id)

        self.room_name = f"negotiation_{self.tariff_id}"
        self.room_group_name = self.room_name

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        cache.set(f"user_channel_{self.user_id}", self.channel_name, timeout=None)

        await self.accept()
        if current_time <self.ALLOWED_START_TIME:
            message = {'message': 'This window is not opened yet.'}
            await self.send(text_data=json.dumps(message))
            await self.close()
            return
        
        if current_time >= self.ALLOWED_END_TIME:
            if user.user_category == 'Generator':
                message = {'message': 'This window is closed.'}
                await self.send(text_data=json.dumps(message))
                await self.close()
                return

        status = await self.check_window_status(self.tariff_id)
        if status == 'Rejected':
            if user.user_category == 'Generator':
                message = {'message': 'This window is rejected by the consumer.'}
                await self.send(text_data=json.dumps(message))
                await self.close()
                return
            elif user.user_category == 'Consumer':
                message = {'message': 'This window is rejected by you.'}
                await self.send(text_data=json.dumps(message))
                await self.close()
                return
        elif status == 'Accepted':
            if user.user_category == 'Generator':
                message = {'message': 'This window is closed.'}
                await self.send(text_data=json.dumps(message))
                await self.close()
                return
            elif user.user_category == 'Consumer':
                message = {'message': 'This window is already accepted by you.'}
                await self.send(text_data=json.dumps(message))
                await self.close()
                return

        await self.send_previous_offers(await self.get_previous_offers(self.tariff_id))

    async def disconnect(self, close_code):
        """Handles WebSocket disconnection."""
        cache.delete(f"user_channel_{self.user_id}")
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """Handles incoming messages."""
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'reject':
            await self.handle_rejection()
        elif action == 'select_generator':
            await self.handle_generator_selection(data.get('selected_generator_id'))
        elif data.get('updated_tariff') is not None:
            await self.handle_tariff_update(data['updated_tariff'])
        else:
            await self.send_status('waiting', 'Waiting for tariff update.')

    async def handle_rejection(self):
        """Handles the rejection action."""
        try:
            await self.update_window_status(self.tariff_id, status='Rejected')  # Mark offer as rejected
            await self.channel_layer.group_send(
                self.room_group_name,
                {'type': 'close_connection', 'message': 'Connection closed by consumer'}
            )
            await self.close()  # Close connection after rejection
        except Exception as e:
            await self.send_error(str(e))

    async def handle_generator_selection(self, selected_generator_id):
        """Handles the generator selection action."""
        try:
            tariff = await self.get_tariff(self.tariff_id)
            consumer_id = self.user_id
            await self.finalize_negotiation(tariff, selected_generator_id, consumer_id)
            await self.send_final_messages(tariff, selected_generator_id)
            await self.update_window_status(self.tariff_id, status='Accepted')
            await self.close()
        except Tariffs.DoesNotExist:
            await self.send_error('Tariff not found')
        except GeneratorOffer.DoesNotExist:
            await self.send_error('Selected Generator Offer not found.')
        except Exception as e:
            await self.send_error(str(e))

    async def handle_tariff_update(self, updated_tariff):
        """Handles tariff update logic."""
        if not self.is_within_allowed_time(datetime.now().time()):
            await self.send_error('Negotiation window is closed.')
            await self.update_window_status(self.tariff_id, status='Closed')
            await self.close()
            return
        
        try:
            tariff = await self.get_tariff(self.tariff_id)
            generator_offer, created = await self.get_or_create_generator_offer(self.user_id, tariff)
            generator_offer.updated_tariff = updated_tariff
            generator_offer.updated_at = timezone.now()
            await self.save_generator_offer(generator_offer)

            message = await self.build_offer_update_message(generator_offer)
            await self.channel_layer.group_send(self.room_group_name, message)

        except Tariffs.DoesNotExist:
            await self.send_error('Tariff not found')
        except Exception as e:
            await self.send_error(str(e))

    async def send_previous_offers(self, offers):
        """Sends previous offers to the client."""
        message = {'type': 'previous_offers', 'offers': offers}
        await self.send(text_data=json.dumps(message))

    async def send_final_messages(self, tariff, selected_generator_id):
        """Sends final messages to all users after a generator is selected."""
        accepted_by_id = await self.get_accepted_by_id(tariff, selected_generator_id)
        selected_offer_updated_tariff = await self.get_updated_tariff(tariff, selected_generator_id)
        consumer = await self.get_user(accepted_by_id)

        generator_offers = await self.get_generator_offers(tariff)

        for offer in generator_offers:
            generator = await self.get_generator(offer)
            generator_channel_name = cache.get(f"user_channel_{generator.id}")

            if generator_channel_name:
                message = self.build_generator_message(
                    tariff_id=self.tariff_id,
                    updated_tariff=offer.updated_tariff,
                    consumer_username=consumer.username,
                    consumer_id=consumer.id,
                    is_selected=(generator.id == selected_generator_id)
                )
                await self.channel_layer.send(generator_channel_name, message)
            else:
                print(f"No channel name found for generator {generator.id}")

        await self.close_negotiation_group()

        consumer_message = {
            'tariff_id': self.tariff_id,
            'selected_generator_id': selected_generator_id,
            'selected_generator_username': (await self.get_user(selected_generator_id)).username,
            'updated_tariff': selected_offer_updated_tariff,
            'consumer_username': consumer.username,
            'consumer_id': consumer.id,
        }
        await self.send(text_data=json.dumps(consumer_message))
        await self.close()

    def build_generator_message(self, tariff_id, updated_tariff, consumer_username, consumer_id, is_selected):
        """Builds a message for the generator."""
        message = {
            'type': 'negotiation_finalized',
            'message': {
                'tariff_id': tariff_id,
                'updated_tariff': updated_tariff,
                'consumer_username': consumer_username,
                'consumer_id': consumer_id,
                'is_selected': is_selected,
                'message': "Your offer has been accepted!" if is_selected else "Another generator's offer has been accepted. Thank you for participating."
            }
        }
        return message

    async def close_negotiation_group(self):
        """Closes the negotiation group and disconnects all members."""
        group_name = f"negotiation_{self.tariff_id}"
        await self.channel_layer.group_send(
            group_name,
            {'type': 'close_connection', 'message': 'The negotiation group is being closed.'}
        )
        await self.channel_layer.group_discard(group_name, self.channel_name)

    async def close_connection(self, event):
        """Closes the WebSocket connection."""
        await self.close()

    async def offer_update(self, event):
        """Sends the updated offer details to all connected clients in the group."""
        await self.send(text_data=json.dumps(event['message']))

    async def negotiation_finalized(self, event):
        """Sends negotiation finalized message."""
        await self.send(text_data=json.dumps(event['message']))

    async def build_offer_update_message(self, generator_offer):
        """Builds the offer update message."""
        generator_username = await self.get_generator_username(generator_offer.generator_id)
        return {
            'type': 'offer_update',
            'message': {
                str(generator_offer.generator_id): {
                    'generator_id': generator_offer.generator_id,
                    'generator_username': generator_username,
                    'tariff_id': generator_offer.tariff_id,
                    'updated_tariff': generator_offer.updated_tariff,
                    'timestamp': localtime(generator_offer.updated_at).strftime('%Y-%m-%d %H:%M:%S'),
                }
            }
        }

    def is_within_allowed_time(self, current_time):
        """Checks if the current time is within the allowed window."""
        return self.ALLOWED_START_TIME <= current_time <= self.ALLOWED_END_TIME

    def get_query_param(self, param):
        """Gets a query parameter from the URL."""
        query_params = parse_qs(self.scope['query_string'].decode())
        return query_params.get(param, [None])[0]
    
    @database_sync_to_async
    def check_window_status(self, tariff_id):
        try:
            tariff = Tariffs.objects.get(id=tariff_id)
            return tariff.window_status
        except Tariffs.DoesNotExist:
            raise Tariffs.DoesNotExist("Tariff not found.")

    async def send_error(self, message):
        """Sends an error message to the client."""
        await self.send_status('error', message)

    async def send_status(self, status, message):
        """Sends a status message to the client."""
        await self.send(text_data=json.dumps({'status': status, 'message': message}))

    @database_sync_to_async
    def get_previous_offers(self, tariff_id):
        """Retrieves all previous offers for the given tariff."""
        offers = GeneratorOffer.objects.filter(tariff_id=tariff_id).values(
            'generator__id',
            'generator__username',
            'updated_tariff',
            'updated_at',
            'generator_id'
        )

        formatted_offers = {}
        for offer in offers:
            formatted_offers[str(offer['generator_id'])] = {
                'generator_id': offer['generator__id'],
                'generator_username': offer['generator__username'],
                'updated_tariff': offer['updated_tariff'],
                'timestamp': localtime(offer['updated_at']).strftime('%Y-%m-%d %H:%M:%S'),
            }

        return formatted_offers

    @database_sync_to_async
    def get_tariff(self, tariff_id):
        """Gets a tariff by ID."""
        return Tariffs.objects.get(id=tariff_id)
    
    @database_sync_to_async
    def update_window_status(self, tariff_id, status):
        """update window status."""
        try:
            tariff = Tariffs.objects.get(id=tariff_id)
            tariff.window_status = status  # negotiation window status to Rejected
            tariff.save()
        except Tariffs.DoesNotExist:
            raise Tariffs.DoesNotExist(
                "Tariff not found."
            )

    @database_sync_to_async
    def get_or_create_generator_offer(self, user_id, tariff):
        """Gets or creates a GeneratorOffer."""
        return GeneratorOffer.objects.get_or_create(generator_id=user_id, tariff=tariff)

    @database_sync_to_async
    def save_generator_offer(self, generator_offer):
        """Saves a GeneratorOffer."""
        generator_offer.save()

    @database_sync_to_async
    def get_generator(self, offer):
        """Gets the generator from an offer."""
        return offer.generator

    @database_sync_to_async
    def get_generator_username(self, generator_id):
        """Gets the username of a generator."""
        try:
            user = User.objects.get(id=generator_id)
            return user.username
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_accepted_by_id(self, tariff, generator_id):
        """Gets the ID of the user who accepted the offer."""
        try:
            selected = GeneratorOffer.objects.get(tariff=tariff, generator_id=generator_id)
            return selected.accepted_by.id
        except GeneratorOffer.DoesNotExist:
            return None

    @database_sync_to_async
    def get_updated_tariff(self, tariff, generator_id):
        """Gets the updated tariff for a generator."""
        try:
            selected = GeneratorOffer.objects.get(tariff=tariff, generator_id=generator_id)
            return selected.updated_tariff
        except GeneratorOffer.DoesNotExist:
            return None

    @database_sync_to_async
    def get_generator_offers(self, tariff):
        """Gets all generator offers for a tariff."""
        return list(GeneratorOffer.objects.filter(tariff=tariff).order_by('-updated_at'))

    @database_sync_to_async
    def get_user(self, user_id):
        """Gets a user by ID."""
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def finalize_negotiation(self, tariff, selected_generator_id, consumer_id):
        """Finalizes the negotiation process."""
        try:
            consumer = User.objects.get(id=consumer_id)
            selected_offer = GeneratorOffer.objects.get(tariff=tariff, generator__id=selected_generator_id)
            selected_offer.is_accepted = True
            selected_offer.accepted_by = consumer
            selected_offer.save()

            GeneratorOffer.objects.filter(tariff=tariff).exclude(id=selected_offer.id).update(is_accepted=False)
        except GeneratorOffer.DoesNotExist:
            raise


# notifications live counting showing
# class NotificationConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.user_id = self.scope["url_route"]["kwargs"]["user_id"]
#         self.group_name = f"user_{self.user_id}"

#         # Join the user's notification group
#         await self.channel_layer.group_add(self.group_name, self.channel_name)
#         await self.accept()

#         # Send current unread notification count on connection
#         unread_count = await self.get_unread_count()
#         await self.send(json.dumps({"unread_count": unread_count}))

#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(self.group_name, self.channel_name)

#     async def send_notification(self, event):
#         """Send new notification update"""
#         await self.send(text_data=json.dumps({"unread_count": event["unread_count"]}))

#     async def mark_notifications_read(self, event):
#         """Clear unread count when user views notifications"""
#         await self.send(text_data=json.dumps({"unread_count": 0}))

#     @sync_to_async
#     def get_unread_count(self):
#         return Notifications.objects.filter(user_id=self.user_id, is_read=False).count()

class TermsSheetConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope["url_route"]["kwargs"]["user_id"]
        self.group_name = f"user_{self.user_id}"

        # Join the user's terms sheet group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send current unread terms sheets count on connection
        unread_count = await self.get_unread_count()
        await self.send(json.dumps({"unread_count": unread_count}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_terms_sheet(self, event):
        """Send new terms sheet update"""
        await self.send(text_data=json.dumps({"unread_count": event["unread_count"]}))

    async def mark_terms_sheet_read(self, event):
        """Handle mark_terms_sheet_read event sent via group_send"""
        await self.send(text_data=json.dumps({"unread_count": 0}))

    @sync_to_async
    def get_unread_count(self):
        user = User.objects.get(id=self.user_id)
        if user.user_category == 'Consumer':
            return StandardTermsSheet.objects.filter(consumer=user.id, consumer_is_read=False).count()
        else:
            return StandardTermsSheet.objects.filter(combination__generator=user.id, generator_is_read=False).count()

    @sync_to_async
    def mark_all_as_read(self):
        user = User.objects.get(id=self.user_id)
        if user.user_category == 'Consumer':
            StandardTermsSheet.objects.filter(consumer=user.id, consumer_is_read=False).update(consumer_is_read=True)
        else:
            StandardTermsSheet.objects.filter(combination__generator=user.id, generator_is_read=False).update(generator_is_read=True)

    async def receive(self, text_data):
        """Handle client requests (e.g., marking all as read)"""
        data = json.loads(text_data)
        if data.get("action") == "mark_as_read":
            await self.mark_all_as_read()
            await self.channel_layer.group_send(
                self.group_name, {"type": "mark_terms_sheet_read"}
            )

class TestNotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.user = await self.get_user()

        if self.user:
            await self.accept()

            # Create a unique group name based on the user ID
            self.group_name = f"notifications_{self.user_id}"

            # Add the user to the group
            await self.channel_layer.group_add(self.group_name, self.channel_name)

            # Send initial unread count
            await self.send_unread_notifications_count()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if self.user:
            # Remove the user from the group
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        if data.get("action") == "mark_as_read":
            await self.mark_notifications_as_read()
            await self.send_unread_notifications_count()

    @database_sync_to_async
    def get_user(self):
        try:
            return User.objects.get(id=self.user_id)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_unread_notifications_count(self):
        return Notifications.objects.filter(user=self.user, is_read=False).count()

    @database_sync_to_async
    def mark_notifications_as_read(self):
        Notifications.objects.filter(user=self.user, is_read=False).update(is_read=True)

    async def send_unread_notifications_count(self):
        count = await self.get_unread_notifications_count()
        await self.send(text_data=json.dumps({
            "unread_count": count
        }))

    async def send_unread_count(self, event):
        """Send updated unread count to the frontend."""
        await self.send(text_data=json.dumps({
            "unread_count": event["unread_count"]
        }))

    async def mark_notifications_read(self, event):
        """Handle mark_notifications_read event and send updated unread count."""
        await self.send(text_data=json.dumps({
            "unread_count": event["unread_count"]
        }))