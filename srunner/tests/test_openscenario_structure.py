#!/usr/bin/env python
"""Empty choice elements and unresolved entity references, for every document version.

The SemanticValidator tests need no CARLA; the configuration tests need the
CARLA mocks (``srunner/tests/carla_mocks`` first on PYTHONPATH) and are
skipped otherwise.
"""

from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from srunner.openscenario.parsing.loader import load_document
from srunner.openscenario.validation.diagnostics import Diagnostic, ValidationError
from srunner.openscenario.validation.schema import SchemaValidator
from srunner.openscenario.validation.semantic import SemanticValidator

try:
    import carla
    from srunner.scenarioconfigs.openscenario_configuration import OpenScenarioConfiguration
    from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
    MOCKED_CARLA = os.path.join("carla_mocks", "carla.py") in (getattr(carla, "__file__", None) or "")
except ImportError:  # pragma: no cover - depends on the local CARLA installation
    MOCKED_CARLA = False

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLE_1_0 = os.path.join(TESTS_DIR, "..", "examples", "FollowLeadingVehicle.xosc")
FIXTURE_1_3 = os.path.join(TESTS_DIR, "fixtures", "openscenario", "conformance_1_3_1.xosc")


def emptied(root, path):
    element = root.find(path)
    for child in list(element):
        element.remove(child)
    return element


def removed(root, parent_path, tag):
    parent = root.find(parent_path)
    parent.remove(parent.find(tag))
    return parent


class _Documents(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.directory)

    def _write(self, root):
        path = os.path.join(self.directory, "variant.xosc")
        ET.ElementTree(root).write(path)
        return path

    def _diagnostics(self, root, code):
        diagnostics = SemanticValidator().validate(load_document(self._write(root)), raise_on_error=False)
        return [item for item in diagnostics if item.code == code]


