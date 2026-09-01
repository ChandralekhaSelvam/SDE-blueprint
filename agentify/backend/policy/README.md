# Policy packs

Hard override rules live here as version-controlled YAML. No model decides a
risk tier: when a score is capped, the cap came from a named rule in a named
file, and the UI shows that path in the evidence panel.

A pack file is optional. If `policy/<industry>.yaml` exists it is merged over
the built-in base pack; otherwise the built-in industry pack in `app/policy.py`
is used. Create a file here to override caps for a specific client without
touching code.

```yaml
name: Consumer products, Unilever tenant
reviewer_role: Regional counsel
bands:
  full_agent: 78      # this client wants a higher autonomous bar
  hitl: 40
residuals:
  full_agent: 0.05
  hitl: 0.20          # more conservative review-time assumption
  human_only: 0.85
overrides:
  - rule: cross_border
    cap: 50
    reason: Cross-border data transfer requires a documented transfer mechanism.
    keywords: ["cross-border", "transfer abroad"]
```

Rules fire on one of three conditions:

- `when` matches a boolean flag on the task (`pii`, `safety_critical`, `executive_judgement`)
- `computed` matches a signal derived in `scoring.py` (`judgement_dominant`)
- `keywords` match the **activity name and notes only**, never the process group
  above it. Matching the whole L1 to L4 path would fire a contract rule on every
  activity in a group merely called "Contract Management".
