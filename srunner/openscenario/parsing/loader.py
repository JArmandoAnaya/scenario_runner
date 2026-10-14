"""Version-aware OpenSCENARIO XML loading, independent of CARLA execution."""

from __future__ import absolute_import

import os
import xml.etree.ElementTree as ET
from xml.parsers import expat

from srunner.openscenario.model.document import OpenScenarioDocument
from srunner.openscenario.validation.diagnostics import Diagnostic, ValidationError


def _malformed(message, source=None):
    return ValidationError([Diagnostic("schema_error", message, source=source,
                                       code=Diagnostic.MALFORMED_DOCUMENT)])


class OpenScenarioVersion(object):
    def __init__(self, major, minor, patch=None):
        self.major = int(major)
        self.minor = int(minor)
        self.patch = None if patch in (None, "") else int(patch)

    @classmethod
    def from_header(cls, header):
        try:
            return cls(header.attrib["revMajor"], header.attrib["revMinor"], header.attrib.get("revPatch"))
        except (KeyError, ValueError) as error:
            raise _malformed("FileHeader must declare integer revMajor and revMinor attributes", header) \
                from error

    def as_tuple(self):
        return (self.major, self.minor, self.patch or 0)

    def __str__(self):
        if self.patch is None:
            return "{}.{}".format(self.major, self.minor)
        return "{}.{}.{}".format(self.major, self.minor, self.patch)

    def __repr__(self):
        return "OpenScenarioVersion({})".format(str(self))

    def __eq__(self, other):
        return isinstance(other, OpenScenarioVersion) and (
            self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((self.major, self.minor, self.patch))


def parse_xml(source):
    """Parse ``source`` into ``(root, lines, source_name)``; ``lines`` maps elements to source lines.

    ``source`` is a path, a binary/text file object, or XML bytes.  The tree is built
    with the standard ElementTree builder, so it is interchangeable with ``ET.parse``.
    """
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate(namespace_separator="}")
    lines = {}

    def fix(name):
        return "{" + name if "}" in name else name

    def start(tag, attributes):
        element = builder.start(fix(tag), dict((fix(key), value) for key, value in attributes.items()))
        lines[element] = parser.CurrentLineNumber

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda tag: builder.end(fix(tag))
    parser.CharacterDataHandler = builder.data
    parser.buffer_text = True

    source_name = None
    try:
        if isinstance(source, bytes):
            parser.Parse(source, True)
        elif hasattr(source, "read"):
            source_name = getattr(source, "name", None)
            data = source.read()
            parser.Parse(data.encode("utf-8") if isinstance(data, str) else data, True)
        else:
            source_name = os.path.abspath(source)
            with open(source, "rb") as handle:
                parser.ParseFile(handle)
    except expat.ExpatError as error:
        raise ValidationError([Diagnostic(
            "schema_error", "Malformed XML: {}".format(expat.ErrorString(error.code)), line=error.lineno,
            path=source_name, code=Diagnostic.MALFORMED_DOCUMENT, rule="asam.net:xosc:1.0.0:xml.valid_schema")]) \
            from error
    return builder.close(), lines, source_name


class OpenScenarioLoader(object):
    """Load XML and retain the declared standard version.

    Malformed documents raise ValidationError (a ValueError) with a MALFORMED_DOCUMENT diagnostic.
    """

    def load(self, source):
        root, lines, source_name = self._read_root(source)
        if root.tag != "OpenSCENARIO":
            raise _malformed("Expected OpenSCENARIO root element, got {!r}".format(root.tag), root)
        header = root.find("FileHeader")
        if header is None:
            raise _malformed("OpenSCENARIO document is missing FileHeader", root)
        if "revMajor" not in header.attrib or "revMinor" not in header.attrib:
            raise _malformed("FileHeader must declare revMajor and revMinor", header)
        return OpenScenarioDocument(root, OpenScenarioVersion.from_header(header), source_name, lines)

    @staticmethod
    def _read_root(source):
        # Duck-typed: xmlschema 1.0.x re-imports xml.etree.ElementTree, so isinstance
        # checks against this module's classes fail for trees parsed before that import.
        if hasattr(source, "getroot"):
            return source.getroot(), {}, None
        if hasattr(source, "tag") and hasattr(source, "attrib"):
            return source, {}, None
        if not hasattr(source, "read") and not isinstance(source, (str, bytes)):
            raise TypeError("source must be an XML path, file object, ElementTree, or Element")
        return parse_xml(source)


def load_document(source):
    return OpenScenarioLoader().load(source)
