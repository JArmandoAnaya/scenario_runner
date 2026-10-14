#!/usr/bin/env python
"""Annex C checker rules: registry coverage and a positive and a negative case per implemented rule.

No CARLA is required.
"""

# pylint: disable=too-many-public-methods

from __future__ import absolute_import

import glob
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

from srunner.openscenario.parsing.loader import load_document
from srunner.openscenario.validation.checker import (
    NOT_IMPLEMENTED, RULES, Checker, rule_coverage)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = sorted(glob.glob(os.path.join(TESTS_DIR, "..", "examples", "*.xosc")))
FIXTURES = sorted(glob.glob(os.path.join(TESTS_DIR, "fixtures", "openscenario", "*.xosc")))
A = "asam.net:xosc:"

# Every rule of ASAM OpenSCENARIO XML 1.3.1 Annex C, in the order of the standard.
ANNEX_C = [
    "1.0.0:general.file_ending", "1.2.0:general.animation_constraint_pedestrian",
    "1.2.0:general.animation_constraint_vehicle", "1.2.0:general.animation_constraint_misc_object_external_reference",
    "1.1.0:data_type.distances_are_not_negative", "1.0.0:data_type.condition_delay_not_negative",
    "1.0.0:data_type.phase_duration_positive", "1.0.0:data_type.time_format",
    "1.2.0:data_type.variable_correctly_typed", "1.2.0:data_type.variable_modification_or_comparison_possible",
    "1.2.0:distance.lateral_distance_disconnection", "1.0.0:naming.no_double_colon_prefix_in_names",
    "1.0.0:naming.parameter_declaration_name_prefix_reserved", "1.1.0:naming.parameter_declaration_parameter_name",
    "1.0.0:naming.unique_element_names_on_same_level", "1.1.0:parameters.parameter_declaration_parameter_scope",
    "1.1.0:parameters.parameter_declaration_parameter_reference_deadlocks",
    "1.0.0:parameters.parameter_declaration_parameter_type_inference", "1.1.0:positioning.geodetic_datum_defined",
    "1.2.0:positioning.longitudinal_distance_requirements", "1.2.0:positioning.lateral_distance_requirements",
    "1.2.0:positioning.distance_action_trajectory_reachability",
    "1.0.0:positioning.positions_shall_not_introduce_dependency_cycles",
    "1.0.0:positioning.road_lane_offset_in_bounds", "1.0.0:reference_control.road_network_availability",
    "1.0.0:reference_control.road_network_reference", "1.0.0:reference_control.road_lane_exists",
    "1.0.0:reference_control.controller_assignment", "1.2.0:reference_control.controller_ambiguity",
    "1.2.0:reference_control.lightstateaction_light_type", "1.2.0:reference_control.lightstateaction_lightstate_on_off",
    "1.2.0:reference_control.lightstateaction_lightstate_flashing",
    "1.2.0:reference_control.resolvable_variable_reference",
    "1.0.0:reference_control.traffic_signal_condition_references",
    "1.0.0:reference_control.traffic_signal_controller_action_references",
    "1.0.0:reference_control.traffic_signal_controller_condition_references",
    "1.0.0:reference_control.traffic_signal_controller_references",
    "1.0.0:reference_control.traffic_signal_state_action_references",
    "1.0.0:reference_control.traffic_signal_state_references", "1.0.0:reference_control.check_varied_parameters",
    "1.1.0:reference_control.single_or_multi_parameters", "1.0.0:reference_control.catalog_reference_resolvability",
    "1.0.0:reference_control.catalogs_referenced_by_directory",
    "1.0.0:reference_control.resolvable_storyboard_element_ref", "1.1.0:general.references_to_scenario_object",
    "1.1.0:general.homogeneous_references_to_entity_selection", "1.1.0:reference_control.traffic_name_exists",
    "1.0.0:reference_control.override_controller_action_only_allows_vehicles",
    "1.0.0:routing.ambiguous_route_waypoints", "1.0.0:routing.route_waypoints_locations",
    "1.0.0:routing.cardinality_of_control_points_in_nurbs", "1.0.0:routing.trajectory_timing_exists_if_requested",
    "1.1.0:routing.offset_should_be_less_than_trajectory_length",
    "1.0.0:scenario_logic.invalid_elements_if_no_road_network", "1.2.0:scenario_logic.controller_activation",
    "1.2.0:scenario_logic.targetspeed_maxspeed_speedprofileaction",
    "1.2.0:scenario_logic.targetspeed_maxspeed_general", "1.0.0:scenario_logic.trajectory_curvature_vs_steering_angle",
    "1.0.0:xml.valid_schema", "1.1.0:expressions.evaluation_of_expressions_possible",
    "1.1.0:expressions.allowed_operators", "1.1.0:expressions.arguments_of_operators",
    "1.1.0:expressions.type_of_boolean", "1.1.0:expressions.type_casting", "1.1.0:expressions.nan_or_infinity",
    "1.1.0:expressions.arithmetic_errors", "1.1.0:expressions.overflow_underflow", "1.1.0:expressions.type_mixture",
]

