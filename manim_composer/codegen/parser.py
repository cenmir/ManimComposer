"""Regex-based parser for generated ManimGL / Manim CE code.

Extracts objects, animations, and scene metadata so that manual
code edits can be synced back to the canvas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedObject:
    name: str
    latex: str
    color: str = "#FFFFFF"
    font_size: int = 48
    pos_x: float = 0.0  # manim coords
    pos_y: float = 0.0


@dataclass
class ParsedAnimation:
    target_name: str
    anim_type: str
    duration: float = 1.0
    easing: str = "smooth"


@dataclass
class ParsedScene:
    name: str
    bg_color: str = "#000000"
    objects: list[ParsedObject] = field(default_factory=list)
    animations: list[ParsedAnimation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns (match both GL Tex and CE MathTex)
# ---------------------------------------------------------------------------

_RE_CLASS = re.compile(r"class\s+(\w+)\s*\(\s*Scene\s*\)\s*:")
_RE_OBJ = re.compile(r"(\w+)\s*=\s*(?:Tex|MathTex)\s*\(\s*r\"([^\"]*)\"\s*\)")
_RE_COLOR = re.compile(r"(\w+)\.set_color\s*\(\s*\"(#[0-9A-Fa-f]{6})\"\s*\)")
_RE_SCALE = re.compile(r"(\w+)\.scale\s*\(\s*([\d.]+)\s*\)")
_RE_MOVE = re.compile(
    r"(\w+)\.move_to\s*\(\s*np\.array\s*\(\s*\[\s*([\d.eE+-]+)\s*,\s*([\d.eE+-]+)\s*,\s*[\d.eE+-]+\s*\]\s*\)\s*\)"
)
_RE_BG_CE = re.compile(r"self\.camera\.background_color\s*=\s*\"(#[0-9A-Fa-f]{6})\"")
_RE_BG_GL = re.compile(r"self\.camera\.background_rgba\s*=\s*color_to_rgba\s*\(\s*\"(#[0-9A-Fa-f]{6})\"\s*\)")
_RE_ADD = re.compile(r"self\.add\s*\(\s*(\w+)\s*\)")
_RE_WAIT = re.compile(r"self\.wait\s*\(\s*([\d.]+)?\s*\)")
_RE_PLAY = re.compile(
    r"self\.play\s*\(\s*(\w+)\s*\(\s*(\w+)\s*\)"
    r"(?:\s*,\s*run_time\s*=\s*([\d.]+))?"
    r"(?:\s*,\s*rate_func\s*=\s*(\w+))?"
)

# CE→GL animation name reverse mapping
_CE_TO_GL_ANIM: dict[str, str] = {
    "Create": "ShowCreation",
}


def parse_code(code: str) -> list[ParsedScene] | None:
    """Parse GL or CE code into structured scene data.

    Returns a list of ParsedScene, or None if no valid scenes found.
    Silently ignores lines that don't match known patterns.
    """
    # Split code into scene blocks by class declarations
    class_matches = list(_RE_CLASS.finditer(code))
    if not class_matches:
        return None

    scenes: list[ParsedScene] = []
    for i, match in enumerate(class_matches):
        scene_name = match.group(1)
        # Extract the block of code for this scene
        start = match.end()
        end = class_matches[i + 1].start() if i + 1 < len(class_matches) else len(code)
        block = code[start:end]

        scene = _parse_scene_block(scene_name, block)
        scenes.append(scene)

    return scenes if scenes else None


def _parse_scene_block(scene_name: str, block: str) -> ParsedScene:
    """Parse a single scene's construct() body."""
    scene = ParsedScene(name=scene_name)
    objects: dict[str, ParsedObject] = {}

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Background color
        m = _RE_BG_CE.search(stripped)
        if m:
            scene.bg_color = m.group(1)
            continue
        m = _RE_BG_GL.search(stripped)
        if m:
            scene.bg_color = m.group(1)
            continue

        # Object declaration
        m = _RE_OBJ.search(stripped)
        if m:
            name, latex = m.group(1), m.group(2)
            obj = ParsedObject(name=name, latex=latex)
            objects[name] = obj
            continue

        # Object color
        m = _RE_COLOR.search(stripped)
        if m:
            name, color = m.group(1), m.group(2)
            if name in objects:
                objects[name].color = color
            continue

        # Object scale
        m = _RE_SCALE.search(stripped)
        if m:
            name = m.group(1)
            try:
                scale = float(m.group(2))
            except ValueError:
                continue
            if name in objects:
                objects[name].font_size = max(8, round(scale * 48))
            continue

        # Object position
        m = _RE_MOVE.search(stripped)
        if m:
            name = m.group(1)
            try:
                x, y = float(m.group(2)), float(m.group(3))
            except ValueError:
                continue
            if name in objects:
                objects[name].pos_x = x
                objects[name].pos_y = y
            continue

        # Add animation
        m = _RE_ADD.search(stripped)
        if m:
            target = m.group(1)
            scene.animations.append(ParsedAnimation(
                target_name=target, anim_type="Add",
                duration=0.0, easing="",
            ))
            continue

        # Wait animation
        m = _RE_WAIT.search(stripped)
        if m:
            dur = float(m.group(1)) if m.group(1) else 1.0
            scene.animations.append(ParsedAnimation(
                target_name="", anim_type="Wait",
                duration=dur, easing="",
            ))
            continue

        # Play animation
        m = _RE_PLAY.search(stripped)
        if m:
            anim_type = m.group(1)
            target = m.group(2)
            dur = float(m.group(3)) if m.group(3) else 1.0
            easing = m.group(4) or "smooth"
            # Normalize CE animation names back to canonical form
            anim_type = _CE_TO_GL_ANIM.get(anim_type, anim_type)
            scene.animations.append(ParsedAnimation(
                target_name=target, anim_type=anim_type,
                duration=dur, easing=easing,
            ))
            continue

    scene.objects = list(objects.values())
    return scene
