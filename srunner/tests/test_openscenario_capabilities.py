#!/usr/bin/env python
"""The OpenSCENARIO 1.3.1 capability matrix and the build-time feature audit (no CARLA required)."""

from __future__ import absolute_import

import glob
import os
import unittest
import xml.etree.ElementTree as ET

from srunner.openscenario.execution.capabilities import (
    CAPABILITY_MATRIX, RUNTIME_STATES, capability_counts, capability_summary, capability_table_markdown)
from srunner.openscenario.execution.feature_audit import audit_document
from srunner.openscenario.parsing.loader import load_document
from srunner.openscenario.validation.schema_model import schema_model
from srunner.tests.test_openscenario_checker import (
    MISC, PEDESTRIAN, VEHICLE, document, init_teleport, private, speed_action, story)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPOSITORY = os.path.dirname(os.path.dirname(TESTS_DIR))
BUILT_DOCUMENTS = sorted(glob.glob(os.path.join(REPOSITORY, "srunner", "examples", "*.xosc")) +
                         glob.glob(os.path.join(TESTS_DIR, "fixtures", "openscenario", "*.xosc")))
# Catalog entries used by the shipped examples are built with them.
CATALOGS = sorted(glob.glob(os.path.join(REPOSITORY, "srunner", "examples", "catalogs", "*.xosc")))
DOCS = os.path.join(REPOSITORY, "Docs", "openscenario_support.md")
CONTAINERS = {"parameter_action": "ParameterAction", "variable_action": "VariableAction"}


def audit(source, catalogs=None):
    return audit_document(load_document(source.encode("utf-8")), catalogs)


def errors(diagnostics):
    return [item for item in diagnostics if item.is_error]


class TestCapabilityMatrix(unittest.TestCase):

    def test_matrix_covers_exactly_the_schema_features(self):
        extracted = set((category, element) for category, elements in schema_model("1.3.1").features().items()
                        for element in elements)
        self.assertEqual(set(CAPABILITY_MATRIX), extracted)

    def test_states_are_well_formed(self):
        for row in CAPABILITY_MATRIX.values():
            with self.subTest(element=row.element):
                self.assertIn(row.parsed, ("typed", "legacy", "schema"))
                self.assertIn(row.semantic, ("validated", "checked", "none"))
                self.assertIn(row.runtime_init, RUNTIME_STATES)
                self.assertIn(row.runtime_story, RUNTIME_STATES)
                self.assertIn(row.verification, ("executed", "built", "none"))
                self.assertIs(row.live_carla_verified, False)
                if row.parsed == "schema":
                    self.assertNotIn("legacy", (row.runtime_init, row.runtime_story))

    def test_executed_claims_name_an_existing_test(self):
        for row in CAPABILITY_MATRIX.values():
            if row.verification != "executed":
                self.assertIsNone(row.evidence)
                continue
            module, test_class, method = row.evidence.rsplit(".", 2)
            path = os.path.join(REPOSITORY, *module.split(".")) + ".py"
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            self.assertIn("class {}(".format(test_class), source, row.evidence)
            self.assertIn("def {}(".format(method), source, row.evidence)

    def test_built_claims_appear_in_a_built_document(self):
        present = set()
        for path in BUILT_DOCUMENTS + CATALOGS:
            root = ET.parse(path).getroot()
            for parent in root.iter():
                for child in parent:
                    present.add((child.tag, parent.tag))
        tags = set(tag for tag, _ in present)
        for row in CAPABILITY_MATRIX.values():
            if row.verification == "none":
                continue
            with self.subTest(element=row.element):
                if row.category in CONTAINERS:
                    self.assertIn((row.element, CONTAINERS[row.category]), present)
                else:
                    self.assertIn(row.element, tags)

    def test_documentation_table_is_generated_from_the_matrix(self):
        with open(DOCS, encoding="utf-8") as handle:
            text = handle.read().replace("\r\n", "\n")
        start = text.index("<!-- capability-table:start -->") + len("<!-- capability-table:start -->")
        end = text.index("<!-- capability-table:end -->")
        self.assertEqual(text[start:end].strip(), capability_table_markdown())
        self.assertIn(capability_summary(), text)

    def test_counts(self):
        counts = capability_counts()
        self.assertEqual(counts["features"], len(CAPABILITY_MATRIX))
        self.assertEqual(counts["live_carla_verified"], 0)
        self.assertEqual(counts["runtime:executable"] + counts["runtime:unsupported"], len(CAPABILITY_MATRIX))