VEHICLE = ('<ScenarioObject name="{name}"><Vehicle name="vehicle.audi.tt" vehicleCategory="car">'
           '<Performance maxSpeed="50" maxAcceleration="5" maxDeceleration="5"/>'
           '<BoundingBox><Center x="0" y="0" z="0"/><Dimensions width="2" length="4" height="1.5"/></BoundingBox>'
           '<Axles><FrontAxle maxSteering="0.5" wheelDiameter="0.6" trackWidth="1.8" positionX="3" positionZ="0.3"/>'
           '<RearAxle maxSteering="0" wheelDiameter="0.6" trackWidth="1.8" positionX="0" positionZ="0.3"/></Axles>'
           '</Vehicle>{controllers}</ScenarioObject>')
PEDESTRIAN = ('<ScenarioObject name="ped"><Pedestrian name="walker" mass="80" pedestrianCategory="pedestrian">'
              '<BoundingBox><Center x="0" y="0" z="0"/><Dimensions width="1" length="1" height="2"/></BoundingBox>'
              '</Pedestrian></ScenarioObject>')
MISC = ('<ScenarioObject name="box"><MiscObject name="box" mass="1" miscObjectCategory="obstacle">'
        '<BoundingBox><Center x="0" y="0" z="0"/><Dimensions width="1" length="1" height="1"/></BoundingBox>'
        '</MiscObject>{controllers}</ScenarioObject>')
CONTROLLER = '<ObjectController name="{name}"><Controller name="{name}"{kind}/></ObjectController>'
SIMTIME = ('<Condition name="Start" delay="0" conditionEdge="none"><ByValueCondition>'
           '<SimulationTimeCondition value="{value}" rule="greaterThan"/></ByValueCondition></Condition>')
DOCUMENT = """<OpenSCENARIO>
<FileHeader revMajor="1" revMinor="{minor}" date="{date}" description="d" author="a"/>
<ParameterDeclarations>{parameters}</ParameterDeclarations>
<VariableDeclarations>{variables}</VariableDeclarations>
<CatalogLocations>{catalogs}</CatalogLocations>
<RoadNetwork>{road}</RoadNetwork>
<Entities>{entities}</Entities>
<Storyboard><Init><Actions>{init}</Actions></Init>{stories}<StopTrigger/></Storyboard>
</OpenSCENARIO>"""


def parts(**values):
    """Keyword arguments of ``document``."""
    return values


def document(minor=3, date="2026-10-14T12:00:00", parameters="", variables="", catalogs="",
             road='<LogicFile filepath="Town01"/>', entities=None, init="", stories=None):
    if entities is None:
        entities = VEHICLE.format(name="hero", controllers="") + PEDESTRIAN + MISC.format(controllers="")
    if stories is None:
        stories = story()
    return DOCUMENT.format(minor=minor, date=date, parameters=parameters, variables=variables, catalogs=catalogs,
                           road=road, entities=entities, init=init, stories=stories)


def story(actions="", actor="hero", condition=None, name="S", event="E", maneuver="M"):
    action = actions or ('<Action name="A"><GlobalAction><VariableAction variableRef="v">'
                         '<SetAction value="1"/></VariableAction></GlobalAction></Action>')
    actors = "".join('<EntityRef entityRef="{}"/>'.format(item) for item in actor.split()) if actor else ""
    return ('<Story name="{name}"><Act name="Act"><ManeuverGroup maximumExecutionCount="1" name="G">'
            '<Actors selectTriggeringEntities="false">{actors}</Actors><Maneuver name="{maneuver}">'
            '<Event name="{event}" priority="override">{action}<StartTrigger><ConditionGroup>{condition}'
            '</ConditionGroup></StartTrigger></Event></Maneuver></ManeuverGroup>'
            '<StartTrigger><ConditionGroup>{start}</ConditionGroup></StartTrigger></Act></Story>').format(
                name=name, actors=actors, action=action, condition=condition or SIMTIME.format(value=0),
                event=event, maneuver=maneuver, start=SIMTIME.format(value=0))


