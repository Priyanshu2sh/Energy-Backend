import json
from datetime import datetime, time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import GeneratorOffer, Tariffs
from urllib.parse import parse_qs

class NegotiationWindowConsumer(AsyncWebsocketConsumer):
    ALLOWED_START_TIME = time(13, 0)  # 10:00 AM
    ALLOWED_END_TIME = time(14, 0)   # 11:00 AM

    async def connect(self):
        # Check if current time is within the allowed window
        current_time = datetime.now().time()
        if not self.is_within_allowed_time(current_time):
            await self.close()
            return
        
        query_params = parse_qs(self.scope['query_string'].decode())
        self.user_id = query_params.get('user_id', [None])[0]
        self.tariff_id = query_params.get('tariff_id', [None])[0]

        if not self.user_id or not self.tariff_id:
            # Close the WebSocket connection if parameters are missing
            await self.close()
            return

        self.room_name = f"negotiation_{self.tariff_id}"  # Room specific to tariff_id
        self.room_group_name = self.room_name

        # Join the WebSocket group based on tariff_id
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Leave the WebSocket group when the user disconnects
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        # Check if the negotiation window is still open
        current_time = datetime.now().time()
        if not self.is_within_allowed_time(current_time):
            await self.send(text_data=json.dumps({
                'status': 'error',
                'message': 'Negotiation window is closed.'
            }))
            await self.close()
            return
        
        # Parse the incoming message
        text_data_json = json.loads(text_data)

        # Extract the data from the incoming request
        # user_id = text_data_json.get('user_id')
        updated_tariff = text_data_json.get('updated_tariff')

        # Process the update only when 'updated_tariff' is provided (triggered by button click)
        if updated_tariff is not None:
            try:
                # Fetch the Tariff and Generator Offer records asynchronously
                tariff = await self.get_tariff(self.tariff_id)
                generator_offer, created = await self.get_or_create_generator_offer(self.user_id, tariff)

                # Update the Generator Offer with the new tariff value
                generator_offer.updated_tariff = updated_tariff
                await self.save_generator_offer(generator_offer)

                # Send confirmation message to the client (all connected clients for this tariff)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'offer_update',
                        'message': {
                            'status': 'success',
                            'generator_id': self.user_id,
                            'tariff_id': self.tariff_id,
                            'updated_tariff': updated_tariff,
                            'timestamp': generator_offer.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                        }
                    }
                )
            except Tariffs.DoesNotExist:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': 'Tariff not found'
                }))
            except Exception as e:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': str(e)
                }))
        else:
            # If no tariff update, send a simple response or ignore
            await self.send(text_data=json.dumps({
                'status': 'waiting',
                'message': 'Waiting for tariff update.'
            }))

    async def offer_update(self, event):
        # Send the updated offer details to all connected clients in the group (for the same tariff)
        await self.send(text_data=json.dumps(event['message']))

    # Helper method to check if the current time is within the allowed window
    def is_within_allowed_time(self, current_time):
        return self.ALLOWED_START_TIME <= current_time <= self.ALLOWED_END_TIME

    # Database interaction methods
    @database_sync_to_async
    def get_tariff(self, tariff_id):
        return Tariffs.objects.get(id=tariff_id)

    @database_sync_to_async
    def get_or_create_generator_offer(self, user_id, tariff):
        # Fetch the GeneratorOffer object or create it
        return GeneratorOffer.objects.get_or_create(
            generator_id=user_id,
            tariff=tariff
        )

    @database_sync_to_async
    def save_generator_offer(self, generator_offer):
        generator_offer.save()
