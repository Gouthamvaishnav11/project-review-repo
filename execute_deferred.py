import frappe

def create_entry():
    # Preconditions
    frappe.db.sql("""
        INSERT IGNORE INTO `tabAccount`
          (name, account_name, account_type, root_type, parent_account, company, is_group,
           lft, rgt, creation, modified, modified_by, owner, docstatus)
        SELECT 'Deferred Room Rev - IN000004','Deferred Room Rev','Current Liability','Liability',
          '287000 - Other current liabilities - IN000004','THE ECO SATVA - KOTA',0,rgt,rgt+1,
          NOW(),NOW(),'Administrator','Administrator',0
        FROM `tabAccount` WHERE name='287000 - Other current liabilities - IN000004'
    """)
    frappe.db.commit()

    frappe.db.set_value("Accounts Settings", None, "book_deferred_entries_via_journal_entry", 1)
    frappe.db.set_value("Accounts Settings", None, "submit_journal_entries", 0)
    frappe.db.commit()

    # Step 1
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
        "posting_date": "2026-02-20",
        "due_date": "2026-02-23",
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
                "service_start_date": "2026-02-20",
                "service_end_date": "2026-02-20",
                "enable_deferred_revenue": 1,
            },
            {
                "item_code": "FO1002",
                "qty": 1,
                "rate": 450,
                "income_account": INCOME,
                "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-02-21",
                "service_end_date": "2026-02-21",
                "enable_deferred_revenue": 1,
            },
            {
                "item_code": "FO1002",
                "qty": 1,
                "rate": 600,
                "income_account": INCOME,
                "deferred_revenue_account": DEFERRED,
                "service_start_date": "2026-02-22",
                "service_end_date": "2026-02-22",
                "enable_deferred_revenue": 1,
            }
        ],
    })
    si.insert(ignore_permissions=True)
    frappe.db.commit()
    print("SINV:", si.name)

    # Step 2
    CC = "Main - IN000004"
    nights = [
        ("2026-02-20", 300,  "Friday Night"),
        ("2026-02-21", 450,  "Saturday Night"),
        ("2026-02-22", 600,  "Sunday Night"),
    ]

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
        frappe.db.commit()
        print(f"{label} JE: {je.name} | submitted")

    # Step 3
    si = frappe.get_doc("Sales Invoice", si.name)
    si.submit()
    frappe.db.commit()
    print("Status:", si.status, "| Outstanding:", si.outstanding_amount)

    # Step 4
    BANK_ACC = "163113 - Hdfc Bank Limited -57500001594753-KOTA - IN000004"
    pay_amt = si.outstanding_amount

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type    = "Receive"
    pe.posting_date    = "2026-02-23"
    pe.company         = COMPANY
    pe.party_type      = "Customer"
    pe.party           = CUSTOMER
    pe.paid_from       = AR_ACC
    pe.paid_to         = BANK_ACC
    pe.paid_amount     = pay_amt
    pe.received_amount = pay_amt
    pe.reference_no    = "CASH_DEFERRED_RUNBOOK"
    pe.reference_date  = "2026-02-23"
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.append("references", {
        "reference_doctype": "Sales Invoice",
        "reference_name": si.name,
        "allocated_amount": pay_amt,
        "outstanding_amount": pay_amt,
        "total_amount": si.grand_total,
    })
    pe.save(ignore_permissions=True)
    pe.submit()
    frappe.db.commit()
    print("PE:", pe.name, "| Paid:", pe.paid_amount)