def private(action):
    return '<Action name="A"><PrivateAction>{}</PrivateAction></Action>'.format(action)


def speed_action(value, following=""):
    return private('<LongitudinalAction><SpeedAction><SpeedActionDynamics dynamicsShape="step" value="0" '
                   'dynamicsDimension="time"{}/><SpeedActionTarget><AbsoluteTargetSpeed value="{}"/>'
                   '</SpeedActionTarget></SpeedAction></LongitudinalAction>'.format(following, value))


def light(target, mode, extra=""):
    light_type = '<VehicleLight vehicleLightType="lowBeam"/>' if target else \
        '<UserDefinedLight userDefinedLightType="beacon"/>'
    return private('<AppearanceAction><LightStateAction><LightType>{}</LightType><LightState mode="{}"{}/>'
                   '</LightStateAction></AppearanceAction>'.format(light_type, mode, extra))


def animation(kind):
    content = {"component": '<ComponentAnimation><VehicleComponent vehicleComponentType="doorFrontLeft"/>'
                            '</ComponentAnimation>',
               "pedestrian": '<PedestrianAnimation motion="walk"/>',
               "file": '<AnimationFile><File filepath="a.fbx"/></AnimationFile>'}[kind]
    return private('<AppearanceAction><AnimationAction><AnimationType>{}</AnimationType></AnimationAction>'
                   '</AppearanceAction>'.format(content))


def trajectory(vertices, timing=True, offset=None):
    points = "".join('<Vertex{}><Position><WorldPosition x="{}" y="0"/></Position></Vertex>'.format(
        ' time="{}"'.format(index) if time else "", x) for index, (x, time) in enumerate(vertices))
    reference = '<Timing domainAbsoluteRelative="relative" offset="0" scale="1"/>' if timing else '<None/>'
    return private('<RoutingAction><FollowTrajectoryAction{}><TrajectoryRef><Trajectory name="T" closed="false">'
                   '<Shape><Polyline>{}</Polyline></Shape></Trajectory></TrajectoryRef><TimeReference>{}'
                   '</TimeReference><TrajectoryFollowingMode followingMode="follow"/></FollowTrajectoryAction>'
                   '</RoutingAction>'.format(' initialDistanceOffset="{}"'.format(offset) if offset else "",
                                             points, reference))


def signals(reference="", phase="go"):
    return ('<LogicFile filepath="Town01"/><TrafficSignals>'
            '<TrafficSignalController name="tsc"><Phase name="go" duration="{}"/></TrafficSignalController>'
            '<TrafficSignalController name="other"{}><Phase name="stop" duration="1"/></TrafficSignalController>'
            '</TrafficSignals>').format(1 if phase == "go" else phase, ' reference="{}"'.format(reference)
                                        if reference else "")


def int_parameter(value, name="p", kind="int"):
    return '<ParameterDeclaration name="{}" parameterType="{}" value="{}"/>'.format(name, kind, value)


def value_condition(value):
    return story(condition=SIMTIME.format(value=value))


INT_VARIABLE = '<VariableDeclaration name="v" variableType="int" value="0"/>'
CATALOG_ENTRIES = {"Vehicles": {"car": ET.fromstring(
    '<Vehicle name="car"><ParameterDeclarations><ParameterDeclaration name="Declared" parameterType="double" '
    'value="1"/></ParameterDeclarations></Vehicle>')}}


def catalog_reference(entry="car", assignment="Declared"):
    return ('<ScenarioObject name="cat"><CatalogReference catalogName="Vehicles" entryName="{}"><ParameterAssignments>'
            '<ParameterAssignment parameterRef="{}" value="2"/></ParameterAssignments></CatalogReference>'
            '</ScenarioObject>'.format(entry, assignment))


def stop_condition(reference, kind="event"):
    return ('<Condition name="State" delay="0" conditionEdge="none"><ByValueCondition>'
            '<StoryboardElementStateCondition storyboardElementType="{}" storyboardElementRef="{}" '
            'state="endTransition"/></ByValueCondition></Condition>'.format(kind, reference))


def init_teleport(entity, position):
    return ('<Private entityRef="{}"><PrivateAction><TeleportAction><Position>{}</Position></TeleportAction>'
            '</PrivateAction></Private>'.format(entity, position))


def activate(reference=""):
    return private('<ActivateControllerAction longitudinal="true"{}/>'.format(
        ' objectControllerRef="{}"'.format(reference) if reference else ""))