class TestFeatureAudit(unittest.TestCase):

    def test_shipped_examples_and_fixtures_have_no_unsupported_features(self):
        for path in BUILT_DOCUMENTS:
            with self.subTest(path=os.path.basename(path)):
                catalogs = None
                with open(path, encoding="utf-8") as handle:
                    uses_catalogs = "CatalogReference" in handle.read()
                if uses_catalogs:
                    catalogs = {}
                    for catalog_path in glob.glob(os.path.join(os.path.dirname(path), "catalogs", "*.xosc")):
                        catalog = ET.parse(catalog_path).getroot().find("Catalog")
                        catalogs[catalog.attrib["name"]] = dict((entry.attrib["name"], entry) for entry in catalog)
                self.assertEqual(errors(audit_document(load_document(path), catalogs)), [])

    def test_unsupported_action_is_reported_with_location(self):
        source = document(stories=story(private(
            '<AppearanceAction><LightStateAction><LightType><VehicleLight vehicleLightType="lowBeam"/></LightType>'
            '<LightState mode="on"/></LightStateAction></AppearanceAction>')))
        reported = errors(audit(source))
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0].category, "unsupported_feature")
        self.assertEqual(reported[0].code, "capability:action/LightStateAction")
        self.assertIn("LightStateAction", reported[0].message)
        self.assertIsNotNone(reported[0].line)

    def test_runtime_depends_on_the_init_or_story_context(self):
        lane_change = ('<PrivateAction><LateralAction><LaneChangeAction><LaneChangeActionDynamics dynamicsShape="step" '
                       'value="0" dynamicsDimension="time"/><LaneChangeTarget><RelativeTargetLane entityRef="hero" '
                       'value="1"/></LaneChangeTarget></LaneChangeAction></LateralAction></PrivateAction>')
        in_init = audit(document(init='<Private entityRef="hero">{}</Private>'.format(lane_change)))
        self.assertIn("in the Init section", errors(in_init)[0].message)
        self.assertEqual(errors(audit(document(stories=story('<Action name="A">{}</Action>'.format(lane_change))))),
                         [])

    def test_inactive_overrides_are_accepted_and_active_ones_rejected(self):
        # OpenSCENARIO 1.0 form: the ControllerAction assigns a controller and lists the overrides.
        override = ('<ControllerAction><AssignControllerAction><Controller name="c"><Properties>'
                    '<Property name="module" value="m"/></Properties></Controller></AssignControllerAction>'
                    '<OverrideControllerValueAction><Throttle active="{}" value="0"/></OverrideControllerValueAction>'
                    '</ControllerAction>')
        self.assertEqual(errors(audit(document(stories=story(private(override.format("false")))))), [])
        reported = errors(audit(document(stories=story(private(override.format("true"))))))
        self.assertEqual([item.code for item in reported], ["capability:override_action/Throttle"])
        # OpenSCENARIO 1.3 form: an OverrideControllerValueAction on its own is never executed.
        alone = private('<ControllerAction><OverrideControllerValueAction><Throttle active="false" value="0"/>'
                        '</OverrideControllerValueAction></ControllerAction>')
        self.assertEqual([item.code for item in errors(audit(document(stories=story(alone))))],
                         ["capability:action/OverrideControllerValueAction"])

    def test_known_variants_of_supported_elements(self):
        cases = [
            private('<ControllerAction><ActivateControllerAction longitudinal="true"/></ControllerAction>'),
            private('<ActivateControllerAction lateral="true"/>'),
            private('<LongitudinalAction><LongitudinalDistanceAction entityRef="ped" timeGap="1" continuous="false" '
                    'freespace="false"/></LongitudinalAction>'),
        ]
        for action in cases:
            with self.subTest(action=action[:60]):
                self.assertTrue(errors(audit(document(stories=story(action)))))
        state = story(condition='<Condition name="C" delay="0" conditionEdge="none"><ByValueCondition>'
                      '<StoryboardElementStateCondition storyboardElementType="event" storyboardElementRef="E" '
                      'state="runningState"/></ByValueCondition></Condition>')
        self.assertIn("runningState", errors(audit(document(stories=state)))[0].message)
        relative = init_teleport("hero", '<WorldPosition x="0" y="0"/>') + \
            '<Private entityRef="ped"><PrivateAction><LongitudinalAction><SpeedAction><SpeedActionDynamics ' \
            'dynamicsShape="step" value="0" dynamicsDimension="time"/><SpeedActionTarget><RelativeTargetSpeed ' \
            'entityRef="hero" value="1" speedTargetValueType="delta" continuous="false"/></SpeedActionTarget>' \
            '</SpeedAction></LongitudinalAction></PrivateAction></Private>'
        self.assertIn("RelativeTargetSpeed", errors(audit(document(init=relative)))[0].message)

    def test_unsupported_positions_entities_and_shapes(self):
        geo = audit(document(init=init_teleport("hero", '<GeoPosition latitudeDeg="1" longitudeDeg="2"/>')))
        self.assertEqual(errors(geo)[0].code, "capability:position/GeoPosition")
        external = audit(document(entities=VEHICLE.format(name="hero", controllers="") +
                                  '<ScenarioObject name="ext"><ExternalObjectReference name="x"/></ScenarioObject>'))
        self.assertEqual(errors(external)[0].code, "capability:entity/ExternalObjectReference")

    def test_catalog_entries_are_audited_and_must_be_available(self):
        source = document(entities=PEDESTRIAN + '<ScenarioObject name="cat"><CatalogReference catalogName="Vehicles" '
                          'entryName="car"/></ScenarioObject>')
        missing = errors(audit(source, {}))
        self.assertEqual(missing[0].category, "backend_capability_error")
        external = {"Vehicles": {"car": ET.fromstring('<ExternalObjectReference name="car"/>')}}
        reported = errors(audit(source, external))
        self.assertEqual(reported[0].code, "capability:entity/ExternalObjectReference")
        self.assertIn("catalog entry Vehicles/car", reported[0].message)

    def test_unmapped_attributes_are_approximation_warnings(self):
        source = document(init='<GlobalAction><EnvironmentAction><Environment name="e"><Weather '
                          'fractionalCloudCover="zeroOktas"><Sun illuminance="100" azimuth="0" elevation="1"/>'
                          '</Weather></Environment></EnvironmentAction></GlobalAction>')
        diagnostics = audit(source)
        self.assertEqual(errors(diagnostics), [])
        self.assertEqual(sorted(item.message.split(" ")[0] for item in diagnostics),
                         ["Sun@illuminance", "Weather@fractionalCloudCover"])
        self.assertTrue(all(item.category == "approximation_warning" for item in diagnostics))

    def test_storyboard_stop_trigger_groups_cannot_mix_criteria(self):
        source = document().replace(
            '<StopTrigger/>', '<StopTrigger><ConditionGroup><Condition name="criteria_CollisionTest" delay="0" '
            'conditionEdge="rising"><ByValueCondition><ParameterCondition parameterRef="" value="" rule="lessThan"/>'
            '</ByValueCondition></Condition><Condition name="Time" delay="0" conditionEdge="rising">'
            '<ByValueCondition><SimulationTimeCondition value="1" rule="greaterThan"/></ByValueCondition>'
            '</Condition></ConditionGroup></StopTrigger>')
        self.assertIn("cannot mix", errors(audit(source))[0].message)

    def test_non_scenario_documents_are_not_executable(self):
        source = ('<OpenSCENARIO><FileHeader revMajor="1" revMinor="3" date="2026-10-14T12:00:00" description="d" '
                  'author="a"/><Catalog name="c"/></OpenSCENARIO>')
        self.assertIn("contains a Catalog", errors(audit(source))[0].message)

    def test_supported_documents_have_no_findings(self):
        source = document(entities=VEHICLE.format(name="hero", controllers="") + MISC.format(controllers=""),
                          stories=story(speed_action(10)))
        self.assertEqual(audit(source), [])


if __name__ == "__main__":
    unittest.main()
