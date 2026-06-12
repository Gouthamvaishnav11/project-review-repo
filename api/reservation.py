# Copyright (c) 2025, Ecohotels and contributors
# reservation.py — Dynamic Configuration via Hotel Configuration DocType

import frappe
import json
from frappe import _
from .logger import APILogger
from .item_mapping import resolve_item_code
from ..doctypes.hotel_configuration.hotel_configuration import get_hotel_config

# ==============================================================================
# Helper Class for API Context
# ==============================================================================

class ReservationAPI:
	def __init__(self):
		self.data         = self._get_request_data()
		self.booking_id   = self.data.get("bookingId")
		self.folio_no     = self.data.get("folioNo")
		self.hotel_code   = self.data.get("hotelCode")

		# Loaded from Hotel Configuration DocType
		self.config           = None
		self.company_name     = None
		self.company_address  = None
		self.cost_center      = None

	def _get_request_data(self):
		"""Safely retrieve and parse request data."""
		if frappe.request and frappe.request.data:
			try:
				return (
					frappe.get_request_header("Content-Type") == "application/json"
					and json.loads(frappe.request.data)
					or frappe.form_dict
				)
			except Exception:
				pass
		return frappe.form_dict

	def validate(self):
		"""Basic validation of required fields."""
		required = ["bookingId", "folioNo", "hotelCode"]
		missing  = [f for f in required if not self.data.get(f)]
		if missing:
			frappe.throw(
				_("Missing required fields: {0}").format(", ".join(missing)),
				exc=frappe.ValidationError
			)

	def load_company_context(self):
		"""
		Load Hotel Configuration from DocType and set company context.
		Replaces all hardcoded HOTEL_CODE_TO_STATE_MAP and ACCOUNTS lookups.
		"""
		# ── Fetch from Hotel Configuration DocType ──
		self.config = get_hotel_config(self.hotel_code)

		self.company_name = self.config.company
		if not self.company_name:
			frappe.throw(f"Company not configured for hotel code: {self.hotel_code}")

		self.cost_center     = f"Main - {self.hotel_code}"
		self.company_address = frappe.db.get_value(
			"Address", {"address_title": self.company_name}, "name"
		)


# ==============================================================================
# Core Logic Functions — All Dynamic
# ==============================================================================

def get_account_details(account_no, company):
	"""Retrieve account name and tax rate from ERPNext."""
	acc = frappe.db.get_value(
		"Account",
		{"account_number": account_no, "company": company},
		["name", "tax_rate"]
	)
	if not acc:
		raise ValueError(f"Account {account_no} not found for company {company}")
	return acc


def parse_items(items_data):
	"""Parse items JSON string if necessary."""
	if isinstance(items_data, str):
		try:
			return json.loads(items_data)
		except json.JSONDecodeError as e:
			raise ValueError(f"Invalid JSON for items: {str(e)}")
	return items_data or []

def get_sales_taxes(company_name, config):
    tax_rate = config.default_sales_tax_rate or 7.0
    sgst_acc = get_account_details(config.sgst_account, company_name)
    cgst_acc = get_account_details(config.cgst_account, company_name)
    return [
        {"charge_type": "On Net Total", "account_head": sgst_acc[0], "rate": tax_rate, "gst_tax_type": "sgst", "description": "SGST"},
        {"charge_type": "On Net Total", "account_head": cgst_acc[0], "rate": tax_rate, "gst_tax_type": "cgst", "description": "CGST"},
    ]

