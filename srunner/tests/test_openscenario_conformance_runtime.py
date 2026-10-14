#!/usr/bin/env python
"""OpenSCENARIO 1.3.1 documents through OpenScenarioConfiguration and OpenScenario.

Runs against the mocked CARLA module in ``srunner/tests/carla_mocks`` (put it
first on PYTHONPATH); no CARLA server is involved.
"""

# pylint: disable=protected-access

from __future__ import absolute_import

import os
import shutil
import tempfile
import unittest
from unittest import mock

import carla
import py_trees

from srunner.openscenario.compatibility.atomics import ExecuteSemanticAction, SemanticValueCondition
from srunner.openscenario.execution.registry import UnsupportedFeatureError
from srunner.openscenario.model.references import Route
from srunner.openscenario.validation.diagnostics import Diagnostic, ValidationError
from srunner.scenarioconfigs.openscenario_configuration import OpenScenarioConfiguration
from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
from srunner.scenariomanager.scenarioatomics.atomic_behaviors import ChangeActorTargetSpeed, ChangeActorWaypoints
from srunner.scenariomanager.scenarioatomics.atomic_trigger_conditions import RelativeAngleToActor, RelativeClearance
from srunner.scenariomanager.timer import GameTime
from srunner.scenarios.open_scenario import OpenScenario
from srunner.tools.openscenario_parser import OpenScenarioParser

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(TESTS_DIR, "fixtures", "openscenario", "conformance_1_3_1.xosc")
MOCKED_CARLA = os.path.join("carla_mocks", "carla.py") in getattr(carla, "__file__", "")


class _Waypoint(object):
    road_id, section_id, lane_id, lane_width = 1, 0, -1, 3.5
    transform = carla.Transform()


class _Map(object):

    @staticmethod
    def get_waypoint(location):
        return _Waypoint()