def expression_case(bad, good, kind="double"):
    return (parts(parameters=int_parameter(bad, kind=kind) + int_parameter(1, "a")),
            parts(parameters=int_parameter(good, kind=kind) + int_parameter(1, "a")))


# rule name -> (bad document keyword arguments, good document keyword arguments)
CASES = {
    "animation_constraint_pedestrian": (parts(stories=story(animation("component"), actor="ped")),
                                        parts(stories=story(animation("pedestrian"), actor="ped"))),
    "animation_constraint_vehicle": (parts(stories=story(animation("pedestrian"))),
                                     parts(stories=story(animation("component")))),
    "animation_constraint_misc_object_external_reference": (parts(stories=story(animation("component"), actor="box")),
                                                            parts(stories=story(animation("file"), actor="box"))),
    "distances_are_not_negative": (
        parts(stories=story(private('<LongitudinalAction><LongitudinalDistanceAction entityRef="ped" distance="-1" '
                                   'continuous="false" freespace="false"/></LongitudinalAction>'))),
        parts(stories=story(private('<LongitudinalAction><LongitudinalDistanceAction entityRef="ped" distance="1" '
                                   'continuous="false" freespace="false"/></LongitudinalAction>')))),
    "condition_delay_not_negative": (parts(stories=story(condition=SIMTIME.format(value=0).replace(
        'delay="0"', 'delay="-1"'))), parts()),
    "phase_duration_positive": (parts(road=signals(phase=-1)), parts(road=signals())),
    "time_format": (parts(date="2026-10-14 12:00"), parts(date="2026-10-14T12:00:00.123Z")),
    "variable_correctly_typed": (parts(variables='<VariableDeclaration name="v" variableType="int" value="abc"/>'),
                                 parts(variables=INT_VARIABLE)),
    "variable_modification_or_comparison_possible": (
        parts(variables='<VariableDeclaration name="v" variableType="string" value="a"/>',
             stories=story('<Action name="A"><GlobalAction><VariableAction variableRef="v"><ModifyAction><Rule>'
                           '<AddValue value="1"/></Rule></ModifyAction></VariableAction></GlobalAction></Action>')),
        parts(variables=INT_VARIABLE,
             stories=story('<Action name="A"><GlobalAction><VariableAction variableRef="v"><ModifyAction><Rule>'
                           '<AddValue value="1"/></Rule></ModifyAction></VariableAction></GlobalAction></Action>'))),
    "no_double_colon_prefix_in_names": (parts(stories=story(name="a::b")), parts(stories=story(name="ab"))),
    "parameter_declaration_name_prefix_reserved": (parts(parameters=int_parameter(1, "OSCspeed")),
                                                   parts(parameters=int_parameter(1, "speed"))),
    "parameter_declaration_parameter_name": (parts(parameters=int_parameter(1, "1speed")),
                                             parts(parameters=int_parameter(1, "speed_1"))),
    "unique_element_names_on_same_level": (parts(stories=story() + story()), parts(stories=story() + story(name="T"))),
    "parameter_declaration_parameter_scope": (
        parts(stories=story(name="S1").replace('<Act ', '<ParameterDeclarations>{}</ParameterDeclarations><Act '.format(
            int_parameter(1, "local")), 1) + story(name="S2", condition=SIMTIME.format(value="$local"))),
        parts(stories=story(name="S1", condition=SIMTIME.format(value="$local")).replace(
            '<Act ', '<ParameterDeclarations>{}</ParameterDeclarations><Act '.format(int_parameter(1, "local")), 1))),
    "parameter_declaration_parameter_reference_deadlocks": (
        parts(parameters=int_parameter("$b", "a") + int_parameter("$a", "b")),
        parts(parameters=int_parameter("1", "a") + int_parameter("$a", "b"))),
    "parameter_declaration_parameter_type_inference": (parts(parameters=int_parameter("1.5")),
                                                       parts(parameters=int_parameter("2"))),
    "positions_shall_not_introduce_dependency_cycles": (
        parts(init=init_teleport("hero", '<RelativeObjectPosition entityRef="ped" dx="1" dy="0"/>') +
             init_teleport("ped", '<RelativeObjectPosition entityRef="hero" dx="1" dy="0"/>')),
        parts(init=init_teleport("hero", '<WorldPosition x="0" y="0"/>') +
             init_teleport("ped", '<RelativeObjectPosition entityRef="hero" dx="1" dy="0"/>'))),
    "road_network_reference": (parts(road=""), parts()),
    "controller_assignment": (
        parts(entities=MISC.format(controllers=CONTROLLER.format(name="c", kind=""))),
        parts(entities=VEHICLE.format(name="hero", controllers=CONTROLLER.format(name="c", kind="")))),
    "controller_ambiguity": (
        parts(entities=VEHICLE.format(name="hero", controllers=CONTROLLER.format(name="c1", kind="") +
                                     CONTROLLER.format(name="c2", kind="")), stories=story(activate())),
        parts(entities=VEHICLE.format(name="hero", controllers=CONTROLLER.format(name="c1", kind="") +
                                     CONTROLLER.format(name="c2", kind="")), stories=story(activate("c1")))),
    "lightstateaction_light_type": (parts(stories=story(light(True, "on"), actor="ped")),
                                    parts(stories=story(light(True, "on")))),
    "lightstateaction_lightstate_on_off": (parts(stories=story(light(True, "on", ' flashingOnDuration="1"'))),
                                           parts(stories=story(light(True, "on")))),
    "lightstateaction_lightstate_flashing": (
        parts(stories=story(light(True, "flashing"))),
        parts(stories=story(light(True, "flashing", ' flashingOnDuration="1" flashingOffDuration="1"')))),
    "resolvable_variable_reference": (parts(), parts(variables=INT_VARIABLE)),
    "traffic_signal_controller_action_references": (
        parts(road=signals(), stories=story('<Action name="A"><GlobalAction><InfrastructureAction><TrafficSignalAction>'
                                           '<TrafficSignalControllerAction trafficSignalControllerRef="tsc" '
                                           'phase="stop"/></TrafficSignalAction></InfrastructureAction></GlobalAction>'
                                           '</Action>')),
        parts(road=signals(), stories=story('<Action name="A"><GlobalAction><InfrastructureAction><TrafficSignalAction>'
                                           '<TrafficSignalControllerAction trafficSignalControllerRef="tsc" '
                                           'phase="go"/></TrafficSignalAction></InfrastructureAction></GlobalAction>'
                                           '</Action>'))),
    "traffic_signal_controller_condition_references": (
        parts(road=signals(), stories=story(condition='<Condition name="C" delay="0" conditionEdge="none">'
                                           '<ByValueCondition><TrafficSignalControllerCondition '
                                           'trafficSignalControllerRef="tsc" phase="red"/></ByValueCondition>'
                                           '</Condition>')),
        parts(road=signals(), stories=story(condition='<Condition name="C" delay="0" conditionEdge="none">'
                                           '<ByValueCondition><TrafficSignalControllerCondition '
                                           'trafficSignalControllerRef="tsc" phase="go"/></ByValueCondition>'
                                           '</Condition>'))),
    "traffic_signal_controller_references": (parts(road=signals("nope")), parts(road=signals("tsc"))),
    "references_to_scenario_object": (parts(stories=story(speed_action(10), actor="box")),
                                      parts(stories=story(speed_action(10)))),
    "homogeneous_references_to_entity_selection": (
        parts(entities=VEHICLE.format(name="hero", controllers="") + PEDESTRIAN + '<EntitySelection name="mixed">'
             '<Members><EntityRef entityRef="hero"/><EntityRef entityRef="ped"/></Members></EntitySelection>',
             stories=story(speed_action(10), actor="mixed")),
        parts(entities=VEHICLE.format(name="hero", controllers="") + PEDESTRIAN + '<EntitySelection name="cars">'
             '<Members><ByType objectType="vehicle"/></Members></EntitySelection>',
             stories=story(speed_action(10), actor="cars"))),
    "traffic_name_exists": (
        parts(stories=story('<Action name="A"><GlobalAction><TrafficAction trafficName="t"><TrafficStopAction/>'
                           '</TrafficAction></GlobalAction></Action>')),
        parts(stories=story('<Action name="A"><GlobalAction><TrafficAction trafficName="t"><TrafficStopAction/>'
                           '</TrafficAction></GlobalAction></Action><Action name="B"><GlobalAction>'
                           '<TrafficAction trafficName="t"><TrafficSwarmAction innerRadius="1" numberOfVehicles="1" '
                           'offset="0" semiMajorAxis="2" semiMinorAxis="2"/></TrafficAction></GlobalAction>'
                           '</Action>'))),
    "override_controller_action_only_allows_vehicles": (
        parts(stories=story(private('<ControllerAction><OverrideControllerValueAction><Throttle active="false" '
                                   'value="0"/></OverrideControllerValueAction></ControllerAction>'), actor="ped")),
        parts(stories=story(private('<ControllerAction><OverrideControllerValueAction><Throttle active="false" '
                                   'value="0"/></OverrideControllerValueAction></ControllerAction>')))),
    "cardinality_of_control_points_in_nurbs": tuple(
        parts(stories=story(private('<RoutingAction><FollowTrajectoryAction><TrajectoryRef><Trajectory name="T" '
                                   'closed="false"><Shape><Nurbs order="{}"><ControlPoint><Position><WorldPosition '
                                   'x="0" y="0"/></Position></ControlPoint><ControlPoint><Position><WorldPosition '
                                   'x="1" y="0"/></Position></ControlPoint><Knot value="0"/><Knot value="1"/></Nurbs>'
                                   '</Shape></Trajectory></TrajectoryRef><TimeReference><None/></TimeReference>'
                                   '<TrajectoryFollowingMode followingMode="follow"/></FollowTrajectoryAction>'
                                   '</RoutingAction>'.format(order))))
        for order in (4, 2)),
    "trajectory_timing_exists_if_requested": (parts(stories=story(trajectory([(0, False), (10, False)]))),
                                              parts(stories=story(trajectory([(0, True), (10, True)])))),
    "offset_should_be_less_than_trajectory_length": (
        parts(stories=story(trajectory([(0, True), (10, True)], offset=100))),
        parts(stories=story(trajectory([(0, True), (10, True)], offset=5)))),
    "invalid_elements_if_no_road_network": (
        parts(road="", init=init_teleport("hero", '<LanePosition roadId="1" laneId="-1" s="0"/>')),
        parts(init=init_teleport("hero", '<LanePosition roadId="1" laneId="-1" s="0"/>'))),
    "controller_activation": (
        parts(entities=VEHICLE.format(name="hero", controllers=CONTROLLER.format(
            name="c", kind=' controllerType="lateral"')), stories=story(activate())),
        parts(entities=VEHICLE.format(name="hero", controllers=CONTROLLER.format(
            name="c", kind=' controllerType="longitudinal"')), stories=story(activate()))),
    "targetspeed_maxspeed_speedprofileaction": tuple(
        parts(stories=story(private('<LongitudinalAction><SpeedProfileAction followingMode="follow"><SpeedProfileEntry '
                                   'speed="{}"/></SpeedProfileAction></LongitudinalAction>'.format(speed))))
        for speed in (100, 10)),
    "targetspeed_maxspeed_general": (parts(stories=story(speed_action(100, ' followingMode="follow"'))),
                                     parts(stories=story(speed_action(10, ' followingMode="follow"')))),
    "evaluation_of_expressions_possible": expression_case("${1 +}", "${1 + 1}"),
    "allowed_operators": expression_case("${2 ** 3}", "${pow(2, 3)}"),
    "arguments_of_operators": expression_case("${max(1)}", "${max(1, 2)}"),
    "type_of_boolean": expression_case("${1 + 1}", "${not false}", kind="boolean"),
    "type_casting": expression_case("${1.5 * 2}", "${round(1.5 * 2)}", kind="int"),
    "nan_or_infinity": expression_case("${1e308 * 10}", "${1e3 * 10}"),
    "arithmetic_errors": expression_case("${1 / 0}", "${1 / 2}"),
    "overflow_underflow": expression_case("${9223372036854775807 + 1}", "${2 + 1}", kind="int"),
    "type_mixture": (parts(parameters=int_parameter(1, "a") + int_parameter(2, "b", "unsignedInt") +
                          int_parameter("${$a + $b}", "c")),
                     parts(parameters=int_parameter(1, "a") + int_parameter(2, "b") +
                           int_parameter("${$a + $b}", "c"))),
}
# Rules whose fixtures need files on disk, catalogs or another document type are tested separately.
SEPARATE = ("file_ending", "geodetic_datum_defined", "road_network_availability", "check_varied_parameters",
            "single_or_multi_parameters", "catalog_reference_resolvability", "catalogs_referenced_by_directory",
            "resolvable_storyboard_element_ref", "valid_schema")
