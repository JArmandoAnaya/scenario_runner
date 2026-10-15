"""Read-only facts extracted from the bundled XSDs (element types, attribute types, feature lists)."""

from __future__ import absolute_import

import xml.etree.ElementTree as ET
from collections import OrderedDict

from srunner.openscenario.validation.schema import SCHEMA_FILES

XSD = "{http://www.w3.org/2001/XMLSchema}"
VALUE_TYPES = {"Double": "double", "Int": "int", "UnsignedInt": "unsignedInt", "UnsignedShort": "unsignedShort",
               "Boolean": "boolean", "DateTime": "dateTime", "String": "string"}

# Category -> (complex type whose choice tree is expanded, label).  Wrapper types (a single choice of
# elements) are expanded recursively, so the leaves are the concrete actions, conditions, positions, ...
FEATURE_ROOTS = OrderedDict([
    ("action", "Action"),
    ("entity_action", "EntityAction"),
    ("traffic_signal_action", "TrafficSignalAction"),
    ("traffic_action", "TrafficAction"),
    ("parameter_action", "ParameterAction"),
    ("variable_action", "VariableAction"),
    ("user_defined_action", "UserDefinedAction"),
    ("override_action", "OverrideControllerValueAction"),
    ("condition", "Condition"),
    ("entity_condition", "EntityCondition"),
    ("position", "Position"),
    ("trajectory_shape", "Shape"),
    ("route_position", "InRoutePosition"),
    ("entity", "EntityObject"),
    ("environment", "Environment"),
    ("weather", "Weather"),
    ("speed_target", "SpeedActionTarget"),
    ("time_reference", "TimeReference"),
    ("distribution", "DistributionDefinition"),
])
# Choice members that are a reuse mechanism rather than a feature of the category.
_NOT_FEATURES = frozenset(("CatalogReference", "ParameterDeclarations"))
_FEATURE_SUFFIXES = ("Action", "Condition", "Position")


