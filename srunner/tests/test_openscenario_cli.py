#!/usr/bin/env python
"""Rejected OpenSCENARIO files through the scenario_runner.py entry point.

Runs against the mocked CARLA module in ``srunner/tests/carla_mocks`` (put it
first on PYTHONPATH); no CARLA server is involved.
"""

# pylint: disable=protected-access

from __future__ import absolute_import

import argparse
import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import carla
import py_trees

from srunner.openscenario.execution.registry import UnsupportedFeatureError
from srunner.openscenario.validation.diagnostics import Diagnostic
from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
from srunner.scenarios.open_scenario import OpenScenario
from srunner.tools.openscenario_parser import OpenScenarioParser

MOCKED_CARLA = os.path.join("carla_mocks", "carla.py") in getattr(carla, "__file__", "")
if MOCKED_CARLA:
    import scenario_runner

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(TESTS_DIR, "fixtures", "openscenario", "conformance_1_3_1.xosc")
LIGHT_STATE_ACTION = (
    '<Action name="Lights"><PrivateAction><AppearanceAction><LightStateAction><LightType>'
    '<VehicleLight vehicleLightType="lowBeam"/></LightType><LightState mode="on"/></LightStateAction>'
    '</AppearanceAction></PrivateAction></Action><Action name="AdvanceStage">')


def runner_arguments(path):
    return argparse.Namespace(
        openscenario=path, openscenarioparams=None, route=None, openscenario2=None, scenario=None, agent=None,
        sync=False, waitForEgo=False, reloadWorld=False, record="", debug=False, randomize=False,
        trafficManagerPort="8000", trafficManagerSeed="0", frameRate=20.0, timeout="10.0", output=False,
        file=False, junit=False, json=False, outputDir="", repetitions=1)


@unittest.skipUnless(MOCKED_CARLA, "requires srunner/tests/carla_mocks first on PYTHONPATH")
class TestRejectedOpenScenarioFiles(unittest.TestCase):

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
    def _runner(path):
        runner = scenario_runner.ScenarioRunner.__new__(scenario_runner.ScenarioRunner)
        runner._args = runner_arguments(path)
        runner.client = carla.Client()
        runner.client.get_trafficmanager = mock.Mock(return_value=mock.Mock())
        runner.world = None
        runner.manager = mock.Mock()
        runner.finished = False
        runner.ego_vehicles = []
        runner.agent_instance = None
        runner._shutdown_requested = False
        return runner

    def _run(self, path):
        """Run the file through ScenarioRunner.run(); return (result, stdout, stderr)."""
        runner = self._runner(path)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = runner.run()
        return runner, result, stdout.getvalue(), stderr.getvalue()

    def _assert_rejected(self, path, expected):
        runner, result, stdout, stderr = self._run(path)
        self.assertFalse(result)
        self.assertNotIn("Traceback", stdout + stderr)
        self.assertIn("The OpenSCENARIO file {} was rejected:".format(path), stdout)
        self.assertIn(expected, stdout)
        self.assertFalse(runner.manager.run_scenario.called)
        return runner, stdout

    def test_schema_violation(self):
        self._assert_rejected(self._variant('<Entities>', '<Entities bogus="1">'), "[schema_error")

    def test_division_by_zero_in_a_numeric_attribute(self):
        self._assert_rejected(self._variant('dy="3"', 'dy="${1 / 0}"'), "expressions.arithmetic_errors")

    def test_missing_file_header(self):
        path = self._variant('<FileHeader', '<Ignored')
        self._assert_rejected(path, "missing FileHeader")

    def test_unsupported_element(self):
        self._assert_rejected(self._variant('<Action name="AdvanceStage">', LIGHT_STATE_ACTION),
                              "LightStateAction")

    def test_bad_trajectory_is_rejected_after_the_actors_are_spawned(self):
        destroyed = []
        removed = []
        original_remove = CarlaDataProvider.remove_actor_by_id

        def remove(actor_id):
            removed.append(actor_id)
            return original_remove(actor_id)

        with mock.patch.object(carla.Vehicle, "destroy", lambda actor: destroyed.append(actor.id), create=True), \
                mock.patch.object(CarlaDataProvider, "remove_actor_by_id", side_effect=remove):
            runner, stdout = self._assert_rejected(
                self._variant('<Vertex time="0">', '<Vertex time="100">'), "vertex times must be non-decreasing")
        self.assertEqual(runner.ego_vehicles, [])
        self.assertIn("Destroying ego vehicle", stdout)
        self.assertTrue(removed, "the non-ego actors spawned before the error are removed")
        self.assertTrue(set(removed) < set(destroyed))
        self.assertEqual(len(destroyed), len(removed) + 1, "the ego vehicle is destroyed as well")

    def test_unsupported_trajectory_found_while_building(self):
        self._assert_rejected(self._variant('name="ConformanceTrajectory" closed="false"',
                                            'name="ConformanceTrajectory" closed="true"'), "Closed trajectories")

    def test_other_scenario_errors_keep_the_traceback(self):
        with mock.patch.object(OpenScenario, "_create_behavior", side_effect=KeyError("bug")):
            _, result, stdout, stderr = self._run(FIXTURE)
        self.assertFalse(result)
        self.assertIn("The scenario cannot be loaded", stdout)
        self.assertIn("Traceback", stderr)

    def test_build_time_diagnostics_are_listed(self):
        error = UnsupportedFeatureError(None, diagnostics=[
            Diagnostic("unsupported_feature", "first"), Diagnostic("unsupported_feature", "second")])
        with mock.patch.object(OpenScenario, "_create_behavior", side_effect=error):
            _, result, stdout, _ = self._run(FIXTURE)
        self.assertFalse(result)
        self.assertIn("  [unsupported_feature] first\n  [unsupported_feature] second\n", stdout)


@unittest.skipUnless(MOCKED_CARLA, "requires srunner/tests/carla_mocks first on PYTHONPATH")
class TestExitStatus(unittest.TestCase):

    def _main(self, runner_class):
        argv = ["scenario_runner.py", "--openscenario", FIXTURE]
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("sys.argv", argv), mock.patch.object(scenario_runner, "ScenarioRunner", runner_class), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            return scenario_runner.main()

    def test_exception_escaping_the_runner_fails(self):
        self.assertTrue(self._main(mock.Mock(side_effect=RuntimeError("no server"))))

    def test_exception_while_running_fails(self):
        runner = mock.Mock()
        runner.return_value.run.side_effect = RuntimeError("lost connection")
        self.assertTrue(self._main(runner))

    def test_rejected_file_fails(self):
        runner = mock.Mock()
        runner.return_value.run.return_value = False
        self.assertTrue(self._main(runner))

    def test_successful_run_succeeds(self):
        runner = mock.Mock()
        runner.return_value.run.return_value = True
        self.assertFalse(self._main(runner))


if __name__ == "__main__":
    unittest.main()
