"""Static organisation model shared by the generator and the detection rules.

Defines departments, roles, resources and which roles may touch which
sensitive resources. The rules engine checks events against this policy.
"""

SENSITIVITY_LEVELS = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}

# department -> (role, list of resources the role normally uses)
DEPARTMENTS: dict[str, dict] = {
    "Engineering": {
        "role": "developer",
        "resources": ["/eng/source-repo", "/eng/ci-pipeline", "/eng/wiki", "/shared/handbook"],
    },
    "Finance": {
        "role": "financial_analyst",
        "resources": ["/finance/reports", "/finance/payroll", "/finance/ledger", "/shared/handbook"],
    },
    "Human Resources": {
        "role": "hr_specialist",
        "resources": ["/hr/employee-records", "/hr/recruitment", "/hr/policies", "/shared/handbook"],
    },
    "Sales": {
        "role": "sales_executive",
        "resources": ["/sales/crm", "/sales/pricing", "/shared/handbook", "/shared/announcements"],
    },
    "Operations": {
        "role": "sysops",
        "resources": ["/ops/monitoring", "/ops/runbooks", "/eng/ci-pipeline", "/ops/backups"],
    },
    "IT Security": {
        "role": "it_admin",
        "resources": ["/admin/user-management", "/secrets/vault", "/ops/monitoring", "/admin/audit-logs"],
    },
}

RESOURCE_SENSITIVITY: dict[str, str] = {
    "/shared/handbook": "public",
    "/shared/announcements": "public",
    "/eng/wiki": "internal",
    "/eng/ci-pipeline": "internal",
    "/hr/policies": "internal",
    "/hr/recruitment": "confidential",
    "/ops/monitoring": "internal",
    "/ops/runbooks": "internal",
    "/sales/crm": "confidential",
    "/sales/pricing": "confidential",
    "/eng/source-repo": "confidential",
    "/finance/reports": "confidential",
    "/finance/ledger": "confidential",
    "/ops/backups": "confidential",
    "/admin/audit-logs": "confidential",
    "/finance/payroll": "restricted",
    "/hr/employee-records": "restricted",
    "/admin/user-management": "restricted",
    "/secrets/vault": "restricted",
    "/db/customer-pii-export": "restricted",
}

# Roles explicitly authorised for each restricted / confidential resource.
AUTHORISED_ROLES: dict[str, set[str]] = {
    "/finance/payroll": {"financial_analyst"},
    "/finance/ledger": {"financial_analyst"},
    "/finance/reports": {"financial_analyst"},
    "/hr/employee-records": {"hr_specialist"},
    "/hr/recruitment": {"hr_specialist"},
    "/admin/user-management": {"it_admin"},
    "/secrets/vault": {"it_admin"},
    "/admin/audit-logs": {"it_admin"},
    "/db/customer-pii-export": set(),  # nobody should bulk-export PII
    "/eng/source-repo": {"developer", "sysops"},
    "/ops/backups": {"sysops", "it_admin"},
    "/sales/crm": {"sales_executive"},
    "/sales/pricing": {"sales_executive", "financial_analyst"},
}

SENSITIVE_RESOURCES = [r for r, s in RESOURCE_SENSITIVITY.items() if s == "restricted"]


def sensitivity_of(resource: str) -> str:
    return RESOURCE_SENSITIVITY.get(resource, "internal")


def is_authorised(role: str, resource: str) -> bool:
    """True when the role may access the resource under the static policy."""
    if role == "it_admin" and resource != "/db/customer-pii-export":
        return True
    allowed = AUTHORISED_ROLES.get(resource)
    if allowed is None:
        # Public / internal resources without an explicit list are open to all.
        return SENSITIVITY_LEVELS[sensitivity_of(resource)] <= 1
    return role in allowed
