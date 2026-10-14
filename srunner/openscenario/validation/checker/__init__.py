"""Static checker for the ASAM OpenSCENARIO XML 1.3.1 Annex C checker rules.

``RULES`` holds the implemented rules and ``NOT_IMPLEMENTED`` the rules that
cannot be decided without the road network or a simulator, each with the reason.
"""

from __future__ import absolute_import

import logging

from srunner.openscenario.validation.checker import rules as _rules  # pylint: disable=unused-import
from srunner.openscenario.validation.checker.context import CheckerContext
from srunner.openscenario.validation.checker.registry import NOT_IMPLEMENTED, RULES, rule_coverage, rules_table_markdown
from srunner.openscenario.validation.diagnostics import Diagnostic

LOGGER = logging.getLogger("[SR:OpenSCENARIO]")
SCHEMA_RULE = "asam.net:xosc:1.0.0:xml.valid_schema"


class Checker(object):
    """Run checker rules on a document and return structured diagnostics.

    ``rules`` restricts the run to the given UIDs; ``exclude`` skips UIDs (for example the schema
    rule when the document was already validated while loading).
    """

    def __init__(self, rules=None, exclude=()):
        self.rules = [RULES[uid] for uid in (rules or RULES) if uid not in exclude]

    def check(self, document, filename=None, parameter_overrides=None, catalogs=None):
        context = CheckerContext(document, filename, parameter_overrides, catalogs)
        diagnostics = []
        for item in self.rules:
            severity = item.severity_for(context.version)
            try:
                findings = list(item.check(context))
            except Exception as error:  # pylint: disable=broad-except
                # A defect in one rule must not hide the findings of the others.
                LOGGER.debug("Checker rule %s failed", item.uid, exc_info=True)
                diagnostics.append(Diagnostic("checker_rule", "Rule could not be evaluated: {}".format(error),
                                              severity="warning", code=item.uid, rule=item.uid))
                continue
            for element, message in findings:
                diagnostics.append(Diagnostic("checker_rule", message, severity=severity, source=element,
                                              code=item.uid, rule=item.uid).locate(document))
        return diagnostics


__all__ = ["Checker", "CheckerContext", "NOT_IMPLEMENTED", "RULES", "SCHEMA_RULE", "rule_coverage",
           "rules_table_markdown"]
