"""Generates the four bundled sample inventories.

Each file is a plausible client process inventory: APQC-shaped codes, real
activity verbs, and the volume/effort metadata a GBS tower would actually
have. Deliberately imperfect — some rows are missing volume, one file uses
different column names, one has a title block above the header — so the ingest
path is exercised rather than flattered.
"""
from __future__ import annotations

import csv
import os
import random

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "mock-data")

HEADER = [
    "L1 Code", "L1 Name", "L2 Code", "L2 Name", "L3 Code", "L3 Name",
    "L4 Code", "L4 Name", "Volume per month", "Avg handle minutes",
    "Rule based", "PII", "Safety critical", "Executive", "Systems",
    "Exception rate", "Notes",
]

UNILEVER = [
    ("11.0", "Manage Enterprise Risk and Compliance", "11.3", "Manage Legal Affairs", "11.3.1", "Contract Intake and Triage", [
        ("Receive and log inbound contract request", 4200, 8, 92, 0, "ServiceNow|SharePoint", 0.04),
        ("Classify contract type against playbook", 4200, 6, 88, 0, "SharePoint API", 0.06),
        ("Route request to the responsible legal pod", 4100, 4, 94, 0, "ServiceNow", 0.03),
        ("Validate counterparty against sanctions list", 3800, 5, 90, 0, "Dow Jones API|SAP", 0.05),
        ("Check requester authority and budget approval", 3600, 7, 82, 0, "SAP|Workday", 0.09),
    ]),
    ("11.0", "Manage Enterprise Risk and Compliance", "11.3", "Manage Legal Affairs", "11.3.2", "Contract Drafting and Review", [
        ("Extract key clauses from NDA", 2900, 22, 84, 0, "SharePoint API|DocuSign", 0.08),
        ("Compare clauses against approved playbook positions", 2700, 26, 76, 0, "SharePoint API", 0.12),
        ("Generate first-pass redline from template library", 2400, 34, 66, 0, "Word Online|DocuSign", 0.16),
        ("Negotiate deviation from standard indemnity", 620, 95, 22, 0, "Outlook", 0.44),
        ("Advise business on residual contractual risk", 480, 120, 14, 0, "Outlook", 0.51),
        ("Assess enforceability in a new jurisdiction", 180, 180, 12, 0, "Westlaw", 0.55),
    ]),
    ("11.0", "Manage Enterprise Risk and Compliance", "11.3", "Manage Legal Affairs", "11.3.3", "Contract Execution and Filing", [
        ("Prepare execution version and signature block", 2200, 14, 89, 0, "DocuSign API", 0.05),
        ("Route contract for electronic signature", 2200, 5, 95, 0, "DocuSign API", 0.03),
        ("File executed contract in the repository", 2100, 6, 96, 0, "SharePoint API", 0.02),
        ("Update contract metadata and key dates", 2100, 9, 91, 0, "SharePoint API|SAP", 0.04),
    ]),
    ("11.0", "Manage Enterprise Risk and Compliance", "11.4", "Manage Compliance Obligations", "11.4.1", "Obligation Monitoring", [
        ("Monitor renewal and expiry dates across portfolio", 1800, 10, 93, 0, "SAP|SharePoint API", 0.04),
        ("Track delivery obligations against contract terms", 1500, 18, 78, 0, "SAP", 0.14),
        ("Notify owner of an approaching contractual deadline", 1700, 4, 96, 0, "Outlook|ServiceNow", 0.02),
        ("Escalate a breach of a material obligation", 240, 65, 28, 0, "Outlook", 0.38),
    ]),
    ("11.0", "Manage Enterprise Risk and Compliance", "11.5", "Manage Disputes", "11.5.1", "Dispute Handling", [
        ("Collect evidence for a commercial dispute", 140, 150, 44, 1, "SharePoint|Outlook", 0.34),
        ("Assess litigation exposure and reserve", 90, 240, 12, 0, "Excel", 0.48),
        ("Approve settlement above delegated authority", 40, 180, 8, 0, "Outlook", 0.52),
    ]),
    ("7.0", "Develop and Manage Human Capital", "7.9", "Manage Employee Relations", "7.9.2", "Employment Matters", [
        ("Review employment contract variation request", 700, 30, 62, 1, "Workday", 0.2),
        ("Advise manager on a disciplinary process", 320, 75, 20, 1, "Workday", 0.42),
        ("Prepare settlement agreement for an exit", 180, 90, 40, 1, "Word Online", 0.3),
    ]),
]

