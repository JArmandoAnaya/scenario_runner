#!/usr/bin/env python
"""Optional OpenSCENARIO 1.3 elements read by the legacy OpenScenarioParser.

Runs against the mocked CARLA module in ``srunner/tests/carla_mocks`` or the
real ``carla`` wheel; no CARLA server is needed.
"""

from __future__ import absolute_import

import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from srunner.tools import openscenario_parser
from srunner.tools.openscenario_parser import OpenScenarioParser


class _Weather(object):

    def __init__(self, carla_weather, dtime=None, animation=False):
        self.carla_weather = carla_weather
        self.dtime = dtime
        self.animation = animation


def weather_of(environment):
    action = ET.fromstring('<PrivateAction><EnvironmentAction><Environment name="env">{}</Environment>'
                           '</EnvironmentAction></PrivateAction>'.format(environment))
    with mock.patch.object(openscenario_parser, "Weather", _Weather):
        return OpenScenarioParser.get_weather_from_env_action(action, {})


class TestOptionalEnvironmentElements(unittest.TestCase):

    def test_environment_without_weather_or_time_of_day_uses_defaults(self):
        weather = weather_of("")
        self.assertEqual(weather.carla_weather.precipitation, 0)
        self.assertIsNone(weather.dtime)

    def test_weather_without_sun_fog_or_precipitation_uses_defaults(self):
        weather = weather_of('<Weather cloudState="free"/>')
        self.assertEqual(weather.carla_weather.cloudiness, 100)
        self.assertEqual(weather.carla_weather.fog_distance, float("inf"))

    def test_rain_without_intensity_is_dry(self):
        weather = weather_of('<Weather><Precipitation precipitationType="rain"/></Weather>')
        self.assertEqual(weather.carla_weather.precipitation, 0)

    def test_snow_is_rejected(self):
        with self.assertRaises(AttributeError):
            weather_of('<Weather><Precipitation precipitationType="snow" intensity="0.5"/></Weather>')

    def test_time_of_day_is_still_read(self):
        weather = weather_of('<TimeOfDay animation="true" dateTime="2026-10-14T12:30:00"/>')
        self.assertEqual((weather.dtime.hour, weather.dtime.minute, weather.animation), (12, 30, True))


class TestOptionalControllerElements(unittest.TestCase):

    def test_controller_action_without_override_values(self):
        action = ET.fromstring(
            '<ControllerAction><AssignControllerAction><Controller name="c"><Properties>'
            '<Property name="module" value="external_control"/><Property name="port" value="1"/>'
            '</Properties></Controller></AssignControllerAction></ControllerAction>')
        self.assertEqual(OpenScenarioParser.get_controller(action, {}), ("external_control", {"port": "1"}))


if __name__ == "__main__":
    unittest.main()