class TestEmptyChoices(_Documents):

    def _empty(self, root):
        return self._diagnostics(root, Diagnostic.EMPTY_CHOICE)

    def test_shipped_examples_and_fixtures_have_no_empty_choice(self):
        examples = os.path.join(TESTS_DIR, "..", "examples")
        paths = [os.path.join(examples, name) for name in sorted(os.listdir(examples)) if name.endswith(".xosc")]
        for path in paths + [FIXTURE_1_3]:
            with self.subTest(document=os.path.basename(path)):
                self.assertEqual(self._empty(ET.parse(path).getroot()), [])

    def test_1_0_schema_accepts_what_the_rule_rejects(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        emptied(root, ".//ByValueCondition")
        self.assertEqual(SchemaValidator().validate(load_document(self._write(root)), raise_on_error=False), [])
        self.assertEqual([item.source.tag for item in self._empty(root)], ["ByValueCondition"])

    def test_empty_by_value_condition(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        removed(root, ".//ByValueCondition[SimulationTimeCondition]", "SimulationTimeCondition")
        diagnostics = self._empty(root)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0].category, "semantic_error")
        self.assertIn("ByValueCondition requires one of ParameterCondition", diagnostics[0].message)

    def test_condition_without_by_value_condition(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        condition = root.find(".//ByValueCondition/..")
        condition.remove(condition.find("ByValueCondition"))
        self.assertEqual([item.source.attrib for item in self._empty(root)], [condition.attrib])

    def test_private_action_without_longitudinal_action(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        removed(root, ".//PrivateAction[LongitudinalAction]", "LongitudinalAction")
        self.assertEqual([item.source.tag for item in self._empty(root)], ["PrivateAction"])

    def test_scenario_object_without_entity(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        removed(root, "Entities/ScenarioObject[@name='adversary']", "Vehicle")
        self.assertEqual([item.source.attrib for item in self._empty(root)], [{"name": "adversary"}])

    def test_1_3_documents_are_checked_too(self):
        root = ET.parse(FIXTURE_1_3).getroot()
        emptied(root, ".//ByValueCondition")
        self.assertEqual([item.source.tag for item in self._empty(root)], ["ByValueCondition"])

    def test_optional_choices_are_not_reported(self):
        root = ET.parse(FIXTURE_1_3).getroot()
        override = ET.SubElement(root.find(".//Init/Actions/Private/PrivateAction/.."), "PrivateAction")
        action = ET.SubElement(ET.SubElement(override, "ControllerAction"), "OverrideControllerValueAction")
        ET.SubElement(action, "Brake", value="0", active="false")
        self.assertEqual(self._empty(root), [])


class TestEntityReferences(_Documents):

    def _unknown(self, root):
        return [item for item in self._diagnostics(root, Diagnostic.UNKNOWN_REFERENCE)
                if "ScenarioObject or EntitySelection" in item.message]

    def test_every_usage_is_checked(self):
        cases = (
            ("Storyboard/Init/Actions/Private", "entityRef"),
            (".//ManeuverGroup/Actors/EntityRef", "entityRef"),
            (".//TriggeringEntities/EntityRef", "entityRef"),
            (".//RelativeDistanceCondition", "entityRef"),
            (".//RelativeRoadPosition", "entityRef"),
        )
        for path, attribute in cases:
            with self.subTest(path=path):
                root = ET.parse(EXAMPLE_1_0).getroot()
                element = root.find(path)
                self.assertIsNotNone(element, path)
                element.set(attribute, "ghost")
                diagnostics = self._unknown(root)
                self.assertEqual([(item.source.tag, item.source.attrib[attribute]) for item in diagnostics],
                                 [(element.tag, "ghost")])

    def test_master_entity_and_trailer_references(self):
        root = ET.parse(FIXTURE_1_3).getroot()
        actions = root.find(".//Event/Action/PrivateAction/..")
        synchronize = ET.fromstring(
            '<PrivateAction><SynchronizeAction masterEntityRef="ghost">'
            '<TargetPositionMaster><WorldPosition x="0" y="0"/></TargetPositionMaster>'
            '<TargetPosition><WorldPosition x="1" y="0"/></TargetPosition></SynchronizeAction></PrivateAction>')
        trailer = ET.fromstring('<PrivateAction><ConnectTrailerAction trailerRef="trailer"/></PrivateAction>')
        actions.extend([synchronize, trailer])
        self.assertEqual(sorted(item.source.tag for item in self._unknown(root)),
                         ["ConnectTrailerAction", "SynchronizeAction"])

    def test_parameter_and_prefixed_references_resolve(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        ET.SubElement(root.find("ParameterDeclarations"), "ParameterDeclaration",
                      name="Owner", parameterType="string", value="hero")
        root.find("Storyboard/Init/Actions/Private").set("entityRef", "$Owner")
        root.find(".//ManeuverGroup/Actors/EntityRef").set("entityRef", "Entities::adversary")
        self.assertEqual(self._unknown(root), [])

    def test_parameters_resolve_in_the_scope_of_the_reference(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        ET.SubElement(root.find("ParameterDeclarations"), "ParameterDeclaration",
                      name="Owner", parameterType="string", value="ghost")
        story = root.find("Storyboard/Story")
        story.insert(0, ET.fromstring('<ParameterDeclarations><ParameterDeclaration name="Owner" '
                                      'parameterType="string" value="adversary"/></ParameterDeclarations>'))
        story.find(".//Actors/EntityRef").set("entityRef", "$Owner")
        self.assertEqual(self._unknown(root), [])
        root.find("Storyboard/Init/Actions/Private").set("entityRef", "$Owner")
        self.assertEqual([item.source.tag for item in self._unknown(root)], ["Private"])

    def test_parameter_override_is_used(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        ET.SubElement(root.find("ParameterDeclarations"), "ParameterDeclaration",
                      name="Owner", parameterType="string", value="ghost")
        root.find("Storyboard/Init/Actions/Private").set("entityRef", "$Owner")
        document = load_document(self._write(root))
        validator = SemanticValidator(parameter_overrides={"Owner": "hero"})
        self.assertEqual([item for item in validator.validate(document, raise_on_error=False)
                          if item.code == Diagnostic.UNKNOWN_REFERENCE], [])

    def test_parameter_naming_no_entity(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        ET.SubElement(root.find("ParameterDeclarations"), "ParameterDeclaration",
                      name="Owner", parameterType="string", value="ghost")
        root.find("Storyboard/Init/Actions/Private").set("entityRef", "$Owner")
        self.assertIn("'ghost'", self._unknown(root)[0].message)


@unittest.skipUnless(MOCKED_CARLA, "requires srunner/tests/carla_mocks first on PYTHONPATH")
class TestConfigurationRejectsStructuralErrors(_Documents):

    def tearDown(self):
        CarlaDataProvider.cleanup()
        super(TestConfigurationRejectsStructuralErrors, self).tearDown()

    def _load(self, root):
        return OpenScenarioConfiguration(self._write(root), carla.Client(), {})

    def test_empty_choices_in_a_1_0_document(self):
        for path, tag in ((".//ByValueCondition[SimulationTimeCondition]", "SimulationTimeCondition"),
                          (".//PrivateAction[LongitudinalAction]", "LongitudinalAction")):
            with self.subTest(removed=tag):
                root = ET.parse(EXAMPLE_1_0).getroot()
                removed(root, path, tag)
                with self.assertRaises(ValidationError) as raised:
                    self._load(root)
                self.assertIn(Diagnostic.EMPTY_CHOICE, [item.code for item in raised.exception.diagnostics])

    def test_empty_choice_in_a_catalog(self):
        catalogs = os.path.join(TESTS_DIR, "..", "examples", "catalogs")
        catalog = ET.parse(os.path.join(catalogs, "ManeuverCatalog.xosc")).getroot()
        action = catalog.find(".//PrivateAction")
        for child in list(action):
            action.remove(child)
        catalog_directory = os.path.join(self.directory, "catalogs")
        os.mkdir(catalog_directory)
        ET.ElementTree(catalog).write(os.path.join(catalog_directory, "ManeuverCatalog.xosc"))
        root = ET.parse(EXAMPLE_1_0).getroot()
        locations = root.find("CatalogLocations")
        for child in list(locations):
            locations.remove(child)
        ET.SubElement(ET.SubElement(locations, "ManeuverCatalog"), "Directory", path=catalog_directory)
        with self.assertRaises(ValidationError) as raised:
            self._load(root)
        self.assertEqual([item.code for item in raised.exception.diagnostics], [Diagnostic.EMPTY_CHOICE])

    def test_unknown_entity_in_a_1_0_document(self):
        root = ET.parse(EXAMPLE_1_0).getroot()
        root.find("Storyboard/Init/Actions/Private").set("entityRef", "ghost")
        with self.assertRaises(ValidationError) as raised:
            self._load(root)
        self.assertEqual([item.code for item in raised.exception.diagnostics], [Diagnostic.UNKNOWN_REFERENCE])
        self.assertIsNotNone(raised.exception.diagnostics[0].line)


if __name__ == "__main__":
    unittest.main()
