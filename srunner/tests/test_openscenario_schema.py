#!/usr/bin/env python
"""Version-aware schema validation of OpenSCENARIO documents (no CARLA required).

``OPENSCENARIO_ASAM_EXAMPLES`` may point at an unzipped copy of the ASAM
OpenSCENARIO XML 1.3.1 examples to also validate that corpus.
"""

from __future__ import absolute_import

import glob
import hashlib
import os
import unittest

from srunner.openscenario.parsing.loader import OpenScenarioVersion, load_document, parse_xml
from srunner.openscenario.validation.diagnostics import Diagnostic, ValidationError
from srunner.openscenario.validation.schema import SCHEMA_FILES, SchemaValidator, compiled_schema, schema_key

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = sorted(glob.glob(os.path.join(TESTS_DIR, "..", "examples", "*.xosc")))
FIXTURES = os.path.join(TESTS_DIR, "fixtures", "openscenario")
FIXTURES_1_3 = [os.path.join(FIXTURES, name) for name in (
    "conformance_1_3_1.xosc", "parameters_variables.xosc", "private_actions_1_3.xosc")]
ASAM_EXAMPLES = os.environ.get("OPENSCENARIO_ASAM_EXAMPLES")
OFFICIAL_1_3_1_SHA256 = "1c86539c61264c691c1031ec78e3a93dcde63876f7f769428c330d4fd86c26a4"

MINIMAL = """<?xml version="1.0" encoding="UTF-8"?>
<OpenSCENARIO>
  <FileHeader revMajor="{major}" revMinor="{minor}" date="2026-10-14T12:00:00" description="d" author="a"/>
  <ParameterDeclarations>
    <ParameterDeclaration name="Speed" parameterType="double" value="{speed}"/>
  </ParameterDeclarations>
  <CatalogLocations/>
  <RoadNetwork/>
  <Entities/>
  <Storyboard>
    <Init><Actions/></Init>
    <StopTrigger/>
  </Storyboard>
</OpenSCENARIO>
"""


def minimal(major=1, minor=3, speed="1.0"):
    return MINIMAL.format(major=major, minor=minor, speed=speed).encode("utf-8")


class TestSchemaSelection(unittest.TestCase):

    def test_bundled_1_3_1_schema_is_the_official_file(self):
        with open(SCHEMA_FILES["1.3.1"], "rb") as handle:
            self.assertEqual(hashlib.sha256(handle.read()).hexdigest(), OFFICIAL_1_3_1_SHA256)

    def test_versions_map_to_bundled_schemas(self):
        self.assertEqual(schema_key(OpenScenarioVersion(1, 0)), "1.0")
        self.assertEqual(schema_key(OpenScenarioVersion(1, 3)), "1.3.1")
        self.assertEqual(schema_key(OpenScenarioVersion(1, 3, 0)), "1.3.1")
        self.assertEqual(schema_key(OpenScenarioVersion(1, 3, 1)), "1.3.1")

    def test_unsupported_versions_are_structured_diagnostics(self):
        for version in ((1, 1), (1, 2), (1, 4), (2, 0), (0, 9), (1, 3, 2)):
            with self.subTest(version=version):
                with self.assertRaises(ValidationError) as raised:
                    schema_key(OpenScenarioVersion(*version))
                diagnostic = raised.exception.diagnostics[0]
                self.assertEqual(diagnostic.code, Diagnostic.UNSUPPORTED_VERSION)
                self.assertEqual(diagnostic.rule, "asam.net:xosc:1.0.0:xml.valid_schema")

    def test_1_1_and_1_2_documents_point_to_the_migration(self):
        with self.assertRaises(ValidationError) as raised:
            SchemaValidator().load(minimal(minor=2))
        self.assertIn("Migrate the document to 1.3", str(raised.exception))

    def test_non_integer_header_is_a_diagnostic_not_a_crash(self):
        with self.assertRaises(ValidationError) as raised:
            SchemaValidator().load(minimal(major="one"))
        self.assertEqual(raised.exception.diagnostics[0].code, Diagnostic.MALFORMED_DOCUMENT)

    def test_compiled_schemas_are_cached(self):
        self.assertIs(compiled_schema("1.3.1"), compiled_schema("1.3.1"))
        self.assertIs(compiled_schema("1.0"), compiled_schema(SCHEMA_FILES["1.0"]))

    def test_1_3_documents_are_rejected_by_the_1_0_schema(self):
        document = load_document(minimal(minor=3))
        self.assertEqual(SchemaValidator().validate(document, raise_on_error=False), [])
        self.assertTrue(SchemaValidator(SCHEMA_FILES["1.0"]).validate(
            load_document(os.path.join(FIXTURES, "parameters_variables.xosc")), raise_on_error=False))

    def test_1_3_1_schema_is_not_a_superset_of_1_0(self):
        # Valid 1.0 documents (OverrideControllerValueAction changed) are invalid under 1.3.1; this is why 1.0
        # keeps its own schema and why 1.1/1.2 documents are not validated against the 1.3.1 schema.
        document = load_document(os.path.join(TESTS_DIR, "..", "examples", "FollowLeadingVehicle.xosc"))
        self.assertTrue(SchemaValidator(SCHEMA_FILES["1.3.1"]).validate(document, raise_on_error=False))


