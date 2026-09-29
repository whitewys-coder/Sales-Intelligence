import json
from ..provider import obj, TEXT
from ..store import now, uid


class SalesAgent:
    name = 'Sales Agent'

    def __init__(self, provider, config):
        self.provider, self.config = provider, config

    def run(self, account):
        if not account.get('validated') or account['status'] != 'pending_review':
            return None
        result = self.provider.extract('Write a concise English first-contact email based ONLY on the verified account below. '
            'One real trigger, one complementary Edge AI deployment use case, invite 15–20 minute discussion. '
            'No invented gains, certifications, attachment claims, or whole-model <1MB claims. No signature (app adds it).\n' +
            json.dumps(account, ensure_ascii=False), obj({'subject': TEXT, 'body': TEXT}))
        return {'id': uid(), 'account_id': account['id'], 'to': account['email'],
                'subject': result['subject'], 'body': result['body'] + '\n\nBest regards,\n' +
                self.config.sender_name + '\nXeroptix\n' + self.config.sender + '\nXeroptix.com',
                'status': 'pending', 'created_at': now(), 'approved_hash': '', 'demo': False}