class SchemaModel(object):
    """Index of one XSD: element and attribute types and choice trees."""

    def __init__(self, path):
        root = ET.parse(path).getroot()
        self.complex_types = dict((node.attrib["name"], node) for node in root.findall(XSD + "complexType"))
        self.groups = dict((node.attrib["name"], node) for node in root.findall(XSD + "group"))
        self.element_types = {}
        for node in root.iter(XSD + "element"):
            if "name" in node.attrib and "type" in node.attrib:
                self.element_types.setdefault(node.attrib["name"], set()).add(node.attrib["type"])
        self.root_types = dict((node.attrib["name"], node.attrib.get("type")) for node in root.findall(XSD + "element"))
        self._attribute_types = {}
        self._child_types = {}
        self._choices = {}

    def attribute_types(self, tag):
        """Map attribute name -> value type ('double', 'int', 'boolean', 'string', ...) for element ``tag``."""
        if tag not in self._attribute_types:
            merged = {}
            for type_name in self.element_types.get(tag, ()):
                node = self.complex_types.get(type_name)
                if node is None:
                    continue
                for attribute in node.iter(XSD + "attribute"):
                    value_type = VALUE_TYPES.get(attribute.attrib.get("type"), "string")
                    previous = merged.setdefault(attribute.attrib["name"], value_type)
                    if previous != value_type:
                        merged[attribute.attrib["name"]] = None
            self._attribute_types[tag] = merged
        return self._attribute_types[tag]

    def _particles(self, node):
        """Element children of a model group, following group references."""
        for child in node:
            if child.tag == XSD + "element":
                yield child
            elif child.tag == XSD + "group" and "ref" in child.attrib:
                yield from self._particles(self.groups[child.attrib["ref"]])
            elif child.tag in (XSD + "choice", XSD + "sequence", XSD + "all"):
                yield from self._particles(child)

    def _content(self, type_name):
        node = self.complex_types.get(type_name, self.groups.get(type_name))
        if node is None:
            return None, []
        models = [child for child in node if child.tag in (XSD + "choice", XSD + "sequence", XSD + "all")]
        if len(models) != 1:
            return None, []
        return models[0].tag[len(XSD):], list(self._particles(models[0]))

    def _is_wrapper(self, type_name):
        kind, particles = self._content(type_name)
        node = self.complex_types.get(type_name)
        has_attributes = node is not None and node.find(XSD + "attribute") is not None
        return kind == "choice" and not has_attributes and all("type" in item.attrib for item in particles) and \
            not any(item.attrib.get("name") in _NOT_FEATURES for item in particles)

    def leaves(self, type_name):
        """Concrete element names reachable from ``type_name`` through choice-only wrapper types."""
        _, particles = self._content(type_name)
        result = []
        for item in particles:
            name = item.attrib.get("name")
            if name is None or name in _NOT_FEATURES:
                continue
            child_type = item.attrib.get("type")
            if child_type and child_type != type_name and self._is_wrapper(child_type) and \
                    all(item.attrib["type"].endswith(_FEATURE_SUFFIXES) for item in self._content(child_type)[1]):
                result.extend(leaf for leaf in self.leaves(child_type) if leaf not in result)
            elif name not in result:
                result.append(name)
        return result

    def child_types(self, type_name):
        """Map child element name -> type name for the content model of complex type ``type_name``."""
        if type_name not in self._child_types:
            node = self.complex_types.get(type_name)
            self._child_types[type_name] = dict(
                (item.attrib["name"], item.attrib["type"]) for item in (self._particles(node) if node is not None
                                                                         else ()) if "type" in item.attrib)
        return self._child_types[type_name]

    def _choice_nodes(self, owner, node, optional=False):
        """Yield ``(owner, choice, optional)`` for every xsd:choice of a model group, following group references.

        ``optional`` is True when an enclosing particle (group reference, sequence or choice) or the choice
        itself has minOccurs="0".
        """
        for child in node:
            if child.tag not in (XSD + "group", XSD + "choice", XSD + "sequence", XSD + "all"):
                continue
            child_optional = optional or child.attrib.get("minOccurs") == "0"
            if child.tag == XSD + "choice":
                yield owner, child, child_optional
            if child.tag == XSD + "group" and "ref" in child.attrib:
                yield from self._choice_nodes(child.attrib["ref"], self.groups[child.attrib["ref"]], child_optional)
            elif child.tag != XSD + "group":
                yield from self._choice_nodes(owner, child, child_optional)

    def choices(self, type_name):
        """``[(owner, members, choice_optional, members_optional)]`` for the element choices of ``type_name``.

        ``owner`` is the complex type or group declaring the choice; ``choice_optional`` is True when the
        choice or an enclosing particle has minOccurs="0" and ``members_optional`` when every member has
        minOccurs="0".
        """
        if type_name not in self._choices:
            node = self.complex_types.get(type_name)
            result = []
            for owner, choice, optional in (self._choice_nodes(type_name, node) if node is not None else ()):
                members = list(choice)
                if not members or any(item.tag != XSD + "element" for item in members):
                    continue
                result.append((owner, tuple(item.attrib["name"] for item in members), optional,
                               all(item.attrib.get("minOccurs") == "0" for item in members)))
            self._choices[type_name] = result
        return self._choices[type_name]

    def optional_choice_owners(self):
        """Types and groups whose element choice may be empty according to this schema."""
        owners = set()
        for type_name in self.complex_types:
            owners.update(owner for owner, _, choice_optional, members_optional in self.choices(type_name)
                          if choice_optional or members_optional)
        return owners

    def empty_choices(self, root, reference=None):
        """Yield ``(element, members)`` for each element below ``root`` that has none of a choice's members.

        The 1.0 XSD marks every choice member minOccurs="0" although the standard requires one of them, so
        whether a choice may be empty is taken from ``reference`` (a SchemaModel, by default this one): a
        choice is required unless it has minOccurs="0" here or its owner's choice may be empty in
        ``reference``.
        """
        optional_owners = (reference or self).optional_choice_owners()
        stack = [(root, self.root_types.get(root.tag))]
        while stack:
            element, type_name = stack.pop()
            if type_name is None:
                continue
            tags = set(child.tag for child in element)
            for owner, members, choice_optional, _ in self.choices(type_name):
                if not choice_optional and owner not in optional_owners and not tags.intersection(members):
                    yield element, members
            child_types = self.child_types(type_name)
            stack.extend((child, child_types.get(child.tag)) for child in reversed(list(element)))

    def features(self):
        """OrderedDict category -> sorted element names, extracted from the schema."""
        return OrderedDict((category, sorted(self.leaves(root))) for category, root in FEATURE_ROOTS.items())


_MODELS = {}


def schema_model(key="1.3.1"):
    if key not in _MODELS:
        _MODELS[key] = SchemaModel(SCHEMA_FILES[key])
    return _MODELS[key]
