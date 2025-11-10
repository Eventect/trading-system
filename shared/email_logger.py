# shared/email_logger.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
import os
from typing import List


class EmailLogger:
    """
    Send daily log summaries via email
    """

    def __init__(self):
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('SENDER_PASSWORD')
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')

        self.logger = logging.getLogger("EmailLogger")
        self.log_buffer = []

    def add_log(self, message: str):
        """Add log message to buffer"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_buffer.append(f"[{timestamp}] {message}")

    def send_daily_summary(self, subject: str = None):
        """Send daily log summary via email"""
        if not all([self.sender_email, self.sender_password, self.recipient_email]):
            self.logger.warning("Email credentials not configured, skipping email")
            return

        if not self.log_buffer:
            self.logger.info("No logs to send")
            return

        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email

            if subject is None:
                subject = f"Trading System Daily Report - {datetime.now().strftime('%Y-%m-%d')}"
            msg['Subject'] = subject

            # Create body
            body = "\n".join(self.log_buffer)
            msg.attach(MIMEText(body, 'plain'))

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            self.logger.info(f"Daily summary sent to {self.recipient_email}")

            # Clear buffer
            self.log_buffer = []

        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")