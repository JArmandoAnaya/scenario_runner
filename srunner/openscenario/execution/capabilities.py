"""Backend capability queries and the OpenSCENARIO 1.3.1 feature capability matrix.

Every feature element the 1.3.1 schema defines (see
:func:`srunner.openscenario.validation.schema_model.SchemaModel.features`) has
one row with three independent states:

* ``parsed``: ``typed`` (typed model in :mod:`srunner.openscenario.model`),
  ``legacy`` (read from the XML by :mod:`srunner.tools.openscenario_parser`) or
  ``schema`` (only validated by the XSD).
* ``semantic``: ``validated`` (semantic validation of a typed model or typed evaluation), ``checked``
  (Annex C checker rules inspect it, no typed model) or ``none``.
* ``runtime_init`` / ``runtime_story``: how the ScenarioRunner backend executes
  the element in the Init section and in stories (``semantic`` executor,
  ``legacy`` atomics, ``unsupported`` or ``n/a``).  Unsupported elements are
  reported at build time by :mod:`srunner.openscenario.execution.feature_audit`.

``verification`` is ``executed`` (a mocked-CARLA test ticks or initialises the
behaviour, named in ``evidence``), ``built`` (a test builds a scenario that
contains the element) or ``none``.  ``live_carla_verified`` is False for every
row: no row has been verified against a running CARLA server by this matrix.
"""

from __future__ import absolute_import

from collections import OrderedDict, namedtuple


class BackendCapabilities(object):
    """Named capabilities a backend declares."""

    def __init__(self, capabilities=None):
        self._capabilities = set(capabilities or [])

    def supports(self, capability):
        return capability in self._capabilities

    def add(self, capability):
        self._capabilities.add(capability)

    def as_set(self):
        return set(self._capabilities)


FeatureCapability = namedtuple("FeatureCapability", (
    "category", "element", "parsed", "semantic", "runtime_init", "runtime_story", "verification", "evidence",
    "live_carla_verified", "notes"))

RUNTIME_STATES = ("semantic", "legacy", "unsupported", "n/a")
U, L, S, NA = "unsupported", "legacy", "semantic", "n/a"
RUNTIME_TEST = "srunner.tests.test_openscenario_runtime"
ROUTING_TEST = "srunner.tests.test_openscenario_routing_runtime"
CONFORMANCE_TEST = "srunner.tests.test_openscenario_conformance_runtime"

