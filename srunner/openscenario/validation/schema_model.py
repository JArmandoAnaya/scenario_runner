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
        self._attribute_types = {}

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

    def features(self):
        """OrderedDict category -> sorted element names, extracted from the schema."""
        return OrderedDict((category, sorted(self.leaves(root))) for category, root in FEATURE_ROOTS.items())


_MODELS = {}


def schema_model(key="1.3.1"):
    if key not in _MODELS:
        _MODELS[key] = SchemaModel(SCHEMA_FILES[key])
    return _MODELS[key]
