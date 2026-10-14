"""ASAM OpenSCENARIO XML 1.3.1 Annex C checker rules that can be decided statically.

Every Annex C rule is registered here, either with an implementation or in the
not-implemented list together with the reason.  Severities follow the rule
wording: "shall" is an error, "should" or "can" a warning.
"""

from __future__ import absolute_import

import math
import os
import re
import xml.etree.ElementTree as ET

from srunner.openscenario.model import expressions
from srunner.openscenario.validation.checker.context import NAME_REFERENCES, Unresolved
from srunner.openscenario.validation.checker.registry import not_implemented, rule
from srunner.openscenario.validation.diagnostics import Diagnostic

A = "asam.net:xosc:"
MOVABLE = frozenset(("Vehicle", "Pedestrian"))
CONTROLLED_ACTIONS = ("ActivateControllerAction", "AssignControllerAction", "AssignRouteAction",
                      "LateralDistanceAction", "LaneChangeAction", "LaneOffsetAction", "LongitudinalDistanceAction",
                      "SpeedAction", "SpeedProfileAction", "SynchronizeAction")
CONTROLLER_DOMAINS = {"lateral": {"lateral"}, "longitudinal": {"longitudinal"}, "lighting": {"lighting"},
                      "animation": {"animation"}, "movement": {"lateral", "longitudinal"},
                      "appearance": {"lighting", "animation"},
                      "all": {"lateral", "longitudinal", "lighting", "animation"}}
FUNCTIONS = ("round", "floor", "ceil", "sqrt", "pow", "sin", "cos", "tan", "asin", "acos", "atan", "sign", "abs",
             "max", "min")
INTEGER_FAMILY = frozenset(("int", "unsignedInt", "unsignedShort"))


def _reason(error):
    diagnostic = getattr(error, "diagnostic", None)
    return diagnostic.message if diagnostic is not None else str(error)


def _elements(context, *tags):
    for element in context.root.iter():
        if element.tag in tags:
            yield element


def _boolean(context, element, attribute):
    value = element.attrib.get(attribute)
    if value is None:
        return False
    try:
        return bool(context.evaluate(value, element, "boolean"))
    except (Unresolved, ValueError):
        return False


def _known_types(context, names):
    """Entity types of ``names`` (ScenarioObjects and selections); unknown entities are skipped."""
    for name in names:
        types = context.entity_types(name)
        if types:
            yield name, types


def _scenario_object_types(context, names):
    for name in names:
        element = context.entities().get(name)
        if element is not None and element.tag == "ScenarioObject":
            types = context.entity_types(name)
            if types:
                yield name, types


def _max_speed(context, name):
    element = context.entities().get(name)
    if element is None or element.tag != "ScenarioObject":
        return None
    entity = context.entity_object(element)
    performance = entity.find("Performance") if entity is not None and entity.tag == "Vehicle" else None
    return context.number(performance, "maxSpeed") if performance is not None else None


def _trajectory(context, action):
    trajectory = action.find("Trajectory")
    if trajectory is None:
        trajectory = action.find("TrajectoryRef/Trajectory")
    reference = action.find("CatalogReference")
    if reference is None:
        reference = action.find("TrajectoryRef/CatalogReference")
    if trajectory is None and reference is not None:
        trajectory = context.catalog_entry(reference)
    return trajectory


# C.1 general ---------------------------------------------------------------------------------------------------

@rule(A + "1.0.0:general.file_ending", "warning", "Scenario descriptions should have the file extension .xosc.")
def file_ending(context):
    if context.filename and not context.filename.lower().endswith(".xosc"):
        yield context.root, "File {!r} does not have the .xosc extension".format(os.path.basename(context.filename))


def _animation_constraint(context, forbidden):
    for animation_type in _elements(context, "AnimationType"):
        kinds = [child.tag for child in animation_type]
        for name, types in _known_types(context, context.subjects(animation_type)):
            for entity_type in sorted(types):
                for kind in kinds:
                    if kind in forbidden.get(entity_type, ()):
                        yield animation_type, "{} cannot be used for {} {!r}".format(kind, entity_type, name)


@rule(A + "1.2.0:general.animation_constraint_pedestrian", "error",
      "If a ScenarioObject is of type Pedestrian, then ComponentAnimation shall not be used as AnimationType.")
def animation_constraint_pedestrian(context):
    return _animation_constraint(context, {"Pedestrian": ("ComponentAnimation",)})


@rule(A + "1.2.0:general.animation_constraint_vehicle", "error",
      "If a ScenarioObject is of type Vehicle, then PedestrianAnimation shall not be used as AnimationType.")
def animation_constraint_vehicle(context):
    return _animation_constraint(context, {"Vehicle": ("PedestrianAnimation",)})


@rule(A + "1.2.0:general.animation_constraint_misc_object_external_reference", "error",
      "If a ScenarioObject is of type MiscObject or ExternalObjectReference, then ComponentAnimation and "
      "PedestrianAnimation shall not be used as AnimationType.")
def animation_constraint_misc_external(context):
    forbidden = ("ComponentAnimation", "PedestrianAnimation")
    return _animation_constraint(context, {"MiscObject": forbidden, "ExternalObjectReference": forbidden})


# C.2 data type -------------------------------------------------------------------------------------------------

DISTANCE_ATTRIBUTES = {
    "LongitudinalDistanceAction": ("distance",), "LateralDistanceAction": ("distance",),
    "DistanceCondition": ("value",), "RelativeDistanceCondition": ("value",), "TraveledDistanceCondition": ("value",),
    "ReachPositionCondition": ("tolerance",), "RelativeClearanceCondition": ("distanceForward", "distanceBackward"),
    "TrafficSourceAction": ("radius",), "TrafficSinkAction": ("radius",),
    "TrafficSwarmAction": ("innerRadius", "semiMajorAxis", "semiMinorAxis"), "Fog": ("visualRange",),
    "Dimensions": ("width", "length", "height"), "Clothoid": ("length",), "ClothoidSplineSegment": ("length",),
}


@rule(A + "1.1.0:data_type.distances_are_not_negative", "warning",
      "Distances should be greater than or equal to zero.", coverage="partial",
      scope="Distance attributes of distance actions and conditions, clearance, traffic area radii, Fog visualRange, "
            "Dimensions, clothoid lengths and transition dynamics with dynamicsDimension 'distance'.")