_ROWS = [
    # category, element, parsed, semantic, init, story, verification, evidence, notes
    ("action", "AcquirePositionAction", "typed", "validated", S, S, "built", None, ""),
    ("action", "ActivateControllerAction", "legacy", "checked", U, L, "built", None,
     "PrivateAction form only, longitudinal attribute required (toggles the CARLA autopilot); the 1.3 form inside "
     "ControllerAction is unsupported"),
    ("action", "AnimationAction", "schema", "checked", U, U, "none", None, ""),
    ("action", "AssignControllerAction", "legacy", "checked", L, L, "built", None,
     "Controller or CatalogReference with a 'module' property; ObjectController content is unsupported"),
    ("action", "AssignRouteAction", "typed", "validated", S, S, "built", None, "Closed routes are driven once"),
    ("action", "ConnectTrailerAction", "schema", "none", U, U, "none", None, ""),
    ("action", "DisconnectTrailerAction", "schema", "none", U, U, "none", None, ""),
    ("action", "EntityAction", "legacy", "none", L, L, "built", None, ""),
    ("action", "EnvironmentAction", "legacy", "none", L, L, "built", None,
     "Mapped to CARLA weather and road friction; 1.3-only attributes are not mapped (approximation warning)"),
    ("action", "FollowTrajectoryAction", "typed", "validated", S, S, "executed",
     ROUTING_TEST + ".TestOpenScenarioRoutingRuntime.test_init_follow_trajectory_preserves_timing_and_following_mode",
     "Polyline shapes only; initialDistanceOffset is unsupported"),
    ("action", "InfrastructureAction", "legacy", "checked", U, L, "none", None, ""),
    ("action", "LaneChangeAction", "legacy", "none", U, L, "built", None, "RelativeTargetLane only"),
    ("action", "LaneOffsetAction", "legacy", "none", L, L, "built", None, ""),
    ("action", "LateralDistanceAction", "legacy", "checked", L, L, "built", None, ""),
    ("action", "LightStateAction", "schema", "checked", U, U, "none", None, ""),
    ("action", "LongitudinalDistanceAction", "legacy", "checked", U, L, "none", None, "distance only; timeGap is "
     "unsupported"),
    ("action", "OverrideControllerValueAction", "legacy", "checked", L, L, "built", None,
     "Accepted inside a ControllerAction that assigns a controller, with every override inactive (no effect)"),
    ("action", "ParameterAction", "typed", "validated", S, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end", ""),
    ("action", "RandomRouteAction", "schema", "none", U, U, "none", None, ""),
    ("action", "SetMonitorAction", "schema", "none", U, U, "none", None, ""),
    ("action", "SpeedAction", "legacy", "checked", L, L, "built", None,
     "Init: AbsoluteTargetSpeed sets the initial speed; RelativeTargetSpeed in Init is unsupported"),
    ("action", "SpeedProfileAction", "typed", "validated", S, S, "executed",
     ROUTING_TEST + ".TestOpenScenarioRoutingRuntime.test_speed_profile_steps_through_every_entry",
     "Entries are commanded to the actor's controller; DynamicConstraints are not enforced"),
    ("action", "SynchronizeAction", "legacy", "checked", U, L, "built", None, ""),
    ("action", "TeleportAction", "legacy", "none", L, L, "built", None, ""),
    ("action", "TrafficAction", "schema", "checked", U, U, "none", None, ""),
    ("action", "UserDefinedAction", "legacy", "none", U, L, "none", None, ""),
    ("action", "VariableAction", "typed", "validated", S, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end", ""),
    ("action", "VisibilityAction", "schema", "none", U, U, "none", None, ""),
    ("entity_action", "AddEntityAction", "legacy", "none", L, L, "built", None, ""),
    ("entity_action", "DeleteEntityAction", "legacy", "none", L, L, "built", None, ""),
    ("traffic_signal_action", "TrafficSignalControllerAction", "legacy", "checked", U, L, "none", None,
     "The single TrafficSignalController/Phase of the RoadNetwork"),
    ("traffic_signal_action", "TrafficSignalStateAction", "legacy", "none", U, L, "none", None,
     "CARLA traffic light states green, red, yellow and off"),
    ("traffic_action", "TrafficAreaAction", "schema", "none", U, U, "none", None, ""),
    ("traffic_action", "TrafficSinkAction", "schema", "none", U, U, "none", None, ""),
    ("traffic_action", "TrafficSourceAction", "schema", "checked", U, U, "none", None, ""),
    ("traffic_action", "TrafficStopAction", "schema", "checked", U, U, "none", None, ""),
    ("traffic_action", "TrafficSwarmAction", "schema", "checked", U, U, "none", None, ""),
    ("parameter_action", "ModifyAction", "typed", "validated", S, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end", ""),
    ("parameter_action", "SetAction", "typed", "validated", S, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end", ""),
    ("variable_action", "ModifyAction", "typed", "validated", S, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end", ""),
    ("variable_action", "SetAction", "typed", "validated", S, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end", ""),
    ("user_defined_action", "CustomCommandAction", "legacy", "none", U, L, "built", None,
     "Runs the command given as type through the shell"),
    ("override_action", "Brake", "legacy", "none", U, U, "built", None, "Only inactive overrides are accepted"),
    ("override_action", "Clutch", "legacy", "none", U, U, "built", None, "Only inactive overrides are accepted"),
    ("override_action", "Gear", "legacy", "none", U, U, "built", None, "Only inactive overrides are accepted"),
    ("override_action", "ParkingBrake", "legacy", "none", U, U, "built", None, "Only inactive overrides are accepted"),
    ("override_action", "SteeringWheel", "legacy", "none", U, U, "built", None, "Only inactive overrides are accepted"),
    ("override_action", "Throttle", "legacy", "none", U, U, "built", None, "Only inactive overrides are accepted"),
    ("condition", "ByEntityCondition", "legacy", "checked", NA, L, "built", None, ""),
    ("condition", "ParameterCondition", "legacy", "validated", NA, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end",
     "Conditions named criteria_<Name> are ScenarioRunner evaluation criteria"),
    ("condition", "SimulationTimeCondition", "legacy", "none", NA, L, "built", None, ""),
    ("condition", "StoryboardElementStateCondition", "legacy", "checked", NA, L, "built", None,
     "startTransition, stopTransition, endTransition and completeState only"),
    ("condition", "TimeOfDayCondition", "legacy", "checked", NA, L, "none", None,
     "dateTime without fractional seconds or time zone"),
    ("condition", "TrafficSignalCondition", "legacy", "none", NA, L, "none", None, "CARLA traffic light states"),
    ("condition", "TrafficSignalControllerCondition", "legacy", "checked", NA, L, "none", None,
     "Phases go, stop and attention of the single TrafficSignalController"),
    ("condition", "UserDefinedValueCondition", "schema", "none", NA, U, "none", None, ""),
    ("condition", "VariableCondition", "legacy", "validated", NA, S, "executed",
     RUNTIME_TEST + ".TestOpenScenarioRuntimeWiring.test_variable_action_gates_variable_condition_end_to_end", ""),
    ("entity_condition", "AccelerationCondition", "legacy", "none", NA, L, "none", None, ""),
    ("entity_condition", "AngleCondition", "schema", "none", NA, U, "none", None, ""),
    ("entity_condition", "CollisionCondition", "legacy", "none", NA, L, "none", None, ""),
    ("entity_condition", "DistanceCondition", "legacy", "checked", NA, L, "built", None,
     "alongRoute selects the distance; coordinateSystem, relativeDistanceType and routingAlgorithm are not mapped "
     "(approximation warning)"),
    ("entity_condition", "EndOfRoadCondition", "legacy", "checked", NA, L, "none", None, ""),
    ("entity_condition", "OffroadCondition", "legacy", "checked", NA, L, "none", None, ""),
    ("entity_condition", "ReachPositionCondition", "legacy", "checked", NA, L, "built", None, ""),
    ("entity_condition", "RelativeAngleCondition", "typed", "validated", NA, S, "executed",
     CONFORMANCE_TEST + ".TestOpenScenario131Conformance.test_relative_conditions_tick",
     "coordinateSystem entity and world only"),
    ("entity_condition", "RelativeClearanceCondition", "typed", "validated", NA, S, "executed",
     CONFORMANCE_TEST + ".TestOpenScenario131Conformance.test_relative_conditions_tick", ""),
    ("entity_condition", "RelativeDistanceCondition", "legacy", "checked", NA, L, "built", None,
     "coordinateSystem and routingAlgorithm are not mapped (approximation warning)"),
    ("entity_condition", "RelativeSpeedCondition", "legacy", "none", NA, L, "none", None, ""),
    ("entity_condition", "SpeedCondition", "legacy", "none", NA, L, "none", None, ""),
    ("entity_condition", "StandStillCondition", "legacy", "none", NA, L, "built", None, ""),
    ("entity_condition", "TimeHeadwayCondition", "legacy", "none", NA, L, "none", None,
     "coordinateSystem, relativeDistanceType and routingAlgorithm are not mapped (approximation warning)"),
    ("entity_condition", "TimeToCollisionCondition", "legacy", "none", NA, L, "none", None,
     "coordinateSystem, relativeDistanceType and routingAlgorithm are not mapped (approximation warning)"),
    ("entity_condition", "TraveledDistanceCondition", "legacy", "checked", NA, L, "built", None, ""),
    ("position", "GeoPosition", "typed", "checked", U, U, "none", None, ""),
    ("position", "LanePosition", "typed", "checked", L, L, "built", None, ""),
    ("position", "RelativeLanePosition", "typed", "checked", L, L, "none", None, ""),
    ("position", "RelativeObjectPosition", "typed", "checked", L, L, "built", None, ""),
    ("position", "RelativeRoadPosition", "typed", "checked", L, L, "built", None, ""),
    ("position", "RelativeWorldPosition", "typed", "checked", L, L, "built", None, ""),
    ("position", "RoadPosition", "typed", "checked", L, L, "built", None, ""),
    ("position", "RoutePosition", "typed", "validated", U, U, "none", None, ""),
    ("position", "TrajectoryPosition", "typed", "none", U, U, "none", None, ""),
    ("position", "WorldPosition", "typed", "checked", L, L, "built", None, ""),
    ("trajectory_shape", "Clothoid", "typed", "validated", U, U, "none", None, ""),
    ("trajectory_shape", "ClothoidSpline", "typed", "validated", U, U, "none", None, ""),
    ("trajectory_shape", "Nurbs", "typed", "validated", U, U, "none", None, ""),
    ("trajectory_shape", "Polyline", "typed", "validated", S, S, "executed",
     ROUTING_TEST + ".TestOpenScenarioRoutingRuntime.test_init_follow_trajectory_preserves_timing_and_following_mode",
     ""),
    ("route_position", "FromCurrentEntity", "typed", "validated", U, U, "none", None, ""),
    ("route_position", "FromLaneCoordinates", "typed", "validated", U, U, "none", None, ""),
    ("route_position", "FromRoadCoordinates", "typed", "validated", U, U, "none", None, ""),
    ("entity", "ExternalObjectReference", "schema", "checked", U, U, "none", None, ""),
    ("entity", "MiscObject", "legacy", "checked", L, L, "built", None, ""),
    ("entity", "Pedestrian", "legacy", "checked", L, L, "built", None, ""),
    ("entity", "Vehicle", "legacy", "checked", L, L, "built", None, ""),
    ("environment", "RoadCondition", "legacy", "none", L, L, "built", None, "frictionScaleFactor only"),
    ("environment", "TimeOfDay", "legacy", "checked", L, L, "built", None,
     "dateTime without fractional seconds or time zone"),
    ("environment", "Weather", "legacy", "none", L, L, "built", None,
     "fractionalCloudCover, temperature and atmosphericPressure are not mapped (approximation warning)"),
    ("weather", "DomeImage", "schema", "none", U, U, "none", None, ""),
    ("weather", "Fog", "legacy", "checked", L, L, "built", None, "visualRange only"),
    ("weather", "Precipitation", "legacy", "none", L, L, "built", None,
     "Rain from the 1.0 intensity attribute; precipitationIntensity is not mapped; snow is unsupported"),
    ("weather", "Sun", "legacy", "none", L, L, "built", None, "1.0 intensity drives cloudiness; illuminance is not "
     "mapped"),
    ("weather", "Wind", "schema", "none", U, U, "none", None, ""),
    ("speed_target", "AbsoluteTargetSpeed", "legacy", "checked", L, L, "built", None, ""),
    ("speed_target", "RelativeTargetSpeed", "legacy", "none", U, L, "none", None, ""),
    ("time_reference", "None", "typed", "validated", S, S, "built", None, ""),
    ("time_reference", "Timing", "typed", "validated", S, S, "executed",
     ROUTING_TEST + ".TestOpenScenarioRoutingRuntime.test_absolute_timing_is_relative_to_the_simulation_start", ""),
    ("distribution", "Deterministic", "schema", "checked", U, U, "none", None,
     "ParameterValueDistribution documents are not executable"),
    ("distribution", "Stochastic", "schema", "checked", U, U, "none", None,
     "ParameterValueDistribution documents are not executable"),
]

CAPABILITY_MATRIX = OrderedDict(
    ((row[0], row[1]), FeatureCapability(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], False,
                                         row[8]))
    for row in _ROWS)


def feature_capability(category, element):
    return CAPABILITY_MATRIX[(category, element)]


def capability_counts():
    """Counts per state, for the documentation summary."""
    counts = OrderedDict([("features", len(CAPABILITY_MATRIX))])
    for field in ("parsed", "semantic"):
        for row in CAPABILITY_MATRIX.values():
            key = "{}:{}".format(field, getattr(row, field))
            counts[key] = counts.get(key, 0) + 1
    for row in CAPABILITY_MATRIX.values():
        executable = S in (row.runtime_init, row.runtime_story) or L in (row.runtime_init, row.runtime_story)
        key = "runtime:executable" if executable else "runtime:unsupported"
        counts[key] = counts.get(key, 0) + 1
        key = "verification:{}".format(row.verification)
        counts[key] = counts.get(key, 0) + 1
    counts["live_carla_verified"] = sum(1 for row in CAPABILITY_MATRIX.values() if row.live_carla_verified)
    return counts


def capability_summary():
    """One-line summary of the matrix and of the checker rule coverage, as published in the documentation."""
    # Deferred: the checker imports the execution package's sibling modules.
    from srunner.openscenario.validation.checker import rule_coverage  # pylint: disable=import-outside-toplevel
    counts, rules = capability_counts(), rule_coverage()
    return ("Summary: {} features; parsed: {} typed, {} legacy, {} schema only; semantic: {} validated, {} checked, "
            "{} none; runtime: {} executable in at least one context, {} unsupported; verified: {} executed, {} built, "
            "{} none; live CARLA verified: {}. Annex C: {} rules implemented, {} partially implemented, {} not "
            "implemented.").format(
                counts["features"], counts.get("parsed:typed", 0), counts.get("parsed:legacy", 0),
                counts.get("parsed:schema", 0), counts.get("semantic:validated", 0), counts.get("semantic:checked", 0),
                counts.get("semantic:none", 0), counts.get("runtime:executable", 0),
                counts.get("runtime:unsupported", 0), counts.get("verification:executed", 0),
                counts.get("verification:built", 0), counts.get("verification:none", 0), counts["live_carla_verified"],
                len(rules["implemented"]), len(rules["partial"]), len(rules["not_implemented"]))


def capability_table_markdown():
    """The capability matrix as the Markdown table published in Docs/openscenario_support.md."""
    lines = ["| Category | Element | Parsed | Semantic | Runtime (Init) | Runtime (Story) | Verified by | Notes |",
             "|---|---|---|---|---|---|---|---|"]
    for row in CAPABILITY_MATRIX.values():
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            row.category, row.element, row.parsed, row.semantic, row.runtime_init, row.runtime_story,
            row.verification, row.notes))
    return "\n".join(lines)


if __name__ == "__main__":
    print(capability_table_markdown())
