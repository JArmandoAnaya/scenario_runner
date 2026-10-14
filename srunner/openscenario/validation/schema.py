"""Version-aware schema validation of OpenSCENARIO documents.

The schema is selected from the document's ``FileHeader`` (``revMajor`` and
``revMinor``; the 1.3.1 schema defines no ``revPatch`` attribute):

* 1.0 documents are validated against the bundled ASAM OpenSCENARIO 1.0 XSD.
* 1.3 documents are validated against the bundled ASAM OpenSCENARIO XML 1.3.1
  XSD; 1.3.1 changes no schema element or concept of 1.3.0.
* 1.1 and 1.2 documents are rejected: no schema for those versions is bundled
  and the 1.3 schema is not backward compatible with them (ASAM corrected the
  schema in 1.3.0 and ships a 1.2 to 1.3 migration script).  Validating them
  against the 1.3.1 schema would reject valid documents.
* Any other version is rejected with a structured diagnostic.

Compiled schemas are cached per process.
"""

from __future__ import absolute_import

import os
import threading

from srunner.openscenario.validation.diagnostics import Diagnostic, ValidationError

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schemas")
SCHEMA_FILES = {
    "1.0": os.path.join(SCHEMA_DIR, "1.0", "OpenSCENARIO.xsd"),
    "1.3.1": os.path.join(SCHEMA_DIR, "1.3.1", "OpenSCENARIO.xsd"),
}
VALID_SCHEMA_RULE = "asam.net:xosc:1.0.0:xml.valid_schema"

_COMPILED = {}
_LOCK = threading.Lock()


def schema_key(version):
    """Return the bundled schema key for ``version`` or raise ValidationError (unsupported version)."""
    major, minor, patch = version.major, version.minor, version.patch
    if (major, minor) == (1, 0) and patch in (None, 0):
        return "1.0"
    if (major, minor) == (1, 3) and patch in (None, 0, 1):
        return "1.3.1"
    if (major, minor) in ((1, 1), (1, 2)):
        message = ("OpenSCENARIO {} documents are not supported: no {}.{} schema is bundled and the 1.3.1 schema is "
                   "not backward compatible with it. Migrate the document to 1.3 (ASAM provides a migration "
                   "script) and declare revMinor=\"3\"".format(version, major, minor))
    elif major == 0:
        message = ("OpenSCENARIO {} documents are not supported; migrate them to 1.0 with "
                   "srunner/openscenario/0.9.x/migration0_9_1to1_0.xslt".format(version))
    else:
        message = "OpenSCENARIO {} is not supported; supported versions are 1.0 and 1.3 (1.3.0/1.3.1)".format(version)
    raise ValidationError([Diagnostic("schema_error", message, code=Diagnostic.UNSUPPORTED_VERSION,
                                      rule=VALID_SCHEMA_RULE)])


def compiled_schema(key_or_path):
    """Return the compiled XSD for a schema key (``"1.0"``, ``"1.3.1"``) or a file path, compiling it once."""
    path = SCHEMA_FILES.get(key_or_path, key_or_path)
    with _LOCK:
        schema = _COMPILED.get(path)
        if schema is None:
            import xmlschema  # pylint: disable=import-outside-toplevel
            schema = xmlschema.XMLSchema(path)
            _COMPILED[path] = schema
    return schema


def _reason(error):
    reason = getattr(error, "reason", None) or getattr(error, "message", None) or str(error)
    return " ".join(str(reason).split())


class SchemaValidator(object):
    """Validate documents against the schema matching their declared version.

    ``schema_path`` forces one schema for every document (no version selection).
    """

    def __init__(self, schema_path=None):
        self.schema_path = schema_path

    def schema_key_for(self, document):
        if self.schema_path:
            return self.schema_path
        version = getattr(document, "version", None)
        if version is None:
            root = document.getroot() if hasattr(document, "getroot") else document
            header = root.find("FileHeader")
            if header is None:
                raise ValidationError([Diagnostic("schema_error", "OpenSCENARIO document is missing FileHeader",
                                                  code=Diagnostic.MALFORMED_DOCUMENT, rule=VALID_SCHEMA_RULE)])
            # Deferred: the loader imports the model, which imports this package.
            from srunner.openscenario.parsing.loader import OpenScenarioVersion  # pylint: disable=import-outside-toplevel
            version = OpenScenarioVersion.from_header(header)
        return schema_key(version)

    def iter_diagnostics(self, document, schema=None):
        """Yield one schema_error Diagnostic per violation, located when the document tracks lines."""
        root = document.root if hasattr(document, "root") else document
        root = root.getroot() if hasattr(root, "getroot") else root
        for error in compiled_schema(schema or self.schema_key_for(document)).iter_errors(root):
            element = getattr(error, "elem", None)
            if not hasattr(element, "tag"):
                element = None
            diagnostic = Diagnostic("schema_error", _reason(error), source=element,
                                    code=Diagnostic.SCHEMA_VIOLATION, rule=VALID_SCHEMA_RULE)
            if element is not None and hasattr(document, "locations"):
                diagnostic.locate(document)
            if diagnostic.path is None:
                diagnostic.path = getattr(error, "path", None)
            yield diagnostic

    def validate(self, source, raise_on_error=True, schema=None):
        try:
            diagnostics = list(self.iter_diagnostics(source, schema))
        except ValidationError as error:
            diagnostics = error.diagnostics
        if diagnostics and raise_on_error:
            raise ValidationError(diagnostics)
        return diagnostics

    def load(self, source):
        """Load ``source`` and validate it; raises ValidationError on an unsupported version or violations."""
        # Deferred: the loader imports the model, which imports this package.
        from srunner.openscenario.parsing.loader import load_document  # pylint: disable=import-outside-toplevel
        document = load_document(source)
        self.validate(document)
        return document

    def validate_document(self, source, raise_on_error=True):
        # Deferred: the loader imports the model, which imports this package.
        from srunner.openscenario.parsing.loader import load_document  # pylint: disable=import-outside-toplevel
        try:
            document = source if hasattr(source, "root") else load_document(source)
        except ValidationError as error:
            if raise_on_error:
                raise
            return error.diagnostics
        return self.validate(document, raise_on_error=raise_on_error)