class TestSchemaDiagnostics(unittest.TestCase):

    def test_every_violation_is_reported_with_line_and_path(self):
        source = minimal().replace(b'parameterType="double"', b'parameterType="speedy"').replace(
            b'<Entities/>', b'<Entities unknown="1"/>')
        with self.assertRaises(ValidationError) as raised:
            SchemaValidator().load(source)
        diagnostics = raised.exception.diagnostics
        self.assertTrue(all(item.category == "schema_error" for item in diagnostics))
        self.assertTrue(all(item.rule == "asam.net:xosc:1.0.0:xml.valid_schema" for item in diagnostics))
        lines = dict((item.line, item) for item in diagnostics)
        self.assertIn(5, lines)
        self.assertEqual(lines[5].path, "/OpenSCENARIO/ParameterDeclarations/ParameterDeclaration[@name='Speed']")
        self.assertIn("line 5", str(lines[5]))
        self.assertIn(9, lines)

    def test_numeric_attributes_accept_numbers_parameters_and_expressions_only(self):
        with open(os.path.join(FIXTURES, "conformance_1_3_1.xosc"), "rb") as handle:
            source = handle.read()
        for value, valid in (("69.4", True), ("$TargetSpeed", True), ("${$BaseSpeed * 2}", True), ("fast", False),
                             ("${[1]}", False)):
            with self.subTest(value=value):
                diagnostics = SchemaValidator().validate(load_document(source.replace(
                    b'maxSpeed="69.444"', 'maxSpeed="{}"'.format(value).encode("utf-8"), 1)), raise_on_error=False)
                self.assertEqual(not diagnostics, valid, diagnostics)

    def test_expressions_are_valid_in_1_3_numeric_attributes(self):
        SchemaValidator().load(minimal(speed="${1 + 2}"))
        with self.assertRaises(ValidationError):
            SchemaValidator().load(minimal(minor=0, speed="${1 + 2}"))

    def test_malformed_xml_is_a_located_diagnostic(self):
        with self.assertRaises(ValidationError) as raised:
            parse_xml(b"<OpenSCENARIO>\n<FileHeader>\n</OpenSCENARIO>")
        self.assertEqual(raised.exception.diagnostics[0].line, 3)

    def test_line_tracking_parser_matches_elementtree(self):
        root, lines, _ = parse_xml(os.path.join(TESTS_DIR, "..", "examples", "FollowLeadingVehicle.xosc"))
        self.assertEqual(root.tag, "OpenSCENARIO")
        self.assertEqual(lines[root.find("FileHeader")], 3)


class TestConformanceCorpus(unittest.TestCase):

    def test_shipped_1_0_examples_validate_against_the_1_0_schema(self):
        self.assertTrue(EXAMPLES)
        for path in EXAMPLES:
            with self.subTest(example=os.path.basename(path)):
                document = load_document(path)
                self.assertEqual(str(document.version), "1.0")
                self.assertEqual(SchemaValidator().validate(document, raise_on_error=False), [])

    def test_1_3_fixtures_validate_against_the_1_3_1_schema(self):
        for path in FIXTURES_1_3:
            with self.subTest(fixture=os.path.basename(path)):
                document = load_document(path)
                self.assertEqual(SchemaValidator().schema_key_for(document), "1.3.1")
                self.assertEqual(SchemaValidator().validate(document, raise_on_error=False), [])

    @unittest.skipUnless(ASAM_EXAMPLES and os.path.isdir(ASAM_EXAMPLES or ""),
                         "set OPENSCENARIO_ASAM_EXAMPLES to the unzipped ASAM examples")
    def test_asam_examples(self):
        paths = sorted(glob.glob(os.path.join(ASAM_EXAMPLES, "*.xosc")))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(example=os.path.basename(path)):
                self.assertEqual(SchemaValidator().validate_document(path, raise_on_error=False), [])


if __name__ == "__main__":
    unittest.main()
