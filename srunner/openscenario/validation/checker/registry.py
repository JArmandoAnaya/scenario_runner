"""Registry of ASAM OpenSCENARIO XML 1.3.1 Annex C checker rules."""

from __future__ import absolute_import

from collections import OrderedDict

RULES = OrderedDict()
NOT_IMPLEMENTED = OrderedDict()


def _since(uid):
    return tuple(int(part) for part in uid.split(":")[2].split("."))


class Rule(object):
    """An implemented checker rule.

    ``severity`` follows the rule wording in Annex C ("shall" -> error, "should"/"can" -> warning).
    ``coverage`` is ``"full"`` or ``"partial"``; ``scope`` says what a partial rule checks.
    ``legacy_severity`` overrides the severity for documents older than 1.3.
    """

    def __init__(self, uid, severity, description, check, coverage="full", scope=None, legacy_severity=None):
        self.uid = uid
        self.name = uid.rsplit(".", 1)[-1]
        self.rule_set = uid.split(":")[3].rsplit(".", 1)[0]
        self.since = _since(uid)
        self.severity = severity
        self.description = description
        self.check = check
        self.coverage = coverage
        self.scope = scope
        self.legacy_severity = legacy_severity

    def severity_for(self, version):
        """Rules newer than the document, or downgraded for pre-1.3 documents, report warnings."""
        if self.severity == "warning" or version < self.since:
            return "warning"
        if self.legacy_severity and version < (1, 3, 0):
            return self.legacy_severity
        return self.severity


class NotImplementedRule(object):
    """A checker rule that is not implemented, with the reason."""

    def __init__(self, uid, severity, description, reason):
        self.uid = uid
        self.name = uid.rsplit(".", 1)[-1]
        self.rule_set = uid.split(":")[3].rsplit(".", 1)[0]
        self.severity = severity
        self.description = description
        self.reason = reason


def rule(uid, severity, description, coverage="full", scope=None, legacy_severity=None):
    """Register the decorated ``check(context)`` generator yielding ``(element, message)`` pairs."""
    def register(check):
        if uid in RULES or uid in NOT_IMPLEMENTED:
            raise ValueError("Duplicate checker rule {}".format(uid))
        RULES[uid] = Rule(uid, severity, description, check, coverage, scope, legacy_severity)
        return check
    return register


def not_implemented(uid, severity, description, reason):
    if uid in RULES or uid in NOT_IMPLEMENTED:
        raise ValueError("Duplicate checker rule {}".format(uid))
    NOT_IMPLEMENTED[uid] = NotImplementedRule(uid, severity, description, reason)


def rule_coverage():
    """Machine-readable coverage: {'implemented': [...], 'partial': [...], 'not_implemented': [...]}."""
    return {
        "implemented": [uid for uid, item in RULES.items() if item.coverage == "full"],
        "partial": [uid for uid, item in RULES.items() if item.coverage == "partial"],
        "not_implemented": list(NOT_IMPLEMENTED),
    }


def rules_table_markdown():
    """The checker rule coverage as the Markdown table published in Docs/openscenario_support.md."""
    lines = ["| Rule UID | Severity | Status | Scope or reason |", "|---|---|---|---|"]
    rows = [(uid, item.severity, item.coverage, item.scope or "") for uid, item in RULES.items()]
    rows += [(uid, item.severity, "not implemented", item.reason) for uid, item in NOT_IMPLEMENTED.items()]
    for uid, severity, status, text in sorted(rows, key=lambda row: row[0].split(":")[3]):
        lines.append("| `{}` | {} | {} | {} |".format(uid, severity, status, text))
    return "\n".join(lines)
