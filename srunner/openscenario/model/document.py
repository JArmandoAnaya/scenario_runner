"""Backend-independent OpenSCENARIO document model."""

from __future__ import absolute_import

import copy

from srunner.openscenario.model.actions import (
    AcquirePositionAction, AssignRouteAction, FollowTrajectoryAction, ParameterAction,
    SpeedProfileAction)
from srunner.openscenario.model.parameters import ParameterDeclaration, VariableDeclaration
from srunner.openscenario.model.references import (
    CatalogReference, Position, RelativeAngleCondition, RelativeClearanceCondition, Route, Trajectory)


class OpenScenarioDocument(object):
    """A parsed document retaining XML and typed semantic declarations."""

    def __init__(self, root, version, source=None):
        self.root = root
        self.version = version
        self.source = source
        self.parameter_declarations = self._read_parameters(root)
        self.variable_declarations = self._read_variables(root)
        self.catalog_references = self._read_catalog_references(root)
        self.parameter_store = self._make_store(self.parameter_declarations)
        self.variable_store = self._make_variable_store(self.variable_declarations)

    @staticmethod
    def _read_parameters(root):
        declarations = []
        container = root.find("ParameterDeclarations")
        if container is None:
            return declarations
        for element in container.findall("ParameterDeclaration"):
            declarations.append(ParameterDeclaration(
                name=element.attrib.get("name"),
                parameter_type=element.attrib.get("parameterType"),
                value=element.attrib.get("value"),
                source=element,
            ))
        return declarations

    def parameter_values(self, overrides=None):
        values = dict((item.name, item.value) for item in self.parameter_declarations)
        if overrides:
            values.update(overrides)
        return values

    @staticmethod
    def _read_variables(root):
        declarations = []
        containers = [root.find("VariableDeclarations")]
        storyboard = root.find("Storyboard")
        if storyboard is not None:
            containers.append(storyboard.find("VariableDeclarations"))
        for container in containers:
            if container is None:
                continue
            for element in container.findall("VariableDeclaration"):
                declarations.append(VariableDeclaration(
                    name=element.attrib.get("name"),
                    variable_type=element.attrib.get("variableType", element.attrib.get("type")),
                    value=element.attrib.get("value"), source=element))
        return declarations

    @staticmethod
    def _make_store(declarations):
        from srunner.openscenario.model.parameters import ParameterStore
        return ParameterStore(declarations)

    @staticmethod
    def _make_variable_store(declarations):
        from srunner.openscenario.model.parameters import VariableStore
        return VariableStore(declarations)

    @staticmethod
    def _read_catalog_references(root):
        references = []
        for element in root.iter("CatalogReference"):
            assignments = {}
            container = element.find("ParameterAssignments")
            if container is not None:
                for assignment in container.findall("ParameterAssignment"):
                    assignments[assignment.attrib.get("parameterRef")] = assignment.attrib.get("value")
            references.append(CatalogReference(
                catalog_name=element.attrib.get("catalogName"),
                entry_name=element.attrib.get("entryName"),
                parameter_assignments=assignments,
                source=element,
            ))
        return references

    def parameter_actions(self):
        """Yield semantic ParameterActions from the Init storyboard.

        This is intentionally narrow: other actions continue through the legacy
        adapter until they are migrated one feature at a time.
        """
        storyboard = self.root.find("Storyboard")
        if storyboard is None:
            return []
        init = storyboard.find("Init")
        if init is None:
            return []
        actions = []
        actions_container = init.find("Actions")
        if actions_container is None:
            return []
        for index, global_action in enumerate(actions_container.iter("GlobalAction")):
            element = global_action.find("ParameterAction")
            if element is None:
                continue
            set_action = element.find("SetAction")
            modify_action = element.find("ModifyAction")
            if set_action is not None:
                action = ParameterAction(
                    parameter_ref=element.attrib.get("parameterRef"),
                    set_value=set_action.attrib.get("value"),
                    source=element,
                )
                action.sequence_index = index
                actions.append(action)
            elif modify_action is not None:
                rule = modify_action.find("Rule")
                if rule is None:
                    continue
                add = rule.find("AddValue")
                multiply = rule.find("MultiplyByValue")
                if add is not None:
                    action = ParameterAction(
                        parameter_ref=element.attrib.get("parameterRef"),
                        modify_rule="+",
                        modify_value=add.attrib.get("value"),
                        source=element,
                    )
                    action.sequence_index = index
                    actions.append(action)
                elif multiply is not None:
                    action = ParameterAction(
                        parameter_ref=element.attrib.get("parameterRef"),
                        modify_rule="*",
                        modify_value=multiply.attrib.get("value"),
                        source=element,
                    )
                    action.sequence_index = index
                    actions.append(action)
        return actions

    def variable_actions(self):
        """Yield variable actions from Init without resolving them through CARLA."""
        from srunner.openscenario.model.actions import VariableModifyAction, VariableSetAction
        storyboard = self.root.find("Storyboard")
        if storyboard is None or storyboard.find("Init") is None:
            return []
        actions = []
        for index, global_action in enumerate(storyboard.find("Init").iter("GlobalAction")):
            element = global_action.find("VariableAction")
            if element is None:
                continue
            set_action = element.find("VariableSetAction")
            modify_action = element.find("VariableModifyAction")
            if set_action is not None:
                action = VariableSetAction(set_action.attrib.get("variableRef"), set_action.attrib.get("value"), element)
            elif modify_action is not None:
                action = VariableModifyAction(modify_action.attrib.get("variableRef"),
                                              modify_action.attrib.get("modification"),
                                              modify_action.attrib.get("value"), element)
            else:
                continue
            action.sequence_index = index
            actions.append(action)
        return actions

    def positions(self):
        return [Position.from_xml(element) for element in self.root.iter("Position")]

    def routes(self):
        return [Route.from_xml(element) for element in self.root.iter("Route")]

    def trajectories(self):
        return [Trajectory.from_xml(element) for element in self.root.iter("Trajectory")]

    @staticmethod
    def _catalog_reference(element):
        if element is None:
            return None
        return CatalogReference(element.attrib.get("catalogName"), element.attrib.get("entryName"),
                                source=element)

    @staticmethod
    def _time_reference(element):
        if element is None:
            return None
        timing = element.find("Timing")
        if timing is not None:
            return {"kind": "Timing", "attributes": dict(timing.attrib), "source": element}
        return {"kind": "None", "attributes": {}, "source": element}

    @staticmethod
    def _following_mode(element):
        if element is None:
            return None
        return element.attrib.get("followingMode")

    def routing_actions(self):
        """Yield typed routing actions; legacy execution remains available."""
        actions = []
        for element in self.root.iter("AssignRouteAction"):
            route = element.find("Route")
            actions.append(AssignRouteAction(
                route=Route.from_xml(route) if route is not None else None,
                catalog_reference=self._catalog_reference(element.find("CatalogReference")),
                source=element))
        for element in self.root.iter("AcquirePositionAction"):
            position = element.find("Position")
            if position is not None:
                actions.append(AcquirePositionAction(Position.from_xml(position), element))
        for element in self.root.iter("FollowTrajectoryAction"):
            trajectory = element.find("Trajectory")
            actions.append(FollowTrajectoryAction(
                trajectory=Trajectory.from_xml(trajectory,
                                               self._time_reference(element.find("TimeReference")),
                                               self._following_mode(element.find("TrajectoryFollowingMode")))
                if trajectory is not None else None,
                catalog_reference=self._catalog_reference(element.find("CatalogReference")),
                time_reference=self._time_reference(element.find("TimeReference")),
                following_mode=self._following_mode(element.find("TrajectoryFollowingMode")),
                source=element))
        return actions

    @staticmethod
    def action_from_xml(element):
        """Create one semantic action from an action XML element.

        This narrow entry point is used by the incremental runtime adapter so
        migrated actions do not need to be rediscovered through the legacy
        parser's global XML traversal.
        """
        if element is None:
            return None
        if element.tag == "AssignRouteAction":
            route = element.find("Route")
            reference = element.find("CatalogReference")
            return AssignRouteAction(
                route=Route.from_xml(route) if route is not None else None,
                catalog_reference=CatalogReference(
                    reference.attrib.get("catalogName"), reference.attrib.get("entryName"),
                    source=reference) if reference is not None else None,
                source=element)
        if element.tag == "AcquirePositionAction":
            position = element.find("Position")
            return AcquirePositionAction(Position.from_xml(position), source=element)
        if element.tag == "FollowTrajectoryAction":
            trajectory = element.find("Trajectory")
            reference = element.find("CatalogReference")
            return FollowTrajectoryAction(
                trajectory=Trajectory.from_xml(
                    trajectory,
                    time_reference=element.attrib.get("timeReference"),
                    following_mode=element.attrib.get("followingMode")) if trajectory is not None else None,
                catalog_reference=CatalogReference(
                    reference.attrib.get("catalogName"), reference.attrib.get("entryName"),
                    source=reference) if reference is not None else None,
                time_reference=element.attrib.get("timeReference"),
                following_mode=element.attrib.get("followingMode"),
                source=element)
        if element.tag == "SpeedProfileAction":
            segments = [dict(child.attrib) for child in list(element)
                        if child.tag in ("SpeedProfileEntry", "Entry", "SpeedSegment")]
            return SpeedProfileAction(segments, element.attrib.get("entityRef"), element)
        return None

    def speed_profile_actions(self):
        actions = []
        for element in self.root.iter("SpeedProfileAction"):
            segments = []
            for child in list(element):
                if child.tag in ("SpeedProfileEntry", "Entry", "SpeedSegment"):
                    segments.append(dict(child.attrib))
            actions.append(SpeedProfileAction(segments, element.attrib.get("entityRef"), element))
        return actions

    def relative_conditions(self):
        conditions = []
        for element in self.root.iter("RelativeAngleCondition"):
            conditions.append(RelativeAngleCondition(
                element.attrib.get("entityRef"), element.attrib.get("angle"), element.attrib.get("rule"),
                element.attrib.get("coordinateSystem", "entity"), element.attrib.get("name"),
                element.attrib.get("edge"), element))
        for element in self.root.iter("RelativeClearanceCondition"):
            conditions.append(RelativeClearanceCondition(
                element.attrib.get("entityRef"), element.attrib.get("distance"),
                element.attrib.get("freespace", "false").lower() == "true", element.attrib.get("rule"),
                element.attrib.get("distanceType", "cartesianDistance"), element.attrib.get("name"),
                element.attrib.get("edge"), element))
        return conditions

    def copy_xml(self):
        return copy.deepcopy(self.root)