def process_purchase_invoice(api_ctx):
	"""
	Handle TPA Booking Purchase Invoice creation/update.
	Commission rate and item fetched from Hotel Configuration.
	Replaces hardcoded commission_rate=18, item=GS100000.
	"""
	data         = api_ctx.data
	config       = api_ctx.config
	booking_type = data.get("bookingType")
	tpa_code     = data.get("travelAgencyCode") or "UNKNOWN_OTA"

	if booking_type != "tpaBooking" or tpa_code == "UNKNOWN_OTA":
		return

	company_name = api_ctx.company_name

	# ── Fetch accounts from Hotel Configuration ──
	tcs        = get_account_details(config.tcs_account, company_name)
	tds        = get_account_details(config.tds_account, company_name)
	igst       = get_account_details(config.igst_account, company_name)
	tpa_credit = get_account_details(config.tpa_credit_account, company_name)

	# ── Fetch commission settings from Hotel Configuration ──
	commission_rate = config.commission_rate or 18.0
	commission_item = config.commission_item or "GS100000"

	commission = data.get("commission")
	tcs_amt    = float(data.get("tcs_amount") or 0)
	tds_amt    = float(data.get("tds_amount") or 0)

	# ── Build purchase taxes ──
	purchase_taxes = []
	if commission_rate > 0:
		purchase_taxes.append({
			"charge_type"  : "On Net Total",
			"account_head" : igst[0],
			"rate"         : commission_rate,
			"description"  : f"{commission_rate}%",
		})
	if tcs_amt > 0:
		purchase_taxes.append({"charge_type": "Actual", "account_head": tcs[0], "tax_amount": tcs_amt, "description": "%"})
	if tds_amt > 0:
		purchase_taxes.append({"charge_type": "Actual", "account_head": tds[0], "tax_amount": tds_amt, "description": "%"})

	supplier = frappe.db.get_value("Supplier", {"custom_erp_id": tpa_code}, "name")

	invoice_payload = {
		"doctype"              : "Purchase Invoice",
		"supplier"             : supplier,
		"company"              : company_name,
		"bill_no"              : data.get("otaBookingId"),
		"custom_booking_id"    : api_ctx.folio_no,
		"credit_to"            : tpa_credit[0] if tpa_credit else "",
		"disable_rounded_total": True,
		"taxes"                : purchase_taxes,
		"items"                : [{"item_code": commission_item, "qty": 1, "rate": commission}],
	}

	existing_pi = frappe.db.get_value(
		"Purchase Invoice", {"custom_booking_id": api_ctx.folio_no}, "name"
	)

	if existing_pi:
		doc = frappe.get_doc("Purchase Invoice", existing_pi)
		doc.update(invoice_payload)
		doc.items = []
		doc.append("items", invoice_payload["items"][0])
		doc.taxes = []
		for tax in purchase_taxes:
			doc.append("taxes", tax)
		doc.save(ignore_permissions=True)
		frappe.msgprint(f"Purchase Invoice '{existing_pi}' updated.")
	else:
		if commission and float(commission) > 0:
			doc = frappe.get_doc(invoice_payload)
			doc.insert(ignore_permissions=True)
			frappe.msgprint(f"Purchase Invoice '{doc.name}' created.")


def get_or_create_customer(api_ctx):
	"""
	Find existing customer or create a new one.
	Customer defaults fetched from Hotel Configuration.
	Replaces hardcoded customer_group, territory, currency.
	"""
	data         = api_ctx.data
	config       = api_ctx.config
	booking_type = data.get("bookingType")
	tpa_code     = data.get("travelAgencyCode") or "UNKNOWN_OTA"

	booker_email  = data.get("bookerEmail")
	booker_mobile = data.get("bookerMobileNo")
	gstin         = data.get("gstNumber")

	customer_name  = f"{data.get('guestFirstName', '')} {data.get('guestLastName', '')}".strip()

	# ── Fetch defaults from Hotel Configuration ──
	customer_group    = config.default_customer_group or "Individual"
	default_territory = config.default_territory      or "India"
	default_currency  = config.default_currency       or "INR"

	existing_customer = None

	# Strategy 1: OTA/TPA booking — look up by OTA ID
	if booking_type == "tpaBooking" and tpa_code:
		existing_customer = frappe.db.get_value(
			"Customer", {"custom_erp_id": tpa_code}, ["name", "gst_category"]
		)

	# Strategy 2: Look up by email or mobile
	if not existing_customer:
		if booker_email:
			existing_customer = frappe.db.get_value(
				"Customer", {"custom_customer_email": booker_email}, ["name", "gst_category"]
			)
	if not existing_customer:
		if booker_mobile:
			existing_customer = frappe.db.get_value(
				"Customer", {"custom_customer_mobile_number": booker_mobile}, ["name", "gst_category"]
			)

	if existing_customer:
		return existing_customer[0], existing_customer[1]

	# Strategy 3: Create new customer
	gst_category = "Registered Regular" if gstin else "Unregistered"
	new_customer = frappe.get_doc({
		"doctype"                        : "Customer",
		"customer_name"                  : customer_name or "Guest",
		"territory"                      : default_territory,
		"custom_customer_email"          : booker_email,
		"custom_customer_mobile_number"  : booker_mobile,
		"customer_group"                 : customer_group,
		"customer_type"                  : customer_group,
		"gst_category"                   : gst_category,
		"gstin"                          : gstin or "",
		"default_currency"               : default_currency,
	})
	new_customer.insert(ignore_permissions=True)
	return new_customer.name, gst_category