HONEYWELL = [
    ("9.0", "Manage Financial Resources", "9.2", "Process Accounts Payable", "9.2.1", "Invoice Receipt and Capture", [
        ("Receive supplier invoice through the portal", 41000, 3, 97, 0, "SAP Ariba API", 0.02),
        ("Extract header and line data from invoice", 41000, 5, 93, 0, "SAP Ariba API|OCR", 0.05),
        ("Validate supplier master data", 39000, 4, 92, 0, "SAP", 0.05),
        ("Detect duplicate invoice submissions", 41000, 2, 98, 0, "SAP", 0.01),
    ]),
    ("9.0", "Manage Financial Resources", "9.2", "Process Accounts Payable", "9.2.2", "Matching and Exception Handling", [
        ("Perform three-way match against PO and receipt", 38000, 6, 91, 0, "SAP", 0.09),
        ("Classify a match exception by root cause", 3400, 14, 72, 0, "SAP", 0.22),
        ("Resolve a price variance with the buyer", 1900, 32, 44, 0, "SAP|Outlook", 0.36),
        ("Resolve a quantity variance with the warehouse", 1500, 28, 48, 0, "SAP|WMS", 0.33),
        ("Approve an exception outside tolerance", 620, 22, 30, 0, "SAP", 0.4),
    ]),
    ("9.0", "Manage Financial Resources", "9.2", "Process Accounts Payable", "9.2.3", "Payment Processing", [
        ("Schedule payment run by due date and terms", 900, 18, 88, 0, "SAP", 0.06),
        ("Release funds to the supplier", 900, 12, 70, 0, "SAP|Bank API", 0.08),
        ("Reconcile the bank statement to the payment run", 620, 26, 84, 0, "SAP|Bank API", 0.1),
        ("Investigate a failed or returned payment", 210, 45, 52, 0, "SAP|Bank API", 0.3),
    ]),
    ("9.0", "Manage Financial Resources", "9.5", "Manage Fixed Assets", "9.5.1", "Asset Accounting", [
        ("Capitalise an asset from a completed project", 480, 35, 76, 0, "SAP", 0.15),
        ("Calculate and post monthly depreciation", 120, 40, 95, 0, "SAP", 0.03),
        ("Reconcile the asset register to the ledger", 96, 90, 82, 0, "SAP|Excel", 0.12),
        ("Assess an asset for impairment", 40, 180, 22, 0, "Excel", 0.44),
    ]),
    ("4.0", "Deliver Physical Products", "4.2", "Procure Materials", "4.2.3", "Supplier Performance", [
        ("Collect supplier delivery performance data", 260, 30, 90, 0, "SAP|Power BI", 0.07),
        ("Generate the quarterly supplier scorecard", 40, 120, 80, 0, "Power BI", 0.12),
        ("Negotiate remediation with an underperforming supplier", 24, 240, 16, 0, "Outlook", 0.5),
    ]),
]

CSL = [
    ("5.0", "Deliver Services", "5.4", "Manage Quality", "5.4.1", "Batch Record Review", [
        ("Collect batch manufacturing records", 1800, 20, 90, 0, "MES|Veeva", 0.06),
        ("Verify critical process parameters against spec", 1800, 45, 78, 1, "MES|LIMS", 0.14),
        ("Reconcile material usage against the bill of materials", 1700, 30, 86, 0, "SAP|MES", 0.09),
        ("Approve batch release for distribution", 1600, 60, 30, 1, "Veeva", 0.18),
    ]),
    ("5.0", "Deliver Services", "5.4", "Manage Quality", "5.4.2", "Deviation and CAPA", [
        ("Log a manufacturing deviation", 620, 25, 84, 0, "Veeva QMS", 0.08),
        ("Classify deviation severity and impact", 620, 50, 54, 1, "Veeva QMS", 0.24),
        ("Investigate root cause of a critical deviation", 180, 300, 18, 1, "Veeva QMS", 0.46),
        ("Draft the CAPA plan", 210, 150, 40, 1, "Veeva QMS", 0.3),
        ("Verify CAPA effectiveness after implementation", 190, 90, 62, 0, "Veeva QMS", 0.2),
    ]),
    ("11.0", "Manage Enterprise Risk and Compliance", "11.2", "Manage Regulatory Compliance", "11.2.4", "Pharmacovigilance", [
        ("Receive an adverse event report", 3400, 12, 88, 1, "Argus Safety API", 0.05),
        ("Code the event using MedDRA terminology", 3400, 22, 74, 1, "Argus Safety", 0.16),
        ("Assess causality between product and event", 3100, 40, 34, 1, "Argus Safety", 0.28),
        ("Determine expedited reporting obligation", 2900, 18, 66, 1, "Argus Safety", 0.15),
        ("Submit the report to the regulatory authority", 2600, 20, 80, 1, "Gateway API", 0.08),
    ]),
    ("11.0", "Manage Enterprise Risk and Compliance", "11.2", "Manage Regulatory Compliance", "11.2.5", "Submission Management", [
        ("Compile a regulatory submission dossier", 90, 400, 58, 0, "Veeva Vault", 0.2),
        ("Validate submission against the health authority checklist", 90, 120, 82, 0, "Veeva Vault", 0.1),
        ("Respond to a health authority information request", 140, 260, 24, 0, "Veeva Vault", 0.42),
    ]),
]

