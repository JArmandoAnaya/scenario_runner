## OpenSCENARIO Support

The scenario_runner supports [OpenSCENARIO](http://www.openscenario.org/) 1.0 and ASAM OpenSCENARIO XML 1.3 (1.3.0
and 1.3.1) documents; see [Versions, validation and conformance](#versions-validation-and-conformance) for what is
validated, what is checked and what is executed.
The current implementation covers maneuver Actions, Conditions, Stories and the Storyboard.
If you would like to use evaluation criteria for a scenario to evaluate pass/fail results, these can be implemented
as StopTriggers (see below). However, not all features for these elements are yet available. If in doubt, please see the
module documentation in srunner/tools/openscenario_parser.py

An example for a supported scenario based on OpenSCENARIO is available [here](https://github.com/carla-simulator/scenario_runner/blob/master/srunner/examples/FollowLeadingVehicle.xosc)

In addition, it is recommended to take a look into the official documentation available [here](https://releases.asam.net/OpenSCENARIO/1.0.0/Model-Documentation/index.html) and [here](https://releases.asam.net/OpenSCENARIO/1.0.0/ASAM_OpenSCENARIO_BS-1-2_User-Guide_V1-0-0.html#_foreword).

### Versions, validation and conformance

`scenario_runner.py --openscenario` accepts **OpenSCENARIO 1.0** and **ASAM OpenSCENARIO XML 1.3** (1.3.0 and 1.3.1)
documents. The version is read from the `FileHeader` (`revMajor`, `revMinor`) and selects the schema the document is
validated against:

| Declared version | Schema | Result |
|---|---|---|
| 1.0 | bundled ASAM OpenSCENARIO 1.0 XSD (`srunner/openscenario/schemas/1.0/`) | validated, then loaded |
| 1.3 | bundled, unmodified ASAM OpenSCENARIO XML 1.3.1 XSD (`srunner/openscenario/schemas/1.3.1/`) | validated, then loaded |
| 1.1, 1.2 | none | rejected; migrate the document to 1.3 with the ASAM migration script |
| 0.9 | none | rejected; migrate with `srunner/openscenario/0.9.x/migration0_9_1to1_0.xslt` |
| anything else (1.4, 2.x, ...) | none | rejected |

1.3.1 changes no schema element of 1.3.0, so both are validated with the 1.3.1 XSD. The 1.3 schema is not backward
compatible: ASAM corrected the schema in 1.3.0, and valid 1.0 documents (for example every shipped example, because
of `OverrideControllerValueAction`) fail the 1.3.1 schema. Validating 1.1 or 1.2 documents against it would reject
valid documents, so they are refused with a diagnostic instead. Catalog files are validated against the schema of
their own `FileHeader`; catalogs that still declare a pre-1.0 header (as the shipped example catalogs do) are
validated against the 1.0 schema, as before. Schema validation is never skipped.

Validation uses the pinned `xmlschema` package, which compiles the 1.3.1 XSD; on the ASAM 1.3.1 example corpus it
accepts and rejects the same files as libxml2. Compiled schemas are cached per process.

A document goes through three independent levels before it runs. Each level reports structured diagnostics
(category, rule or capability code, message, XPath-like location and source line) and the scenario is not started if
any level reports an error:

1. **Schema** (`schema_error`): XSD validation of the declared version. Every violation is listed.
2. **Semantics** (`semantic_error`, `checker_rule`): the typed model and its validation (parameters, variables,
   expressions, routes, trajectories), plus the static checker rules of ASAM OpenSCENARIO XML 1.3.1 Annex C
   (`srunner/openscenario/validation/checker/`). Errors abort with a `ValidationError` listing all diagnostics;
   warnings are logged. A structural check applies to documents of every version:
    * An element whose content is a choice (for example `Action`, `PrivateAction`, `GlobalAction`, `Condition`,
      `ByValueCondition`, `EntityCondition`, `Position`, `Shape` or the entity of a `ScenarioObject`) must contain
      one of the alternatives (code `empty_choice`). The 1.0 XSD declares every alternative optional and accepts
      such empty elements; the choices that may be empty are taken from the 1.3.1 XSD. Catalog files are checked
      as well.
3. **Runtime capability** (`unsupported_feature`, `backend_capability_error`, `approximation_warning`): every element
   of the scenario and of the catalog entries it references is looked up in the capability matrix below. Elements the
   ScenarioRunner backend cannot execute in the context they are used in (Init or story), and known unsupported
   variants of supported elements, abort with an `UnsupportedFeatureError` listing all of them. This happens while
   the configuration is loaded, before the world is changed or any actor is spawned. Attributes that are accepted but
   not mapped to CARLA are logged as approximation warnings.

Passing all three levels means the document is schema valid, passes the implemented checker rules and only uses
features with a ScenarioRunner implementation. It does not mean full conformance to ASAM OpenSCENARIO XML 1.3.1: the
checker does not implement every Annex C rule, several supported elements are approximations, and no feature in
this list has been verified against a running CARLA server by these tests.

#### Annex C checker rules

Each rule is identified by its Annex C UID. Rules worded with "shall" are errors, rules worded with "should" or
"can" are warnings. A rule introduced after the version a document declares (the `x.y.z` in its UID) is reported as a
warning for that document, so OpenSCENARIO 1.0 files are not rejected for rules that did not exist for them. The
rules are applied to the scenario document; referenced catalog files are only used to resolve references.
`partial` rules check the scope given in the table. The table is generated from the rule registry
(`srunner.openscenario.validation.checker.rules_table_markdown()`), and a test keeps it in sync.

<!-- checker-rules:start -->
| Rule UID | Severity | Status | Scope or reason |
|---|---|---|---|
| `asam.net:xosc:1.0.0:data_type.condition_delay_not_negative` | error | full |  |
| `asam.net:xosc:1.1.0:data_type.distances_are_not_negative` | warning | partial | Distance attributes of distance actions and conditions, clearance, traffic area radii, Fog visualRange, Dimensions, clothoid lengths and transition dynamics with dynamicsDimension 'distance'. |
| `asam.net:xosc:1.0.0:data_type.phase_duration_positive` | error | full |  |
| `asam.net:xosc:1.0.0:data_type.time_format` | error | full | Interpreted as yyyy-MM-ddTHH:mm:ss with optional milliseconds (1-3 digits) and an optional 'Z' or +hh:mm/-hh:mm zone. Checked on every dateTime-typed attribute and dateTime declarations. |
| `asam.net:xosc:1.2.0:data_type.variable_correctly_typed` | error | full |  |
| `asam.net:xosc:1.2.0:data_type.variable_modification_or_comparison_possible` | error | full |  |
| `asam.net:xosc:1.2.0:distance.lateral_distance_disconnection` | warning | not implemented | Requires the OpenDRIVE road reference-line topology. |
| `asam.net:xosc:1.1.0:expressions.allowed_operators` | error | full |  |
| `asam.net:xosc:1.1.0:expressions.arguments_of_operators` | error | full |  |
| `asam.net:xosc:1.1.0:expressions.arithmetic_errors` | error | full |  |
| `asam.net:xosc:1.1.0:expressions.evaluation_of_expressions_possible` | error | partial | Expressions are evaluated with the declared parameter values (and command-line overrides); expressions in CatalogReference ParameterAssignments are not checked against the types of the catalog parameters. |
| `asam.net:xosc:1.1.0:expressions.nan_or_infinity` | error | full |  |
| `asam.net:xosc:1.1.0:expressions.overflow_underflow` | error | partial | Integer overflow beyond 64 bits, unsigned range violations and floating point overflow; floating point underflow is not detected. |
| `asam.net:xosc:1.1.0:expressions.type_casting` | error | full |  |
| `asam.net:xosc:1.1.0:expressions.type_mixture` | error | full |  |
| `asam.net:xosc:1.1.0:expressions.type_of_boolean` | error | full |  |
| `asam.net:xosc:1.2.0:general.animation_constraint_misc_object_external_reference` | error | full |  |
| `asam.net:xosc:1.2.0:general.animation_constraint_pedestrian` | error | full |  |
| `asam.net:xosc:1.2.0:general.animation_constraint_vehicle` | error | full |  |
| `asam.net:xosc:1.0.0:general.file_ending` | warning | full |  |
| `asam.net:xosc:1.1.0:general.homogeneous_references_to_entity_selection` | error | full |  |
| `asam.net:xosc:1.1.0:general.references_to_scenario_object` | error | full |  |
| `asam.net:xosc:1.0.0:naming.no_double_colon_prefix_in_names` | error | full |  |
| `asam.net:xosc:1.0.0:naming.parameter_declaration_name_prefix_reserved` | error | full |  |
| `asam.net:xosc:1.1.0:naming.parameter_declaration_parameter_name` | error | full |  |
| `asam.net:xosc:1.0.0:naming.unique_element_names_on_same_level` | error | full |  |
| `asam.net:xosc:1.1.0:parameters.parameter_declaration_parameter_reference_deadlocks` | warning | full |  |
| `asam.net:xosc:1.1.0:parameters.parameter_declaration_parameter_scope` | error | full | Every $reference in attribute values and expressions, ParameterAction and ParameterCondition parameterRef. The parameterRef of ScenarioRunner criteria conditions (Condition name 'criteria_<Name>') is a criterion argument name and is not checked. |
| `asam.net:xosc:1.0.0:parameters.parameter_declaration_parameter_type_inference` | error | full | Literal values and plain $references; expression values are checked by the expression rules. |
| `asam.net:xosc:1.2.0:positioning.distance_action_trajectory_reachability` | error | not implemented | The trajectory is the one the actor follows at runtime. |
| `asam.net:xosc:1.1.0:positioning.geodetic_datum_defined` | error | partial | Checked when the LogicFile is a resolvable OpenDRIVE (.xodr) file. |
| `asam.net:xosc:1.2.0:positioning.lateral_distance_requirements` | error | not implemented | Requires route computation over the OpenDRIVE road network. |
| `asam.net:xosc:1.2.0:positioning.longitudinal_distance_requirements` | error | not implemented | Requires route computation over the OpenDRIVE road network. |
| `asam.net:xosc:1.0.0:positioning.positions_shall_not_introduce_dependency_cycles` | error | partial | Initial positions: Init TeleportActions and AddEntityActions with relative positions. |
| `asam.net:xosc:1.0.0:positioning.road_lane_offset_in_bounds` | error | not implemented | Requires OpenDRIVE road and lane geometry. |
| `asam.net:xosc:1.0.0:reference_control.catalog_reference_resolvability` | error | full | Catalogs are read from every .xosc file in the CatalogLocations directories; checked when the document location is known. |
| `asam.net:xosc:1.0.0:reference_control.catalogs_referenced_by_directory` | error | full |  |
| `asam.net:xosc:1.0.0:reference_control.check_varied_parameters` | error | partial | Distribution parameterName/parameterRef against a resolvable ScenarioFile, and CatalogReference ParameterAssignments against resolvable catalog entries. |
| `asam.net:xosc:1.2.0:reference_control.controller_ambiguity` | error | partial | Counts the ObjectController elements of the ScenarioObject; checks ActivateControllerAction controllerRef/objectControllerRef. |
| `asam.net:xosc:1.0.0:reference_control.controller_assignment` | error | full |  |
| `asam.net:xosc:1.2.0:reference_control.lightstateaction_light_type` | error | full |  |
| `asam.net:xosc:1.2.0:reference_control.lightstateaction_lightstate_flashing` | warning | full |  |
| `asam.net:xosc:1.2.0:reference_control.lightstateaction_lightstate_on_off` | warning | full |  |
| `asam.net:xosc:1.0.0:reference_control.override_controller_action_only_allows_vehicles` | error | full |  |
| `asam.net:xosc:1.0.0:reference_control.resolvable_storyboard_element_ref` | error | full |  |
| `asam.net:xosc:1.2.0:reference_control.resolvable_variable_reference` | error | full |  |
| `asam.net:xosc:1.0.0:reference_control.road_lane_exists` | error | not implemented | Requires OpenDRIVE road and lane ids; CARLA towns referenced by name are only known to the server. |
| `asam.net:xosc:1.0.0:reference_control.road_network_availability` | warning | full | A filepath without a file extension is a CARLA map name resolved by the simulator and is not checked. |
| `asam.net:xosc:1.0.0:reference_control.road_network_reference` | warning | full |  |
| `asam.net:xosc:1.1.0:reference_control.single_or_multi_parameters` | error | full |  |
| `asam.net:xosc:1.1.0:reference_control.traffic_name_exists` | error | full |  |
| `asam.net:xosc:1.0.0:reference_control.traffic_signal_condition_references` | error | not implemented | Requires OpenDRIVE signal ids. |
| `asam.net:xosc:1.0.0:reference_control.traffic_signal_controller_action_references` | error | full |  |
| `asam.net:xosc:1.0.0:reference_control.traffic_signal_controller_condition_references` | error | partial | The phase is checked against the scenario's TrafficSignalControllers; the controller reference into the road network file is not checked. |
| `asam.net:xosc:1.0.0:reference_control.traffic_signal_controller_references` | error | partial | The reference attribute; the optional reference of name into the road network is not checked. |
| `asam.net:xosc:1.0.0:reference_control.traffic_signal_state_action_references` | error | not implemented | Requires OpenDRIVE signal ids. |
| `asam.net:xosc:1.0.0:reference_control.traffic_signal_state_references` | error | not implemented | Requires OpenDRIVE signal ids. |
| `asam.net:xosc:1.0.0:routing.ambiguous_route_waypoints` | warning | not implemented | Ambiguity depends on the OpenDRIVE road network. |
| `asam.net:xosc:1.0.0:routing.cardinality_of_control_points_in_nurbs` | error | full |  |
| `asam.net:xosc:1.1.0:routing.offset_should_be_less_than_trajectory_length` | error | partial | Polyline trajectories whose vertices are all WorldPositions (the standard notes the rule cannot be checked statically for relative positions). |
| `asam.net:xosc:1.0.0:routing.route_waypoints_locations` | warning | not implemented | Requires OpenDRIVE junction geometry. |
| `asam.net:xosc:1.0.0:routing.trajectory_timing_exists_if_requested` | error | full |  |
| `asam.net:xosc:1.2.0:scenario_logic.controller_activation` | error | partial | Controllers resolvable from the ScenarioObject, the action or a catalog. |
| `asam.net:xosc:1.0.0:scenario_logic.invalid_elements_if_no_road_network` | error | full |  |
| `asam.net:xosc:1.2.0:scenario_logic.targetspeed_maxspeed_general` | warning | partial | AbsoluteTargetSpeed targets. |
| `asam.net:xosc:1.2.0:scenario_logic.targetspeed_maxspeed_speedprofileaction` | warning | full |  |
| `asam.net:xosc:1.0.0:scenario_logic.trajectory_curvature_vs_steering_angle` | warning | not implemented | Requires curvature evaluation of Clothoid, ClothoidSpline and Nurbs shapes. |
| `asam.net:xosc:1.0.0:xml.valid_schema` | error | full | Bundled schemas: 1.0 and 1.3.1 (used for 1.3.0 and 1.3.1 documents); other versions are rejected. |
<!-- checker-rules:end -->

Two findings concern ScenarioRunner conventions rather than the checker:

* Conditions named `criteria_<Name>` in the Storyboard `StopTrigger` are ScenarioRunner evaluation criteria (see
  below). Their `ParameterCondition` `parameterRef` is the criterion argument, not a parameter, and is not checked
  against the parameter declarations.
* A `LogicFile` `filepath` without a file extension is a CARLA map name resolved by the simulator and is not checked
  for existence. An empty `SceneGraphFile` `filepath` (used by the shipped examples) is reported as a warning.

#### Capability matrix

The matrix lists every action, condition, position, trajectory shape, route position, entity, environment and
weather element, speed target, time reference and distribution that the 1.3.1 schema defines. The list of elements is
extracted from the bundled XSD (`srunner.openscenario.validation.schema_model`) and a test fails if an element is
missing from the matrix, so the table cannot fall out of date. Columns:

* **Parsed**: `typed` (typed model in `srunner/openscenario/model/`), `legacy` (read from the XML by
  `srunner/tools/openscenario_parser.py`) or `schema` (validated only).
* **Semantic**: `validated` (semantic validation of the typed model or its typed evaluation), `checked` (inspected
  by Annex C checker rules only) or `none`.
* **Runtime (Init)** / **Runtime (Story)**: `semantic` (semantic executor), `legacy` (legacy atomics),
  `unsupported` (rejected at build time) or `n/a`.
* **Verified by**: `executed` (a test with the mocked CARLA module ticks or initialises the behaviour), `built` (a
  test builds a scenario containing the element) or `none`. No element is verified against a live CARLA server.

Summary: 108 features; parsed: 31 typed, 57 legacy, 20 schema only; semantic: 24 validated, 42 checked, 42 none; runtime: 73 executable in at least one context, 35 unsupported; verified: 14 executed, 47 built, 47 none; live CARLA verified: 0. Annex C: 44 rules implemented, 12 partially implemented, 12 not implemented.

<!-- capability-table:start -->
| Category | Element | Parsed | Semantic | Runtime (Init) | Runtime (Story) | Verified by | Notes |
|---|---|---|---|---|---|---|---|
| action | AcquirePositionAction | typed | validated | semantic | semantic | built |  |
| action | ActivateControllerAction | legacy | checked | unsupported | legacy | built | PrivateAction form only, longitudinal attribute required (toggles the CARLA autopilot); the 1.3 form inside ControllerAction is unsupported |
| action | AnimationAction | schema | checked | unsupported | unsupported | none |  |
| action | AssignControllerAction | legacy | checked | legacy | legacy | built | Controller or CatalogReference with a 'module' property; ObjectController content is unsupported |
| action | AssignRouteAction | typed | validated | semantic | semantic | built | Closed routes are driven once |
| action | ConnectTrailerAction | schema | none | unsupported | unsupported | none |  |
| action | DisconnectTrailerAction | schema | none | unsupported | unsupported | none |  |
| action | EntityAction | legacy | none | legacy | legacy | built |  |
| action | EnvironmentAction | legacy | none | legacy | legacy | built | Mapped to CARLA weather and road friction; 1.3-only attributes are not mapped (approximation warning) |
| action | FollowTrajectoryAction | typed | validated | semantic | semantic | executed | Polyline shapes only; initialDistanceOffset is unsupported |
| action | InfrastructureAction | legacy | checked | unsupported | legacy | none |  |
| action | LaneChangeAction | legacy | none | unsupported | legacy | built | RelativeTargetLane only |
| action | LaneOffsetAction | legacy | none | legacy | legacy | built |  |
| action | LateralDistanceAction | legacy | checked | legacy | legacy | built |  |
| action | LightStateAction | schema | checked | unsupported | unsupported | none |  |
| action | LongitudinalDistanceAction | legacy | checked | unsupported | legacy | none | distance only; timeGap is unsupported |
| action | OverrideControllerValueAction | legacy | checked | legacy | legacy | built | Accepted inside a ControllerAction that assigns a controller, with every override inactive (no effect) |
| action | ParameterAction | typed | validated | semantic | semantic | executed |  |
| action | RandomRouteAction | schema | none | unsupported | unsupported | none |  |
| action | SetMonitorAction | schema | none | unsupported | unsupported | none |  |
| action | SpeedAction | legacy | checked | legacy | legacy | built | Init: AbsoluteTargetSpeed sets the initial speed; RelativeTargetSpeed in Init is unsupported |
| action | SpeedProfileAction | typed | validated | semantic | semantic | executed | Entries are commanded to the actor's controller; DynamicConstraints are not enforced |
| action | SynchronizeAction | legacy | checked | unsupported | legacy | built |  |
| action | TeleportAction | legacy | none | legacy | legacy | built |  |
| action | TrafficAction | schema | checked | unsupported | unsupported | none |  |
| action | UserDefinedAction | legacy | none | unsupported | legacy | none |  |
| action | VariableAction | typed | validated | semantic | semantic | executed |  |
| action | VisibilityAction | schema | none | unsupported | unsupported | none |  |
| entity_action | AddEntityAction | legacy | none | legacy | legacy | built |  |
| entity_action | DeleteEntityAction | legacy | none | legacy | legacy | built |  |
| traffic_signal_action | TrafficSignalControllerAction | legacy | checked | unsupported | legacy | none | The single TrafficSignalController/Phase of the RoadNetwork |
| traffic_signal_action | TrafficSignalStateAction | legacy | none | unsupported | legacy | none | CARLA traffic light states green, red, yellow and off |
| traffic_action | TrafficAreaAction | schema | none | unsupported | unsupported | none |  |
| traffic_action | TrafficSinkAction | schema | none | unsupported | unsupported | none |  |
| traffic_action | TrafficSourceAction | schema | checked | unsupported | unsupported | none |  |
| traffic_action | TrafficStopAction | schema | checked | unsupported | unsupported | none |  |
| traffic_action | TrafficSwarmAction | schema | checked | unsupported | unsupported | none |  |
| parameter_action | ModifyAction | typed | validated | semantic | semantic | executed |  |
| parameter_action | SetAction | typed | validated | semantic | semantic | executed |  |
| variable_action | ModifyAction | typed | validated | semantic | semantic | executed |  |
| variable_action | SetAction | typed | validated | semantic | semantic | executed |  |
| user_defined_action | CustomCommandAction | legacy | none | unsupported | legacy | built | Runs the command given as type through the shell |
| override_action | Brake | legacy | none | unsupported | unsupported | built | Only inactive overrides are accepted |
| override_action | Clutch | legacy | none | unsupported | unsupported | built | Only inactive overrides are accepted |
| override_action | Gear | legacy | none | unsupported | unsupported | built | Only inactive overrides are accepted |
| override_action | ParkingBrake | legacy | none | unsupported | unsupported | built | Only inactive overrides are accepted |
| override_action | SteeringWheel | legacy | none | unsupported | unsupported | built | Only inactive overrides are accepted |
| override_action | Throttle | legacy | none | unsupported | unsupported | built | Only inactive overrides are accepted |
| condition | ByEntityCondition | legacy | checked | n/a | legacy | built |  |
| condition | ParameterCondition | legacy | validated | n/a | semantic | executed | Conditions named criteria_<Name> are ScenarioRunner evaluation criteria |
| condition | SimulationTimeCondition | legacy | none | n/a | legacy | built |  |
| condition | StoryboardElementStateCondition | legacy | checked | n/a | legacy | built | startTransition, stopTransition, endTransition and completeState only |
| condition | TimeOfDayCondition | legacy | checked | n/a | legacy | none | dateTime without fractional seconds or time zone |
| condition | TrafficSignalCondition | legacy | none | n/a | legacy | none | CARLA traffic light states |
| condition | TrafficSignalControllerCondition | legacy | checked | n/a | legacy | none | Phases go, stop and attention of the single TrafficSignalController |
| condition | UserDefinedValueCondition | schema | none | n/a | unsupported | none |  |
| condition | VariableCondition | legacy | validated | n/a | semantic | executed |  |
| entity_condition | AccelerationCondition | legacy | none | n/a | legacy | none |  |
| entity_condition | AngleCondition | schema | none | n/a | unsupported | none |  |
| entity_condition | CollisionCondition | legacy | none | n/a | legacy | none |  |
| entity_condition | DistanceCondition | legacy | checked | n/a | legacy | built | alongRoute selects the distance; coordinateSystem, relativeDistanceType and routingAlgorithm are not mapped (approximation warning) |
| entity_condition | EndOfRoadCondition | legacy | checked | n/a | legacy | none |  |
| entity_condition | OffroadCondition | legacy | checked | n/a | legacy | none |  |
| entity_condition | ReachPositionCondition | legacy | checked | n/a | legacy | built |  |
| entity_condition | RelativeAngleCondition | typed | validated | n/a | semantic | executed | coordinateSystem entity and world only |
| entity_condition | RelativeClearanceCondition | typed | validated | n/a | semantic | executed |  |
| entity_condition | RelativeDistanceCondition | legacy | checked | n/a | legacy | built | coordinateSystem and routingAlgorithm are not mapped (approximation warning) |
| entity_condition | RelativeSpeedCondition | legacy | none | n/a | legacy | none |  |
| entity_condition | SpeedCondition | legacy | none | n/a | legacy | none |  |
| entity_condition | StandStillCondition | legacy | none | n/a | legacy | built |  |
| entity_condition | TimeHeadwayCondition | legacy | none | n/a | legacy | none | coordinateSystem, relativeDistanceType and routingAlgorithm are not mapped (approximation warning) |
| entity_condition | TimeToCollisionCondition | legacy | none | n/a | legacy | none | coordinateSystem, relativeDistanceType and routingAlgorithm are not mapped (approximation warning) |
| entity_condition | TraveledDistanceCondition | legacy | checked | n/a | legacy | built |  |
| position | GeoPosition | typed | checked | unsupported | unsupported | none |  |
| position | LanePosition | typed | checked | legacy | legacy | built |  |
| position | RelativeLanePosition | typed | checked | legacy | legacy | none |  |
| position | RelativeObjectPosition | typed | checked | legacy | legacy | built |  |
| position | RelativeRoadPosition | typed | checked | legacy | legacy | built |  |
| position | RelativeWorldPosition | typed | checked | legacy | legacy | built |  |
| position | RoadPosition | typed | checked | legacy | legacy | built |  |
| position | RoutePosition | typed | validated | unsupported | unsupported | none |  |
| position | TrajectoryPosition | typed | none | unsupported | unsupported | none |  |
| position | WorldPosition | typed | checked | legacy | legacy | built |  |
| trajectory_shape | Clothoid | typed | validated | unsupported | unsupported | none |  |
| trajectory_shape | ClothoidSpline | typed | validated | unsupported | unsupported | none |  |
| trajectory_shape | Nurbs | typed | validated | unsupported | unsupported | none |  |
| trajectory_shape | Polyline | typed | validated | semantic | semantic | executed |  |
| route_position | FromCurrentEntity | typed | validated | unsupported | unsupported | none |  |
| route_position | FromLaneCoordinates | typed | validated | unsupported | unsupported | none |  |
| route_position | FromRoadCoordinates | typed | validated | unsupported | unsupported | none |  |
| entity | ExternalObjectReference | schema | checked | unsupported | unsupported | none |  |
| entity | MiscObject | legacy | checked | legacy | legacy | built |  |
| entity | Pedestrian | legacy | checked | legacy | legacy | built |  |
| entity | Vehicle | legacy | checked | legacy | legacy | built |  |
| environment | RoadCondition | legacy | none | legacy | legacy | built | frictionScaleFactor only |
| environment | TimeOfDay | legacy | checked | legacy | legacy | built | dateTime without fractional seconds or time zone |
| environment | Weather | legacy | none | legacy | legacy | built | fractionalCloudCover, temperature and atmosphericPressure are not mapped (approximation warning) |
| weather | DomeImage | schema | none | unsupported | unsupported | none |  |
| weather | Fog | legacy | checked | legacy | legacy | built | visualRange only |
| weather | Precipitation | legacy | none | legacy | legacy | built | Rain from the 1.0 intensity attribute; precipitationIntensity is not mapped; snow is unsupported |
| weather | Sun | legacy | none | legacy | legacy | built | 1.0 intensity drives cloudiness; illuminance is not mapped |
| weather | Wind | schema | none | unsupported | unsupported | none |  |
| speed_target | AbsoluteTargetSpeed | legacy | checked | legacy | legacy | built |  |
| speed_target | RelativeTargetSpeed | legacy | none | unsupported | legacy | none |  |
| time_reference | None | typed | validated | semantic | semantic | built |  |
| time_reference | Timing | typed | validated | semantic | semantic | executed |  |
| distribution | Deterministic | schema | checked | unsupported | unsupported | none | ParameterValueDistribution documents are not executable |
| distribution | Stochastic | schema | checked | unsupported | unsupported | none | ParameterValueDistribution documents are not executable |
<!-- capability-table:end -->

#### ASAM example corpus

The ASAM OpenSCENARIO XML 1.3.1 deliverables ship example scenarios. They are not part of this repository; set
`OPENSCENARIO_ASAM_EXAMPLES` to an unzipped copy to run the schema part of the corpus test
(`srunner/tests/test_openscenario_schema.py`). Results for the 20 top-level examples, built with the mocked CARLA
module:

* Schema: all 20 are valid. (The 8 files under `Migration/Version_1.3/Examples` are partial migration snippets and
  are invalid for both `xmlschema` and libxml2.)
* Checker: `TrailerConnect.xosc` is rejected because its `Catalogs/Controllers` catalog directory is not part of
  the example archive (`reference_control.catalogs_referenced_by_directory`). The other 19 pass.
* Build: 5 build (`SequentialEvents_0-100-0kph_Explicit`, `SequentialEvents_0-100-0kph_Implicit`,
  `DoubleLaneChanger`, `FastOvertakeWithReInitialization`, `Overtaker`). 6 are rejected with unsupported-feature
  diagnostics: `CloseVehicleCrossing` (`TrajectoryPosition`, `initialDistanceOffset`), `EndOfTrafficJam`
  (`ActivateControllerAction` inside `ControllerAction`), `SimpleOvertake` (`AbsoluteTargetLane`),
  `SynchronizedArrivalToIntersection` (`RoutePosition`) and the two `ParameterValueDistribution` files, which are not
  scenarios. 4 (`CutIn`, `EndofTrafficJamNeighboringLaneOccupied`, `SlowPrecedingVehicle`, `TrafficJam`) need road
  network queries that the CARLA mocks do not implement and could not be checked without a simulator.

### Migrating OpenSCENARIO 0.9.x to 1.0
The easiest way to convert old OpenSCENARIO samples to the official standard 1.0 is to use _xsltproc_ and the migration scheme located in the openscenario folder.
Example:

```bash
xsltproc -o newScenario.xosc migration0_9_1to1_0.xslt oldScenario.xosc
```


### Level of support
In the following the OpenSCENARIO attributes are listed with their current support status.

#### General OpenSCENARIO setup

This covers all part that are defined outside the OpenSCENARIO Storyboard

| Attribute                          | Support                            | Notes                              |
| ---------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| `FileHeader`                       | &#9989;                              | Use "CARLA:" at the beginning of the description to use the CARLA coordinate system.                                |
| `CatalogLocations`<br>`ControllerCatalog`                                      | &#9989;                              | While the catalog is supported, the reference/usage may not work.                |
| `CatalogLocations`<br>`EnvironmentCatalog`                                     | &#9989;                              |                                    |
| `CatalogLocations`<br>`ManeuverCatalog`                                        | &#9989;                              |                                    |
| `CatalogLocations`<br>`MiscObjectCatalog`                                      | &#9989;                              |                                    |
| `CatalogLocations`<br>`PedestrianCatalog`                                      | &#9989;                              |                                    |
| `CatalogLocations`<br>`RouteCatalog`                                           | &#9989;                              | While the catalog is supported, the reference/usage may not work.                |
| `CatalogLocations`<br>`TrajectoryCatalog`                                      | &#9989;                              | While the catalog is supported, the reference/usage may not work.                |
| `CatalogLocations`<br>`VehicleCatalog`                                         | &#9989;                              |                                    |
| `ParameterDeclarations`            | &#9989;                              |                                    |
| `RoadNetwork`<br>`LogicFile`                                                   | &#9989;                              | The CARLA level can be used directly (e.g. LogicFile=Town01). Also any OpenDRIVE path can be provided.              |
| `RoadNetwork`<br>`SceneGraphFile`                                              | &#10060;                               | The provided information is not used.                                            |
| `RoadNetwork`<br>`TafficSignals`                                               | &#10060;                               | The provided information is not used.                                            |
| `Entities`<br>`EntitySelection`                                                | &#10060;                               | The provided information is not used.                                            |
| `Entities` `ScenarioObject`<br>`CatalogReference`                               | &#9989;                              | The provided information is not used.                                            |
| `Entities` `ScenarioObject`<br>`MiscObject`                                     | &#9989;                              | The name should match a CARLA vehicle model, otherwise a default vehicle based on the vehicleCategory is used. BoundingBox entries are ignored.                   |
| `Entities` `ScenarioObject`<br>`ObjectController`                               | &#10060;                               | The provided information is not used.                                            |
| `Entities` `ScenarioObject`<br>`Pedestrian`                                     | &#9989;                              | The name should match a CARLA vehicle model, otherwise a default vehicle based on the vehicleCategory is used. BoundingBox entries are ignored.                   |
| `Entities` `ScenarioObject`<br>`Vehicle`                                        | &#9989;                              | The name should match a CARLA vehicle model, otherwise a default vehicle based on the vehicleCategory is used. The color can be set via properties ('Property name="color" value="0,0,255"'). Axles, Performance, BoundingBox entries are ignored. |

<br>


#### OpenSCENARIO Storyboard

##### OpenSCENARIO Actions

The OpenSCENARIO Actions can be used for two different purposes. First, Actions can be used to
define the initial behavior of something, e.g. a traffic participant. Therefore, Actions can be
used within the OpenSCENARIO Init. In addition, Actions are also used within the OpenSCENARIO
story. In the following, the support status for both application areas is listed. If an action
contains of submodules, which are not listed, the support status applies to all submodules.

###### GlobalAction



| GlobalAction                          | Init  support                            | Story support                              | Notes                              |
| ---------------------------------------- | ---------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| `EntityAction`                | &#9989;                          | &#9989;                          |                               |
| `EnvironmentAction`           | &#9989;                         | &#10060;                          |                               |
| `ParameterAction`             | &#9989;                          | &#9989;                          | Values may be literals, `$name` references or `${...}` expressions (see [Parameters, variables and expressions](#parameters-variables-and-expressions)). The parameter must be declared. |
| `VariableAction`              | &#9989;                          | &#9989;                          | `SetAction` and `ModifyAction` (`AddValue`, `MultiplyByValue`). See [Parameters, variables and expressions](#parameters-variables-and-expressions). |
| `InfrastructureAction` `TrafficSignalAction`<br>`TrafficAction`                                               | &#10060;                          | &#10060;                          |                               |
| `InfrastructureAction` `TrafficSignalAction`<br>`TrafficSignalControllerAction`                               | &#10060;                          | &#9989;                          |                               |
| `InfrastructureAction` `TrafficSignalAction`<br>`TrafficSignalStateAction`                                    | &#10060;                          | &#9989;                         | As traffic signals in CARLA towns have no unique ID, they have to be set by providing their position (Example: TrafficSignalStateAction name="pos=x,y" state="green"). The id can also be used for none CARLA town (Example: TrafficSignalStateAction name="id=n" state="green") |

<br>



###### UserDefinedAction



| UserDefinedAction                          | Init  support                            | Story support                              | Notes                              |
| ---------------------------------------- | ---------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| `CustomCommandAction`                       | &#10060;                                        | &#9989;                                       | This action is currently used to trigger the execution of an additional script. Example: type="python /path/to/script args". |

<br>


###### PrivateAction


| PrivateAction                          | Init  support                            | Story support                              | Notes                              |
| ---------------------------------------- | ---------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| `ActivateControllerAction`                          | &#10060;             | &#9989;            | Can be used to activate/deactive the CARLA autopilot.                                             |
| `ControllerAction`                                  | &#9989;            | &#9989;            | AssignControllerAction is supported, but a Python module has to be provided for the controller implementation, and in OverrideControllerValueAction all values need to be `False`. |
| `LateralAction`<br> `LaneChangeAction`             | &#10060;             | &#9989;            | Currently all lane changes have a linear dynamicShape, the dynamicDimension is defined as the distance and are relative to the actor itself (RelativeTargetLane).                  |
| `LateralAction`<br>`LaneOffsetAction`             | &#10060;             | &#9989;             |  Currently all type of dynamicShapes are ignored and depend on the controller. This action might not work as intended if the offset is high enough to make the vehicle exit its lane  |
| `LateralAction`<br> `LateralDistanceAction`        | &#9989;             | &#9989;             |                  |
| `LongitudinalAction`<br> `LongitudinalDistanceAction`| &#10060;             | &#9989;              |`timeGap` attribute is not supported              |
| `LongitudinalAction`<br> `SpeedAction`             | &#9989;            | &#9989;            |                  |
| `SynchronizeAction`                                 | &#10060;             | &#10060;             |                  |
| `TeleportAction`                                    | &#9989;            | &#9989;            |                  |
| `VisibilityAction`                                  | &#10060;             | &#10060;             |                  |
| `RoutingAction`<br> `AcquirePositionAction`        | &#9989;             | &#9989;            | The target position is reached with the `fastest` route option. See [Routes, trajectories and speed profiles](#routes-trajectories-and-speed-profiles). |
| `RoutingAction`<br> `AssignRouteAction`            | &#9989;             | &#9989;            | Route Options (shortest/fastest/etc) are supported. Shortests means direct path between A and B, all other will use the shortest path along the road network between A and B. Inline routes and `CatalogReference`s are supported. |
| `RoutingAction`<br> `FollowTrajectoryAction`       | &#9989;             | &#9989;             | Only `Polyline` shapes. `TimeReference` (`None` or `Timing` with offset/scale, absolute or relative) is applied to the vertex times; the `trajectoryFollowingMode` is kept but executed by the actor's controller. `TrajectoryRef` (OpenSCENARIO 1.1+) is supported. |
| `LongitudinalAction`<br> `SpeedProfileAction`      | &#9989;             | &#9989;             | OpenSCENARIO 1.2+. Each entry becomes a target speed step; see [Routes, trajectories and speed profiles](#routes-trajectories-and-speed-profiles). |

<br>



##### OpenSCENARIO Conditions

Conditions in OpenSCENARIO can be defined either as ByEntityCondition or as ByValueCondition.
Both can be used for StartTrigger and StopTrigger conditions.
The following two tables list the support status for each.

###### ByEntityCondition


| EntityCondition                                | Support                                        | Notes                                          |
| ---------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- |
| `AccelerationCondition`                        | &#9989;                                          |                                                |
| `CollisionCondition`                           | &#9989;                                          |                                                |
| `DistanceCondition`                            | &#9989;                                          | \*freespace\* attribute is still not supported |
| `EndOfRoadCondition`                           | &#9989;                                          |                                                |
| `OffroadCondition`                             | &#9989;                                          |                                                |
| `ReachPositionCondition`                       | &#9989;                                          |                                                |
| `RelativeAngleCondition`                       | &#9989;                                          | OpenSCENARIO 1.2+. `coordinateSystem` `entity` (default) and `world` only |
| `RelativeClearanceCondition`                   | &#9989;                                          | OpenSCENARIO 1.2+. See [Routes, trajectories and speed profiles](#routes-trajectories-and-speed-profiles) |
| `RelativeDistanceCondition`                    | &#9989;                                          |                                                |
| `RelativeSpeedCondition`                       | &#9989;                                          |                                                |
| `SpeedCondition`                               | &#9989;                                          |                                                |
| `StandStillCondition`                          | &#9989;                                          |                                                |
| `TimeHeadwayCondition`                         | &#9989;                                          |                                                |
| `TimeToCollisionCondition`                     | &#9989;                                          |                                                |
| `TraveledDistanceCondition`                    | &#9989;                                          |                                                |

<br>

###### ByValueCondition


| ValueCondition            | Support                   | Notes                     |
| -------------------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------- |
| `ParameterCondition`         | &#9989;                     | The level of support depends on the parameter. It is recommended to use other conditions if possible. Please also consider the note below. The `value` may be a `$name` reference or a `${...}` expression.                                                  |
| `VariableCondition`          | &#9989;                     | Compares a declared variable with `value` (literal, `$name` parameter reference or `${...}` expression). For `string` variables only `equalTo` and `notEqualTo` are allowed. |
| `SimulationTimeCondition`                                    | &#9989;                     |                           |
| `StoryboardElementStateCondition`                            | &#9989;                     | startTransition, stopTransition, endTransition and completeState are currently supported.                  |
| `TimeOfDayCondition`         | &#9989;                     |                           |
| `TrafficSignalCondition`                                     | &#9989;                     | As traffic signals in CARLA towns have no unique ID, they have to be set by providing their position (Example: TrafficSignalCondition name="pos=x,y" state="green"). The id can also be used for none CARLA town (Example: TrafficSignalCondition name="id=n" state="green") |
| `TrafficSignalControllerCondition`                           | &#9989;                      |                           |
| `UserDefinedValueCondition`                                  | &#10060;                      |                           |

<br>

!!! Note
     In the OpenSCENARIO 1.0 standard, a definition of test / evaluation criteria is not
     defined. For this purpose, you can re-use StopTrigger conditions with CARLA. The following
     StopTrigger conditions for evaluation criteria are supported through ParameterConditions by
     providing the criteria name for the condition:

     * criteria_RunningStopTest
     * criteria_RunningRedLightTest
     * criteria_WrongLaneTest
     * criteria_OnSideWalkTest
     * criteria_KeepLaneTest
     * criteria_CollisionTest
     * criteria_DrivenDistanceTest

The other conditions of the Storyboard `StopTrigger` end the scenario when their condition group fires, as the
standard defines. A condition group must not mix `criteria_` conditions with other conditions (unsupported-feature
diagnostic). Before this release such conditions were ignored.

An `Act` without a `StartTrigger` (optional since OpenSCENARIO 1.1) starts immediately.


#### Parameters, variables and expressions

ParameterDeclarations, VariableDeclarations, `ParameterAction`, `VariableAction`, `ParameterCondition` and
`VariableCondition` are evaluated by a typed semantic layer (`srunner/openscenario/`) when the scenario is built
and while it runs:

* Values can be literals, `$name` parameter references or `${...}` expressions as defined by OpenSCENARIO 1.1+.
  Expressions support numeric and Boolean literals (`true`, `false`, `0`, `1`), parameter references, the operators
  `+`, `-`, `*`, `/`, `%` (remainder), `not`, `and`, `or`, parentheses and the functions `round`, `floor`, `ceil`,
  `sqrt`, `pow`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `sign`, `abs`, `max`, `min`. Anything else (for example
  `**`, comparisons, strings or other function names) is rejected. Expressions are parsed safely and never executed
  as Python code.
* Results are converted to the declared type of the target parameter or variable. Integers convert implicitly to
  `double`; a `double` result is only accepted for an integer type when converted explicitly with `round`, `floor`
  or `ceil`. `round` rounds halves away from zero. Division by zero, square roots of negative numbers, NaN, infinity
  and integer overflow are errors.
* ParameterDeclaration and VariableDeclaration values may themselves be references or expressions; they are
  evaluated in declaration order after `--openscenarioparams` overrides have been applied.
* Variables are declared in `VariableDeclarations` and can be changed with `VariableAction` in the `Init` and in
  stories. As required by the standard, variables can only be read through `VariableCondition`; referencing a
  variable from an expression or attribute is an error.
* Parameter changes made by `ParameterAction` are written to the global parameter table read by `$name`
  references, so behaviors that read the parameter after the change see the new value.
* `$name` references and `${...}` expressions are also resolved in the other attributes ScenarioRunner reads, for
  example weather, positions, condition values and `delay`, Boolean flags such as `freespace` or `continuous`,
  entity models (`Vehicle name="$Model"`), properties and catalog paths. Attributes read while the configuration is
  loaded are evaluated with the declaration values and the `--openscenarioparams` overrides. Attributes that name
  an element (`ScenarioObject`, story element and condition names, `storyboardElementRef`) are identifiers and are
  used as written.
* When the configuration is loaded, and again when the scenario is built (before its non-ego actors are spawned),
  the document is checked for duplicate parameter or variable declarations, references to undeclared parameters or
  variables in any attribute, invalid expression syntax and declaration values that do not match their type. While
  the configuration is loaded (before the world is changed or any actor is spawned) the Annex C checker rules run as
  well, including parameter scoping. Any error aborts the scenario with a `ValidationError` listing all problems.
* A document that is not an OpenSCENARIO document (wrong root element, missing `FileHeader` or `revMajor`/`revMinor`,
  XML syntax error) raises a `ValidationError` as well. So does an attribute whose value cannot be evaluated while
  the scenario is built (for example a division by zero or a value of the wrong type); each diagnostic names the
  failing attribute value.
* An error that can only be detected while the scenario runs (for example a `VariableAction` value that does not
  match the variable type) makes the corresponding behavior fail and is logged; it does not crash the runner.

Not supported yet:

* OpenSCENARIO 1.0 documents are validated against the 1.0 schema, which restricts numeric attributes to literals
  and `$name` references; `${...}` in numeric attributes needs a 1.3 document. Variables are likewise a 1.3 feature.
* Runtime parameter scoping: nested `ParameterDeclarations` are checked for scope by the checker, but at runtime all
  declarations share one global parameter table. `ConstraintGroup`s, parameter value distributions,
  `MonitorDeclarations` and reading or writing variables from outside the scenario are not supported.

#### Routes, trajectories and speed profiles

`AssignRouteAction`, `AcquirePositionAction`, `FollowTrajectoryAction` and `SpeedProfileAction` (in the `Init` and in
stories), and the `RelativeAngleCondition` and `RelativeClearanceCondition` entity conditions, are parsed into typed
objects by the semantic layer and turned into behaviors from those objects:

* Routes and trajectories keep their positions as typed positions until the behavior starts, so relative positions
  are resolved against the actors' poses at that moment.
* `FollowTrajectoryAction` reads `TimeReference` and `TrajectoryFollowingMode` from their child elements. With
  `TimeReference/None` the vertex times are ignored. With `Timing` each vertex time `t` becomes `t * scale + offset`,
  measured from the start of the action (`relative`) or of the simulation (`absolute`); every vertex then needs a
  time, and with `absolute` vertices whose time has already passed are skipped. Controllers that need times, such as
  `vehicle_velocity_control`, drive towards the vertices at the actor's target speed when there are none. The following mode is passed on, but how closely the actor tracks the trajectory depends on its controller;
  `position` is reported as an approximation warning.
* `SpeedProfileAction` commands each `SpeedProfileEntry` speed as a target speed of the actor's controller. An entry
  with a `time` holds its target for that time before the next entry starts; an entry without a `time`, and the last
  entry, last until the speed is reached. With `entityRef` the speeds are relative to the speed of that entity.
  `DynamicConstraints` and the difference between the `follow` and `position` modes are not enforced (approximation
  warning).
* `RelativeAngleCondition` compares the heading, pitch or roll of the triggering entity relative to the referenced
  entity with `angle` ± `angleTolerance`. Heading and pitch follow the OpenSCENARIO convention unless the scenario
  uses CARLA coordinates; roll keeps the CARLA sign. The `lane`, `road` and `trajectory` coordinate systems are not supported.
* `RelativeClearanceCondition` is true while no entity (or none of the listed `EntityRef`s) is between
  `distanceBackward` behind and `distanceForward` ahead of the triggering entity, along its heading, in the
  `RelativeLaneRange`s (positive lanes are to its left; no range means all lanes). Missing distances count as 0 m.
  Lanes of the opposite driving direction are only considered with `oppositeLanes="true"`, and `freeSpace="true"`
  measures between bounding boxes. Relative lanes are exact for entities on the same road section and estimated
  from the lateral offset elsewhere.
* Attribute values may be `$name` references or `${...}` expressions; they are evaluated when the scenario is built,
  so a later `ParameterAction` does not change them.
* Several of these actions in the `Init` of one actor run in parallel.

The scenario is aborted with a structured diagnostic instead of running something different from what was written:

* Structural errors (for example a `Polyline` with fewer than two vertices, a `Route` with fewer than two waypoints, a
  missing `TimeReference`, an unknown `followingMode`, a `ParameterAction` or `VariableAction` whose `ModifyAction`
  has no valid `Rule`) raise a `ValidationError`.
* Features the CARLA backend cannot execute are reported by the capability audit while the configuration is
  loaded, as an `UnsupportedFeatureError` with `unsupported_feature` diagnostics: `Clothoid`, `ClothoidSpline` and
  `Nurbs` trajectories, a non-zero `initialDistanceOffset`, `RoutePosition`, `TrajectoryPosition` and `GeoPosition`,
  and the unsupported `RelativeAngleCondition` coordinate systems. The backend keeps its own
  `backend_capability_error` checks (for example for closed trajectories) for scenarios built through the Python API.
* Entity conditions that are not supported at all raise an `UnsupportedFeatureError` instead of being silently
  dropped.

Other actions keep their previous implementation. All of these features, including `SpeedProfileAction`,
`TrajectoryRef`, `RelativeAngleCondition` and `RelativeClearanceCondition`, are available from
`scenario_runner.py --openscenario` with OpenSCENARIO 1.3 documents.

##### OpenSCENARIO Positions

There are several ways of defining positions in OpenSCENARIO. In the following we list the
current support status for each definition format.

| Position                          | Support                            | Notes                              |
| ---------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| `LanePosition`           | &#9989;                    |                          |
| `RelativeLanePosition`   | &#9989;                    |                          |
| `RelativeObjectPosition` | &#9989;                    |                          |
| `RelativeRoadPosition`   | &#9989;                     |                          |
| `RelativeWorldPosition`  | &#9989;                    |                          |
| `RoadPosition`           | &#9989;                     |                          |
| `RoutePosition`          | &#10060;                     | Parsed and validated; using it aborts the scenario with an unsupported-feature diagnostic |
| `GeoPosition`            | &#10060;                     | Using it aborts the scenario with an unsupported-feature diagnostic |
| `TrajectoryPosition`     | &#10060;                     | Using it aborts the scenario with an unsupported-feature diagnostic |
| `WorldPosition`          | &#9989;                    |                          |

<br>
