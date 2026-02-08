## Description

<!-- What does this PR do? Be specific. "Fixes stuff" is not helpful. -->

**Summary:**


**Related Issue:**
Fixes #(issue number)
<!-- Or: Relates to #(issue), Closes #(issue) -->

---

## Type of Change

<!-- Mark the relevant option with an 'x' -->

- [ ] Bug fix (fixes an issue without changing existing functionality)
- [ ] New feature (adds functionality without breaking existing features)
- [ ] Breaking change (fixes or adds functionality that breaks existing behaviour)
- [ ] Documentation update (no code changes)
- [ ] Refactoring (code structure improvements, no functional changes)
- [ ] Protocol implementation (new or improved protocol support)
- [ ] Device implementation (new PLC, RTU, or other device)
- [ ] Security feature (detection, logging, or defensive capability)

---

## Testing

<!-- How did you verify this works? Be specific. -->

**What I tested:**
-

**Test results:**
```
# Paste relevant test output, e.g.:
# pytest tests/unit/test_your_feature.py
# All tests passed
```

**Manual testing:**
<!-- If applicable: commands run, expected output, observed behaviour -->


---

## Checklist

<!-- Tick these off before submitting. If you can't tick something, explain why in comments. -->

**Code Quality:**
- [ ] All tests pass locally (`pytest tests/`)
- [ ] Code passes linting (`ruff check .`)
- [ ] Added tests for new functionality (if applicable)
- [ ] No new warnings or errors introduced

**Documentation:**
- [ ] Updated relevant documentation (README, architecture.md, etc.)
- [ ] Added docstrings for new public methods
- [ ] Updated configuration examples (if config changes)

**Architecture:**
- [ ] Follows project architecture (no circular dependencies)
- [ ] Uses DataStore for device state access (not direct references)
- [ ] Uses SimulationTime for all time queries
- [ ] Implements ICSLogger integration (if adding/modifying devices)
- [ ] New methods are async where appropriate

**Security & Research:**
- [ ] No credentials or sensitive data in code
- [ ] Security features have tests demonstrating detection
- [ ] Attack simulations are clearly documented as research tools

---

## Breaking Changes

<!-- Does this change existing behaviour? Will users need to update their code or config? -->

- [ ] Yes, this introduces breaking changes (describe below)
- [ ] No breaking changes

**If yes, describe what breaks and how to migrate:**


---

## Additional Context

<!-- Anything else reviewers should know? -->

**Implementation notes:**


**Known limitations:**


**Screenshots/Output:**
<!-- If relevant, paste command output, simulator logs, or visual results -->


---

## Review Notes

<!-- For the maintainer -->

*"Remember: industrial control systems are unforgiving. If this code looks like it might cause a cascade failure at 3am, it probably will. Review accordingly."*

**Maintainer checklist:**
- [ ] Architecture compliance verified
- [ ] Test coverage adequate
- [ ] Documentation clear and accurate
- [ ] No security concerns
- [ ] Commit messages follow convention