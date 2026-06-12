# Copyright (c) 2025, Ecohotels and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EcohotelsProductMapping(Document):

	def validate(self):
		self.validate_unique_mapping()

	def validate_unique_mapping(self):
		existing = frappe.db.get_value(
			"Ecohotels Product Mapping",
			{
				"pms_product_id": self.pms_product_id,
				"tax_rate": self.tax_rate,
				"name": ("!=", self.name)
			},
			"name"
		)
		if existing:
			frappe.throw(
				f"A mapping for PMS Product ID '{self.pms_product_id}' "
				f"with Tax Rate '{self.tax_rate}%' already exists: {existing}"
			)
