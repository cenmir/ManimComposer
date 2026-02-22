"""Code generation from SceneState for ManimGL and Manim Community."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manim_composer.models.scene_state import SceneState


_CE_ANIM_NAMES: dict[str, str] = {
    "ShowCreation": "Create",
}


def _generate_body(
    scene_state: SceneState,
    indent: str = "",
    anim_map: dict[str, str] | None = None,
    ce: bool = False,
) -> list[str]:
    """Generate the construct() body lines (objects + animations).

    *anim_map* optionally remaps animation type names (e.g. for CE).
    *ce* uses Manim Community constructors (MathTex instead of Tex).
    """
    lines: list[str] = []
    objects = scene_state.all_objects()
    animations = scene_state.all_animations()

    if not objects and not animations:
        return lines

    # --- Object declarations ---
    for name, tracked in objects:
        item = scene_state.get_item(name)
        if not item:
            continue

        if tracked.obj_type == "mathtex":
            cls = "MathTex" if ce else "Tex"
            constructor = f'{cls}(r"{tracked.latex}")'

        lines.append(f"{indent}{name} = {constructor}")

        if tracked.obj_type == "mathtex" and tracked.color and tracked.color.upper() != "#FFFFFF":
            lines.append(f'{indent}{name}.set_color("{tracked.color}")')

        if tracked.obj_type == "mathtex" and tracked.font_size != 48:
            scale = tracked.font_size / 48.0
            lines.append(f"{indent}{name}.scale({scale:.4g})")

        # Position — read live from the canvas item
        pos = item.pos()
        mx = pos.x() / 100.0
        my = -pos.y() / 100.0  # flip Y
        if abs(mx) > 0.01 or abs(my) > 0.01:
            lines.append(
                f"{indent}{name}.move_to(np.array([{mx:.2f}, {my:.2f}, 0]))"
            )

    # --- Animations ---
    if animations:
        for anim in animations:
            if anim.anim_type == "Add":
                lines.append(f"{indent}self.add({anim.target_name})")
                continue
            if anim.anim_type == "Wait":
                if abs(anim.duration - 1.0) > 0.01:
                    lines.append(f"{indent}self.wait({anim.duration:.1f})")
                else:
                    lines.append(f"{indent}self.wait()")
                continue

            anim_type = anim.anim_type
            if anim_map:
                anim_type = anim_map.get(anim_type, anim_type)
            anim_call = f"{anim_type}({anim.target_name})"
            params: list[str] = []
            if abs(anim.duration - 1.0) > 0.01:
                params.append(f"run_time={anim.duration:.1f}")
            if anim.easing and anim.easing != "smooth":
                params.append(f"rate_func={anim.easing}")

            if params:
                lines.append(
                    f"{indent}self.play({anim_call}, {', '.join(params)})"
                )
            else:
                lines.append(f"{indent}self.play({anim_call})")

    if objects and not animations:
        lines.append(f"{indent}self.wait()")

    return lines


def generate_manimgl_code(
    scene_state: SceneState,
    scene_name: str = "ComposedScene",
    interactive: bool = False,
    replay_file: str = "",
    include_import: bool = True,
    bg_color: str = "#000000",
) -> str:
    """Generate a complete ManimGL script from the current scene state."""
    lines: list[str] = []
    if include_import:
        lines += ["from manimlib import *", "", ""]
    lines += [
        f"class {scene_name}(Scene):",
        "    def construct(self):",
    ]

    if bg_color and bg_color.upper() != "#000000":
        lines.append(f'        self.camera.background_rgba = color_to_rgba("{bg_color}")')
        lines.append("")

    if interactive:
        lines.append("        # Lock 16:9 aspect ratio on resize")
        lines.append("        if self.window:")
        lines.append("            self.window.fixed_aspect_ratio = 16 / 9")
        lines.append("")
        lines.append("        # Scene boundary border")
        lines.append("        _border = Rectangle(width=FRAME_WIDTH, height=FRAME_HEIGHT,")
        lines.append("                            stroke_color=WHITE, stroke_width=1)")
        lines.append("        self.add(_border)")
        lines.append("")

    body = _generate_body(scene_state, indent="        ")
    if not body and not interactive:
        lines.append("        pass")
    else:
        lines.extend(body)

    if interactive:
        lines.append("")
        lines.append("        # Keep GL window alive, watch for hot-reload")
        lines.append("        import os as _os, time as _time")
        lines.append(f'        _rp = r"{replay_file}"')
        lines.append("        _lm = 0.0")
        lines.append("        while not self.is_window_closing():")
        lines.append("            self.update_frame(dt=0)")
        lines.append("            try:")
        lines.append("                _mt = _os.path.getmtime(_rp)")
        lines.append("                if _mt > _lm:")
        lines.append("                    _lm = _mt")
        lines.append("                    exec(open(_rp).read())")
        lines.append("                    self.update_frame(dt=0, force_draw=True)")
        lines.append("            except FileNotFoundError:")
        lines.append("                pass")
        lines.append("            _time.sleep(0.02)")

    return "\n".join(lines) + "\n"


def generate_manimce_code(
    scene_state: SceneState,
    scene_name: str = "ComposedScene",
    include_import: bool = True,
    bg_color: str = "#000000",
) -> str:
    """Generate a complete Manim Community Edition script from the current scene state."""
    lines: list[str] = []
    if include_import:
        lines += ["from manim import *", "", ""]
    lines += [
        f"class {scene_name}(Scene):",
        "    def construct(self):",
    ]

    if bg_color and bg_color.upper() != "#000000":
        lines.append(f'        self.camera.background_color = "{bg_color}"')
        lines.append("")

    body = _generate_body(scene_state, indent="        ", anim_map=_CE_ANIM_NAMES, ce=True)
    if not body:
        lines.append("        pass")
    else:
        lines.extend(body)

    return "\n".join(lines) + "\n"


def generate_replay_code(scene_state: SceneState, bg_color: str = "#000000") -> str:
    """Generate a replay snippet to hot-reload into a running preview.

    Clears the scene and re-executes the construct body.
    """
    lines: list[str] = [
        "self.clear()",
    ]
    if bg_color and bg_color.upper() != "#000000":
        lines.append(f'self.camera.background_rgba = color_to_rgba("{bg_color}")')
    else:
        lines.append('self.camera.background_rgba = color_to_rgba("#000000")')
    lines.append(
        "self.add(Rectangle(width=FRAME_WIDTH, height=FRAME_HEIGHT,"
        " stroke_color=WHITE, stroke_width=1))"
    )
    body = _generate_body(scene_state, indent="")
    lines.extend(body)
    return "\n".join(lines) + "\n"
