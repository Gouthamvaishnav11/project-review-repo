# Copyright (c) 2025, Ecohotels and contributors
# patches/seed_dynamic_config.py
#
# Run with:
#   bench --site mysite.localhost execute ecohotels.patches.seed_dynamic_config.execute
#
# Purpose:
#   Migrate all hardcoded constants from reservation.py into the new
#   Hotel Configuration and Ecohotels Product Mapping DocTypes.
#   This ensures zero-downtime transition from hardcoded to dynamic config.

import frappe


# ── Hardcoded data from old reservation.py ────────────────────────────────────

HOTEL_CONFIGS = [
	{
		"hotel_code"          : "IN000002",
		"state"               : "32-Kerala",
		"sgst_account"        : "294300",
		"cgst_account"        : "294001",
		"igst_account"        : "166102",
		"tds_account"         : "166201",
		"tcs_account"         : "166202",
		"tpa_credit_account"  : "269200",
		"default_sales_tax_rate": 7.0,
		"commission_rate"     : 18.0,
		"commission_item"     : "GS100000",
		"default_customer_group": "Individual",
		"default_territory"   : "India",
		"default_currency"    : "INR",
		"default_payment_term": "Default Payment term",
	},
	{
		"hotel_code"          : "IN000004",
		"state"               : "08-Rajasthan",
		"sgst_account"        : "294300",
		"cgst_account"        : "294001",
		"igst_account"        : "166102",
		"tds_account"         : "166201",
		"tcs_account"         : "166202",
		"tpa_credit_account"  : "269200",
		"default_sales_tax_rate": 7.0,
		"commission_rate"     : 18.0,
		"commission_item"     : "GS100000",
		"default_customer_group": "Individual",
		"default_territory"   : "India",
		"default_currency"    : "INR",
		"default_payment_term": "Default Payment term",
	},
	{
		"hotel_code"          : "IN000005",
		"state"               : "24-Gujarat",
		"sgst_account"        : "294300",
		"cgst_account"        : "294001",
		"igst_account"        : "166102",
		"tds_account"         : "166201",
		"tcs_account"         : "166202",
		"tpa_credit_account"  : "269200",
		"default_sales_tax_rate": 7.0,
		"commission_rate"     : 18.0,
		"commission_item"     : "GS100000",
		"default_customer_group": "Individual",
		"default_territory"   : "India",
		"default_currency"    : "INR",
		"default_payment_term": "Default Payment term",
	},
	{
		"hotel_code"          : "IN000006",
		"state"               : "09-Uttar Pradesh",
		"sgst_account"        : "294300",
		"cgst_account"        : "294001",
		"igst_account"        : "166102",
		"tds_account"         : "166201",
		"tcs_account"         : "166202",
		"tpa_credit_account"  : "269200",
		"default_sales_tax_rate": 7.0,
		"commission_rate"     : 18.0,
		"commission_item"     : "GS100000",
		"default_customer_group": "Individual",
		"default_territory"   : "India",
		"default_currency"    : "INR",
		"default_payment_term": "Default Payment term",
	},
	{
		"hotel_code"          : "IN000007",
		"state"               : "09-Uttar Pradesh",
		"sgst_account"        : "294300",
		"cgst_account"        : "294001",
		"igst_account"        : "166102",
		"tds_account"         : "166201",
		"tcs_account"         : "166202",
		"tpa_credit_account"  : "269200",
		"default_sales_tax_rate": 7.0,
		"commission_rate"     : 18.0,
		"commission_item"     : "GS100000",
		"default_customer_group": "Individual",
		"default_territory"   : "India",
		"default_currency"    : "INR",
		"default_payment_term": "Default Payment term",
	},
]

# NOTE: tax_rate=0 means generic mapping (no tax-specific routing)
PRODUCT_MAPPINGS = [
	{"pms_product_id": "6x66252",   "tax_rate": 0,   "erp_item": "FO001008",  "description": "Extra charges"},
	{"pms_product_id": "6x1599",    "tax_rate": 0,   "erp_item": "FO001007",  "description": "Food"},
	{"pms_product_id": "6x66253",   "tax_rate": 0,   "erp_item": "ALC1",      "description": "Alcoholic Beverage"},
	{"pms_product_id": "6x3314",    "tax_rate": 0,   "erp_item": "LA002000",  "description": "Laundry"},
	{"pms_product_id": "6x691",     "tax_rate": 0,   "erp_item": "FO1002",    "description": "Room"},
	{"pms_product_id": "6x2563181", "tax_rate": 0,   "erp_item": "FO001012",  "description": "Room (Above 7500)"},
	{"pms_product_id": "6x2563180", "tax_rate": 0,   "erp_item": "FO001013",  "description": "Food (Above 7500)"},
	{"pms_product_id": "6x66253",   "tax_rate": 18,  "erp_item": "FI000147",  "description": "Alcoholic Beverage (18% GST)"},
	{"pms_product_id": "6x791434",  "tax_rate": 0,   "erp_item": "FO002004",  "description": "Other"},
]


def execute():
	"""Main patch entry point."""
	print("=" * 60)
	print("Seeding Hotel Configuration DocType...")
	seed_hotel_configurations()

	print("Seeding Ecohotels Product Mapping DocType...")
	seed_product_mappings()

	frappe.db.commit()
	print("Seed completed successfully.")
	print("=" * 60)


def seed_hotel_configurations():
	"""Create Hotel Configuration records from hardcoded constants."""
	for config in HOTEL_CONFIGS:
		hotel_code = config["hotel_code"]

		if frappe.db.exists("Hotel Configuration", hotel_code):
			print(f"  [SKIP] Hotel Configuration '{hotel_code}' already exists.")
			continue

		# Resolve company from hotel code
		company = frappe.db.get_value("Company", {"abbr": hotel_code}, "name")
		if not company:
			print(f"  [WARN] Company not found for hotel code '{hotel_code}'. Skipping.")
			continue

		doc = frappe.get_doc({
			"doctype": "Hotel Configuration",
			**config,
			"company": company,
		})
		doc.insert(ignore_permissions=True, ignore_links=True)
		print(f"  [OK] Created Hotel Configuration: {hotel_code} — {config['state']}")


def seed_product_mappings():
	"""Create Ecohotels Product Mapping records from hardcoded PRODUCT_ID_MAP."""
	for mapping in PRODUCT_MAPPINGS:
		existing = frappe.db.get_value(
			"Ecohotels Product Mapping",
			{
				"pms_product_id": mapping["pms_product_id"],
				"tax_rate"      : mapping["tax_rate"],
			},
			"name"
		)

		if existing:
			print(f"  [SKIP] Mapping '{mapping['pms_product_id']}' (tax={mapping['tax_rate']}) already exists.")
			continue

		doc = frappe.get_doc({
			"doctype": "Ecohotels Product Mapping",
			**mapping,
		})
		doc.insert(ignore_permissions=True)
		print(f"  [OK] Created mapping: {mapping['pms_product_id']} (tax={mapping['tax_rate']}) → {mapping['erp_item']}")