CASES["resolvable_variable_reference"] = (
    parts(stories=story(condition='<Condition name="C" delay="0" conditionEdge="none"><ByValueCondition>'
                       '<VariableCondition variableRef="missing" value="1" rule="equalTo"/></ByValueCondition>'
                       '</Condition>'), variables=INT_VARIABLE),
    parts(stories=story(condition='<Condition name="C" delay="0" conditionEdge="none"><ByValueCondition>'
                       '<VariableCondition variableRef="v" value="1" rule="equalTo"/></ByValueCondition>'
                       '</Condition>'), variables=INT_VARIABLE))
CASES["condition_delay_not_negative"] = (CASES["condition_delay_not_negative"][0], parts(variables=INT_VARIABLE))


def uid(name):
    return next(key for key in RULES if key.endswith("." + name))


def findings(source, name, **kwargs):
    return [item for item in Checker().check(load_document(source.encode("utf-8")), **kwargs) if item.rule == uid(name)]


class TestRegistry(unittest.TestCase):

    def test_every_annex_c_rule_is_implemented_or_listed_as_not_implemented(self):
        expected = [A + item for item in ANNEX_C]
        self.assertEqual(len(expected), 68)
        self.assertEqual(sorted(list(RULES) + list(NOT_IMPLEMENTED)), sorted(expected))

    def test_not_implemented_rules_carry_a_reason(self):
        for item in NOT_IMPLEMENTED.values():
            self.assertTrue(item.reason, item.uid)

    def test_coverage_is_machine_readable(self):
        summary = rule_coverage()
        self.assertEqual(len(summary["implemented"]) + len(summary["partial"]), len(RULES))
        self.assertEqual(summary["not_implemented"], list(NOT_IMPLEMENTED))
        for key in summary["partial"]:
            self.assertTrue(RULES[key].scope, key)

    def test_every_implemented_rule_has_a_positive_and_a_negative_case(self):
        names = set(RULES[key].name for key in RULES)
        self.assertEqual(names, set(CASES) | set(SEPARATE))

    def test_newer_rules_are_warnings_for_older_documents(self):
        source = document(minor=0, parameters=int_parameter(1, "1speed"))
        diagnostics = [item for item in Checker().check(load_document(source.encode("utf-8")))
                       if item.rule == uid("parameter_declaration_parameter_name")]
        self.assertEqual([item.severity for item in diagnostics], ["warning"])

    def test_shipped_examples_and_fixtures_have_no_checker_errors(self):
        for path in EXAMPLES + FIXTURES:
            with self.subTest(path=os.path.basename(path)):
                errors = [item for item in Checker().check(load_document(path)) if item.is_error]
                self.assertEqual(errors, [])