def distances_are_not_negative(context):
    for element in context.root.iter():
        attributes = DISTANCE_ATTRIBUTES.get(element.tag, ())
        if element.attrib.get("dynamicsDimension") == "distance":
            attributes = attributes + ("value",)
        for attribute in attributes:
            value = context.number(element, attribute)
            if value is not None and value < 0:
                yield element, "Distance {}@{} is negative ({})".format(element.tag, attribute, value)


@rule(A + "1.0.0:data_type.condition_delay_not_negative", "error", "The condition delay shall be non negative.")
def condition_delay_not_negative(context):
    for condition in _elements(context, "Condition"):
        delay = context.number(condition, "delay")
        if delay is not None and delay < 0:
            yield condition, "Condition delay is negative ({})".format(delay)


@rule(A + "1.0.0:data_type.phase_duration_positive", "error",
      "The attribute duration in the complex type Phase shall contain non-negative values.")
def phase_duration_positive(context):
    for phase in _elements(context, "Phase"):
        duration = context.number(phase, "duration")
        if duration is not None and duration < 0:
            yield phase, "Phase duration is negative ({})".format(duration)


TIME_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?(Z|[+-]\d{2}:\d{2})?$")


@rule(A + "1.0.0:data_type.time_format", "error",
      "Date and time shall use the format yyyy-MM-dd'T'HH:mm:ss'.'FFFZ (ISO 8601).",
      scope="Interpreted as yyyy-MM-ddTHH:mm:ss with optional milliseconds (1-3 digits) and an optional 'Z' or "
            "+hh:mm/-hh:mm zone. Checked on every dateTime-typed attribute and dateTime declarations.")
def time_format(context):
    for element in context.root.iter():
        values = [(attribute, element.attrib[attribute]) for attribute in element.attrib
                  if context.attribute_type(element, attribute) == "dateTime"]
        declared_type = element.attrib.get("parameterType") or element.attrib.get("variableType")
        if element.tag in ("ParameterDeclaration", "VariableDeclaration") and declared_type == "dateTime":
            values.append(("value", element.attrib.get("value")))
        for attribute, raw in values:
            try:
                value = str(context.evaluate(raw, element, "string"))
            except (Unresolved, ValueError):
                continue
            if not TIME_FORMAT.match(value.strip()):
                yield element, "{}@{} value {!r} does not follow yyyy-MM-ddTHH:mm:ss[.FFF][Z]".format(
                    element.tag, attribute, value)


def _variable_values(context):
    """(element, variable name, value, kind) for declarations, VariableActions and VariableConditions."""
    for name, declaration in context.variables().items():
        yield declaration, name, declaration.attrib.get("value"), "declaration"
    for action in _elements(context, "VariableAction"):
        name = (action.attrib.get("variableRef") or "").lstrip("$")
        set_action = action.find("SetAction")
        if set_action is not None:
            yield set_action, name, set_action.attrib.get("value"), "set"
        for operand in action.findall("ModifyAction/Rule/*"):
            yield operand, name, operand.attrib.get("value"), "modify"
    for condition in _elements(context, "VariableCondition"):
        yield condition, (condition.attrib.get("variableRef") or "").lstrip("$"), condition.attrib.get("value"), \
            "condition"


@rule(A + "1.2.0:data_type.variable_correctly_typed", "error",
      "It shall be possible to convert the value in VariableDeclaration, VariableAction, and VariableCondition to the "
      "type of the declared variable.")
def variable_correctly_typed(context):
    variables = context.variables()
    for element, name, value, _ in _variable_values(context):
        declaration = variables.get(name)
        if declaration is None or value is None:
            continue
        variable_type = declaration.attrib.get("variableType")
        try:
            context.evaluate(value, element, variable_type)
        except Unresolved:
            continue
        except ValueError as error:
            yield element, "Value {!r} cannot be converted to the {} type of variable {!r}: {}".format(
                value, variable_type, name, _reason(error))


@rule(A + "1.2.0:data_type.variable_modification_or_comparison_possible", "error",
      "A VariableModifyAction shall only act on int, unsignedInt, unsignedShort or double types; a VariableCondition "
      "on a string variable shall use the rule equalTo or notEqualTo.")
def variable_modification_or_comparison(context):
    variables = context.variables()
    for action in _elements(context, "VariableAction"):
        declaration = variables.get((action.attrib.get("variableRef") or "").lstrip("$"))
        if action.find("ModifyAction") is not None and declaration is not None and \
                declaration.attrib.get("variableType") not in ("int", "unsignedInt", "unsignedShort", "double"):
            yield action, "VariableModifyAction cannot modify {} variable {!r}".format(
                declaration.attrib.get("variableType"), declaration.attrib.get("name"))
    for condition in _elements(context, "VariableCondition"):
        declaration = variables.get((condition.attrib.get("variableRef") or "").lstrip("$"))
        rule_name = context.text(condition, "rule")
        if declaration is not None and declaration.attrib.get("variableType") == "string" and \
                rule_name not in (None, "equalTo", "notEqualTo"):
            yield condition, "Rule {!r} cannot compare string variable {!r}".format(
                rule_name, declaration.attrib.get("name"))


# C.3 distance --------------------------------------------------------------------------------------------------

not_implemented(A + "1.2.0:distance.lateral_distance_disconnection", "warning",
                "A lateral distance relation should not be used when the road reference lines along the chain are not "
                "contiguous.", "Requires the OpenDRIVE road reference-line topology.")

# C.4 naming ----------------------------------------------------------------------------------------------------


@rule(A + "1.0.0:naming.no_double_colon_prefix_in_names", "error", "The :: shall not be used in names itself.")
def no_double_colon_prefix_in_names(context):
    for element in context.root.iter():
        name = element.attrib.get("name")
        if name and "::" in name and element.tag not in NAME_REFERENCES:
            yield element, "Name {!r} contains '::'".format(name)


@rule(A + "1.0.0:naming.parameter_declaration_name_prefix_reserved", "error",
      "Parameter names starting with OSC are reserved; the prefix OSC shall not be used.")
def parameter_name_prefix_reserved(context):
    for declaration in _elements(context, "ParameterDeclaration"):
        if (declaration.attrib.get("name") or "").startswith("OSC"):
            yield declaration, "Parameter name {!r} uses the reserved prefix 'OSC'".format(declaration.attrib["name"])


PARAMETER_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@rule(A + "1.1.0:naming.parameter_declaration_parameter_name", "error",
      "The parameter name shall match the regular expression [A-Za-z_][A-Za-z0-9_]*.")
