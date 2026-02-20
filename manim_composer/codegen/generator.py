"""ManimGL code generation from SceneState."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manim_composer.models.scene_state import SceneState


def _generate_body(scene_state: SceneState, indent: str = "") -> list[str]:
    """Generate the construct() body lines (objects + animations)."""
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
            constructor = f'Tex(r"{tracked.latex}")'

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
            anim_call = f"{anim.anim_type}({anim.target_name})"
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
) -> str:
    """Generate a complete ManimGL script from the current scene state."""
    lines: list[str] = [
        "from manimlib import *",
        "",
        "",
        f"class {scene_name}(Scene):",
        "    def construct(self):",
    ]

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
        lines.append("            except FileNotFoundError:")
        lines.append("                pass")
        lines.append("            _time.sleep(0.02)")

    return "\n".join(lines) + "\n"


def generate_replay_code(scene_state: SceneState) -> str:
    """Generate a replay snippet to hot-reload into a running preview.

    Clears the scene and re-executes the construct body.
    """
    lines: list[str] = [
        "self.clear()",
        "self.add(Rectangle(width=FRAME_WIDTH, height=FRAME_HEIGHT,"
        " stroke_color=WHITE, stroke_width=1))",
    ]
    body = _generate_body(scene_state, indent="")
    lines.extend(body)
    return "\n".join(lines) + "\n"
