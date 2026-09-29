"""IMAP SSL + SMTP SSL. Never fetch arbitrary model-supplied URLs."""
import email
import hashlib
import imaplib
import re
import smtplib
import ssl
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses, formatdate
from .agents.validation import address


class Mailbox:
    def __init__(self, config):
        self.c = config

    def scan(self):
        """All sent headers for dedup; bounded inbox. Fail closed on overflow."""
        result = []
        with imaplib.IMAP4_SSL(self.c.imap_host, timeout=30) as imap:
            imap.login(self.c.mail_user, self.c.mail_password)
            for folder, direction in ((self.c.sent_folder, 'sent'), (self.c.inbox_folder, 'received')):
                status, _ = imap.select('"' + folder.replace('"', '') + '"', readonly=True)
                if status != 'OK':
                    raise RuntimeError('IMAP folder unavailable; check configured folder names')
                status, data = imap.uid('search', None, 'ALL')
                if status != 'OK':
                    raise RuntimeError('IMAP search failed')
                ids = data[0].split()
                if len(ids) > self.c.mail_limit:
                    raise RuntimeError('Mailbox exceeds MAIL_SCAN_LIMIT; increase limit or use a dedicated sales mailbox. Sync incomplete, sending blocked.')
                for message_uid in ids:
                    status, parts = imap.uid('fetch', message_uid, '(BODY.PEEK[])')
                    raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                    if status != 'OK' or raw is None:
                        raise RuntimeError('IMAP message fetch failed; sync incomplete')
                    if len(raw) > 5_000_000:
                        raise RuntimeError('Email exceeds 5 MB scan limit; sync incomplete')
                    msg = email.message_from_bytes(raw, policy=policy.default)
                    body = msg.get_body(preferencelist=('plain',)) if msg.is_multipart() else msg
                    text = body.get_content() if body and body.get_content_type() == 'text/plain' else ''
                    # Preserve delivery-status parts for failed recipient evidence.
                    dsn = []
                    for part in msg.walk():
                        if part.get_content_type() == 'message/delivery-status':
                            dsn.extend(str(x) for x in part.get_payload())
                    result.append({'id': str(msg.get('Message-ID') or hashlib.sha256(raw).hexdigest()),
                                   'direction': direction, 'from': getaddresses([str(msg.get('From', ''))])[0][1].lower(),
                                   'to': [x[1].lower() for x in getaddresses([str(msg.get('To', '')), str(msg.get('Cc', ''))])],
                                   'subject': str(msg.get('Subject', '')), 'body': str(text)[:16000],
                                   'references': str(msg.get('References', '')) + ' ' + str(msg.get('In-Reply-To', '')),
                                   'date': str(msg.get('Date', '')), 'dsn': '\n'.join(dsn)})
        return result

    def send(self, draft, message_id):
        if not address(draft['to']) or not address(self.c.sender):
            raise ValueError('Invalid sender/recipient')
        if any(c in draft['subject'] for c in '\r\n'):
            raise ValueError('Header newline rejected')
        msg = EmailMessage()
        msg['From'], msg['To'], msg['Subject'] = self.c.sender, draft['to'], draft['subject']
        msg['Date'], msg['Message-ID'] = formatdate(localtime=False), message_id
        msg.set_content(draft['body'])
        with smtplib.SMTP_SSL(self.c.smtp_host, 465, timeout=30, context=ssl.create_default_context()) as smtp:
            smtp.login(self.c.mail_user, self.c.mail_password)
            refused = smtp.send_message(msg)
            if refused:
                raise RuntimeError('SMTP recipient refused')