def parameter_declaration_parameter_name(context):
    for declaration in _elements(context, "ParameterDeclaration"):
        if not PARAMETER_NAME.match(declaration.attrib.get("name") or ""):
            yield declaration, "Parameter name {!r} does not match [A-Za-z_][A-Za-z0-9_]*".format(
                declaration.attrib.get("name"))


@rule(A + "1.0.0:naming.unique_element_names_on_same_level", "error",
      "Element names at each level shall be unique within the directly enclosing element.")
def unique_element_names_on_same_level(context):
    for parent in context.root.iter():
        seen = set()
        for child in parent:
            name = child.attrib.get("name")
            if name is None or child.tag in NAME_REFERENCES:
                continue
            if name in seen:
                yield child, "Name {!r} is used more than once in {}".format(name, parent.tag)
            seen.add(name)


# C.5 parameters ------------------------------------------------------------------------------------------------

PARAMETER_NAME_REFERENCES = (("ParameterAction", "parameterRef"), ("ParameterCondition", "parameterRef"))


def _referenced_names(element, attribute, value):
    if (element.tag, attribute) in PARAMETER_NAME_REFERENCES:
        return [value.lstrip("$")] if value else []
    if element.tag == "ParameterAssignment" and attribute == "parameterRef":
        return []
    try:
        return expressions.references(value)
    except ValueError:
        return []


def _criterion_argument(context, element, attribute):
    """ScenarioRunner criteria conditions (``criteria_<Name>``) use parameterRef as the criterion argument name."""
    if element.tag != "ParameterCondition" or attribute != "parameterRef":
        return False
    condition = context.nearest(element, ("Condition",))
    return condition is not None and (condition.attrib.get("name") or "").startswith("criteria_")


@rule(A + "1.1.0:parameters.parameter_declaration_parameter_scope", "error",
      "A parameter shall not be used out of scope; the scope is the subtree rooted in the element containing the "
      "ParameterDeclaration.",
      scope="Every $reference in attribute values and expressions, ParameterAction and ParameterCondition "
            "parameterRef. The parameterRef of ScenarioRunner criteria conditions (Condition name 'criteria_<Name>') "
            "is a criterion argument name and is not checked.")
def parameter_declaration_parameter_scope(context):
    for element in context.root.iter():
        for attribute, value in element.attrib.items():
            if _criterion_argument(context, element, attribute):
                continue
            names = _referenced_names(element, attribute, value)
            if not names:
                continue
            scope = context.declarations_in_scope(element)
            for name in names:
                if name not in scope:
                    yield element, "Parameter {!r} used in {}@{} is not declared in scope".format(
                        name, element.tag, attribute)


@rule(A + "1.1.0:parameters.parameter_declaration_parameter_reference_deadlocks", "warning",
      "Chained or mutual parameter references should not result in self references.")
def parameter_reference_deadlocks(context):
    def dependencies(declaration):
        scope = context.declarations_in_scope(declaration)
        try:
            names = expressions.references(declaration.attrib.get("value"))
        except ValueError:
            names = []
        return [scope[name] for name in names if name in scope]

    for declaration in _elements(context, "ParameterDeclaration"):
        stack, seen = [(declaration, [declaration])], set()
        while stack:
            current, path = stack.pop()
            for target in dependencies(current):
                if target is declaration:
                    yield declaration, "Parameter {!r} references itself: {}".format(
                        declaration.attrib.get("name"), " -> ".join(
                            item.attrib.get("name") for item in path + [declaration]))
                    stack = []
                    break
                if target not in seen:
                    seen.add(target)
                    stack.append((target, path + [target]))


@rule(A + "1.0.0:parameters.parameter_declaration_parameter_type_inference", "error",
      "In the ParameterDeclaration the inferred type of the value shall match the parameterType.",
      scope="Literal values and plain $references; expression values are checked by the expression rules.")
def parameter_type_inference(context):
    for declaration in _elements(context, "ParameterDeclaration"):
        value = declaration.attrib.get("value")
        if value is None or expressions.is_expression(value):
            continue
        try:
            context.parameter_value(declaration)
        except Unresolved:
            continue
        except ValueError as error:
            yield declaration, "Value {!r} does not match parameterType {}: {}".format(
                value, declaration.attrib.get("parameterType"), _reason(error))


# C.6 positioning -----------------------------------------------------------------------------------------------

@rule(A + "1.1.0:positioning.geodetic_datum_defined", "error",
      "If a scenario uses a geo position, the referenced road network shall define a geodetic datum.",
      coverage="partial", scope="Checked when the LogicFile is a resolvable OpenDRIVE (.xodr) file.")
def geodetic_datum_defined(context):
    geo = next(_elements(context, "GeoPosition"), None)
    logic = context.root.find("RoadNetwork/LogicFile")
    if geo is None or logic is None:
        return
    path = context.resolve_file(context.text(logic, "filepath"))
    if not path or not path.lower().endswith(".xodr") or not os.path.isfile(path):
        return
    try:
        header = ET.parse(path).getroot().find("header")
    except (ET.ParseError, OSError):
        return
    reference = header.find("geoReference") if header is not None else None
    if reference is None or not (reference.text or "").strip():
        yield geo, "GeoPosition is used but {} defines no geoReference".format(os.path.basename(path))


not_implemented(A + "1.2.0:positioning.longitudinal_distance_requirements", "error",
                "A route between start and target position shall be computable as a chain of road reference lines.",
                "Requires route computation over the OpenDRIVE road network.")
not_implemented(A + "1.2.0:positioning.lateral_distance_requirements", "error",
                "A route between start and target position shall be computable as a chain of continuous road "
                "reference lines.", "Requires route computation over the OpenDRIVE road network.")
not_implemented(A + "1.2.0:positioning.distance_action_trajectory_reachability", "error",
                "The distance of a LongitudinalDistanceAction in trajectory coordinates shall not exceed the "
                "trajectory arc length.", "The trajectory is the one the actor follows at runtime.")

RELATIVE_POSITIONS = ("RelativeWorldPosition", "RelativeObjectPosition", "RelativeRoadPosition",
                      "RelativeLanePosition")


@rule(A + "1.0.0:positioning.positions_shall_not_introduce_dependency_cycles", "error",
      "Positions shall not introduce a dependency cycle that cannot be resolved.", coverage="partial",
      scope="Initial positions: Init TeleportActions and AddEntityActions with relative positions.")