@unittest.skipUnless(MOCKED_CARLA, "requires srunner/tests/carla_mocks first on PYTHONPATH")
class TestOpenScenario131Conformance(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        py_trees.blackboard.Blackboard().__dict__.clear()

    def tearDown(self):
        CarlaDataProvider.cleanup()
        OpenScenarioParser.set_execution_context(None)
        shutil.rmtree(self.directory)

    def _variant(self, old, new):
        with open(FIXTURE, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn(old, source)
        path = os.path.join(self.directory, "variant.xosc")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source.replace(old, new, 1))
        return path

    @staticmethod
    def _load(path=FIXTURE):
        client = carla.Client()
        config = OpenScenarioConfiguration(path, client, {})
        CarlaDataProvider.set_client(client)
        ego_vehicles = [CarlaDataProvider.request_new_actor(vehicle.model, vehicle.transform, vehicle.rolename,
                                                            color=vehicle.color, actor_category=vehicle.category)
                        for vehicle in config.ego_vehicles]
        return OpenScenario(world=client.get_world(), ego_vehicles=ego_vehicles, config=config, config_file=path,
                            timeout=100000)

    def _node(self, scenario, name, node_type=None):
        matches = [node for node in scenario.scenario_tree.iterate()
                   if node.name == name and (node_type is None or isinstance(node, node_type))]
        self.assertEqual(len(matches), 1, "expected one node {!r}, got {}".format(name, matches))
        return matches[0]

    @staticmethod
    def _actor(scenario, name):
        return next(actor for actor in scenario.other_actors + scenario.ego_vehicles
                    if actor.attributes["role_name"] == name)

    def test_document_reaches_the_runtime(self):
        scenario = self._load()
        config = scenario.config
        self.assertEqual(str(config.document.version), "1.3")
        actors = dict((actor.rolename, actor) for actor in config.other_actors + config.ego_vehicles)
        self.assertEqual(actors["npc"].speed, 10.0)
        self.assertEqual(actors["npc"].transform.location.x, 10.0)
        self.assertEqual((actors["parked"].transform.location.x, actors["parked"].transform.location.y), (20.0, 5.0))
        self.assertEqual(CarlaDataProvider.get_osc_global_param_value("$TargetSpeed"), 10.0)

        accelerate = self._node(scenario, "AccelerateAction", ChangeActorTargetSpeed)
        self.assertEqual(float(accelerate._target_speed), 10.0)
        route = self._node(scenario, "FollowRouteAction", ChangeActorWaypoints)
        self.assertIsInstance(route.route, Route)
        self.assertEqual([strategy for _, strategy in route._waypoints], ["shortest", "shortest", "fastest"])
        profile = self._node(scenario, "ProfileAction", py_trees.composites.Sequence)
        self.assertEqual(profile.entries, [(5.0, 2.0), (10.0, None)])
        trajectory = self._node(scenario, "TrajectoryAction", ChangeActorWaypoints)
        self.assertEqual(trajectory._times, [0.0, 4.0])

    def test_variables_and_parameters_drive_conditions(self):
        scenario = self._load()
        variables = scenario.execution_context.evaluation.variables
        stage = self._node(scenario, "StageOne", SemanticValueCondition)
        stage.tick_once()
        self.assertEqual(stage.status, py_trees.common.Status.RUNNING)

        self._node(scenario, "ParametersInit", py_trees.composites.Sequence).tick_once()
        self.assertEqual(variables.get("Stage"), 1)
        stage.tick_once()
        self.assertEqual(stage.status, py_trees.common.Status.SUCCESS)

        advance = self._node(scenario, "AdvanceStage", ExecuteSemanticAction)
        advance.tick_once()
        self.assertEqual(advance.status, py_trees.common.Status.SUCCESS)
        self.assertEqual(variables.get("Stage"), 2)
        mode = self._node(scenario, "ModeIdle", SemanticValueCondition)
        mode.tick_once()
        self.assertEqual(mode.status, py_trees.common.Status.SUCCESS)

    def test_relative_conditions_tick(self):
        scenario = self._load()
        hero, npc = self._actor(scenario, "hero"), self._actor(scenario, "npc")
        poses = {hero.id: carla.Transform(carla.Location(0, 2, 0), carla.Rotation(yaw=0)),
                 npc.id: carla.Transform(carla.Location(10, 2, 0), carla.Rotation(yaw=0))}
        transform = staticmethod(lambda actor: poses[actor.id])
        angle = self._node(scenario, "SameHeading", RelativeAngleToActor)
        clearance = self._node(scenario, "ClearAhead", RelativeClearance)
        with mock.patch.object(CarlaDataProvider, "get_transform", transform), \
                mock.patch.object(CarlaDataProvider, "get_map", return_value=_Map()), \
                mock.patch.object(RelativeClearance, "_transform", transform):
            angle.tick_once()
            self.assertEqual(angle.status, py_trees.common.Status.SUCCESS)
            clearance.tick_once()
            self.assertEqual(clearance.status, py_trees.common.Status.SUCCESS)

            poses[hero.id] = carla.Transform(carla.Location(12, 2, 0), carla.Rotation(yaw=90))
            angle.tick_once()
            self.assertEqual(angle.status, py_trees.common.Status.RUNNING)
            clearance.tick_once()
            self.assertEqual(clearance.status, py_trees.common.Status.RUNNING)

    def test_storyboard_stop_trigger_ends_the_scenario(self):
        scenario = self._load()
        stop = self._node(scenario, "StoryboardStopTrigger")
        with mock.patch.object(GameTime, "_current_game_time", 0.0):
            stop.tick_once()
        self.assertEqual(stop.status, py_trees.common.Status.RUNNING)
        with mock.patch.object(GameTime, "_current_game_time", 61.0):
            stop.tick_once()
        self.assertEqual(stop.status, py_trees.common.Status.SUCCESS)
        self.assertEqual(self._node(scenario, "Storyboard", py_trees.composites.Parallel).policy,
                         py_trees.common.ParallelPolicy.SUCCESS_ON_ONE)

    def test_schema_violations_are_reported_with_their_location(self):
        with self.assertRaises(ValidationError) as raised:
            self._load(self._variant('<Entities>', '<Entities bogus="1">'))
        diagnostic = raised.exception.diagnostics[0]
        self.assertEqual(diagnostic.category, "schema_error")
        self.assertEqual(diagnostic.path, "/OpenSCENARIO/Entities")
        self.assertIsNotNone(diagnostic.line)

    def test_checker_rule_violations_abort_the_build(self):
        with self.assertRaises(ValidationError) as raised:
            self._load(self._variant('variableRef="Mode"', 'variableRef="Missing"'))
        rules = set(item.rule for item in raised.exception.diagnostics)
        self.assertIn("asam.net:xosc:1.2.0:reference_control.resolvable_variable_reference", rules)

    def test_expression_errors_in_numeric_attributes_abort_the_build(self):
        with self.assertRaises(ValidationError) as raised:
            self._load(self._variant('dy="3"', 'dy="${1 / 0}"'))
        rules = [item.rule for item in raised.exception.diagnostics]
        self.assertEqual(rules, ["asam.net:xosc:1.1.0:expressions.arithmetic_errors"])

    def test_unsupported_features_are_reported_at_build_time(self):
        light = ('<Action name="Lights"><PrivateAction><AppearanceAction><LightStateAction><LightType>'
                 '<VehicleLight vehicleLightType="lowBeam"/></LightType><LightState mode="on"/></LightStateAction>'
                 '</AppearanceAction></PrivateAction></Action>')
        with self.assertRaises(UnsupportedFeatureError) as raised:
            self._load(self._variant('<Action name="AdvanceStage">', light + '<Action name="AdvanceStage">'))
        diagnostic = raised.exception.diagnostics[0]
        self.assertEqual(diagnostic.code, "capability:action/LightStateAction")
        self.assertIn("Event[@name='Accelerate']", diagnostic.path)

    def test_unsupported_versions_are_rejected(self):
        with self.assertRaises(ValidationError) as raised:
            self._load(self._variant('revMinor="3"', 'revMinor="2"'))
        self.assertEqual(raised.exception.diagnostics[0].code, Diagnostic.UNSUPPORTED_VERSION)


if __name__ == "__main__":
    unittest.main()