def prepare_sales_order_fields(api_ctx, customer_id, gst_category, items, taxes):
	"""
	Map API data to Sales Order fields.
	Payment terms and place of supply fetched from Hotel Configuration.
	Replaces hardcoded payment_terms and state.
	"""
	data   = api_ctx.data
	config = api_ctx.config

	# ── Fetch from Hotel Configuration ──
	place_of_supply = config.state
	payment_term    = config.default_payment_term or "Default Payment term"

	booker_name = f"{data.get('bookerFirstName', '')} {data.get('bookerLastName', '')}".strip()

	sales_order_fields = {
		"customer"                          : customer_id,
		"custom_booking_id"                 : api_ctx.booking_id,
		"custom_folio_no"                   : api_ctx.folio_no,
		"transaction_date"                  : data.get("startDate"),
		"delivery_date"                     : data.get("endDate"),
		"company"                           : api_ctx.company_name,
		"company_address"                   : api_ctx.company_address,
		"currency"                          : config.default_currency or "INR",
		"gst_category"                      : gst_category,
		"taxes"                             : taxes,
		"place_of_supply"                   : place_of_supply,
		"posting_date"                      : data.get("invoicestartDate"),
		"due_date"                          : data.get("invoiceendDate"),
		"custom_invoice_start_date"         : data.get("invoicestartDate"),
		"custom_invoice_end_date"           : data.get("invoiceendDate"),
		"custom_invoice_number"             : data.get("invoiceno"),
		"custom_arrival_date_and_time"      : data.get("startDate"),
		"custom_departure_date_and_time"    : data.get("endDate"),
		"custom_hotel_name"                 : data.get("hotelName"),
		"custom_hotel_mobile_number"        : data.get("HotelMobile"),
		"custom_hotel_email"                : data.get("HotelEmail"),
		"custom_hotel_website"              : data.get("HotelWebsite"),
		"custom_hotel_address"              : data.get("HotelAddress"),
		"custom_total_days_of_room_stay"    : data.get("TotalDaysOfRoomStay"),
		"custom_room_amenities"             : data.get("roomAmenities"),
		"custom_number_of_adults"           : data.get("numberOfAdults"),
		"custom_number_of_child"            : data.get("numberOfChild"),
		"custom_number_of_rooms"            : data.get("numberOfRooms"),
		"custom_pms_total"                  : data.get("pmsTotal"),
		"custom_pms_tax"                    : data.get("pmsTax"),
		"custom_room_type"                  : data.get("roomType"),
		"custom_booking_type"               : data.get("bookingType"),
		"custom_order_status"               : data.get("orderStatus"),
		"custom_order_source"               : data.get("orderSource"),
		"custom_booker_first_name"          : data.get("bookerFirstName"),
		"custom_booker_last_name"           : data.get("bookerLastName"),
		"custom_booker_email"               : data.get("bookerEmail"),
		"custom_booker_mobile_number"       : data.get("bookerMobileNo"),
		"custom_booker_address"             : data.get("bookerAddress"),
		"custom_booker_country"             : data.get("bookerCountry"),
		"custom_booker_city"                : data.get("bookerCity"),
		"custom_booker_state"               : data.get("bookerState"),
		"custom_booker_zip_code"            : data.get("bookerZip"),
		"custom_guest_first_name"           : data.get("guestFirstName"),
		"custom_guest_last_name"            : data.get("guestLastName"),
		"custom_guest_email"                : data.get("guestEmail"),
		"custom_guest_mobile_number"        : data.get("guestMobileNo"),
		"custom_guest_address"              : data.get("address"),
		"custom_pms_addon_description"      : data.get("pmsAddonsDescription"),
		"custom_guest_status"               : data.get("guestStatus"),
		"custom_departing_flight"           : data.get("departingFlight"),
		"custom_arrival_flight"             : data.get("arrivalFlight"),
		"custom_estimated_arrival"          : data.get("estimatedArrival"),
		"custom_estimated_departure"        : data.get("estimatedDeparture"),
		"custom_transit_details"            : data.get("transitDetails"),
		"custom_guest_preferences"          : data.get("guestPreferences"),
		"custom_reservation_comments"       : data.get("reservationComments"),
		"custom_cashier_comments"           : data.get("cashierComments"),
		"custom_billing_instructions"       : data.get("billingInstructions"),
		"custom_reservation_booking_status" : data.get("reservationBookingStatus"),
		"custom_market_segment"             : data.get("marketSegment"),
		"disable_rounded_total"             : True,
		"cost_center"                       : api_ctx.cost_center,
		"items"                             : [],
		"payment_terms_template"            : payment_term,
		"custom_paymaster"                  : data.get("paymasterName"),
		"custom_isgroupbooking"             : 1 if data.get("isGroupBooking") else 0,
	}

	if data.get("bookingType") == "tpaBooking":
		sales_order_fields["custom_ota_id"] = data.get("travelAgencyCode")

	# ── Resolve items dynamically ──
	so_items = []
	for idx, item in enumerate(items, start=1):
		item_code = resolve_item_code(
			item,
			endpoint_name="Reservation",
			item_index=idx,
			folio_no=api_ctx.folio_no,
			booking_id=api_ctx.booking_id,
		)

		if not frappe.db.exists("Item", item_code):
			raise ValueError(
				f"Item #{idx}: ERP item_code '{item_code}' does not exist in ERPNext."
			)

		so_items.append({
			"item_code"           : item_code,
			"qty"                 : item.get("quantity", 0),
			"rate"                : item.get("net", 0),
			"custom_service_date" : item.get("date"),
		})

	sales_order_fields["items"] = so_items
	return sales_order_fields


