"""Structured diagnostics shared by validation and execution boundaries."""

from __future__ import absolute_import

import contextlib


class Diagnostic(object):
    CATEGORIES = frozenset((
        "schema_error", "semantic_error", "checker_rule", "unsupported_feature",
        "backend_capability_error", "approximation_warning", "runtime_error"))

    UNKNOWN_REFERENCE = "unknown_reference"
    INVALID_EXPRESSION = "invalid_expression"
    TYPE_MISMATCH = "type_mismatch"
    ARITHMETIC_ERROR = "arithmetic_error"
    DUPLICATE_DECLARATION = "duplicate_declaration"
    UNDECLARED_OVERRIDE = "undeclared_override"
    MALFORMED_DOCUMENT = "malformed_document"
    NOT_MIGRATED = "not_migrated"
    UNSUPPORTED_VERSION = "unsupported_version"
    SCHEMA_VIOLATION = "schema_violation"
    EMPTY_CHOICE = "empty_choice"

    def __init__(self, category, message, path=None, severity="error", source=None, code=None, rule=None,
                 line=None):
        if category not in self.CATEGORIES:
            raise ValueError("Unknown diagnostic category: {}".format(category))
        self.category = category
        self.message = message
        self.path = path
        self.severity = severity
        self.source = source
        self.code = code
        self.rule = rule
        self.line = line

    @property
    def is_error(self):
        """Warnings are reported but do not block execution."""
        return self.severity == "error"

    def locate(self, document):
        """Fill ``line`` and ``path`` from the source element when ``document`` knows it."""
        locations = getattr(document, "locations", None)
        if locations is None or not hasattr(self.source, "tag"):
            return self
        if self.line is None:
            self.line = locations.line(self.source)
        if self.path is None:
            self.path = locations.path(self.source)
        return self

    def __str__(self):
        location = ""
        if self.path or self.line is not None:
            location = " at {}{}".format(self.path or "", " (line {})".format(self.line) if self.line else "")
        rule = " {}".format(self.rule) if self.rule else ""
        return "[{}{}]{} {}".format(self.category, rule, location, self.message)

    def __repr__(self):
        return "Diagnostic(category={!r}, code={!r}, rule={!r}, message={!r}, path={!r}, line={!r})".format(
            self.category, self.code, self.rule, self.message, self.path, self.line)


class DiagnosticError(ValueError):
    """Base of the errors carrying structured ``diagnostics``."""

    diagnostics = ()


class ValidationError(DiagnosticError):
    def __init__(self, diagnostics):
        self.diagnostics = list(diagnostics)
        super(ValidationError, self).__init__("; ".join(str(item) for item in self.diagnostics))


@contextlib.contextmanager
def diagnostics_as_validation_error():
    """Re-raise a DiagnosticError (e.g. EvaluationError) raised in the block as a ValidationError."""
    try:
        yield
    except ValidationError:
        raise
    except DiagnosticError as error:
        raise ValidationError(error.diagnostics) from error