def position_dependency_cycles(context):
    init = context.root.find("Storyboard/Init/Actions")
    if init is None:
        return
    edges = {}
    for private in init.findall("Private"):
        for position in private.findall("PrivateAction/TeleportAction/Position"):
            edges.setdefault(private.attrib.get("entityRef"), []).append(position)
    for entity_action in init.findall("GlobalAction/EntityAction"):
        for position in entity_action.findall("AddEntityAction/Position"):
            edges.setdefault(entity_action.attrib.get("entityRef"), []).append(position)

    def targets(name):
        for position in edges.get(name, ()):
            for relative in position:
                if relative.tag in RELATIVE_POSITIONS and relative.attrib.get("entityRef"):
                    yield relative.attrib["entityRef"], position

    for start in sorted(edges):
        stack, seen = [(start, [start])], set()
        while stack:
            name, path = stack.pop()
            for target, position in targets(name):
                if target == start:
                    yield position, "Initial position of {!r} depends on itself: {}".format(
                        name, " -> ".join(path + [start]))
                    stack = []
                    break
                if target not in seen:
                    seen.add(target)
                    stack.append((target, path + [target]))


not_implemented(A + "1.0.0:positioning.road_lane_offset_in_bounds", "error",
                "s, t and offset coordinates shall be within the referenced road or lane.",
                "Requires OpenDRIVE road and lane geometry.")

# C.7 reference control -----------------------------------------------------------------------------------------


@rule(A + "1.0.0:reference_control.road_network_availability", "warning",
      "LogicFile and SceneGraphFile filepath should point to a resolvable file.",
      scope="A filepath without a file extension is a CARLA map name resolved by the simulator and is not checked.")
def road_network_availability(context):
    for element in context.root.findall("RoadNetwork/*"):
        if element.tag not in ("LogicFile", "SceneGraphFile"):
            continue
        path = context.text(element, "filepath")
        if path is None or not context.base_dir:
            continue
        if not path:
            yield element, "{} filepath is empty".format(element.tag)
        elif os.path.splitext(path)[1] and not os.path.isfile(context.resolve_file(path)):
            yield element, "{} {!r} does not exist".format(element.tag, path)


@rule(A + "1.0.0:reference_control.road_network_reference", "warning",
      "The RoadNetwork element should reference a LogicFile.")
def road_network_reference(context):
    network = context.root.find("RoadNetwork")
    if network is not None and network.find("LogicFile") is None:
        yield network, "RoadNetwork does not reference a LogicFile"


not_implemented(A + "1.0.0:reference_control.road_lane_exists", "error",
                "Referenced road and lane ids shall exist in the road network.",
                "Requires OpenDRIVE road and lane ids; CARLA towns referenced by name are only known to the server.")


@rule(A + "1.0.0:reference_control.controller_assignment", "error",
      "A ScenarioObject containing a MiscObject or an ExternalObjectReference shall not have an ObjectController "
      "assigned.")
def controller_assignment(context):
    for name, element in sorted(context.entities().items()):
        types = context.entity_types(name) if element.tag == "ScenarioObject" else None
        if types and types & {"MiscObject", "ExternalObjectReference"} and element.find("ObjectController") is not None:
            yield element.find("ObjectController"), "{} {!r} cannot have an ObjectController".format(
                sorted(types)[0], name)
    for action in _elements(context, "AssignControllerAction"):
        for name, types in _scenario_object_types(context, context.subjects(action)):
            if types & {"MiscObject", "ExternalObjectReference"}:
                yield action, "A controller cannot be assigned to {} {!r}".format(sorted(types)[0], name)


@rule(A + "1.2.0:reference_control.controller_ambiguity", "error",
      "If multiple controllers are assigned to a ScenarioObject, ActivateControllerAction shall reference the "
      "controller.", coverage="partial",
      scope="Counts the ObjectController elements of the ScenarioObject; checks ActivateControllerAction "
            "controllerRef/objectControllerRef.")
def controller_ambiguity(context):
    counts = dict((name, len(element.findall("ObjectController"))) for name, element in context.entities().items())
    for action in _elements(context, "ActivateControllerAction"):
        if action.attrib.get("controllerRef") or action.attrib.get("objectControllerRef"):
            continue
        for name in context.subjects(action):
            if counts.get(name, 0) > 1:
                yield action, "{!r} has {} controllers; ActivateControllerAction must name one".format(
                    name, counts[name])


@rule(A + "1.2.0:reference_control.lightstateaction_light_type", "error",
      "If the actor of a LightStateAction is not a Vehicle, the light type VehicleLight shall not be used.")
def lightstateaction_light_type(context):
    for action in _elements(context, "LightStateAction"):
        if action.find("LightType/VehicleLight") is None:
            continue
        for name, types in _known_types(context, context.subjects(action)):
            if types - {"Vehicle"}:
                yield action, "VehicleLight cannot be used for {} {!r}".format(sorted(types - {"Vehicle"})[0], name)


@rule(A + "1.2.0:reference_control.lightstateaction_lightstate_on_off", "warning",
      "If the light state on or off is used, flashingOnDuration and flashingOffDuration should not be set.")
def lightstateaction_lightstate_on_off(context):
    for state in _elements(context, "LightState"):
        if context.text(state, "mode") in ("on", "off") and (
                "flashingOnDuration" in state.attrib or "flashingOffDuration" in state.attrib):
            yield state, "Light mode {!r} sets flashing durations".format(context.text(state, "mode"))


@rule(A + "1.2.0:reference_control.lightstateaction_lightstate_flashing", "warning",
      "If the light state flashing is used, flashingOnDuration and flashingOffDuration should be set.")
def lightstateaction_lightstate_flashing(context):
    for state in _elements(context, "LightState"):
        if context.text(state, "mode") == "flashing" and not (
                "flashingOnDuration" in state.attrib and "flashingOffDuration" in state.attrib):
            yield state, "Light mode 'flashing' without flashingOnDuration and flashingOffDuration"


@rule(A + "1.2.0:reference_control.resolvable_variable_reference", "error",
      "A variable referenced from a VariableCondition or VariableAction shall be declared.")
def resolvable_variable_reference(context):
    variables = context.variables()
    for element in _elements(context, "VariableAction", "VariableCondition"):
        name = (element.attrib.get("variableRef") or "").lstrip("$")
        if name not in variables:
            yield element, "Unknown variable reference {!r}".format(element.attrib.get("variableRef"))