# ==============================================================================
# Main Endpoint
# ==============================================================================

@frappe.whitelist(allow_guest=True)
def create_sales_order():
	"""
	Main entry point for Sales Order creation API.
	All configurations fetched dynamically from Hotel Configuration DocType.
	"""
	api    = ReservationAPI()
	logger = APILogger("Reservation", "create_sales_order")

	logger.log_request(
		payload    = frappe.request.data or frappe.form_dict,
		folio_no   = api.folio_no,
		booking_id = api.booking_id
	)

	response_data = {
		"booking_id": api.booking_id,
		"folio_no"  : api.folio_no,
		"status"    : "failure"
	}

	try:
		# 1. Validate & load configuration
		api.validate()
		api.load_company_context()  # Fetches Hotel Configuration DocType

		# 2. Reject unknown OTA
		booking_type = api.data.get("bookingType")
		tpa_code     = api.data.get("travelAgencyCode") or "UNKNOWN_OTA"
		if booking_type == "tpaBooking" and tpa_code == "UNKNOWN_OTA":
			raise ValueError("Unknown OTA. Cannot process reservation with unknown travel agency.")

		# 3. Parse items
		items_data = parse_items(api.data.get("items"))

		# 4. Get sales taxes (dynamic from Hotel Configuration)
		sales_taxes = get_sales_taxes(api.company_name, api.config)

		# 5. Get or create customer (dynamic defaults)
		customer_id, gst_category = get_or_create_customer(api)

		# 6. Process Purchase Invoice (dynamic commission)
		process_purchase_invoice(api)

		# 7. Prepare Sales Order fields (dynamic item mapping + defaults)
		so_fields = prepare_sales_order_fields(api, customer_id, gst_category, items_data, sales_taxes)

		# 8. Create or update Sales Order
		existing_so = frappe.db.get_value(
			"Sales Order",
			{"custom_booking_id": api.booking_id, "custom_folio_no": api.folio_no},
			["name", "docstatus"],
			as_dict=True
		)

		if existing_so:
			if existing_so.docstatus == 1:
				raise frappe.ValidationError(
					f"Sales Order '{existing_so.name}' is already submitted. Cannot update a submitted document."
				)
			elif existing_so.docstatus == 0:
				so_doc = frappe.get_doc("Sales Order", existing_so.name)
				so_doc.update(so_fields)
				so_doc.items = []
				for item in so_fields["items"]:
					so_doc.append("items", item)
				so_doc.payment_schedule = []
				so_doc.save(ignore_permissions=True)
				message = f"Sales Order '{so_doc.name}' updated successfully."
			elif existing_so.docstatus == 2:
				so_fields["doctype"] = "Sales Order"
				so_doc = frappe.get_doc(so_fields)
				so_doc.payment_schedule = []
				so_doc.insert(ignore_permissions=True)
				message = f"Previous Sales Order was cancelled. New Sales Order '{so_doc.name}' created successfully."
		else:
			so_fields["doctype"] = "Sales Order"
			so_doc = frappe.get_doc(so_fields)
			so_doc.payment_schedule = []
			so_doc.insert(ignore_permissions=True)
			message = f"Sales Order '{so_doc.name}' created successfully."

		response_data["sales_order_name"] = so_doc.name
		response_data["outstanding"]       = so_doc.grand_total

		# 9. Success response
		response_data.update({"status": "success", "message": message, "code": 200})
		frappe.response.http_status_code = 200
		logger.log_success(response_data, status_code=200)
		return response_data

	except ValueError as e:
		frappe.log_error(f"Validation Error: {str(e)}", "Reservation API Validation")
		response_data.update({"error_code": "ERR_VALIDATION", "message": str(e), "title": "Validation Failed", "code": 400})
		frappe.response.http_status_code = 400
		logger.log_error(e, status_code=400, response_data=response_data)
		return response_data

	except frappe.DoesNotExistError as e:
		frappe.log_error(f"Not Found: {str(e)}", "Reservation API Lookup")
		response_data.update({"error_code": "ERR_NOT_FOUND", "message": str(e), "title": "Resource Not Found", "code": 404})
		frappe.response.http_status_code = 404
		logger.log_error(e, status_code=404, response_data=response_data)
		return response_data

	except Exception as e:
		frappe.log_error(f"System Error: {str(e)}", "Reservation API System")
		response_data.update({"error_code": "ERR_SYSTEM", "message": str(e), "title": "System Error", "code": 500})
		frappe.response.http_status_code = 500
		logger.log_error(e, status_code=500, response_data=response_data)
		return response_data
