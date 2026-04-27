"""Build the final XML feedback output."""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def _indent(elem, level: int = 0) -> None:
    """Add pretty-print indentation to XML tree in-place."""
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


def build_xml_output(
    platform_id: str,
    mode: str,
    level: str,
    language: str,
    kc_name: str,
    kc_description: str,
    components: dict,
    platform_exercise_id: str | None = None,
) -> str:
    """
    Build XML string from assembled components.

    components: dict[characteristic_name → {type, content, iterations, caption?, quality_score?}]

    Returns a well-formed XML string.
    """
    root = ET.Element("feedback")

    # --- Metadata ---
    meta = ET.SubElement(root, "metadata")
    ET.SubElement(meta, "platform").text = platform_id
    ET.SubElement(meta, "mode").text = mode
    ET.SubElement(meta, "level").text = level
    ET.SubElement(meta, "language").text = language
    if level in ("exercise", "error") and platform_exercise_id:
        ET.SubElement(meta, "platform_exercise_id").text = platform_exercise_id
    ET.SubElement(meta, "generated_at").text = datetime.now(timezone.utc).isoformat()

    # --- Knowledge Component ---
    kc = ET.SubElement(root, "knowledge_component")
    ET.SubElement(kc, "name").text = kc_name
    ET.SubElement(kc, "description").text = kc_description

    # --- Components ---
    components_el = ET.SubElement(root, "components")

    for char_name, comp in components.items():
        comp_el = ET.SubElement(components_el, "component")
        comp_el.set("characteristic", char_name)
        comp_el.set("type", comp.get("type", "text"))

        ET.SubElement(comp_el, "iterations").text = str(comp.get("iterations", 1))

        if comp.get("type") == "image":
            ET.SubElement(comp_el, "image_url").text = comp.get("image_url", "")
            ET.SubElement(comp_el, "caption").text = comp.get("caption", "")
            if "quality_score" in comp:
                ET.SubElement(comp_el, "quality_score").text = str(
                    round(comp["quality_score"], 3)
                )
        else:
            # Text component
            ET.SubElement(comp_el, "content").text = comp.get("content", "")

        # Orchestrator evaluation metadata (present when quality gate ran)
        if comp.get("evaluation_notes"):
            ET.SubElement(comp_el, "evaluation_notes").text = comp["evaluation_notes"]

        # Future extension slot — code output
        # ET.SubElement(comp_el, "code_display") — reserved for v2

    _indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
