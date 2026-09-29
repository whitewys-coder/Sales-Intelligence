import hashlib
import json
import threading
from datetime import date
from pathlib import Path
from .config import Config
from .store import Store, now, uid
from .provider import Provider
from .mail import Mailbox
from .agents import ResearchAgent, ValidationAgent, ScoringAgent, SalesAgent, FollowUpAgent
from .agents.validation import evidence_gate

DEFAULT_SCOPE = ('European manufacturing in Germany, France, Spain, Italy, Netherlands, Belgium, Switzerland, '
                 'Austria, Hungary, Czechia; Chinese manufacturers expanding into Europe, USA or South America. '
                 'Industries: manufacturing, energy, automotive, smart hardware, industrial equipment.')


def digest(d):
    return hashlib.sha256(json.dumps({k: d[k] for k in ('to', 'subject', 'body')},
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Engine:
    def __init__(self, config, provider=None, mailbox=None):
        self.c = config
        self.db = Store(Path(config.data_dir) / (config.mode + '.sqlite3'))
        self.p = provider or Provider(config)
        self.mailbox = mailbox or Mailbox(config)
        self.lock = threading.Lock()
        self.followup = FollowUpAgent(self.p, self.mailbox, self.db)
        self.research = ResearchAgent(self.p, config)
        self.validation = ValidationAgent(self.p)
        self.scoring = ScoringAgent()
        self.sales = SalesAgent(self.p, config)

    def state(self):
        return {'mode': self.c.mode, 'busy': self.lock.locked(),
                'configured': bool(self.c.api_key and self.c.model and self.c.mail_password),
                'schedule_enabled': self.c.schedule_enabled, 'timezone': self.c.timezone,
                'schedule_hour': self.c.schedule_hour,
                'accounts': self.db.all('accounts'), 'drafts': self.db.all('drafts'),
                'runs': self.db.all('runs')[:50], 'events': self.db.all('events')[:100],
                'settings': self.db.all('settings')}

    def known(self, a):
        keys = {a.get('domain'), a.get('group_domain')} - {None, ''}
        return any(keys & {x.get('domain'), x.get('group_domain')} for x in self.db.all('accounts')) or any(
            x.get('domain') in keys or x['id'] == a.get('email') for x in self.db.all('contacts'))

    def stage(self, agent, run_id, fn):
        self.db.event(agent, 'running', 'Started', run_id)
        try:
            value = fn()
        except Exception as exc:
            self.db.event(agent, 'failed', type(exc).__name__ + ': ' + str(exc)[:300], run_id)
            raise
        self.db.event(agent, 'completed', 'Completed', run_id)
        return value

    def run(self, scope=DEFAULT_SCOPE, schedule_key=''):
        if not self.lock.acquire(blocking=False):
            raise ValueError('Another run or send is in progress')
        run = {'id': uid(), 'started_at': now(), 'status': 'running', 'mode': self.c.mode,
               'schedule_key': schedule_key, 'scope': scope, 'new_accounts': 0, 'new_drafts': 0}
        self.db.put('runs', run)
        try:
            self.c.check_live()
            if self.c.mode == 'demo':
                self.demo(run)
            else:
                self.stage(self.followup.name, run['id'], self.followup.run)
                exclusions = [x.get('group_domain') or x.get('domain') for x in self.db.all('accounts')]
                exclusions += [x.get('domain') for x in self.db.all('contacts')]
                candidates, audit = self.stage(self.research.name, run['id'], lambda: self.research.run(scope, exclusions))
                run['research'] = audit
                for candidate in candidates:
                    a = self.stage(self.validation.name, run['id'], lambda: self.validation.run(candidate, scope))
                    if self.known(a):
                        self.db.event(self.validation.name, 'excluded', 'Existing account/group/domain: ' + a.get('company', ''), run['id'])
                        continue
                    a.update(id=uid(), updated_at=now(), demo=False)
                    a = self.stage(self.scoring.name, run['id'], lambda: self.scoring.run(a))
                    # Generate before saving account so a transient failure can be retried on a later run.
                    draft = self.stage(self.sales.name, run['id'], lambda: self.sales.run(a))
                    self.db.put('accounts', a)
                    run['new_accounts'] += 1
                    if draft:
                        self.db.put('drafts', draft)
                        run['new_drafts'] += 1
            run['status'] = 'completed'
        except Exception as exc:
            run.update(status='failed', error=type(exc).__name__ + ': ' + str(exc)[:300])
        finally:
            run['finished_at'] = now()
            self.db.put('runs', run)
            self.lock.release()
        return run

    def demo(self, run):
        for name in ('Follow-up Agent', 'Research Agent'):
            self.db.event(name, 'demo', 'Synthetic fixture; no network/mailbox access', run['id'])
        a = {'id': 'demo-factory', 'company': 'DEMO • Example Factory', 'domain': 'factory.example',
             'group_domain': 'factory.example', 'country': 'Germany', 'employees': 120,
             'trigger': 'Synthetic equipment upgrade, not a real sales lead', 'trigger_date': date.today().isoformat(),
             'contact': 'Demo Director', 'email': 'sales@factory.example', 'technical_fit': True,
             'contact_verified': True, 'email_verified': True, 'strategic': True, 'validated': True,
             'sources': [], 'validation_issues': [], 'evidence_review_required': True,
             'demo': True, 'why_now': 'Synthetic demonstration', 'fit_reason': 'Demonstration only'}
        self.db.event('Validation Agent', 'demo', 'Synthetic evidence only; cannot be sent', run['id'])
        if self.db.get('accounts', a['id']):
            self.db.event('Scoring Agent', 'demo', 'Existing fixture retained (idempotent)', run['id'])
            self.db.event('Sales Agent', 'demo', 'Existing fixture retained (idempotent)', run['id'])
            return
        self.scoring.run(a)
        self.db.put('accounts', a)
        self.db.event('Scoring Agent', 'demo', 'Deterministic score calculated', run['id'])
        d = dict(id='demo-draft', account_id=a['id'], to=a['email'], subject='DEMO — Edge AI pilot',
                 body='Synthetic demonstration only. No real customer or email will be contacted.',
                 status='pending', created_at=now(), approved_hash='', demo=True)
        self.db.put('drafts', d)
        self.db.event('Sales Agent', 'demo', 'Synthetic draft prepared; sending disabled', run['id'])
        run.update(new_accounts=1, new_drafts=1)

    def edit(self, ident, subject, body):
        with self.lock:
            d = self.db.get('drafts', ident)
            if not d or d['status'] not in ('pending', 'approved'):
                raise ValueError('Draft cannot be edited')
            if not subject.strip() or not body.strip() or '\n' in subject or '\r' in subject:
                raise ValueError('Invalid subject or body')
            d.update(subject=subject[:300], body=body[:20000], status='pending', approved_hash='')
            return self.db.put('drafts', d)

    def approve(self, ident, expected_hash, evidence_reviewed):
        with self.lock:
            d = self.db.get('drafts', ident)
            if not d or d['status'] not in ('pending', 'approved'):
                raise ValueError('Draft is not pending')
            if not evidence_reviewed or digest(d) != expected_hash:
                raise ValueError('Review evidence and current draft before approval')
            a = self.db.get('accounts', d['account_id'])
            if not a.get('validated') or a['status'] != 'pending_review':
                raise ValueError('Account not eligible')
            d.update(status='approved', approved_hash=digest(d), approved_at=now())
            self.db.put('drafts', d)
            self.db.event('Sales Agent', 'approved', 'Human approved immutable draft ' + ident)
            return d

    def send(self, ident):
        if self.c.mode != 'live':
            raise ValueError('Demo mode cannot send email')
        with self.lock:
            self.c.check_live()
            d = self.db.get('drafts', ident)
            if not d or d.get('demo') or d['status'] != 'approved' or digest(d) != d.get('approved_hash'):
                raise ValueError('Current draft requires approval')
            self.followup.run()  # Fresh complete history/rejection/bounce check before every send
            a = self.db.get('accounts', d['account_id'])
            if a['status'] in ('sent', 'replied', 'rejected', 'bounced'):
                raise ValueError('Account already contacted or suppressed')
            if any(x['id'] == d['to'] or x.get('domain') in (a['domain'], a['group_domain']) for x in self.db.all('contacts')):
                raise ValueError('Recipient/group has previous contact; use a manual follow-up')
            mid = '<' + d['id'] + '@' + self.c.sender.split('@')[-1] + '>'
            d.update(status='sending', message_id=mid)
            self.db.put('drafts', d)  # Persist BEFORE external side effect; crash never auto-retries
            try:
                self.mailbox.send(d, mid)
            except Exception:
                d['status'] = 'unknown'
                self.db.put('drafts', d)
                self.db.event('Sales Agent', 'unknown', 'SMTP outcome uncertain; inspect sent mailbox. Never retry automatically.')
                raise RuntimeError('SMTP outcome uncertain; no retry allowed. Reconcile with mailbox.') from None
            d.update(status='sent', sent_at=now())
            self.db.put('drafts', d)
            a['status'] = 'sent'
            self.db.put('accounts', a)
            self.db.put('contacts', {'id': d['to'], 'domain': a['domain'], 'status': 'sent', 'last_message_id': mid})
            self.db.event('Sales Agent', 'sent', 'SMTP accepted draft ' + ident + '; not proof of delivery')
            return d

    def feedback(self, ident, valid, reason):
        with self.lock:
            a = self.db.get('accounts', ident)
            if not a:
                raise ValueError('Unknown account')
            a['feedback'] = {'valid': valid, 'reason': reason[:2000], 'time': now()}
            self.db.put('accounts', a)
            return a
