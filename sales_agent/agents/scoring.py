from datetime import date


class ScoringAgent:
    name = 'Scoring Agent'

    def run(self, a, today=None):
        today = today or date.today()
        try:
            age = (today - date.fromisoformat(a['trigger_date'])).days
        except (ValueError, KeyError):
            age = 999
        n = a.get('employees', 0)
        points = {
            'trigger': 25 if a.get('validated') else 0,
            'technical_fit': 20 if a.get('technical_fit') else 0,
            'freshness': 15 if 0 <= age <= 30 else 10 if 30 < age <= 60 else 5 if 60 < age <= 90 else 0,
            'decision_maker': 15 if a.get('contact_verified') and a.get('contact') else 0,
            'public_email': 10 if a.get('email_verified') else 0,
            'size': 10 if 10 <= n <= 500 else 5 if 501 <= n <= 2000 else 2 if n > 0 else 0,
            'strategic': 5 if a.get('strategic') else 0,
        }
        a['score_breakdown'], a['score'] = points, sum(points.values())
        a['status'] = 'pending_review' if a.get('validated') and a['score'] >= 90 else 'nurture' if a.get('validated') and a['score'] >= 80 else 'watch'
        return a