not_implemented(A + "1.0.0:reference_control.traffic_signal_condition_references", "error",
                "TrafficSignalCondition name shall reference a signal of the road network.",
                "Requires OpenDRIVE signal ids.")


def _signal_controllers(context):
    return dict((controller.attrib.get("name"), controller)
                for controller in context.root.findall("RoadNetwork/TrafficSignals/TrafficSignalController"))


def _phases(controller):
    return set(phase.attrib.get("name") for phase in controller.findall("Phase"))


@rule(A + "1.0.0:reference_control.traffic_signal_controller_action_references", "error",
      "TrafficSignalControllerAction phase and trafficSignalControllerRef shall reference elements of the scenario.")
def signal_controller_action_references(context):
    controllers = _signal_controllers(context)
    for action in _elements(context, "TrafficSignalControllerAction"):
        name, phase = context.text(action, "trafficSignalControllerRef"), context.text(action, "phase")
        if name not in controllers:
            yield action, "Unknown TrafficSignalController {!r}".format(name)
        elif phase not in _phases(controllers[name]):
            yield action, "TrafficSignalController {!r} has no phase {!r}".format(name, phase)


@rule(A + "1.0.0:reference_control.traffic_signal_controller_condition_references", "error",
      "TrafficSignalControllerCondition phase shall reference a phase of the scenario.", coverage="partial",
      scope="The phase is checked against the scenario's TrafficSignalControllers; the controller reference into "
            "the road network file is not checked.")
def signal_controller_condition_references(context):
    controllers = _signal_controllers(context)
    for condition in _elements(context, "TrafficSignalControllerCondition"):
        name, phase = context.text(condition, "trafficSignalControllerRef"), context.text(condition, "phase")
        candidates = [controllers[name]] if name in controllers else list(controllers.values())
        if not any(phase in _phases(controller) for controller in candidates):
            yield condition, "Phase {!r} is not defined by {}".format(
                phase, "TrafficSignalController {!r}".format(name) if name in controllers else "the scenario")


@rule(A + "1.0.0:reference_control.traffic_signal_controller_references", "error",
      "TrafficSignalController reference shall name an existing TrafficSignalController.", coverage="partial",
      scope="The reference attribute; the optional reference of name into the road network is not checked.")
def traffic_signal_controller_references(context):
    controllers = _signal_controllers(context)
    for controller in controllers.values():
        reference = context.text(controller, "reference")
        if reference and reference not in controllers:
            yield controller, "Unknown TrafficSignalController reference {!r}".format(reference)


not_implemented(A + "1.0.0:reference_control.traffic_signal_state_action_references", "error",
                "TrafficSignalStateAction name shall reference a signal of the road network.",
                "Requires OpenDRIVE signal ids.")
not_implemented(A + "1.0.0:reference_control.traffic_signal_state_references", "error",
                "TrafficSignalState trafficSignalId shall reference a signal of the road network.",
                "Requires OpenDRIVE signal ids.")


def _global_parameter_names(context, path):
    resolved = context.resolve_file(path)
    if not resolved or not os.path.isfile(resolved):
        return None
    try:
        root = ET.parse(resolved).getroot()
    except (ET.ParseError, OSError):
        return None
    return set(item.attrib.get("name") for item in root.findall("ParameterDeclarations/ParameterDeclaration"))


@rule(A + "1.0.0:reference_control.check_varied_parameters", "error",
      "Varied and assigned parameters shall reference existing ParameterDeclarations.", coverage="partial",
      scope="Distribution parameterName/parameterRef against a resolvable ScenarioFile, and CatalogReference "
            "ParameterAssignments against resolvable catalog entries.")
def check_varied_parameters(context):
    for reference in _elements(context, "CatalogReference"):
        entry = context.catalog_entry(reference)
        if entry is None:
            continue
        declared = set(item.attrib.get("name") for item in entry.findall("ParameterDeclarations/ParameterDeclaration"))
        for assignment in reference.findall("ParameterAssignments/ParameterAssignment"):
            if assignment.attrib.get("parameterRef") not in declared:
                yield assignment, "Catalog entry {!r} declares no parameter {!r}".format(
                    entry.attrib.get("name"), assignment.attrib.get("parameterRef"))
    distribution = context.root.find("ParameterValueDistribution")
    if distribution is None:
        return
    scenario = distribution.find("ScenarioFile")
    names = _global_parameter_names(context, scenario.attrib.get("filepath")) if scenario is not None else None
    if names is None:
        return
    for element in distribution.iter():
        name = element.attrib.get("parameterName") if element.tag in (
            "DeterministicSingleParameterDistribution", "StochasticDistribution") else None
        if element.tag == "ParameterAssignment":
            name = element.attrib.get("parameterRef")
        if name is not None and name not in names:
            yield element, "Scenario file declares no parameter {!r}".format(name)


@rule(A + "1.1.0:reference_control.single_or_multi_parameters", "error",
      "Single- and multi-parameter distributions shall not vary the same parameter.")
def single_or_multi_parameters(context):
    singles = set(item.attrib.get("parameterName") for item in
                  _elements(context, "DeterministicSingleParameterDistribution"))
    for multi in _elements(context, "DeterministicMultiParameterDistribution"):
        for assignment in multi.iter("ParameterAssignment"):
            if assignment.attrib.get("parameterRef") in singles:
                yield assignment, "Parameter {!r} is varied by a single- and a multi-parameter distribution".format(
                    assignment.attrib.get("parameterRef"))


@rule(A + "1.0.0:reference_control.catalog_reference_resolvability", "error",
      "CatalogReference catalogName and entryName shall reference a valid catalog and entry.",
      scope="Catalogs are read from every .xosc file in the CatalogLocations directories; checked when the "
            "document location is known.")
def catalog_reference_resolvability(context):
    catalogs = context.catalogs()
    if catalogs is None:
        return
    for reference in _elements(context, "CatalogReference"):
        catalog, entry = context.text(reference, "catalogName"), context.text(reference, "entryName")
        if catalog is None or entry is None:
            continue
        if catalog not in catalogs:
            yield reference, "Unknown catalog {!r}".format(catalog)
        elif entry not in catalogs[catalog]:
            yield reference, "Catalog {!r} has no entry {!r}".format(catalog, entry)


@rule(A + "1.0.0:reference_control.catalogs_referenced_by_directory", "error",
      "Directories specified in CatalogLocations shall exist.")
