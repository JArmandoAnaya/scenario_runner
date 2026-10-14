"""Build-time audit of schema-valid features the ScenarioRunner backend cannot execute.

The audit walks the scenario (and the catalog entries it references) before any
behaviour is built and reports, for every element:

* ``unsupported_feature`` errors for elements whose capability row says
  ``unsupported`` in the context they are used in (Init or story), and for
  known unsupported variants of supported elements;
* ``backend_capability_error`` errors for catalog references the runtime
  cannot resolve;
* ``approximation_warning`` warnings for attributes that are accepted but not
  mapped to CARLA.
"""

from __future__ import absolute_import

import re

from srunner.openscenario.execution.capabilities import CAPABILITY_MATRIX
from srunner.openscenario.execution.registry import UnsupportedFeatureError
from srunner.openscenario.validation.checker.context import CheckerContext, Unresolved
from srunner.openscenario.validation.diagnostics import Diagnostic

_INDEX = {}
for _row in CAPABILITY_MATRIX.values():
    _INDEX.setdefault(_row.element, []).append(_row)
_CONTAINERS = {"parameter_action": "ParameterAction", "variable_action": "VariableAction"}
_STATES = ("startTransition", "stopTransition", "endTransition", "completeState")
_RUNTIME_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
_NOT_MAPPED = {
    "Weather": ("fractionalCloudCover", "temperature", "atmosphericPressure"),
    "Sun": ("illuminance",),
    "Precipitation": ("precipitationIntensity",),
    "DistanceCondition": ("coordinateSystem", "relativeDistanceType", "routingAlgorithm"),
    "RelativeDistanceCondition": ("coordinateSystem", "routingAlgorithm"),
    "TimeHeadwayCondition": ("coordinateSystem", "relativeDistanceType", "routingAlgorithm"),
    "TimeToCollisionCondition": ("coordinateSystem", "relativeDistanceType", "routingAlgorithm"),
}


def _row_for(element, parent):
    candidates = _INDEX.get(element.tag, ())
    if len(candidates) == 1:
        return candidates[0]
    for row in candidates:
        if parent is not None and _CONTAINERS.get(row.category) == parent.tag:
            return row
    return None


def _activate_controller(audit, element, parent, context):
    if parent is not None and parent.tag == "ControllerAction":
        return "ActivateControllerAction inside ControllerAction is not supported by the ScenarioRunner backend"
    if element.attrib.get("longitudinal") is None:
        return "ActivateControllerAction requires the longitudinal attribute in the ScenarioRunner backend"
    return None


def _override_controller(audit, element, parent, context):
    if parent is not None and parent.find("AssignControllerAction") is None:
        return "OverrideControllerValueAction is only accepted together with an AssignControllerAction"
    return None


def _assign_controller(audit, element, parent, context):
    if element.find("Controller") is None and element.find("CatalogReference") is None:
        return "AssignControllerAction requires a Controller or a CatalogReference in the ScenarioRunner backend"
    return None


def _lane_change(audit, element, parent, context):
    if element.find("LaneChangeTarget/AbsoluteTargetLane") is not None:
        return "LaneChangeAction AbsoluteTargetLane is not supported by the ScenarioRunner backend"
    return None


def _longitudinal_distance(audit, element, parent, context):
    if "timeGap" in element.attrib:
        return "LongitudinalDistanceAction timeGap is not supported by the ScenarioRunner backend"
    return None


def _storyboard_state(audit, element, parent, context):
    state = audit.text(element, "state")
    if state not in _STATES:
        return "StoryboardElementStateCondition state {!r} is not supported by the ScenarioRunner backend".format(state)
    return None


def _precipitation(audit, element, parent, context):
    if audit.text(element, "precipitationType") == "snow":
        return "Snow precipitation is not supported by CARLA"
    return None


def _init_speed(audit, element, parent, context):
    if context == "init" and element.find("SpeedActionTarget/RelativeTargetSpeed") is not None:
        return "RelativeTargetSpeed is not supported in the Init section"
    return None


def _date_time(audit, element, parent, context):
    value = audit.text(element, "dateTime")
    if value is not None and not _RUNTIME_DATETIME.match(value):
        return "dateTime {!r} with fractional seconds or a time zone is not supported by the runtime".format(value)
    return None


def _trajectory_offset(audit, element, parent, context):
    if element.attrib.get("initialDistanceOffset") not in (None, "0", "0.0"):
        return "FollowTrajectoryAction initialDistanceOffset is not supported by the ScenarioRunner backend"
    return None


def _angle_coordinates(audit, element, parent, context):
    system = audit.text(element, "coordinateSystem")
    if system not in (None, "entity", "world"):
        return "RelativeAngleCondition coordinateSystem {!r} is not supported by the ScenarioRunner backend".format(
            system)
    return None


_VARIANTS = {
    "ActivateControllerAction": (_activate_controller,),
    "OverrideControllerValueAction": (_override_controller,),
    "AssignControllerAction": (_assign_controller,),
    "LaneChangeAction": (_lane_change,),
    "LongitudinalDistanceAction": (_longitudinal_distance,),
    "StoryboardElementStateCondition": (_storyboard_state,),
    "Precipitation": (_precipitation,),
    "SpeedAction": (_init_speed,),
    "TimeOfDay": (_date_time,),
    "TimeOfDayCondition": (_date_time,),
    "FollowTrajectoryAction": (_trajectory_offset,),
    "RelativeAngleCondition": (_angle_coordinates,),
}


