"""Крошечный валидатор подмножества JSON Schema (stdlib-only).

Схема, против которой никто не валидирует, — это ровно тот вид вранья, ради
которого harness и затевался. Поэтому здесь минимальный, но настоящий чекер:
type, required, properties, additionalProperties, items, enum, const, pattern,
minItems. Конструкция вне этого списка — ошибка схемы, а не «пропустим».
"""

from __future__ import annotations

import re
from typing import Any

SUPPORTED = {
    "type",
    "required",
    "properties",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "pattern",
    "minItems",
    "description",
    "$schema",
    "title",
    "definitions",
    "$ref",
}

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class SchemaError(ValueError):
    pass


def validate(instance: Any, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    root = root if root is not None else schema
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise SchemaError(f"{path}: schema uses unsupported keywords {sorted(unknown)}")

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/definitions/"):
            raise SchemaError(f"{path}: only '#/definitions/<name>' refs are supported")
        target = root.get("definitions", {}).get(ref.split("/")[-1])
        if target is None:
            raise SchemaError(f"{path}: unresolved $ref {ref}")
        return validate(instance, target, root, path)

    errors: list[str] = []

    if "type" in schema:
        expected = schema["type"]
        names = expected if isinstance(expected, list) else [expected]
        for name in names:
            if name not in TYPES:
                raise SchemaError(f"{path}: unknown type {name!r}")
        # bool — подкласс int: без этой проверки true проходит как integer.
        ok = any(
            isinstance(instance, TYPES[name])
            and not (name in ("integer", "number") and isinstance(instance, bool))
            and not (name == "boolean" and not isinstance(instance, bool))
            for name in names
        )
        if not ok:
            return [f"{path}: expected type {expected}, got {type(instance).__name__}"]

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")

    if "pattern" in schema and isinstance(instance, str):
        if not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match /{schema['pattern']}/")

    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required property '{name}'")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for name in instance:
                if name not in properties:
                    errors.append(f"{path}: unexpected property '{name}'")
        for name, subschema in properties.items():
            if name in instance:
                errors += validate(instance[name], subschema, root, f"{path}.{name}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: expected at least {schema['minItems']} item(s), got {len(instance)}")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors += validate(item, schema["items"], root, f"{path}[{index}]")

    return errors