class TestRules(unittest.TestCase):

    def test_cases(self):
        for name, (bad, good) in sorted(CASES.items()):
            with self.subTest(rule=name):
                reported = findings(document(**bad), name)
                self.assertTrue(reported, "{} not reported".format(name))
                self.assertEqual(reported[0].severity, RULES[uid(name)].severity)
                self.assertEqual(reported[0].category, "checker_rule")
                self.assertIsNotNone(reported[0].line)
                self.assertTrue(reported[0].path.startswith("/OpenSCENARIO"))
                self.assertEqual(findings(document(**good), name), [])

    def test_file_ending(self):
        self.assertTrue(findings(document(), "file_ending", filename="scenario.xml"))
        self.assertEqual(findings(document(), "file_ending", filename="scenario.xosc"), [])

    def test_storyboard_element_references(self):
        self.assertTrue(findings(document(stories=story(condition=stop_condition("Missing"))),
                                 "resolvable_storyboard_element_ref"))
        self.assertEqual(findings(document(stories=story(condition=stop_condition("E"))),
                                  "resolvable_storyboard_element_ref"), [])
        self.assertEqual(findings(document(stories=story(condition=stop_condition("S::Act::G::M::E"))),
                                  "resolvable_storyboard_element_ref"), [])
        ambiguous = story(condition=stop_condition("E")) + story(name="T")
        self.assertIn("ambiguous", findings(document(stories=ambiguous), "resolvable_storyboard_element_ref")[0]
                      .message)

    def test_catalog_rules(self):
        good = document(entities=catalog_reference())
        self.assertEqual(findings(good, "catalog_reference_resolvability", catalogs=CATALOG_ENTRIES), [])
        self.assertEqual(findings(good, "check_varied_parameters", catalogs=CATALOG_ENTRIES), [])
        self.assertTrue(findings(document(entities=catalog_reference("bus")), "catalog_reference_resolvability",
                                 catalogs=CATALOG_ENTRIES))
        self.assertTrue(findings(document(entities=catalog_reference(assignment="Nope")), "check_varied_parameters",
                                 catalogs=CATALOG_ENTRIES))

    def test_valid_schema(self):
        path = os.path.join(TESTS_DIR, "fixtures", "openscenario", "conformance_1_3_1.xosc")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertEqual(findings(source, "valid_schema"), [])
        self.assertTrue(findings(source.replace('<Entities>', '<Entities bogus="1">'), "valid_schema"))

    def test_single_or_multi_parameters(self):
        template = ('<OpenSCENARIO><FileHeader revMajor="1" revMinor="3" date="2026-10-14T12:00:00" description="d" '
                    'author="a"/><ParameterValueDistribution><ScenarioFile filepath="s.xosc"/><Deterministic>'
                    '<DeterministicSingleParameterDistribution parameterName="a"><DistributionSet><Element value="1"/>'
                    '</DistributionSet></DeterministicSingleParameterDistribution>'
                    '<DeterministicMultiParameterDistribution><ValueSetDistribution><ParameterValueSet>'
                    '<ParameterAssignment parameterRef="{}" value="1"/></ParameterValueSet></ValueSetDistribution>'
                    '</DeterministicMultiParameterDistribution></Deterministic></ParameterValueDistribution>'
                    '</OpenSCENARIO>')
        self.assertTrue(findings(template.format("a"), "single_or_multi_parameters"))
        self.assertEqual(findings(template.format("b"), "single_or_multi_parameters"), [])


