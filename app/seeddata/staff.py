"""Fictional staff personas. Emails use the reserved example.invalid domain."""

PLATFORM_ADMIN = {
    "employee_code": "POS-ADMIN-01",
    "display_name": "POS Platform Admin",
    "email": "platform.admin@example.invalid",
}

# branch code, employee code, display name, email, role
STAFF = {
    "lahore-grill-house": [
        ("JT", "LGH-MGR-JT", "Sana Iftikhar", "lgh.mgr.jt@example.invalid", "manager"),
        ("DHA", "LGH-MGR-DHA", "Omar Farooqi", "lgh.mgr.dha@example.invalid", "manager"),
        ("JT", "LGH-CSH-JT", "Hiba Nadeem", "lgh.csh.jt@example.invalid", "cashier"),
        ("DHA", "LGH-CSH-DHA", "Daniyal Qazi", "lgh.csh.dha@example.invalid", "cashier"),
        ("JT", "LGH-KIT-JT", "Rashid Mehmood", "lgh.kit.jt@example.invalid", "kitchen"),
        ("DHA", "LGH-KIT-DHA", "Kamran Siddiqui", "lgh.kit.dha@example.invalid", "kitchen"),
        ("", "LGH-INV-01", "Nadia Saleem", "lgh.inv.01@example.invalid", "inventory"),
    ],
    "urban-bites-lahore": [
        ("GUL", "UBL-MGR-GUL", "Maham Riaz", "ubl.mgr.gul@example.invalid", "manager"),
        ("MT", "UBL-MGR-MT", "Faraz Chaudhry", "ubl.mgr.mt@example.invalid", "manager"),
        ("GUL", "UBL-CSH-GUL", "Ayesha Noor", "ubl.csh.gul@example.invalid", "cashier"),
        ("MT", "UBL-CSH-MT", "Hamza Javed", "ubl.csh.mt@example.invalid", "cashier"),
        ("GUL", "UBL-KIT-GUL", "Bilal Hussain", "ubl.kit.gul@example.invalid", "kitchen"),
        ("MT", "UBL-KIT-MT", "Saad Iqbal", "ubl.kit.mt@example.invalid", "kitchen"),
        ("", "UBL-INV-01", "Rabia Yousaf", "ubl.inv.01@example.invalid", "inventory"),
    ],
    "daily-mart-lahore": [
        ("WT", "DML-MGR-WT", "Tariq Mahmood", "dml.mgr.wt@example.invalid", "manager"),
        ("FT", "DML-MGR-FT", "Saima Khalid", "dml.mgr.ft@example.invalid", "manager"),
        ("WT", "DML-CSH-WT", "Usman Ghani", "dml.csh.wt@example.invalid", "cashier"),
        ("FT", "DML-CSH-FT", "Laiba Asif", "dml.csh.ft@example.invalid", "cashier"),
        ("", "DML-INV-01", "Haris Naeem", "dml.inv.01@example.invalid", "inventory"),
    ],
}

OWNER_CODES = {
    "lahore-grill-house": "LGH-OWN-01",
    "urban-bites-lahore": "UBL-OWN-01",
    "daily-mart-lahore": "DML-OWN-01",
}