def catalogs_referenced_by_directory(context):
    for directory, path in context.catalog_directories():
        if path is not None and not os.path.isdir(path):
            yield directory, "Catalog directory {!r} does not exist".format(directory.attrib.get("path"))


STORYBOARD_TYPES = {"Story": "story", "Act": "act", "ManeuverGroup": "maneuverGroup", "Maneuver": "maneuver",
                    "Event": "event", "Action": "action"}


def _storyboard_index(context):
    """storyboardElementType -> list of qualified names; second value is False if catalog maneuvers are unknown."""
    index, complete = {}, True

    def visit(element, prefix):
        for child in element:
            kind = STORYBOARD_TYPES.get(child.tag)
            if child.tag == "Action" and element.tag != "Event":
                kind = None
            path = prefix
            if kind is not None and child.attrib.get("name") is not None:
                path = prefix + [child.attrib["name"]]
                index.setdefault(kind, []).append(path)
            visit(child, path)

    storyboard = context.root.find("Storyboard")
    if storyboard is not None:
        visit(storyboard, [])
        for group in storyboard.iter("ManeuverGroup"):
            for reference in group.findall("CatalogReference"):
                entry = context.catalog_entry(reference)
                if entry is None:
                    complete = False
                    continue
                prefix = [ancestor.attrib.get("name") for ancestor in reversed(list(context.ancestors(reference)))
                          if ancestor.tag in STORYBOARD_TYPES] + [entry.attrib.get("name")]
                index.setdefault("maneuver", []).append(prefix)
                visit(entry, prefix)
    return index, complete


@rule(A + "1.0.0:reference_control.resolvable_storyboard_element_ref", "error",
      "StoryboardElementStateCondition storyboardElementRef shall point to an existing element of the given type "
      "and be uniquely resolvable.")
def resolvable_storyboard_element_ref(context):
    index, complete = _storyboard_index(context)
    for condition in _elements(context, "StoryboardElementStateCondition"):
        reference = context.text(condition, "storyboardElementRef")
        kind = context.text(condition, "storyboardElementType")
        if reference is None or kind is None:
            continue
        parts = reference.split("::")
        matches = [path for path in index.get(kind, []) if path[-len(parts):] == parts]
        if not matches and complete:
            yield condition, "No {} named {!r}".format(kind, reference)
        elif len(matches) > 1:
            yield condition, "{} reference {!r} is ambiguous ({} matches)".format(kind, reference, len(matches))


@rule(A + "1.1.0:general.references_to_scenario_object", "error",
      "A single ScenarioObject referenced as actor of a movement or controller action shall be a Vehicle or a "
      "Pedestrian.")
def references_to_scenario_object(context):
    for action in _elements(context, *CONTROLLED_ACTIONS):
        for name, types in _scenario_object_types(context, context.subjects(action)):
            if types - MOVABLE:
                yield action, "{} cannot act on {} {!r}".format(action.tag, sorted(types)[0], name)


@rule(A + "1.1.0:general.homogeneous_references_to_entity_selection", "error",
      "An EntitySelection referenced as actor of a movement or controller action shall be a group of vehicles or a "
      "group of pedestrians.")
def homogeneous_entity_selection(context):
    for action in _elements(context, *CONTROLLED_ACTIONS):
        for name in context.subjects(action):
            element = context.entities().get(name)
            if element is None or element.tag != "EntitySelection":
                continue
            types = context.entity_types(name)
            if types is not None and (len(types) != 1 or types - MOVABLE):
                yield action, "EntitySelection {!r} mixes or contains non-movable types ({})".format(
                    name, ", ".join(sorted(types)) or "empty")


@rule(A + "1.1.0:reference_control.traffic_name_exists", "error",
      "The trafficName of a TrafficStopAction shall exist in a traffic creation action.")
def traffic_name_exists(context):
    creators = set(context.text(action, "trafficName") for action in _elements(context, "TrafficAction")
                   if action.find("TrafficStopAction") is None)
    for action in _elements(context, "TrafficAction"):
        if action.find("TrafficStopAction") is not None and context.text(action, "trafficName") not in creators:
            yield action, "No traffic creation action defines trafficName {!r}".format(
                context.text(action, "trafficName"))


@rule(A + "1.0.0:reference_control.override_controller_action_only_allows_vehicles", "error",
      "Only a Vehicle ScenarioObject or a selection of vehicles shall be the actor of an "
      "OverrideControllerValueAction.")
def override_controller_only_vehicles(context):
    for action in _elements(context, "OverrideControllerValueAction"):
        for name, types in _known_types(context, context.subjects(action)):
            if types != {"Vehicle"}:
                yield action, "OverrideControllerValueAction cannot act on {!r} ({})".format(
                    name, ", ".join(sorted(types)))


# C.8 routing ---------------------------------------------------------------------------------------------------

not_implemented(A + "1.0.0:routing.ambiguous_route_waypoints", "warning",
                "Ambiguous route waypoints can be given as road or lane positions.",
                "Ambiguity depends on the OpenDRIVE road network.")
not_implemented(A + "1.0.0:routing.route_waypoints_locations", "warning",
                "Route waypoints should not be located in junctions.", "Requires OpenDRIVE junction geometry.")


@rule(A + "1.0.0:routing.cardinality_of_control_points_in_nurbs", "error",
      "The number of ControlPoint elements in Nurbs shall be greater than or equal to the order of the curve.")
def cardinality_of_control_points_in_nurbs(context):
    for nurbs in _elements(context, "Nurbs"):
        order = context.number(nurbs, "order")
        count = len(nurbs.findall("ControlPoint"))
        if order is not None and count < order:
            yield nurbs, "Nurbs of order {:g} has only {} control points".format(order, count)


def _shape_has_timing(shape):
    polyline, nurbs = shape.find("Polyline"), shape.find("Nurbs")
    if polyline is not None:
        return all("time" in vertex.attrib for vertex in polyline.findall("Vertex"))
    if nurbs is not None:
        return all("time" in point.attrib for point in nurbs.findall("ControlPoint"))
    clothoid, spline = shape.find("Clothoid"), shape.find("ClothoidSpline")
    if clothoid is not None:
        return "startTime" in clothoid.attrib and "stopTime" in clothoid.attrib
    if spline is not None:
        return "timeEnd" in spline.attrib and all(
            "timeStart" in segment.attrib for segment in spline.findall("ClothoidSplineSegment"))
    return True


