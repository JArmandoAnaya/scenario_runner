"""Document facts shared by the checker rules: scopes, entities, catalogs and static evaluation."""

from __future__ import absolute_import

import glob
import os

from srunner.openscenario.model import expressions
from srunner.openscenario.model.parameters import convert_value
from srunner.openscenario.validation.diagnostics import ValidationError
from srunner.openscenario.validation.schema_model import schema_model

ENTITY_TYPES = ("Vehicle", "Pedestrian", "MiscObject", "ExternalObjectReference")
OBJECT_TYPES = {"vehicle": "Vehicle", "pedestrian": "Pedestrian", "miscellaneous": "MiscObject",
                "external": "ExternalObjectReference"}
# Elements whose ``name`` attribute references something instead of declaring a name.
NAME_REFERENCES = frozenset(("TrafficSignalStateAction", "TrafficSignalCondition", "UserDefinedValueCondition"))


class Unresolved(Exception):
    """A value depends on something the static checker cannot evaluate."""


class CheckerContext(object):
    """Lazily computed views of one document for the checker rules."""

    def __init__(self, document, filename=None, parameter_overrides=None, catalogs=None):
        self.document = document
        self.root = document.root
        self.version = document.version.as_tuple()
        self.filename = filename or document.source
        self.overrides = dict(parameter_overrides or {})
        self._catalogs = catalogs
        self._catalog_problems = None
        self._entities = None
        self._scopes = {}
        self.cache = {}
        self._schema = schema_model()

    @property
    def base_dir(self):
        return os.path.dirname(os.path.abspath(self.filename)) if self.filename else None

    def parent(self, element):
        return self.document.locations.parent(element)

    def ancestors(self, element):
        element = self.parent(element)
        while element is not None:
            yield element
            element = self.parent(element)

    def nearest(self, element, tags):
        for ancestor in self.ancestors(element):
            if ancestor.tag in tags:
                return ancestor
        return None

    def attribute_type(self, element, attribute):
        return self._schema.attribute_types(element.tag).get(attribute)

    # Parameters -------------------------------------------------------------------------------------------------

    def declarations_in_scope(self, element):
        """Name -> ParameterDeclaration element visible at ``element`` (innermost scope wins)."""
        if element in self._scopes:
            return self._scopes[element]
        parent = self.parent(element)
        visible = dict(self.declarations_in_scope(parent)) if parent is not None else {}
        container = element.find("ParameterDeclarations")
        if container is not None:
            for declaration in container.findall("ParameterDeclaration"):
                visible[declaration.attrib.get("name")] = declaration
        self._scopes[element] = visible
        return visible

    def variables(self):
        declared = {}
        for container in (self.root.find("VariableDeclarations"), self.root.find("Storyboard/VariableDeclarations")):
            if container is None:
                continue
            for declaration in container.findall("VariableDeclaration"):
                declared[declaration.attrib.get("name")] = declaration
        return declared

    def is_global(self, declaration):
        return self.parent(self.parent(declaration)) is self.root

    def parameter_value(self, declaration, _stack=()):
        """Typed static value of a ParameterDeclaration, honouring overrides of global parameters."""
        name = declaration.attrib.get("name")
        if declaration in _stack:
            raise Unresolved("cyclic parameter reference {!r}".format(name))
        value = declaration.attrib.get("value")
        if self.is_global(declaration) and name in self.overrides:
            value = self.overrides[name]
        return self.evaluate(value, declaration, declaration.attrib.get("parameterType"),
                             _stack=_stack + (declaration,))

    def evaluate(self, value, element, expected_type=None, _stack=()):
        """Statically evaluate a literal, ``$name`` or ``${...}`` value visible at ``element``.

        Raises EvaluationError for errors in the value itself and Unresolved when it depends on an
        unknown or cyclic reference.
        """
        if value is None:
            raise Unresolved("no value")
        scope = self.declarations_in_scope(element)

        def lookup(name):
            if name not in scope:
                raise Unresolved("unknown parameter {!r}".format(name))
            return self.parameter_value(scope[name], _stack)

        if expressions.is_expression(value):
            return expressions.coerce(expressions.evaluate(value, lookup), expected_type, value)
        name = expressions.reference_name(value)
        if name is not None:
            resolved = lookup(name)
            return convert_value(resolved, expected_type, value) if expected_type else resolved
        return convert_value(value, expected_type, value) if expected_type else value

    def number(self, element, attribute):
        """Float value of a numeric attribute, or None when absent or not statically known."""
        try:
            return float(self.evaluate(element.attrib.get(attribute), element, "double"))
        except (Unresolved, ValidationError, ValueError, TypeError):
            return None

    def text(self, element, attribute):
        value = element.attrib.get(attribute)
        if value is None:
            return None
        try:
            return str(self.evaluate(value, element, "string"))
        except (Unresolved, ValidationError, ValueError, TypeError):
            return None

    # Entities ---------------------------------------------------------------------------------------------------

    def entities(self):
        """Name -> ScenarioObject or EntitySelection element."""
        if self._entities is None:
            self._entities = {}
            entities = self.root.find("Entities")
            if entities is not None:
                for element in entities:
                    if element.tag in ("ScenarioObject", "EntitySelection"):
                        self._entities[element.attrib.get("name")] = element
        return self._entities

    def entity_object(self, scenario_object):
        """The Vehicle/Pedestrian/... element of a ScenarioObject (resolving catalog references), or None."""
        for child in scenario_object:
            if child.tag in ENTITY_TYPES:
                return child
            if child.tag == "CatalogReference":
                entry = self.catalog_entry(child)
                return entry if entry is not None and entry.tag in ENTITY_TYPES else None
        return None

    def entity_types(self, name, _seen=()):
        """Set of entity types behind ``name`` (a selection yields its members' types); None if unknown."""
        element = self.entities().get(name)
        if element is None or name in _seen:
            return None
        if element.tag == "ScenarioObject":
            entity = self.entity_object(element)
            return {entity.tag} if entity is not None else None
        types = set()
        members = element.find("Members")
        for member in (members if members is not None else []):
            if member.tag == "ByType":
                types.add(OBJECT_TYPES.get(member.attrib.get("objectType"), member.attrib.get("objectType")))
            elif member.tag == "EntityRef":
                member_types = self.entity_types(member.attrib.get("entityRef"), _seen + (name,))
                if member_types is None:
                    return None
                types.update(member_types)
        return types

    def subjects(self, element):
        """Entity names an action or condition applies to (Private, ManeuverGroup actors, triggering entities)."""
        for ancestor in self.ancestors(element):
            if ancestor.tag == "ByEntityCondition":
                return [ref.attrib.get("entityRef") for ref in ancestor.findall("TriggeringEntities/EntityRef")]
            if ancestor.tag == "Private":
                return [ancestor.attrib.get("entityRef")]
            if ancestor.tag == "ManeuverGroup":
                return [ref.attrib.get("entityRef") for ref in ancestor.findall("Actors/EntityRef")]
            if ancestor.tag in ("GlobalAction", "Catalog"):
                return []
        return []

    # Catalogs ---------------------------------------------------------------------------------------------------

    def catalog_directories(self):
        """(location element, absolute directory or None) for each CatalogLocations entry."""
        locations = self.root.find("CatalogLocations")
        result = []
        for location in (locations if locations is not None else []):
            directory = location.find("Directory")
            if directory is None:
                continue
            path = self.text(directory, "path")
            if path is not None and not os.path.isabs(path) and self.base_dir:
                path = os.path.join(self.base_dir, path)
            result.append((directory, path if path is not None and (os.path.isabs(path) or self.base_dir) else None))
        return result

    def catalogs(self):
        """Catalog name -> {entry name: element}; None when the document location is unknown."""
        if self._catalogs is not None:
            return self._catalogs
        if not self.filename:
            return None
        # Deferred: the loader imports the model, which imports the validation package.
        from srunner.openscenario.parsing.loader import parse_xml  # pylint: disable=import-outside-toplevel
        self._catalogs = {}
        for _, directory in self.catalog_directories():
            if directory is None or not os.path.isdir(directory):
                continue
            for path in sorted(glob.glob(os.path.join(directory, "*.xosc"))):
                try:
                    root = parse_xml(path)[0]
                except (ValidationError, OSError):
                    continue
                catalog = root.find("Catalog")
                if catalog is None:
                    continue
                entries = self._catalogs.setdefault(catalog.attrib.get("name"), {})
                for entry in catalog:
                    entries.setdefault(entry.attrib.get("name"), entry)
        return self._catalogs

    def catalog_entry(self, reference):
        catalogs = self.catalogs()
        if catalogs is None:
            return None
        entry_name = self.text(reference, "entryName")
        return catalogs.get(self.text(reference, "catalogName"), {}).get(entry_name)

    def resolve_file(self, path):
        if not path:
            return None
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_dir, path) if self.base_dir else None
