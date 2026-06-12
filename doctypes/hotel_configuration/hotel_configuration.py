# Copyright (c) 2025, Ecohotels and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HotelConfiguration(Document):

	def validate(self):
		self.validate_hotel_code()

	def validate_hotel_code(self):
		if not self.hotel_code:
			frappe.throw("Hotel Code is mandatory.")


def get_hotel_config(hotel_code):
	"""
	Fetch Hotel Configuration for a given hotel_code.
	Raises an error if not found.
	"""
	config = frappe.db.get_value(
		"Hotel Configuration",
		{"hotel_code": hotel_code},
		[
			"name", "company", "state",
			"sgst_account", "cgst_account", "igst_account",
			"tds_account", "tcs_account", "tpa_credit_account",
			"default_sales_tax_rate", "commission_rate", "commission_item",
			"default_customer_group", "default_territory",
			"default_currency", "default_payment_term"
		],
		as_dict=True
	)

	if not config:
		frappe.throw(
			f"Hotel Configuration not found for hotel code: {hotel_code}. "
			f"Please configure it under Ecohotels > Hotel Configuration."
		)

	return config
