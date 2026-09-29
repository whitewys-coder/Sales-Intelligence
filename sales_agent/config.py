import os
from dataclasses import dataclass
from pathlib import Path


def load_env(path='.env'):
    if Path(path).is_file():
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Config:
    mode: str = 'demo'
    data_dir: str = 'data'
    token: str = ''
    api_key: str = ''
    model: str = ''
    sender: str = ''
    sender_name: str = 'Sales Team'
    imap_host: str = 'imap.gmail.com'
    smtp_host: str = 'smtp.gmail.com'
    mail_user: str = ''
    mail_password: str = ''
    sent_folder: str = '[Gmail]/Sent Mail'
    inbox_folder: str = 'INBOX'
    mail_limit: int = 1000
    max_accounts: int = 5
    timezone: str = 'Asia/Shanghai'
    schedule_hour: int = 9
    schedule_enabled: bool = False
    bind: str = '127.0.0.1'
    port: int = 8080

    @classmethod
    def env(cls):
        load_env()
        c = cls(mode=os.getenv('APP_MODE', 'demo'), data_dir=os.getenv('DATA_DIR', 'data'),
                token=os.getenv('APP_TOKEN', ''), api_key=os.getenv('OPENAI_API_KEY', ''),
                model=os.getenv('OPENAI_MODEL', ''), sender=os.getenv('SENDER_EMAIL', ''),
                sender_name=os.getenv('SENDER_NAME', 'Sales Team'),
                imap_host=os.getenv('IMAP_HOST', 'imap.gmail.com'),
                smtp_host=os.getenv('SMTP_HOST', 'smtp.gmail.com'),
                mail_user=os.getenv('MAIL_USER', ''), mail_password=os.getenv('MAIL_PASSWORD', ''),
                sent_folder=os.getenv('IMAP_SENT_FOLDER', '[Gmail]/Sent Mail'),
                inbox_folder=os.getenv('IMAP_INBOX_FOLDER', 'INBOX'),
                mail_limit=int(os.getenv('MAIL_SCAN_LIMIT', '1000')),
                max_accounts=int(os.getenv('MAX_ACCOUNTS', '5')),
                timezone=os.getenv('APP_TIMEZONE', 'Asia/Shanghai'),
                schedule_hour=int(os.getenv('SCHEDULE_HOUR', '9')),
                schedule_enabled=os.getenv('SCHEDULE_ENABLED', 'false').lower() == 'true',
                bind=os.getenv('HOST', '127.0.0.1'), port=int(os.getenv('PORT', '8080')))
        if c.mode not in ('demo', 'live'):
            raise ValueError('APP_MODE must be demo or live')
        if len(c.token) < 24 or c.token.startswith('REPLACE_'):
            raise ValueError('Set APP_TOKEN to a random value of at least 24 characters')
        if not 1 <= c.max_accounts <= 10 or not 0 <= c.schedule_hour <= 23:
            raise ValueError('MAX_ACCOUNTS=1..10; SCHEDULE_HOUR=0..23')
        return c

    def check_live(self):
        if self.mode == 'live' and not all((self.api_key, self.model, self.sender,
                                           self.mail_user, self.mail_password)):
            raise ValueError('Live mode requires OpenAI model/key and email connection settings')