class _Audit(object):

    def __init__(self, document, catalogs, parameter_overrides):
        self.document = document
        self.catalogs = catalogs
        self.values = CheckerContext(document, parameter_overrides=parameter_overrides, catalogs={})
        self.diagnostics = []

    def report(self, category, element, message, severity="error", code=None):
        self.diagnostics.append(Diagnostic(category, message, source=element, severity=severity,
                                           code=code).locate(self.document))

    def boolean(self, element, attribute):
        value = element.attrib.get(attribute)
        if value is None:
            return False
        try:
            return bool(self.values.evaluate(value, self._anchor(element), "boolean"))
        except (Unresolved, ValueError):
            return str(value).strip().lower() in ("true", "1")

    def text(self, element, attribute):
        value = element.attrib.get(attribute)
        try:
            return None if value is None else str(self.values.evaluate(value, self._anchor(element), "string"))
        except (Unresolved, ValueError):
            return value

    def _anchor(self, element):
        # Catalog entry elements are not part of the document; evaluate them in the global scope.
        return element if self.document.locations.parent(element) is not None or element is self.document.root \
            else self.document.root

    def walk(self, element, parent, context, where=""):
        row = _row_for(element, parent)
        if row is not None:
            runtime = row.runtime_init if context == "init" else row.runtime_story
            message = None
            if runtime == "unsupported" and self._unsupported_applies(row, element):
                message = "{} is not supported by the ScenarioRunner backend{}".format(
                    element.tag, " in the Init section" if context == "init" and row.runtime_story != "unsupported"
                    else "")
            elif runtime != "unsupported":
                message = self.variant_gap(element, parent, context)
            if message:
                self.report("unsupported_feature", element, message + where,
                            code="capability:{}/{}".format(row.category, row.element))
            self.approximations(element, where)
        if element.tag == "CatalogReference":
            self.catalog_reference(element, context)
        for child in element:
            child_context = context
            if child.tag == "Init" and element.tag == "Storyboard":
                child_context = "init"
            elif child.tag in ("Story", "StopTrigger") and element.tag == "Storyboard":
                child_context = "story"
            self.walk(child, element, child_context, where)

    def catalog_reference(self, reference, context):
        catalog, entry_name = self.text(reference, "catalogName"), self.text(reference, "entryName")
        entry = (self.catalogs or {}).get(catalog, {}).get(entry_name)
        if entry is None:
            self.report("backend_capability_error", reference,
                        "Catalog entry {}/{} is not available to the runtime, which loads <Type>Catalog.xosc from "
                        "each CatalogLocations directory".format(catalog, entry_name))
            return
        if entry.tag == "Maneuver":
            context = "story"
        self.walk(entry, reference, context, " (catalog entry {}/{})".format(catalog, entry_name))

    def _unsupported_applies(self, row, element):
        if row.category == "override_action":
            return self.boolean(element, "active")
        return True

    def variant_gap(self, element, parent, context):
        """Message for a known unsupported variant of an otherwise supported element, else None."""
        for check in _VARIANTS.get(element.tag, ()):
            message = check(self, element, parent, context)
            if message:
                return message
        return None

    def approximations(self, element, where):
        for attribute in _NOT_MAPPED.get(element.tag, ()):
            if attribute in element.attrib:
                self.report("approximation_warning", element, "{}@{} is not mapped to CARLA and is ignored{}".format(
                    element.tag, attribute, where), severity="warning")

    def storyboard(self):
        storyboard = self.document.root.find("Storyboard")
        if storyboard is None:
            return
        for group in storyboard.findall("StopTrigger/ConditionGroup"):
            names = [(condition.attrib.get("name") or "").startswith("criteria_")
                     for condition in group.findall("Condition")]
            if any(names) and not all(names):
                self.report("unsupported_feature", group,
                            "A Storyboard StopTrigger ConditionGroup cannot mix criteria_ conditions with other "
                            "conditions")
        init = storyboard.find("Init/Actions")
        environments = init.findall("GlobalAction/EnvironmentAction") if init is not None else []
        for extra in environments[1:]:
            self.report("approximation_warning", extra, "Only the first EnvironmentAction of the Init section is "
                        "applied", severity="warning")


def audit_document(document, catalogs=None, parameter_overrides=None):
    """Diagnostics for every schema-valid feature of ``document`` the backend cannot execute.

    ``catalogs`` is the runtime catalog mapping (catalog name -> {entry name: element}).
    """
    audit = _Audit(document, catalogs, parameter_overrides)
    if document.root.find("Storyboard") is None:
        kind = next((child.tag for child in document.root if child.tag != "FileHeader"), "empty")
        audit.report("unsupported_feature", document.root,
                     "Only scenario definitions can be executed; this document contains a {}".format(kind),
                     code="capability:document")
        return audit.diagnostics
    audit.walk(document.root, None, "definition")
    audit.storyboard()
    return audit.diagnostics


def raise_for_unsupported(diagnostics, subject=None):
    errors = [diagnostic for diagnostic in diagnostics if diagnostic.is_error]
    if errors:
        raise UnsupportedFeatureError(subject, diagnostics=errors)
