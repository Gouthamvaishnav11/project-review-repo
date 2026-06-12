# Copyright (c) 2025, Ecohotels and contributors
# item_mapping.py — Dynamic Item Resolution using Ecohotels Product Mapping DocType

import frappe
from .logger import APILogger


def resolve_item_code(item, endpoint_name, item_index, folio_no=None, booking_id=None):
	"""
	Resolve PMS productid to an ERPNext item_code using the
	Ecohotels Product Mapping DocType.

	Resolution order:
	  1. Tax-specific mapping  (pms_product_id + tax_rate match)
	  2. Generic mapping       (pms_product_id with tax_rate = 0 or not set)

	Raises ValueError if no mapping found.
	"""
	product_id = item.get("productid")
	tax        = item.get("tax")

	if not product_id:
		raise ValueError(
			f"Item #{item_index}: 'productid' is mandatory but was not provided."
		)

	# ── Step 1: Tax-specific mapping ──────────────────────────────────────────
	if tax is not None:
		try:
			tax_val = float(tax)
			item_code = frappe.db.get_value(
				"Ecohotels Product Mapping",
				{"pms_product_id": product_id, "tax_rate": tax_val},
				"erp_item"
			)
			if item_code:
				return item_code
		except (TypeError, ValueError):
			pass  # Invalid tax value — fall through to generic

	# ── Step 2: Generic mapping (tax_rate = 0) ────────────────────────────────
	item_code = frappe.db.get_value(
		"Ecohotels Product Mapping",
		{"pms_product_id": product_id, "tax_rate": 0},
		"erp_item"
	)
	if item_code:
		return item_code

	# ── Step 3: Generic mapping (tax_rate is null/not set) ────────────────────
	item_code = frappe.db.get_value(
		"Ecohotels Product Mapping",
		{"pms_product_id": product_id, "tax_rate": ("is", "not set")}, #Try ["tax_rate", "is", "not set"] if {"tax_rate": ("is", "not set")} doesn't work  
		"erp_item"
	)
	if item_code:
		return item_code

	# ── No mapping found ──────────────────────────────────────────────────────
	raise ValueError(
		f"Item #{item_index}: No ERP item mapped for PMS productid "
		f"'{product_id}' (tax: '{tax}'). "
		f"Please add a mapping in Ecohotels > Ecohotels Product Mapping. "
		f"[folio_no={folio_no}, booking_id={booking_id}]"
	)
