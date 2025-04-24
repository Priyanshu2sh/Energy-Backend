import logging
from django.utils.timezone import now

class TimezoneFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ct = now()  # Uses Asia/Kolkata
        if datefmt:
            return ct.strftime(datefmt)
        return ct.isoformat()