# Charter file deliberately uses different column names and a title block.
CHARTER = [
    ("6.0", "Manage Customer Service", "6.2", "Handle Service Requests", "6.2.1", "Request Intake", [
        ("Receive a subscriber service request", 96000, 3, 95, 1, "Salesforce API", 0.03),
        ("Verify subscriber identity and account status", 94000, 4, 90, 1, "Salesforce|Billing API", 0.05),
        ("Classify the request by service type", 94000, 3, 93, 0, "Salesforce API", 0.05),
        ("Route the request to the correct queue", 92000, 2, 96, 0, "Salesforce API", 0.02),
    ]),
    ("6.0", "Manage Customer Service", "6.2", "Handle Service Requests", "6.2.2", "Resolution", [
        ("Run automated line diagnostics", 62000, 5, 94, 0, "OSS API", 0.06),
        ("Reset customer premises equipment remotely", 41000, 4, 96, 0, "OSS API", 0.04),
        ("Diagnose an intermittent node degradation", 6200, 40, 42, 0, "OSS|Splunk", 0.34),
        ("Schedule a field technician dispatch", 12000, 8, 86, 1, "Salesforce|Field Service", 0.1),
        ("Handle an escalated complaint from a regulator", 320, 120, 18, 1, "Salesforce", 0.46),
    ]),
    ("6.0", "Manage Customer Service", "6.4", "Manage Billing Enquiries", "6.4.1", "Billing Disputes", [
        ("Retrieve the disputed billing record", 21000, 6, 92, 1, "Billing API", 0.05),
        ("Recalculate charges against the rate plan", 19000, 12, 88, 1, "Billing API", 0.1),
        ("Apply an adjustment within the agreed threshold", 14000, 8, 82, 1, "Billing API", 0.12),
        ("Approve a credit above the agent threshold", 2100, 15, 34, 1, "Billing API", 0.3),
        ("Investigate a systemic billing error", 180, 200, 22, 0, "Billing API|Splunk", 0.44),
    ]),
    ("8.0", "Manage Information Technology", "8.5", "Manage IT Operations", "8.5.3", "Incident Management", [
        ("Detect a network incident from telemetry", 4200, 5, 92, 0, "Splunk|OSS", 0.08),
        ("Correlate alerts into a single incident", 3800, 10, 84, 0, "Splunk", 0.14),
        ("Assign incident severity and notify stakeholders", 3600, 8, 78, 0, "ServiceNow", 0.12),
        ("Coordinate a major incident bridge", 120, 180, 20, 0, "Teams|ServiceNow", 0.4),
    ]),
]


def rows_for(dataset) -> list[list]:
    rng = random.Random(42)
    out = []
    for l1c, l1n, l2c, l2n, l3c, l3n, activities in dataset:
        for idx, (name, vol, aht, rule, pii, systems, exc) in enumerate(activities, start=1):
            # Roughly one in nine rows is missing volume data, as in real inventories.
            drop = rng.random() < 0.11
            out.append([
                l1c, l1n, l2c, l2n, l3c, l3n, f"{l3c}.{idx}", name,
                "" if drop else vol, "" if drop else aht,
                rule, "Y" if pii else "N", "N", "N", systems, exc, "",
            ])
    return out


def write_csv(path: str, rows: list[list], header: list[str], title: str | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if title:
            writer.writerow([title])
            writer.writerow([f"Exported {len(rows)} activities"])
            writer.writerow([])
        writer.writerow(header)
        writer.writerows(rows)


if __name__ == "__main__":
    write_csv(os.path.join(OUT, "unilever-legal.csv"), rows_for(UNILEVER), HEADER)
    write_csv(os.path.join(OUT, "honeywell-p2p.csv"), rows_for(HONEYWELL), HEADER)
    write_csv(os.path.join(OUT, "csl-quality.csv"), rows_for(CSL), HEADER)

    # Same data, hostile formatting: aliased columns and a title block.
    alt_header = [
        "Category", "Category Name", "Process Group", "Process Group Name",
        "Process", "Process Name", "PCF ID", "Activity Name", "Monthly Volume",
        "AHT", "Rule Bound %", "Contains PII", "Safety", "Strategic",
        "Applications", "Error Rate", "Comments",
    ]
    write_csv(
        os.path.join(OUT, "charter-care.csv"), rows_for(CHARTER), alt_header,
        title="Charter Communications - Care Tower Process Inventory (extract)",
    )
    print("wrote 4 sample inventories to", os.path.abspath(OUT))
