# Sample process inventories

Four inventories, one per industry card, shaped like real client extracts
rather than clean fixtures. Each is deliberately imperfect so the ingest path
is exercised instead of flattered.

| File | Industry | Function | Activities | What it tests |
|---|---|---|---|---|
| `unilever-legal.csv` | Consumer products | Legal | 25 | Judgement-heavy casework alongside routine filing |
| `honeywell-p2p.csv` | Industrial | Procurement | 20 | High-volume transactional work, three-way match exceptions |
| `csl-quality.csv` | Life sciences | Quality | 17 | GxP activities, pharmacovigilance, PII throughout |
| `charter-care.csv` | Telecom and media | Customer service | 18 | **Two title rows above the header and non-standard column names** |

`charter-care.csv` is the important one. Its header sits on row four and its
columns are named `PCF ID`, `Activity Name`, `AHT`, `Rule Bound %` and
`Contains PII` rather than the canonical names. If ingest handles that file it
will handle most client exports.

## Columns

Only `L4 Name` is genuinely required. Everything else improves the score's
confidence and is reported as missing when absent.

| Column | Aliases recognised | Effect when absent |
|---|---|---|
| `L4 Name` | Activity, Task name, Activity Name, PCF element | Required |
| `L1/L2/L3/L4 Code` | Category, Process Group, Process, PCF ID | Codes are generated |
| `Volume per month` | Volume, Monthly Volume, Transactions | Frequency assumed median |
| `Avg handle minutes` | AHT, Handle time, Minutes per task | No effort estimate for that row |
| `FTE` | Headcount, HC | Derived from volume × AHT instead |
| `Rule based` | Rule Bound %, Standardisation | Inferred from the activity verb |
| `PII` | Contains PII, Personal data, GDPR | Inferred from keywords |
| `Systems` | Applications, Apps, Platform | Integration maturity assumed partial |
| `Exception rate` | Error rate, Rework rate | Inferred from the activity verb |

Booleans accept `Y/N`, `Yes/No`, `true/false`, `1/0`. Percentages accept either
`0.08` or `8%`. Excel's habit of turning `9.0` into `9` is corrected on read.

## Regenerating

```bash
cd backend && python tests/make_mock_data.py
```

The generator is seeded, so the files are reproducible. Roughly one row in nine
has its volume and handle time removed on purpose, which is what forces the
"effort shown as a range, not a point" warning in the UI.
