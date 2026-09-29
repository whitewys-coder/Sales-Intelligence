import json
from datetime import date
from ..provider import obj, array, TEXT


class ResearchAgent:
    name = 'Research Agent'

    def __init__(self, provider, config):
        self.provider, self.config = provider, config

    def run(self, scope, exclusions):
        report, sources = self.provider.research(
            f'Today {date.today()}. Find at most {self.config.max_accounts} NEW accounts. Scope: {scope}. '
            '10–500 employees first; larger strategic exceptions explicitly labeled. Priorities: '
            '1 Physical AI/Embodied AI; 2 tenders; 3 AI/vision/automation upgrades and hiring; 4 expansion. '
            'Triggers within 90 days. Exclude same-product machine-vision integrators and embedded-AI hardware vendors. '
            'Exclude Africa and Southeast Asia expansion destinations. No quota filling. '
            'For each give company, official domain, parent group, trigger/date, why now, sources and public email. '
            'Exclude these already known domains/groups: ' + json.dumps(exclusions))
        result = self.provider.extract('Extract candidate names/domains from research below; zero candidates allowed.\n' + report,
                                       obj({'candidates': array(obj({'company': TEXT, 'domain': TEXT}))}))
        return result['candidates'][:self.config.max_accounts], {'report': report, 'sources': sources}
