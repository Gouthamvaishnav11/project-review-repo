import frappe

def create_entry():
    # Step 1: Create Sales Invoice
    COMPANY  = "THE ECO SATVA - KOTA"
    DEFERRED = "Deferred Room Rev - IN000004"
    INCOME   = "410001 - Direct - Walk-In Customers - IN000004"
    AR_ACC   = "162600 - WalkIn- Trade Receivables - IN000004"
    CUSTOMER = "Walk-in Customer"

    sgst = frappe.db.get_value("Account", {"account_number": "294300", "company": COMPANY}, ["name","tax_rate"])
    cgst = frappe.db.get_value("Account", {"account_number": "294001", "company": COMPANY}, ["name","tax_rate"])

    si = frappe.get_doc({
        "doctype": "Sales Invoice",
        "naming_series": "RWAK-.YY.-.#####",
        "customer": CUSTOMER,
        "posting_date": "2026-03-05", # Making it a future date to clearly separate from previous test
        "due_date": "2026-03-08",
        "company": COMPANY,
        "debit_to": AR_ACC,
        "currency": "INR",
        "gst_category": "Unregistered",
        "place_of_supply": "08-Rajasthan",
        "taxes_and_charges": "Output GST In-state - IN000004",
        "cost_center": "Main - IN000004",
        "disable_rounded_total": True,
        "taxes": [
            {"charge_type":"On Net Total","account_head":sgst[0],"rate":sgst[1],"gst_tax_type":"sgst","description":"SGST"},
            {"charge_type":"On Net Total","account_head":cgst[0],"rate":cgst[1],"gst_tax_type":"cgst","description":"CGST"},
        ],
        "items": [
            {
                "item_code": "FO1002",
                "qty": 1,
                "rate": 300,
                "income_account": INCOME,
                "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-03-05",
                "service_end_date": "2026-03-05",
                "enable_deferred_revenue": 1,
            },
            {
                "item_code": "FO1002",
                "qty": 1,
                "rate": 450,
                "income_account": INCOME,
                "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-03-06",
                "service_end_date": "2026-03-06",
                "enable_deferred_revenue": 1,
            },
            {
                "item_code": "FO1002",
                "qty": 1,
                "rate": 600,
                "income_account": INCOME,
                "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-03-07",
                "service_end_date": "2026-03-07",
                "enable_deferred_revenue": 1,
            }
        ],
    })
    si.insert(ignore_permissions=True)
    frappe.db.commit()
    print("SINV Created:", si.name)

    # Step 2: Create Nightly Journal Entries
    CC = "Main - IN000004"
    nights = [
        ("2026-03-05", 300,  "Night 1"),
        ("2026-03-06", 450,  "Night 2"),
        ("2026-03-07", 600,  "Night 3"),
    ]

    je_names = []
    for dt, amt, label in nights:
        je = frappe.new_doc("Journal Entry")
        je.company      = COMPANY
        je.posting_date = dt
        je.voucher_type = "Journal Entry"
        je.user_remark  = f"Nightly Deferred Recognition – {label} | Ref: {si.name}"
        
        je.append("accounts", {"account": DEFERRED, "debit_in_account_currency": amt, "credit_in_account_currency": 0, "cost_center": CC})
        je.append("accounts", {"account": INCOME,   "debit_in_account_currency": 0,   "credit_in_account_currency": amt, "cost_center": CC})
        je.flags.ignore_mandatory = True
        je.save(ignore_permissions=True)
        je.submit()
        je_names.append(je.name)
        frappe.db.commit()
        print(f"{label} JE: {je.name} | submitted")

    # Step 3: Submit Sales Invoice
    si = frappe.get_doc("Sales Invoice", si.name)
    si.submit()
    frappe.db.commit()
    print("Final Status:", si.status, "| Outstanding:", si.outstanding_amount)
    
    # We purposefully do NOT create a payment entry here.
    print(f"\nRun the following query to check the ledger for this invoice:")
    print(f"bench --site development mariadb --execute \"SELECT gl.account, SUM(gl.debit) as total_debit, SUM(gl.credit) as total_credit, SUM(gl.debit) - SUM(gl.credit) as net_balance FROM \\\`tabGL Entry\\\` gl WHERE gl.voucher_no IN ('{si.name}', '{je_names[0]}', '{je_names[1]}', '{je_names[2]}') GROUP BY gl.account ORDER BY gl.account;\"")

