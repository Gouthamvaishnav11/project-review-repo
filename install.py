import frappe

INDEXES = {
    "tabSales Invoice": [
        ["idx_si_custom_folio", "custom_folio_number"],
        ["idx_si_custom_booking", "custom_booking_id"],
    ],
    "tabSales Order": [
        ["idx_so_custom_booking", "custom_booking_id"],
        ["idx_so_custom_folio", "custom_folio_no"],
    ],
    "tabPayment Entry": [
        ["idx_pe_reference_no", "reference_no"],
        ["idx_pe_custom_folio", "custom_folio_number"],
        ["idx_pe_custom_booking", "custom_booking_id"],
    ],
    "tabJournal Entry": [
        ["idx_je_docstatus_company", "docstatus, company"],
    ],
    "tabJournal Entry Account": [
        ["idx_jea_parent_party_ref", "parent, reference_type, reference_name"],
    ],
}


def after_migrate():
    """Create missing indexes after migrate."""
    for table, indexes in INDEXES.items():
        for index_name, columns in indexes:
            _create_index_if_not_exists(table, index_name, columns)


def _create_index_if_not_exists(table, index_name, columns):
    """Create index only if it doesn't already exist."""
    try:
        # Check information_schema to avoid duplicating indexes
        existing = frappe.db.sql(
            "SELECT 1 FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s",
            (table, index_name),
        )
        if existing:
            return

        frappe.db.sql(
            f"CREATE INDEX `{index_name}` ON `{table}` ({columns})"
        )
        frappe.log_error(
            title="Ecohotels :: Index Created",
            message=f"Index `{index_name}` on `{table}` ({columns})",
        )
    except Exception as e:
        frappe.log_error(
            title="Ecohotels :: Index Creation Error",
            message=f"Failed to create index `{index_name}` on `{table}` ({columns}): {e}",
        )
