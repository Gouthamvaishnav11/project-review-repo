import frappe

def make_test():
    COMPANY  = "THE ECO SATVA - KOTA"
    DEFERRED = "Deferred Room Rev - IN000004"
    INCOME   = "410001 - Direct - Walk-In Customers - IN000004"
    AR_ACC   = "162600 - WalkIn- Trade Receivables - IN000004"
    CUSTOMER = "Walk-in Customer"

    # Create a Sales Invoice
    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": CUSTOMER,
        "company": COMPANY,
        "debit_to": AR_ACC,
        "due_date": "2026-03-01",
        "items": [{
            "item_code": "FO1002",
            "qty": 1,
            "rate": 100,
            "income_account": INCOME,
        }],
        "disable_rounded_total": True
    })
    si.insert(ignore_permissions=True)
    si.submit()
    print("SINV Created:", si.name, "Outstanding:", si.outstanding_amount)

    # Create JE linked to the Sales Invoice
    try:
        je = frappe.new_doc("Journal Entry")
        je.company = COMPANY
        je.voucher_type = "Journal Entry"
        je.posting_date = "2026-02-23"
        je.append("accounts", {
            "account": DEFERRED, 
            "debit_in_account_currency": 50, 
            "credit_in_account_currency": 0,
            "reference_type": "Sales Invoice",
            "reference_name": si.name
        })
        je.append("accounts", {
            "account": INCOME,   
            "debit_in_account_currency": 0,   
            "credit_in_account_currency": 50,
            "reference_type": "Sales Invoice",
            "reference_name": si.name
        })
        je.flags.ignore_mandatory = True
        je.save(ignore_permissions=True)
        je.submit()
        print("JE Created:", je.name)
    except Exception as e:
        print("Error submitting JE:", str(e))

    # Reload SI and check status
    si = frappe.get_doc("Sales Invoice", si.name)
    print("SINV After JE:", si.name, "Status:", si.status, "Outstanding:", si.outstanding_amount)

make_test()