class TestFileRules(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory)
        self.scenario = os.path.join(self.directory, "scenario.xosc")

    def write(self, name, content):
        path = os.path.join(self.directory, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_geodetic_datum(self):
        self.write("geo.xodr", '<OpenDRIVE><header><geoReference>+proj=utm</geoReference></header></OpenDRIVE>')
        self.write("plain.xodr", '<OpenDRIVE><header/></OpenDRIVE>')
        teleport = init_teleport("hero", '<GeoPosition latitudeDeg="1" longitudeDeg="2"/>')
        for road, expected in (("geo.xodr", False), ("plain.xodr", True)):
            source = document(road='<LogicFile filepath="{}"/>'.format(road), init=teleport)
            self.assertEqual(bool(findings(source, "geodetic_datum_defined", filename=self.scenario)), expected)

    def test_road_network_availability(self):
        self.write("road.xodr", "<OpenDRIVE/>")
        for road, expected in (("road.xodr", False), ("Town01", False), ("missing.xodr", True)):
            source = document(road='<LogicFile filepath="{}"/>'.format(road))
            self.assertEqual(bool(findings(source, "road_network_availability", filename=self.scenario)), expected)

    def test_catalog_directories_and_resolution(self):
        os.mkdir(os.path.join(self.directory, "catalogs"))
        self.write("catalogs/VehicleCatalog.xosc", '<OpenSCENARIO><FileHeader revMajor="1" revMinor="3" date="d" '
                   'description="d" author="a"/><Catalog name="Vehicles"><Vehicle name="car"/></Catalog>'
                   '</OpenSCENARIO>')
        location = '<VehicleCatalog><Directory path="{}"/></VehicleCatalog>'
        good = document(catalogs=location.format("catalogs"), entities=catalog_reference(assignment="x"))
        self.assertEqual(findings(good, "catalogs_referenced_by_directory", filename=self.scenario), [])
        self.assertEqual(findings(good, "catalog_reference_resolvability", filename=self.scenario), [])
        self.assertTrue(findings(document(catalogs=location.format("nope")), "catalogs_referenced_by_directory",
                                 filename=self.scenario))
        self.assertTrue(findings(document(catalogs=location.format("catalogs"), entities=catalog_reference("bus")),
                                 "catalog_reference_resolvability", filename=self.scenario))

    def test_varied_parameters_against_the_scenario_file(self):
        self.write("s.xosc", document(parameters=int_parameter(1, "a")))
        source = ('<OpenSCENARIO><FileHeader revMajor="1" revMinor="3" date="2026-10-14T12:00:00" description="d" '
                  'author="a"/><ParameterValueDistribution><ScenarioFile filepath="s.xosc"/><Deterministic>'
                  '<DeterministicSingleParameterDistribution parameterName="{}"><DistributionSet>'
                  '<Element value="1"/></DistributionSet></DeterministicSingleParameterDistribution></Deterministic>'
                  '</ParameterValueDistribution></OpenSCENARIO>')
        self.assertEqual(findings(source.format("a"), "check_varied_parameters", filename=self.scenario), [])
        self.assertTrue(findings(source.format("z"), "check_varied_parameters", filename=self.scenario))


if __name__ == "__main__":
    unittest.main()
