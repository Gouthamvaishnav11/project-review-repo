import frappe
from frappe import _
from frappe.utils import cint, flt
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.accounts_controller import (
	get_advance_journal_entries,
	get_advance_payment_entries_for_regional,
)
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_dimensions
from erpnext.accounts.party import get_party_account


class CustomSalesInvoice(SalesInvoice):
	"""
	Custom Sales Invoice class that overrides advance allocation logic
	to filter advances based on folio number matching with Sales Orders.
	"""

	def get_advance_entries(self, include_unallocated=True):
		"""
		Override the core get_advance_entries method to match Payment Entries
		based on custom_folio_number and custom_booking_id.
		
		Logic:
		- If custom_folio_number and custom_booking_id are set on the Sales Invoice:
		  - Find Payment Entries where custom_folio_number and custom_booking_id match
		  - Ignore Sales Order relationships completely
		  - Only return matching Payment Entries
		- If these fields are not set:
		  - Fall back to standard ERPNext behavior
		"""
		
		# Get custom folio number and booking ID from Sales Invoice
		folio_number = self.get("custom_folio_number")
		booking_id = self.get("custom_booking_id")
		
		# If no folio number or booking ID is set, use standard behavior
		if not folio_number or not booking_id:
			return super().get_advance_entries(include_unallocated=include_unallocated)

		# Get Payment Entries matching folio number and booking ID
		return self._get_payment_entries_by_folio_and_booking(folio_number, booking_id)
	
	def _get_payment_entries_by_folio_and_booking(self, folio_number, booking_id):
		"""
		Find Payment Entries that match custom_booking_id AND (custom_folio_number OR custom_paymaster_reference child table).
		
		This method handles two scenarios:
		1. Unallocated Payment Entries (PE.unallocated_amount > 0)
		2. Payment Entries allocated to Sales Orders (which can be transferred to SI)
		
		For SO allocations, we provide the reference_row (voucher_detail_no) so ERPNext's
		check_if_advance_entry_modified validates correctly.
		"""
		result = []
		sales_order_name = frappe.db.get_value(
			"Sales Order",
			{"custom_booking_id": booking_id, "custom_folio_no": folio_number},
			"name",
		)

		# Dynamically get the child table name for custom_paymaster_reference
		# try-except block to handle cases where field might not exist yet during migration/setup
		try:
			paymaster_child_doctype = frappe.get_meta("Payment Entry").get_field("custom_paymaster_reference").options
			paymaster_table = f"`tab{paymaster_child_doctype}`"
			
			# Flag to know if we should join
			use_paymaster_logic = True
		except Exception:
			use_paymaster_logic = False
			paymaster_table = ""

		# Base Query Parts
		# We use DISTINCT because a PE might be matched via both header and child table (unlikely but safe)
		
		# ---------------------------------------------------------
		# 1. Allocated to Sales Order
		# ---------------------------------------------------------
		
		if use_paymaster_logic:
			sql_so = f"""
				SELECT DISTINCT
					pe.name as pe_name,
					pe.posting_date,
					pe.paid_amount,
					pe.remarks,
					pe.paid_from as account,
					pm.allocated_amount as pm_allocated_amount,
					pref.name as ref_row_name,
					pref.allocated_amount,
					pref.reference_name as sales_order
				FROM
					`tabPayment Entry` pe
				INNER JOIN
					`tabPayment Entry Reference` pref ON pref.parent = pe.name
				LEFT JOIN
					{paymaster_table} pm ON pm.parent = pe.name
					AND pm.folio_no = %(folio_number)s
				WHERE
					pe.docstatus = 1
					AND pe.payment_type = 'Receive'
					AND pe.party_type = 'Customer'
					AND pe.party = %(customer)s
					AND pe.company = %(company)s
					AND pe.custom_api_pms_folio = 1
					AND (
						pe.custom_folio_number = %(folio_number)s 
						OR pm.folio_no = %(folio_number)s
					)
					AND pe.custom_booking_id = %(booking_id)s
					AND pref.reference_doctype = 'Sales Order'
					AND pref.reference_name = %(sales_order_name)s
					AND pref.docstatus = 1
				ORDER BY
					pe.posting_date
			"""
		else:
			# Fallback if field doesn't exist
			sql_so = """
				SELECT
					pe.name as pe_name,
					pe.posting_date,
					pe.paid_amount,
					pe.remarks,
					pe.paid_from as account,
					pref.name as ref_row_name,
					pref.allocated_amount,
					pref.reference_name as sales_order
				FROM
					`tabPayment Entry` pe
				INNER JOIN
					`tabPayment Entry Reference` pref ON pref.parent = pe.name
				WHERE
					pe.docstatus = 1
					AND pe.payment_type = 'Receive'
					AND pe.party_type = 'Customer'
					AND pe.party = %(customer)s
					AND pe.company = %(company)s
					AND pe.custom_api_pms_folio = 1
					AND pe.custom_folio_number = %(folio_number)s
					AND pe.custom_booking_id = %(booking_id)s
					AND pref.reference_doctype = 'Sales Order'
					AND pref.reference_name = %(sales_order_name)s
					AND pref.docstatus = 1
				ORDER BY
					pe.posting_date
			"""

		so_allocated_entries = frappe.db.sql(
			sql_so,
			{
				"customer": self.customer,
				"company": self.company,
				"folio_number": folio_number,
				"booking_id": booking_id,
				"sales_order_name": sales_order_name,
			},
			as_dict=True,
		)
		
		# Add Sales Order allocated entries with their reference row
		for entry in so_allocated_entries:
			result.append(frappe._dict({
				"reference_type": "Payment Entry",
				"reference_name": entry.pe_name,
				"reference_row": entry.ref_row_name,  # This is key - voucher_detail_no
				"remarks": entry.remarks or "",
				"amount": entry.get("pm_allocated_amount") if flt(entry.get("pm_allocated_amount")) > 0 else entry.allocated_amount,
				"exchange_rate": 1,
				"paid_from": entry.account,
				"paid_to": None,
			}))
		
		# ---------------------------------------------------------
		# 2. Unallocated Entries
		# ---------------------------------------------------------
		
		if use_paymaster_logic:
			sql_unallocated = f"""
				SELECT DISTINCT
					pe.name,
					pe.posting_date,
					pe.unallocated_amount,
					pe.remarks,
					pe.paid_from as account,
					pm.allocated_amount as pm_allocated_amount,
					(SELECT SUM(allocated_amount) FROM {paymaster_table} WHERE parent = pe.name) as total_pm_allocated,
					-- We MUST return the full unallocated_amount as amount,
					-- so that Frappe's check_if_advance_entry_modified validation passes.
					-- We return the per-folio allocation separately.
					pe.unallocated_amount as advance_amount
				FROM
					`tabPayment Entry` pe
				LEFT JOIN
					{paymaster_table} pm ON pm.parent = pe.name
					AND pm.folio_no = %(folio_number)s
				WHERE
					pe.docstatus = 1
					AND pe.payment_type = 'Receive'
					AND pe.party_type = 'Customer'
					AND pe.party = %(customer)s
					AND pe.company = %(company)s
					AND pe.custom_api_pms_folio = 1
					AND (
						pe.custom_folio_number = %(folio_number)s 
						OR pm.folio_no = %(folio_number)s
					)
					AND pe.custom_booking_id = %(booking_id)s
					AND pe.unallocated_amount > 0
				ORDER BY
					pe.posting_date
			"""
		else:
			sql_unallocated = """
				SELECT
					pe.name,
					pe.posting_date,
					pe.unallocated_amount,
					pe.remarks,
					pe.paid_from as account
				FROM
					`tabPayment Entry` pe
				WHERE
					pe.docstatus = 1
					AND pe.payment_type = 'Receive'
					AND pe.party_type = 'Customer'
					AND pe.party = %(customer)s
					AND pe.company = %(company)s
					AND pe.custom_api_pms_folio = 1
					AND pe.custom_folio_number = %(folio_number)s
					AND pe.custom_booking_id = %(booking_id)s
					AND pe.unallocated_amount > 0
				ORDER BY
					pe.posting_date
			"""

		unallocated_entries = frappe.db.sql(
			sql_unallocated,
			{
				"customer": self.customer,
				"company": self.company,
				"folio_number": folio_number,
				"booking_id": booking_id,
			},
			as_dict=True,
		)
		
		for entry in unallocated_entries:
			result.append(frappe._dict({
				"reference_type": "Payment Entry",
				"reference_name": entry.name,
				"reference_row": None,
				"remarks": entry.remarks or "",
				"amount": entry.unallocated_amount,   # MUST be exactly unallocated_amount for validation
				"pm_allocated_amount": entry.get("pm_allocated_amount"), # Store for set_advances
				"total_pm_allocated": entry.get("total_pm_allocated", 0), # To detect legacy vs explicit mode
				"exchange_rate": 1,
				"paid_from": entry.account,
				"paid_to": None,
			}))
		
		return result

	@frappe.whitelist()
	def set_advances(self):
		"""
		Override set_advances to respect the per-folio pm_allocated_amount.
		We must put the full 'amount' into `advance_amount` for Frappe's validation,
		but we cap the `allocated_amount` to the child row's limit.
		"""
		res = self.get_advance_entries(
			include_unallocated=not cint(self.get("only_include_allocated_payments"))
		)

		self.set("advances", [])

		advance_allocated = 0
		if self.docstatus == 1 and flt(self.outstanding_amount) > 0:
			invoice_total = flt(self.outstanding_amount)
		elif self.get("party_account_currency") == self.company_currency:
			invoice_total = self.get("base_rounded_total") or self.base_grand_total
		else:
			invoice_total = self.get("rounded_total") or self.grand_total

		# Checkout uses this to allocate advances only up to the "net collectible"
		# (e.g. grand_total - commission). This avoids mutating submitted invoices.
		limit = None
		try:
			limit = self.flags.get("advance_allocation_limit")
		except Exception:
			limit = None
		if limit is not None:
			invoice_total = min(flt(invoice_total), max(0.0, flt(limit)))

		for d in res:
			available_for_this_folio = d.amount

			# If the PayMaster entry has ANY explicit allocations across its children,
			# then we operate in Strict Explicit Mode, restricting by this folio's share.
			# Otherwise (legacy mode or 0 sum), we let it allocate greedily.
			if flt(d.get("total_pm_allocated")) > 0:
				available_for_this_folio = min(d.amount, flt(d.get("pm_allocated_amount")))

			# We can't exceed what's left on the invoice
			remaining_on_invoice = invoice_total - advance_allocated
			
			allocated_amount = min(remaining_on_invoice, available_for_this_folio)
			
			# Filter out rows that resolve to 0 allocation unless they are meant to be added
			if allocated_amount <= 0:
				continue

			advance_allocated += flt(allocated_amount)

			advance_row = {
				"doctype": self.doctype + " Advance",
				"reference_type": d.reference_type,
				"reference_name": d.reference_name,
				"reference_row": d.reference_row,
				"remarks": d.remarks,
				"advance_amount": flt(d.amount), # MUST be full unallocated amount for ERPNext validation
				"allocated_amount": allocated_amount,
				"ref_exchange_rate": flt(d.exchange_rate),
				"difference_posting_date": self.posting_date,
			}
			if d.get("paid_from"):
				advance_row["account"] = d.paid_from
			if d.get("paid_to"):
				advance_row["account"] = d.paid_to

			self.append("advances", advance_row)

	def _get_live_payment_entry_advance_amount(self, advance):
		"""Return the current PE availability used by ERPNext's advance validation."""
		pe_name = advance.get("reference_name")
		if not pe_name:
			return flt(advance.get("advance_amount"))

		reference_row = advance.get("reference_row")
		if reference_row:
			rows = frappe.db.sql(
				"""
				SELECT pref.allocated_amount, pref.reference_doctype
				FROM `tabPayment Entry` pe
				INNER JOIN `tabPayment Entry Reference` pref ON pref.parent = pe.name
				WHERE pe.name = %s
				  AND pe.docstatus = 1
				  AND pe.party_type = %s
				  AND pe.party = %s
				  AND pref.name = %s
				  AND pref.reference_doctype IN ('', 'Sales Order', 'Purchase Order')
				FOR UPDATE
				""",
				(pe_name, "Customer", self.customer, reference_row),
				as_dict=True,
			)
			if not rows:
				frappe.throw(
					_(
						"Payment Entry {0} reference row {1} is no longer available as an advance for Sales Invoice {2}."
					).format(pe_name, reference_row, self.name)
				)
			return rows[0].allocated_amount

		rows = frappe.db.sql(
			"""
			SELECT unallocated_amount
			FROM `tabPayment Entry`
			WHERE name = %s
			  AND docstatus = 1
			  AND party_type = %s
			  AND party = %s
			FOR UPDATE
			""",
			(pe_name, "Customer", self.customer),
			as_dict=True,
		)
		if not rows:
			frappe.throw(
				_("Payment Entry {0} is no longer available as an advance for Sales Invoice {1}.").format(
					pe_name, self.name
				)
			)
		return rows[0].unallocated_amount

	def update_against_document_in_jv(self):
		"""Link invoice advances using live Payment Entry availability at submit time.

		Core ERPNext validates a PE advance by comparing SI Advance.advance_amount
		with the current PE unallocated/reference-row amount. PMS allocation updates
		can leave the draft SI row stale, so refresh that value while building the
		reconciliation args instead of changing the payment flow.
		"""
		if self.doctype != "Sales Invoice":
			return super().update_against_document_in_jv()

		party_type = "Customer"
		party = self.customer
		party_account = self.debit_to
		dr_or_cr = "credit_in_account_currency"

		lst = []
		for d in self.get("advances"):
			if flt(d.allocated_amount) <= 0:
				continue

			live_advance_amount = flt(d.advance_amount)
			if d.reference_type == "Payment Entry":
				live_advance_amount = self._get_live_payment_entry_advance_amount(d)
				d.advance_amount = flt(live_advance_amount)

				precision = d.precision("allocated_amount")
				if flt(d.allocated_amount, precision) > flt(live_advance_amount, precision):
					frappe.throw(
						_(
							"Payment Entry {0} has only {1} available, but Sales Invoice {2} is trying to allocate {3}."
						).format(d.reference_name, live_advance_amount, self.name, d.allocated_amount)
					)

			args = frappe._dict(
				{
					"voucher_type": d.reference_type,
					"voucher_no": d.reference_name,
					"voucher_detail_no": d.reference_row,
					"against_voucher_type": self.doctype,
					"against_voucher": self.name,
					"account": party_account,
					"party_type": party_type,
					"party": party,
					"is_advance": "Yes",
					"dr_or_cr": dr_or_cr,
					"unadjusted_amount": live_advance_amount,
					"allocated_amount": flt(d.allocated_amount),
					"precision": d.precision("advance_amount"),
					"exchange_rate": (
						self.conversion_rate
						if self.party_account_currency != self.company_currency
						else 1
					),
					"grand_total": (
						self.base_grand_total
						if self.party_account_currency == self.company_currency
						else self.grand_total
					),
					"outstanding_amount": self.outstanding_amount,
					"difference_account": frappe.get_cached_value(
						"Company", self.company, "exchange_gain_loss_account"
					),
					"exchange_gain_loss": flt(d.get("exchange_gain_loss")),
					"difference_posting_date": d.get("difference_posting_date"),
				}
			)
			lst.append(args)

		if lst:
			from erpnext.accounts.utils import reconcile_against_document

			active_dimensions = get_dimensions()[0]
			for x in lst:
				for dim in active_dimensions:
					if self.get(dim.fieldname):
						x.update({dim.fieldname: self.get(dim.fieldname)})
			reconcile_against_document(lst, active_dimensions=active_dimensions)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_sales_invoice_pdf():
	"""API endpoint to get Sales Invoice PDF by custom_folio_number"""
	try:
		# Get custom_folio_number from request body
		if not hasattr(frappe.local, 'form_dict'):
			frappe.local.form_dict = frappe.form_dict

		custom_folio_number = frappe.local.form_dict.get('custom_folio_number')

		if not custom_folio_number:
			frappe.throw(_("custom_folio_number is required"), frappe.MandatoryError)

		# Query Sales Invoice by custom_folio_number
		sales_invoices = frappe.get_all(
			"Sales Invoice",
			filters={"custom_folio_number": custom_folio_number, "docstatus": 1},
			fields=["name", "customer", "company"]
		)

		if not sales_invoices:
			frappe.throw(_("No Sales Invoice found with custom_folio_number: {0}").format(custom_folio_number))

		if len(sales_invoices) > 1:
			frappe.throw(_("Multiple Sales Invoices found with custom_folio_number: {0}").format(custom_folio_number))

		sales_invoice = sales_invoices[0]

		# Get the Sales Invoice document
		doc = frappe.get_doc("Sales Invoice", sales_invoice.name)

		# Generate PDF using ERPNext's print functionality
		print_format = "Sales Invoice Print Template"

		# Check if the print format exists
		if not frappe.db.exists("Print Format", print_format):
			frappe.throw(_("Print Format '{0}' not found").format(print_format))

		pdf_file = frappe.get_print(
			"Sales Invoice",
			doc.name,
			print_format,
			doc=doc,
			as_pdf=True
		)

		# Set response headers and content
		frappe.local.response.filename = f"Sales_Invoice_{custom_folio_number}.pdf"
		frappe.local.response.filecontent = pdf_file
		frappe.local.response.type = "pdf"

		return pdf_file

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Sales Invoice PDF Generation Error")
		frappe.throw(_("Error generating PDF: {0}").format(str(e)))
# Copyright (c) 2025, ecohotels and contributors
# For license information, please see license.txt
