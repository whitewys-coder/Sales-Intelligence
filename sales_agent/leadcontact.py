"""LeadContact enrichment. No phone API, no sending, no implicit retries."""
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from urllib.parse import urlparse

BASE = 'https://api.leadcontact.ai/api/rest'


def profile_url(value):
    p = urlparse(value)
    if p.scheme != 'https' or p.username or p.password or p.port or not (p.hostname == 'linkedin.com' or (p.hostname or '').endswith('.linkedin.com')) or not re.fullmatch(r'/in/[^/]+/?', p.path):
        raise ValueError('A verified HTTPS LinkedIn person URL is required')
    return 'https://www.linkedin.com' + p.path.rstrip('/')


class LeadContact:
    def __init__(self, key=None):
        self.key = key if key is not None else os.getenv('LEADCONTACT_API_KEY', '')
        if not self.key:
            raise ValueError('LEADCONTACT_API_KEY is missing')

    def request(self, path, payload=None):
        # Fixed endpoints prevent accidental phone calls or token exfiltration.
        if path not in ('/credits', '/email/query', '/employess/query/advanced'):
            raise ValueError('Unsupported LeadContact endpoint')
        req = urllib.request.Request(BASE + path, data=None if payload is None else json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=45) as r:
                result = json.load(r)
        except Exception:
            raise RuntimeError('LeadContact transport failure; outcome may be uncertain; not retried') from None
        if result.get('code') != 200:
            raise RuntimeError('LeadContact API rejected request (code %s)' % result.get('code'))
        return result.get('data') or {}

    def credits(self):
        points = self.request('/credits').get('remainingPoints')
        if not isinstance(points, (int, float)):
            raise RuntimeError('LeadContact balance missing')
        return points

    def search(self, keyword):
        return self.request('/employess/query/advanced', {'keyword': keyword,
            'location': ['Germany'], 'companySize': ['11_50', '51_200', '201_500'],
            'currentTitlesOnly': True, 'seniority': ['Owner / Founder', 'CXO', 'Director', 'Head', 'Manager']})

    def email(self, url):
        url = profile_url(url)
        if self.credits() < 10:
            raise RuntimeError('Insufficient LeadContact credits')
        data = self.request('/email/query', {'profileUrl': url})
        return {'provider': 'LeadContact', 'profile_url': url,
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'sources': [{'email': s.get('email'), 'provider_valid': s.get('valid'), 'name': s.get('name')}
                        for s in data.get('sources', []) if s.get('email')],
            'delivery_verified': False, 'human_review_required': True}


def enrich_account(account, client):
    """Supplement only; never change eligibility, recipient or evidence gate."""
    url = account.get('linkedin_url', '')
    if not account.get('contact_verified') or not url:
        return False
    # The profile URL must have actually been retrieved during validation.
    if url not in {s.get('url') for s in account.get('sources', []) if s.get('kind') == 'contact'}:
        return False
    if account.get('excluded') or not account.get('in_scope') or not account.get('technical_fit'):
        return False
    account['leadcontact'] = client.email(url)
    return True


def main():
    import argparse
    from pathlib import Path
    from .config import load_env
    load_env()
    p = argparse.ArgumentParser(description='Research-only LeadContact tools; never sends email')
    p.add_argument('action', choices=['credits', 'search', 'email'])
    p.add_argument('--keyword', default='Montageautomatisierung')
    p.add_argument('--profile-url')
    p.add_argument('--output', help='Private JSON output path; never commit personal data')
    args = p.parse_args()
    c = LeadContact()
    result = c.credits() if args.action == 'credits' else c.search(args.keyword) if args.action == 'search' else c.email(args.profile_url or '')
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(text)
    else:
        print(text)

if __name__ == '__main__':
    main()
