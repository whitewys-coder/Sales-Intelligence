import json
import re
from datetime import date
from urllib.parse import urlparse
from ..provider import obj, array, TEXT, BOOL, NUMBER

SOURCE = obj({'url': TEXT, 'kind': TEXT, 'claim': TEXT, 'publisher': TEXT})
SCHEMA = obj({**{k: TEXT for k in ('company', 'domain', 'group_domain', 'country', 'trigger', 'trigger_date',
                                 'contact', 'email', 'why_now', 'fit_reason', 'exclusion_reason')},
              'employees': NUMBER, 'in_scope': BOOL, 'excluded': BOOL, 'independent_sources': BOOL,
              'technical_fit': BOOL, 'strategic': BOOL, 'contact_verified': BOOL,
              'email_verified': BOOL, 'sources': array(SOURCE)})


def domain(value):
    parsed = urlparse(value if '://' in value else 'https://' + value)
    host = (parsed.hostname or '').lower().removeprefix('www.').rstrip('.')
    return host if re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}', host) else ''


def address(value):
    return bool(re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value))


def evidence_gate(a, retrieved_urls, today=None):
    today = today or date.today()
    problems = []
    a['domain'] = domain(a.get('domain', ''))
    a['group_domain'] = domain(a.get('group_domain', '')) or a['domain']
    if not a['domain']:
        problems.append('invalid company domain')
    sources = a.get('sources', [])
    credible = [s for s in sources if s.get('url') in retrieved_urls and urlparse(s['url']).scheme == 'https']
    if len({domain(s['url']) for s in credible}) < 2 or not a.get('independent_sources'):
        problems.append('two independent retrieved sources required')
    official = [s for s in credible if s.get('kind') == 'official_trigger' and
                domain(s['url']) in (a['domain'], a['group_domain'])]
    if a['group_domain'] != a['domain'] and not any(s.get('kind') == 'group' for s in credible):
        problems.append('parent group evidence missing')
    if not any(s.get('kind') == 'employees' for s in credible):
        a['employees'] = 0
    if not any(s.get('kind') == 'contact' for s in credible):
        a['contact_verified'] = False
    if not official:
        problems.append('official trigger source missing')
    try:
        age = (today - date.fromisoformat(a['trigger_date'])).days
        if not 0 <= age <= 90:
            problems.append('trigger outside 90-day window')
    except (ValueError, KeyError):
        problems.append('trigger date unknown')
    if a.get('excluded') or not a.get('in_scope') or not a.get('technical_fit'):
        problems.append('scope/exclusion/technical-fit gate failed')
    email_sources = [s for s in credible if s.get('kind') == 'email' and a.get('email', '').lower() in s.get('claim', '').lower()]
    if not address(a.get('email', '')) or not a.get('email_verified') or not email_sources:
        problems.append('public email evidence missing')
    # Model assertions alone are not enough to authorize sending: UI requires a human evidence review.
    a['evidence_review_required'] = True
    a['validation_issues'] = problems
    a['sources'] = credible
    a['validated'] = not problems
    return a


class ValidationAgent:
    name = 'Validation Agent'

    def __init__(self, provider):
        self.provider = provider

    def run(self, candidate, scope):
        report, urls = self.provider.research('Independently verify this account: ' + json.dumps(candidate) +
            '. Scope: ' + scope + '. Open official source for trigger and date; two independent sources for company. '
            'Verify group ownership (not logo alone), public contact/email and staff count. Identify evidence for '
            'scope/technical fit/exclusions. Reprinted press releases are one source. Tender requires software eligibility '
            'and unexpired deadline; otherwise excluded. Show exact publicly listed email only. '
            'No evidence = unverified. Label sources official_trigger, email, contact, company, employees, or group.')
        a = self.provider.extract('Extract validated facts from this independent report. Use source kinds as specified. '
            'group_domain may equal domain only if no parent evidence. email_verified means publicly documented, not delivery. '
            'Set independent_sources=false if only duplicated press releases. Scope: ' + scope + '\n' + report, SCHEMA)
        a['validation_report'] = report
        return evidence_gate(a, set(urls))
