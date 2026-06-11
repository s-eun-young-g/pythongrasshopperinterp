"""Small read-side helpers for tests: pull structure out of a .ghx string.

This is intentionally a separate, dependency-free reader so the tests validate
the emitter's output by *parsing it back*, not by trusting the emitter.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


def _chunk(parent: ET.Element, name: str) -> ET.Element | None:
    for chunks in parent.findall("chunks"):
        for chunk in chunks.findall("chunk"):
            if chunk.get("name") == name:
                return chunk
    return None


def _items(chunk: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    items = chunk.find("items")
    if items is None:
        return out
    for item in items.findall("item"):
        out[item.get("name")] = (item.text or "").strip()
    return out


def parse_objects(ghx: str) -> list[dict]:
    """Return one dict per canvas Object: name, nickname, and (for sliders) value."""
    root = ET.fromstring(ghx)
    definition = _chunk(root, "Definition")
    objects = _chunk(definition, "DefinitionObjects")
    result = []
    for chunks in objects.findall("chunks"):
        for obj in chunks.findall("chunk"):
            if obj.get("name") != "Object":
                continue
            obj_items = _items(obj)
            container = _chunk(obj, "Container")
            cont_items = _items(container) if container is not None else {}
            entry = {
                "name": obj_items.get("Name", ""),
                "nickname": cont_items.get("NickName", ""),
            }
            slider = _chunk(container, "Slider") if container is not None else None
            if slider is not None:
                entry["value"] = float(_items(slider).get("Value", "nan"))
            result.append(entry)
    return result


def all_instance_guids(ghx: str) -> set[str]:
    """Every InstanceGuid declared anywhere in the document."""
    root = ET.fromstring(ghx)
    return {e.text.strip() for e in root.iter("item")
            if e.get("name") == "InstanceGuid" and e.text}


def all_sources(ghx: str) -> list[str]:
    """Every wire Source guid (what a downstream input cites)."""
    root = ET.fromstring(ghx)
    return [e.text.strip() for e in root.iter("item")
            if e.get("name") == "Source" and e.text]


def object_count(ghx: str) -> int:
    root = ET.fromstring(ghx)
    definition = _chunk(root, "Definition")
    objects = _chunk(definition, "DefinitionObjects")
    return int(_items(objects)["ObjectCount"])
