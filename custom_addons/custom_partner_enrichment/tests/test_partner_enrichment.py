# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPartnerEnrichment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.company = Partner.create({'name': 'Empresa prueba', 'is_company': True})
        cls.contact = Partner.create({
            'name': 'Contacto prueba',
            'parent_id': cls.company.id,
        })

    def test_company_values_reach_contacts(self):
        self.company.write({
            'company_size': 'pyme',
            'commercial_value': 'strategic',
            'customer_stage': 'active',
        })
        self.assertEqual(self.contact.company_size, 'pyme')
        self.assertEqual(self.contact.commercial_value, 'strategic')
        self.assertEqual(self.contact.customer_stage, 'active')

    def test_clearing_company_value_clears_contacts(self):
        self.company.customer_stage = 'prospect'
        self.assertEqual(self.contact.customer_stage, 'prospect')
        self.company.customer_stage = False
        self.assertFalse(self.contact.customer_stage)

    def test_new_contact_inherits_values(self):
        self.company.write({'company_size': 'micro', 'customer_stage': 'developing'})
        new_contact = self.env['res.partner'].create({
            'name': 'Contacto nuevo',
            'parent_id': self.company.id,
        })
        self.assertEqual(new_contact.company_size, 'micro')
        self.assertEqual(new_contact.customer_stage, 'developing')

    def test_personal_fields_are_not_propagated(self):
        self.company.write({
            'contact_profile': 'other',
            'linkedin_url': 'https://www.linkedin.com/company/prueba',
        })
        self.assertFalse(self.contact.contact_profile)
        self.assertFalse(self.contact.linkedin_url)

        self.contact.write({
            'contact_profile': 'it',
            'linkedin_url': 'https://www.linkedin.com/in/prueba',
        })
        self.assertEqual(self.company.contact_profile, 'other')
        self.assertEqual(self.company.linkedin_url, 'https://www.linkedin.com/company/prueba')