@rule(A + "1.0.0:routing.trajectory_timing_exists_if_requested", "error",
      "If the TimeReference of a FollowTrajectoryAction uses Timing, the trajectory shape shall provide the timing.")
def trajectory_timing_exists_if_requested(context):
    for action in _elements(context, "FollowTrajectoryAction"):
        if action.find("TimeReference/Timing") is None:
            continue
        trajectory = _trajectory(context, action)
        shape = trajectory.find("Shape") if trajectory is not None else None
        if shape is not None and not _shape_has_timing(shape):
            yield action, "Timing is requested but trajectory {!r} has no timing in its shape".format(
                trajectory.attrib.get("name"))


@rule(A + "1.1.0:routing.offset_should_be_less_than_trajectory_length", "error",
      "initialDistanceOffset shall be less or equal to the arc length of the trajectory.", coverage="partial",
      scope="Polyline trajectories whose vertices are all WorldPositions (the standard notes the rule cannot be "
            "checked statically for relative positions).")
def offset_within_trajectory_length(context):
    for action in _elements(context, "FollowTrajectoryAction"):
        offset = context.number(action, "initialDistanceOffset")
        trajectory = _trajectory(context, action)
        polyline = trajectory.find("Shape/Polyline") if trajectory is not None else None
        if offset is None or polyline is None:
            continue
        points = []
        for vertex in polyline.findall("Vertex"):
            world = vertex.find("Position/WorldPosition")
            if world is None:
                points = None
                break
            coordinates = [context.number(world, axis) for axis in ("x", "y", "z")]
            points.append([value or 0.0 for value in coordinates])
        if not points:
            continue
        length = sum(math.sqrt(sum((b - a) ** 2 for a, b in zip(p, q))) for p, q in zip(points, points[1:]))
        if offset > length + 1e-9:
            yield action, "initialDistanceOffset {:g} exceeds the trajectory length {:g}".format(offset, length)


# C.9 scenario logic --------------------------------------------------------------------------------------------

ROAD_NETWORK_ELEMENTS = ("RoadPosition", "LanePosition", "GeoPosition", "LaneChangeAction", "InfrastructureAction",
                         "EndOfRoadCondition", "OffroadCondition", "TrafficSignalAction", "TrafficSignalCondition",
                         "TrafficSignalControllerCondition", "TrafficSignalController")


@rule(A + "1.0.0:scenario_logic.invalid_elements_if_no_road_network", "error",
      "Without a road network (LogicFile), road-network-dependent elements shall not be used.")
def invalid_elements_if_no_road_network(context):
    if context.root.find("RoadNetwork/LogicFile") is not None or context.root.find("RoadNetwork") is None:
        return
    for element in _elements(context, *ROAD_NETWORK_ELEMENTS):
        yield element, "{} requires a road network LogicFile".format(element.tag)


def _controller_of(context, element):
    """The Controller element of an ObjectController/AssignControllerAction (resolving catalogs), or None."""
    controller = element.find("Controller")
    if controller is None and element.find("ObjectController") is not None:
        return _controller_of(context, element.find("ObjectController"))
    if controller is None and element.find("CatalogReference") is not None:
        controller = context.catalog_entry(element.find("CatalogReference"))
    return controller if controller is not None and controller.tag == "Controller" else None


def _activated_controller(context, action, name):
    scenario_object = context.entities().get(name)
    if scenario_object is None:
        return None
    controllers = scenario_object.findall("ObjectController")
    object_ref, controller_ref = action.attrib.get("objectControllerRef"), action.attrib.get("controllerRef")
    for object_controller in controllers:
        controller = _controller_of(context, object_controller)
        if object_ref and object_controller.attrib.get("name") == object_ref:
            return controller
        if controller_ref and controller is not None and controller.attrib.get("name") == controller_ref:
            return controller
    if len(controllers) == 1 and not object_ref and not controller_ref:
        return _controller_of(context, controllers[0])
    return None


@rule(A + "1.2.0:scenario_logic.controller_activation", "error",
      "A controller shall not be activated in a domain that its controllerType does not define.",
      coverage="partial", scope="Controllers resolvable from the ScenarioObject, the action or a catalog.")
def controller_activation(context):
    checks = []
    for action in _elements(context, "ActivateControllerAction"):
        domains = set(domain for domain in ("lateral", "longitudinal", "lighting", "animation")
                      if _boolean(context, action, domain))
        for name in context.subjects(action):
            checks.append((action, domains, _activated_controller(context, action, name)))
    for action in _elements(context, "AssignControllerAction"):
        domains = set(domain for domain in ("lateral", "longitudinal", "lighting", "animation")
                      if _boolean(context, action, "activate" + domain[0].upper() + domain[1:]))
        checks.append((action, domains, _controller_of(context, action)))
    for action, domains, controller in checks:
        if controller is None or not domains:
            continue
        controller_type = context.text(controller, "controllerType") or "movement"
        invalid = domains - CONTROLLER_DOMAINS.get(controller_type, set())
        if invalid:
            yield action, "Controller {!r} of type {!r} cannot be activated for {}".format(
                controller.attrib.get("name"), controller_type, ", ".join(sorted(invalid)))


@rule(A + "1.2.0:scenario_logic.targetspeed_maxspeed_speedprofileaction", "warning",
      "With followingMode follow and no entityRef, SpeedProfileEntry speeds should not exceed the actor's maxSpeed.")
def targetspeed_maxspeed_speedprofileaction(context):
    for action in _elements(context, "SpeedProfileAction"):
        if context.text(action, "followingMode") != "follow" or action.attrib.get("entityRef"):
            continue
        for name in context.subjects(action):
            max_speed = _max_speed(context, name)
            for entry in action.findall("SpeedProfileEntry"):
                speed = context.number(entry, "speed")
                if max_speed is not None and speed is not None and speed > max_speed:
                    yield entry, "Speed {:g} exceeds maxSpeed {:g} of {!r}".format(speed, max_speed, name)


@rule(A + "1.2.0:scenario_logic.targetspeed_maxspeed_general", "warning",
      "With followingMode follow, a SpeedAction target should not exceed the vehicle's maxSpeed.",
      coverage="partial", scope="AbsoluteTargetSpeed targets.")
