import frappe
from frappe.utils import today, add_months, add_days


@frappe.whitelist()
def create_process_deferred_income(
    company=None,
    start_date=None,
    end_date=None,
    posting_date=None,
    account=None,
):
    """
    Create and submit a Process Deferred Accounting document for Income type.

    Args:
        company (str): Company name. Defaults to default company.
        start_date (str): Start date (YYYY-MM-DD). Defaults to first day of last month.
        end_date (str): End date (YYYY-MM-DD). Defaults to yesterday.
        posting_date (str): Posting date (YYYY-MM-DD). Defaults to today.
        account (str): Optional specific deferred revenue account to filter.
    """
    try:
        if not company:
            company = frappe.defaults.get_defaults().get("company")

        if not posting_date:
            posting_date = today()

        if not start_date:
            start_date = add_months(today(), -1)

        if not end_date:
            end_date = add_days(today(), -1)

        doc = frappe.new_doc("Process Deferred Accounting")
        doc.company = company
        doc.type = "Income"
        doc.posting_date = posting_date
        doc.start_date = start_date
        doc.end_date = end_date

        if account:
            doc.account = account

        doc.insert(ignore_permissions=True)
        doc.submit()
        frappe.db.commit()

        return {
            "status": "success",
            "message": "Process Deferred Accounting created and submitted successfully",
            "name": doc.name,
            "data": {
                "name": doc.name,
                "company": doc.company,
                "type": doc.type,
                "start_date": str(doc.start_date),
                "end_date": str(doc.end_date),
                "posting_date": str(doc.posting_date),
                "account": doc.account,
                "docstatus": doc.docstatus,
            },
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Process Deferred Income Error")
        return {"status": "error", "message": str(e)}
