"""Fixed choice lists for the Teller form (dropdowns are mandatory, so typos are impossible)."""

PAYMENT_METHODS = [
    ("CASH", "Cash"),
    ("CDM", "Cash deposit machine (CDM)"),
    ("TRANSFER", "Bank transfer"),
]

RELATIONSHIPS = [
    ("SELF", "Self (sender owns the account)"),
    ("SIBLING", "Sibling"),
    ("PARENT", "Parent"),
    ("SPOUSE", "Spouse"),
    ("CHILD", "Child"),
    ("RELATIVE", "Other relative"),
    ("FRIEND", "Friend"),
    ("EMPLOYER", "Employer"),
    ("OTHER", "Other"),
]