def targetspeed_maxspeed_general(context):
    for action in _elements(context, "SpeedAction"):
        dynamics, target = action.find("SpeedActionDynamics"), action.find("SpeedActionTarget/AbsoluteTargetSpeed")
        if dynamics is None or target is None or context.text(dynamics, "followingMode") != "follow":
            continue
        speed = context.number(target, "value")
        for name in context.subjects(action):
            max_speed = _max_speed(context, name)
            if max_speed is not None and speed is not None and speed > max_speed:
                yield target, "Target speed {:g} exceeds maxSpeed {:g} of {!r}".format(speed, max_speed, name)


not_implemented(A + "1.0.0:scenario_logic.trajectory_curvature_vs_steering_angle", "warning",
                "The minimum radius of a non-Polyline trajectory should not be less than the actor's turning circle.",
                "Requires curvature evaluation of Clothoid, ClothoidSpline and Nurbs shapes.")

# C.10 XML ------------------------------------------------------------------------------------------------------


@rule(A + "1.0.0:xml.valid_schema", "error",
      "The document shall comply with the schema of the version declared in its FileHeader.",
      scope="Bundled schemas: 1.0 and 1.3.1 (used for 1.3.0 and 1.3.1 documents); other versions are rejected.")
def valid_schema(context):
    # Deferred: the schema validator imports the loader lazily as well.
    from srunner.openscenario.validation.schema import SchemaValidator  # pylint: disable=import-outside-toplevel
    for diagnostic in SchemaValidator().validate(context.document, raise_on_error=False):
        yield diagnostic.source if diagnostic.source is not None else context.root, diagnostic.message


# C.11 expressions ----------------------------------------------------------------------------------------------

_FUNCTION_WITHOUT_PARENTHESES = re.compile(r"\b(" + "|".join(FUNCTIONS) + r")\b(?!\s*\()")


def _expected_type(context, element, attribute):
    if element.tag == "ParameterDeclaration" and attribute == "value":
        return element.attrib.get("parameterType")
    if element.tag == "VariableDeclaration" and attribute == "value":
        return element.attrib.get("variableType")
    if element.tag == "ParameterAssignment":
        return None
    value_type = context.attribute_type(element, attribute)
    return value_type if value_type != "dateTime" else None


def _classify_static(error, text):
    message = error.diagnostic.message
    if message.startswith(("Unsupported function", "Unsupported expression construct", "Unknown identifier",
                           "Unsupported literal")):
        return "allowed_operators"
    if "expects" in message or (message.startswith("Invalid expression syntax") and
                                _FUNCTION_WITHOUT_PARENTHESES.search(text.strip()[2:-1])):
        return "arguments_of_operators"
    return "evaluation_of_expressions_possible"


_EVALUATION_RULES = {
    Diagnostic.ARITHMETIC_ERROR: (("NaN or infinite", "nan_or_infinity"), ("overflow", "overflow_underflow"),
                                  ("", "arithmetic_errors")),
    Diagnostic.TYPE_MISMATCH: (("boolean is expected", "type_of_boolean"), ("implicitly converted", "type_casting"),
                               ("out of range", "overflow_underflow")),
}


def _classify_evaluation(error):
    diagnostic = error.diagnostic
    for marker, name in _EVALUATION_RULES.get(diagnostic.code, ()):
        if marker in diagnostic.message:
            return name
    return "evaluation_of_expressions_possible"


def _expression_findings(context):
    """{rule name: [(element, message)]} for every ``${...}`` attribute value, computed once per document."""
    if "expressions" in context.cache:
        return context.cache["expressions"]
    findings = {}
    for element in context.root.iter():
        for attribute, value in element.attrib.items():
            if not expressions.is_expression(value):
                continue
            where = "{}@{}".format(element.tag, attribute)
            try:
                names = expressions.check_expression(value)
            except ValueError as error:
                findings.setdefault(_classify_static(error, value), []).append(
                    (element, "{}: {}".format(where, _reason(error))))
                continue
            scope = context.declarations_in_scope(element)
            families = set(scope[name].attrib.get("parameterType").replace("integer", "int") for name in names
                           if name in scope and scope[name].attrib.get("parameterType")) & INTEGER_FAMILY
            if len(families) > 1:
                findings.setdefault("type_mixture", []).append((element, "{}: {!r} mixes parameters of types {}".format(
                    where, value, ", ".join(sorted(families)))))
            try:
                context.evaluate(value, element, _expected_type(context, element, attribute))
            except Unresolved:
                continue
            except ValueError as error:
                if getattr(error, "diagnostic", None) is None:
                    continue
                findings.setdefault(_classify_evaluation(error), []).append(
                    (element, "{}: {}".format(where, _reason(error))))
    context.cache["expressions"] = findings
    return findings


def _expression_rule(name, description, coverage="full", scope=None):
    def check(context):
        return iter(_expression_findings(context).get(name, ()))
    check.__name__ = name
    rule(A + "1.1.0:expressions." + name, "error", description, coverage, scope)(check)


_expression_rule("evaluation_of_expressions_possible",
                 "The evaluation of expressions shall be possible (literals and parameters; operators only for numeric "
                 "and boolean types; no unresolvable type mismatch).",
                 coverage="partial",
                 scope="Expressions are evaluated with the declared parameter values (and command-line overrides); "
                       "expressions in CatalogReference ParameterAssignments are not checked against the types of "
                       "the catalog parameters.")
_expression_rule("allowed_operators", "Expressions shall only use the operators round, floor, ceil, sqrt, pow, *, /, "
                 "%, +, -, not, and, or, sin, cos, tan, asin, acos, atan, sign, abs, max, min.")
_expression_rule("arguments_of_operators", "Function arguments shall follow the operator name in parentheses.")
_expression_rule("type_of_boolean", "An arithmetic function shall not be used where a Boolean value is expected.")
_expression_rule("type_casting", "Only integer to double (and integer literal) implicit conversions are allowed; use "
                 "round, floor or ceil to convert double to int.")
_expression_rule("nan_or_infinity", "Expressions resulting in NaN or Infinity shall result in an error.")
_expression_rule("arithmetic_errors", "Expressions shall be free of arithmetic errors (division by zero, sqrt of a "
                 "negative value, ...).")
_expression_rule("overflow_underflow", "Expressions shall not result in an arithmetic overflow or underflow.",
                 coverage="partial", scope="Integer overflow beyond 64 bits, unsigned range violations and floating "
                 "point overflow; floating point underflow is not detected.")
_expression_rule("type_mixture", "Parameters of the types unsignedInt, unsignedShort, and int shall not be mixed in an "
                 "expression.")
