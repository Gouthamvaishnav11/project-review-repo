import json

import frappe
from frappe import _

from .logger import APILogger


def _get_request_data():
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


def _validate_payload(data):
    required = ["bookingId", "folioNo"]
    missing = [field for field in required if not data.get(field)]
    if missing:
        frappe.throw(
            _("Missing required fields: {0}").format(", ".join(missing)),
            exc=frappe.ValidationError,
        )

    # Validate that status is provided as "Cancel" (case-insensitive)
    status_fields = [
        "status",
        "orderStatus",
        "invoiceorderStatus",
        "guestStatus",
        "reservationBookingStatus",
        "invoiceguestStatus",
        "invoicereservationBookingStatus"
    ]
    
    has_cancel_status = False
    provided_status = None
    for field in status_fields:
        val = data.get(field)
        if val:
            provided_status = val
            if str(val).strip().lower() in ["cancel", "cancelled", "cancellation"]:
                has_cancel_status = True
                break

    if not has_cancel_status:
        frappe.throw(
            _("Invalid status. Cancellation API expects status to be 'Cancel'. Provided status: '{0}'").format(provided_status or "None"),
            exc=frappe.ValidationError,
        )


def _submit_if_draft(doc):
    if doc.docstatus == 0:
        doc.submit()


def _cancel_doc(doctype, name, cancelled, submitted_before_cancel):
    doc = frappe.get_doc(doctype, name)

    if doc.docstatus == 2:
        return

    was_draft = doc.docstatus == 0
    if was_draft:
        _submit_if_draft(doc)
        submitted_before_cancel.append(name)

    doc.cancel()
    cancelled.append(name)


def _get_names(doctype, filters):
    return frappe.get_all(doctype, filters=filters, pluck="name")


@frappe.whitelist(allow_guest=False)
def cancel_reservation_checkin(payload=None):
    """
    Cancel reservation/checkin flow by bookingId + folioNo.

    Cancellation order:
    1. Payment Entry
    2. Sales Invoice
    3. Sales Order

    Draft documents are submitted first, then cancelled.
    """
    data = payload or _get_request_data()
    booking_id = data.get("bookingId")
    folio_no = data.get("folioNo")

    logger = APILogger("Cancellation", "cancel_reservation_checkin")
    logger.log_request(payload=data, folio_no=folio_no, booking_id=booking_id)

    response_data = {
        "status": "failure",
        "booking_id": booking_id,
        "folio_no": folio_no,
        "cancelled": {
            "payment_entries": [],
            "sales_invoices": [],
            "purchase_invoices": [],
            "sales_orders": [],
        },
        "submitted_before_cancel": {
            "payment_entries": [],
            "sales_invoices": [],
            "purchase_invoices": [],
            "sales_orders": [],
        },
    }

    try:
        _validate_payload(data)

        sales_order_names = _get_names(
            "Sales Order",
            {
                "custom_folio_no": folio_no,
                "custom_booking_id": booking_id,
                "docstatus": ["!=", 2],
            },
        )

        for so_name in sales_order_names:
            _cancel_doc(
                "Sales Order",
                so_name,
                response_data["cancelled"]["sales_orders"],
                response_data["submitted_before_cancel"]["sales_orders"],
            )

        total_cancelled = len(response_data["cancelled"]["sales_orders"])

        if total_cancelled == 0:
            response_data.update(
                {
                    "status": "success",
                    "message": "No active Sales Order found for the provided folioNo and bookingId.",
                    "code": 200,
                }
            )
        else:
            response_data.update(
                {
                    "status": "success",
                    "message": "Cancellation completed successfully.",
                    "code": 200,
                }
            )

        frappe.db.commit()
        frappe.response.http_status_code = 200
        logger.log_success(response_data, status_code=200)
        return response_data

    except (ValueError, frappe.ValidationError) as e:
        frappe.db.rollback()
        msg = str(e)
        if hasattr(e, "message"):
            msg = e.message
        elif isinstance(e, tuple) and len(e) > 0:
            msg = e[0]
            
        frappe.log_error(f"Validation Error: {msg}", "Cancellation API Validation")
        response_data.update(
            {
                "error_code": "ERR_VALIDATION",
                "message": msg,
                "title": "Validation Failed",
                "code": 400,
            }
        )
        frappe.response.http_status_code = 400
        logger.log_error(e, status_code=400, response_data=response_data)
        return response_data

    except frappe.DoesNotExistError as e:
        frappe.db.rollback()
        frappe.log_error(f"Not Found Error: {str(e)}", "Cancellation API Lookup")
        response_data.update(
            {
                "error_code": "ERR_NOT_FOUND",
                "message": str(e),
                "title": "Resource Not Found",
                "code": 404,
            }
        )
        frappe.response.http_status_code = 404
        logger.log_error(e, status_code=404, response_data=response_data)
        return response_data

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"System Error: {str(e)}", "Cancellation API System")
        response_data.update(
            {
                "error_code": "ERR_SYSTEM",
                "message": str(e),
                "title": "System Error",
                "code": 500,
            }
        )
        frappe.response.http_status_code = 500
        logger.log_error(e, status_code=500, response_data=response_data)
        return response_data
