import unittest
from unittest.mock import Mock
from sales_agent.leadcontact import LeadContact, profile_url, enrich_account

class LeadContactTests(unittest.TestCase):
    def test_profile_validation(self):
        for url in ['https://linkedin.com.evil.test/in/x', 'http://linkedin.com/in/x', 'https://linkedin.com/company/x']:
            with self.assertRaises(ValueError): profile_url(url)
        self.assertEqual(profile_url('https://de.linkedin.com/in/alex/'), 'https://www.linkedin.com/in/alex')
    def test_phone_never_supported(self):
        with self.assertRaises(ValueError): LeadContact('test').request('/phone/query', {})
    def test_insufficient_balance_blocks_paid_call(self):
        c=LeadContact('test'); c.credits=Mock(return_value=9); c.request=Mock()
        with self.assertRaises(RuntimeError): c.email('https://www.linkedin.com/in/alex')
        c.request.assert_not_called()
    def test_enrichment_does_not_authorize_sending(self):
        a={'contact_verified':True,'linkedin_url':'https://www.linkedin.com/in/alex','in_scope':True,'technical_fit':True,'email':'','validated':False,'sources':[{'kind':'contact','url':'https://www.linkedin.com/in/alex'}]}
        c=Mock();c.email.return_value={'sources':[{'email':'a@example.com','provider_valid':True}]}
        self.assertTrue(enrich_account(a,c));self.assertFalse(a['validated']);self.assertEqual(a['email'],'')
        a['sources']=[];c.reset_mock();self.assertFalse(enrich_account(a,c));c.email.assert_not_called()
