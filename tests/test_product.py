import tempfile
import unittest
from datetime import date, datetime
from sales_agent.config import Config
from sales_agent.engine import Engine, digest
from sales_agent.agents.validation import evidence_gate
from sales_agent.agents.scoring import ScoringAgent
from sales_agent.server import schedule_tick

class FakeProvider:
    def extract(self, prompt, schema):
        return {'category': 'rejected', 'summary': 'Unsubscribe', 'next_action': 'Stop'}

class FakeMailbox:
    def __init__(self):
        self.messages, self.sent, self.fail = [], [], False
    def scan(self):
        return self.messages
    def send(self, d, mid):
        self.sent.append(mid)
        if self.fail:
            raise TimeoutError()

class ProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = Config(data_dir=self.tmp.name, token='test-token-'*4)
        self.mail = FakeMailbox()
        self.e = Engine(self.c, FakeProvider(), self.mail)
    def tearDown(self):
        self.tmp.cleanup()
    def seeded(self):
        self.e.run()
        return self.e.db.get('drafts', 'demo-draft')
    def live_seeded(self):
        d = self.seeded()
        self.c.mode = 'live'
        self.c.api_key = self.c.model = self.c.mail_password = 'test-only'
        self.c.sender = self.c.mail_user = 'owner@example.org'
        d['demo'] = False
        self.e.db.put('drafts', d)
        self.e.approve(d['id'], digest(d), True)
        return d
    def test_demo_full_pipeline_and_dedup(self):
        first, second = self.e.run(), self.e.run()
        self.assertEqual(first['status'], 'completed')
        self.assertEqual(first['new_accounts'], 1)
        self.assertEqual(second['new_accounts'], 0)
        self.assertEqual(len(self.e.db.all('accounts')), 1)
        self.assertEqual(len({e['agent'] for e in self.e.db.all('events')}), 5)
    def test_demo_never_sends(self):
        d = self.seeded()
        self.e.approve(d['id'], digest(d), True)
        with self.assertRaises(ValueError): self.e.send(d['id'])
        self.assertEqual(self.mail.sent, [])
    def test_edit_invalidates_approval_and_stale_hash(self):
        d = self.seeded()
        old = digest(d)
        self.e.approve(d['id'], old, True)
        edited = self.e.edit(d['id'], 'New subject', 'New content')
        self.assertEqual(edited['status'], 'pending')
        with self.assertRaises(ValueError): self.e.approve(d['id'], old, True)
        with self.assertRaises(ValueError): self.e.approve(d['id'], digest(edited), False)
    def test_send_once(self):
        d = self.live_seeded()
        self.e.send(d['id'])
        with self.assertRaises(ValueError): self.e.send(d['id'])
        self.assertEqual(len(self.mail.sent), 1)
    def test_unknown_delivery_never_retried(self):
        d = self.live_seeded()
        self.mail.fail = True
        with self.assertRaises(RuntimeError): self.e.send(d['id'])
        self.assertEqual(self.e.db.get('drafts', d['id'])['status'], 'unknown')
        with self.assertRaises(ValueError): self.e.send(d['id'])
        self.assertEqual(len(self.mail.sent), 1)
    def test_history_blocks_first_contact(self):
        d = self.live_seeded()
        self.e.db.put('contacts', {'id': 'someone@factory.example', 'domain': 'factory.example', 'status': 'sent'})
        with self.assertRaises(ValueError): self.e.send(d['id'])
        self.assertFalse(self.mail.sent)
    def test_unsubscribe_blocks_sending_and_is_idempotent(self):
        d = self.live_seeded()
        self.mail.messages = [{'id': 'message-test', 'direction': 'received', 'from': d['to'],
            'to': ['owner@example.org'], 'references': '', 'subject': 'No thanks',
            'body': 'Please unsubscribe', 'dsn': ''}]
        with self.assertRaises(ValueError): self.e.send(d['id'])
        self.assertEqual(self.e.db.get('accounts', 'demo-factory')['status'], 'rejected')
        self.e.followup.run()
        self.assertEqual(len(self.e.db.all('messages')), 1)
        self.assertFalse(self.mail.sent)
    def test_unretrieved_sources_and_future_date_rejected(self):
        a = {'domain': 'factory.example', 'group_domain': 'factory.example', 'trigger_date': '2999-01-01',
             'independent_sources': True, 'sources': [{'url': 'https://factory.example/news', 'kind': 'official_trigger'}],
             'in_scope': True, 'technical_fit': True, 'email': 'sales@factory.example', 'email_verified': True}
        self.assertFalse(evidence_gate(a, set())['validated'])
        self.assertGreaterEqual(len(a['validation_issues']), 3)
    def test_score_total_and_gate(self):
        a = {'trigger_date': date.today().isoformat(), 'employees': 120, 'technical_fit': True,
             'email_verified': True, 'contact_verified': True, 'contact': 'Example', 'strategic': True, 'validated': False}
        ScoringAgent().run(a)
        self.assertEqual(a['score'], sum(a['score_breakdown'].values()))
        self.assertEqual(a['status'], 'watch')
    def test_schedule_once_daily_and_restart(self):
        schedule_tick(self.e, datetime(2026, 9, 29, 8))
        self.assertEqual(len(self.e.db.all('runs')), 0)
        schedule_tick(self.e, datetime(2026, 9, 29, 9))
        restarted = Engine(self.c, FakeProvider(), self.mail)
        schedule_tick(restarted, datetime(2026, 9, 29, 10))
        self.assertEqual(len(self.e.db.all('runs')), 1)
    def test_demo_live_databases_are_separate(self):
        self.e.run()
        live = Engine(Config(data_dir=self.tmp.name, mode='live'))
        self.assertEqual(live.db.all('accounts'), [])

if __name__ == '__main__': unittest.main()
