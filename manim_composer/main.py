"""Manim Composer — Entry point."""

import sys
import os
import tempfile

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QButtonGroup, QGraphicsScene,
    QAbstractItemView, QGraphicsView, QListView, QPlainTextEdit,
)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QTextCursor, QCursor
from PyQt6.QtCore import Qt, QEvent, QProcess, QPointF, QProcessEnvironment, QTimer
from PyQt6 import uic

from manim_composer.views.canvas_items.mathtex_item import MathTexItem
from manim_composer.models.scene_state import SceneState, TrackedObject, AnimationEntry
from manim_composer.controllers.properties_controller import PropertiesController
from manim_composer.codegen.generator import generate_manimce_code, generate_manimgl_code, generate_replay_code
from manim_composer.codegen.parser import parse_code
from manim_composer import latex_manager
from manim_composer.syntax_highlighter import PythonHighlighter

# Launcher script template for manimgl preview.
# Patches the -no-pdf issue on MiKTeX before running manimgl.
_LAUNCHER_TEMPLATE = r'''
import sys, re, subprocess, tempfile
from pathlib import Path

# Set argv BEFORE importing manimlib — config is parsed at import time
sys.argv = ["manimlib", "{scene_file}", "{scene_name}", "-c", "#000000"]

# Now import manimlib (triggers config initialization with correct argv)
import manimlib.utils.tex_file_writing as _tex_mod
from manimlib.utils.cache import cache_on_disk as _cache_on_disk

# Patch manimgl: MiKTeX's latex rejects -no-pdf (only needed for xelatex)
_orig_LatexError = _tex_mod.LatexError

@_cache_on_disk
def _patched_full_tex_to_svg(full_tex, compiler="latex", message=""):
    if message:
        print(message, end="\r")
    dvi_ext = ".dvi" if compiler == "latex" else ".xdv"
    with tempfile.TemporaryDirectory() as td:
        tex_path = Path(td, "working.tex")
        tex_path.write_text(full_tex)
        cmd = [compiler, "-interaction=batchmode", "-halt-on-error",
               f"-output-directory={{td}}", str(tex_path)]
        if compiler == "xelatex":
            cmd.insert(1, "-no-pdf")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = ""
            log_p = tex_path.with_suffix(".log")
            if log_p.exists():
                m = re.search(r"(?<=\n! ).*\n.*\n", log_p.read_text())
                if m:
                    err = m.group()
            raise _orig_LatexError(err or "LaTeX compilation failed")
        proc2 = subprocess.run(
            ["dvisvgm", str(tex_path.with_suffix(dvi_ext)), "-n", "-v", "0", "--stdout"],
            capture_output=True)
        result = proc2.stdout.decode("utf-8")
    if message:
        print(" " * len(message), end="\r")
    return result

_tex_mod.full_tex_to_svg = _patched_full_tex_to_svg

# Position the preview window adjacent to the Composer
from manimlib.config import manim_config
manim_config.window_config.position = ({win_x}, {win_y})

from manimlib.__main__ import main
main()
'''

# Quality presets for Manim CE rendering: label → (width, height, fps)
_QUALITY_PRESETS = {
    "480p 15fps": (854, 480, 15),
    "720p 30fps": (1280, 720, 30),
    "1080p 60fps": (1920, 1080, 60),
    "4K 60fps": (3840, 2160, 60),
}


class ManimComposerWindow(QMainWindow):
    """Main application window, loaded from the .ui file."""

    def __init__(self):
        super().__init__()

        # Load the .ui file
        ui_path = os.path.join(os.path.dirname(__file__), "main_window.ui")
        uic.loadUi(ui_path, self)

        self._fix_widget_enums()
        self._setup_toolbar_tabs()
        self._setup_center_tabs()
        self._setup_tool_button_group()
        default_item = self._setup_canvas()
        self._setup_default_proportions()
        self._setup_window_geometry()

        # MVP wiring
        self._scenes: list[dict] = []  # Each: {"name": str, "state": SceneState}
        self._current_scene_idx: int = 0
        self._scene_counter: int = 1
        self._updating_scenes: bool = False
        self._add_scene_entry("Scene1")
        self._clipboard: dict | None = None
        self._register_default_item(default_item)
        self.props_controller = PropertiesController(self, self.scene_state)
        self._setup_scenes_panel()
        self._setup_animations_panel()
        self._setup_code_generation()
        self._setup_delete_action()
        self._setup_copy_paste()
        self._setup_preview()

        # Set up syntax highlighting for code editors
        self._setup_syntax_highlighting()

    # --- Scene management ---

    @property
    def scene_state(self) -> SceneState:
        return self._scenes[self._current_scene_idx]["state"]

    def _current_scene_name(self) -> str:
        return self._scenes[self._current_scene_idx]["name"]

    def _add_scene_entry(self, name: str, bg_color: str = "#000000") -> None:
        """Create a new scene and add it to the scenes list."""
        self._scenes.append({"name": name, "state": SceneState(), "bg_color": bg_color})
        self._updating_scenes = True
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.scenesList.addItem(item)
        self._updating_scenes = False

    def _setup_scenes_panel(self):
        """Wire scenes list buttons, selection, rename, and drag-drop."""
        self.btnAddScene.clicked.connect(self._on_add_scene)
        self.btnDeleteScene.clicked.connect(self._on_delete_scene)
        self.scenesList.currentRowChanged.connect(self._on_scene_selected)
        self.scenesList.itemClicked.connect(self._on_scene_clicked)
        self.scenesList.itemChanged.connect(self._on_scene_renamed)
        self.scenesList.model().rowsMoved.connect(self._on_scene_rows_moved)
        # Scene properties
        self.editSceneName.editingFinished.connect(self._on_scene_name_edited)
        self.btnSceneBgColor.clicked.connect(self._on_scene_bg_color_clicked)
        # Render settings
        self.comboRenderQuality.setCurrentIndex(2)  # Default 1080p 60fps
        self.comboRenderQuality.currentTextChanged.connect(self._on_quality_changed)
        self.btnBrowseOutput.clicked.connect(self._on_browse_output)
        # Select the first scene by default
        self.scenesList.setCurrentRow(0)

    def _on_add_scene(self):
        """Add a new scene, duplicating current scene's objects with Add animations."""
        old_state = self.scene_state
        old_objects = old_state.all_objects()

        self._scene_counter += 1
        name = f"Scene{self._scene_counter}"
        old_bg = self._scenes[self._current_scene_idx].get("bg_color", "#000000")
        # Hide current scene items
        self._hide_scene_items(self._current_scene_idx)
        self._add_scene_entry(name, bg_color=old_bg)
        new_idx = len(self._scenes) - 1
        new_state = self._scenes[new_idx]["state"]

        # Copy name counters so next_name won't collide with cloned names
        new_state._name_counters = dict(old_state._name_counters)

        # Clone each object from the previous scene
        for obj_name, tracked in old_objects:
            old_item = old_state.get_item(obj_name)
            if not old_item:
                continue
            pos = old_item.pos()
            new_item = MathTexItem(
                latex=tracked.latex, color=tracked.color,
                font_size=tracked.font_size,
            )
            self.canvas_scene.addItem(new_item)
            new_item.setPos(pos)
            new_tracked = TrackedObject(
                name=tracked.name, obj_type=tracked.obj_type,
                latex=tracked.latex, color=tracked.color,
                font_size=tracked.font_size,
            )
            new_state.register(obj_name, new_tracked, new_item)
            new_state.add_animation(AnimationEntry(
                target_name=obj_name, anim_type="Add",
                duration=0.0, easing="",
            ))

        self.scenesList.setCurrentRow(new_idx)

    def _on_delete_scene(self):
        """Delete the currently selected scene."""
        if len(self._scenes) <= 1:
            self.statusBar.showMessage("Cannot delete the only scene", 3000)
            return
        idx = self.scenesList.currentRow()
        if idx < 0:
            return
        # Remove canvas items for this scene
        state = self._scenes[idx]["state"]
        for name, _ in state.all_objects():
            obj_item = state.get_item(name)
            if obj_item:
                self.canvas_scene.removeItem(obj_item)
        self._scenes.pop(idx)
        self.scenesList.takeItem(idx)
        # Select adjacent scene
        new_idx = min(idx, len(self._scenes) - 1)
        self.scenesList.setCurrentRow(new_idx)

    def _on_scene_selected(self, row: int):
        """Switch to the selected scene."""
        if row < 0 or row >= len(self._scenes):
            return
        # Hide old scene items
        if self._current_scene_idx != row:
            self._hide_scene_items(self._current_scene_idx)
        self._current_scene_idx = row
        # Show new scene items
        self._show_scene_items(row)
        self._refresh_animations_list()
        self._refresh_code_editors()
        # Apply this scene's background color
        bg = self._scenes[row].get("bg_color", "#000000")
        self.canvas_scene.setBackgroundBrush(QBrush(QColor(bg)))
        # Show scene properties
        self._show_scene_properties(row)
        self.canvas_scene.clearSelection()

    def _on_scene_clicked(self, item):
        """Show scene properties when clicking an already-selected scene."""
        row = self.scenesList.row(item)
        if row >= 0:
            self._show_scene_properties(row)

    def _hide_scene_items(self, idx: int):
        """Hide all canvas items for the given scene index."""
        if 0 <= idx < len(self._scenes):
            state = self._scenes[idx]["state"]
            for name, _ in state.all_objects():
                item = state.get_item(name)
                if item:
                    item.setVisible(False)

    def _show_scene_items(self, idx: int):
        """Show all canvas items for the given scene index."""
        if 0 <= idx < len(self._scenes):
            state = self._scenes[idx]["state"]
            for name, _ in state.all_objects():
                item = state.get_item(name)
                if item:
                    item.setVisible(True)

    def _on_scene_renamed(self, item):
        """Update scene name when the user edits it in the list."""
        if self._updating_scenes:
            return
        row = self.scenesList.row(item)
        if 0 <= row < len(self._scenes):
            self._scenes[row]["name"] = item.text()
            self._refresh_code_editors()

    def _on_scene_rows_moved(self, _src, start, _end, _dst, dest_row):
        """Sync drag-drop reorder of scenes."""
        old_idx = start
        new_idx = dest_row if dest_row < start else dest_row - 1
        scene = self._scenes.pop(old_idx)
        self._scenes.insert(new_idx, scene)
        # Update current index if it was the moved scene
        if self._current_scene_idx == old_idx:
            self._current_scene_idx = new_idx
        elif old_idx < self._current_scene_idx <= new_idx:
            self._current_scene_idx -= 1
        elif new_idx <= self._current_scene_idx < old_idx:
            self._current_scene_idx += 1
        self._refresh_code_editors()

    # --- Scene properties ---

    def _show_scene_properties(self, row: int):
        """Show the scene properties page for the given scene index."""
        if row < 0 or row >= len(self._scenes):
            return
        scene = self._scenes[row]
        self._updating_scenes = True
        self.propertiesStack.setCurrentIndex(4)  # propsScenePage
        self.editSceneName.setText(scene["name"])
        bg = scene.get("bg_color", "#000000")
        self.btnSceneBgColor.setText(bg)
        self.btnSceneBgColor.setStyleSheet(f"background-color: {bg};")
        self._updating_scenes = False

    def _on_scene_name_edited(self):
        """Update scene name from the properties panel."""
        if self._updating_scenes:
            return
        idx = self._current_scene_idx
        new_name = self.editSceneName.text().strip()
        if not new_name or new_name == self._scenes[idx]["name"]:
            return
        self._scenes[idx]["name"] = new_name
        self._updating_scenes = True
        self.scenesList.item(idx).setText(new_name)
        self._updating_scenes = False
        self._refresh_code_editors()

    def _on_scene_bg_color_clicked(self):
        """Pick a background color for the current scene."""
        from PyQt6.QtWidgets import QColorDialog
        idx = self._current_scene_idx
        current = self._scenes[idx].get("bg_color", "#000000")
        color = QColorDialog.getColor(QColor(current), self, "Scene Background Color")
        if color.isValid():
            hex_color = color.name()
            self._scenes[idx]["bg_color"] = hex_color
            self.btnSceneBgColor.setText(hex_color)
            self.btnSceneBgColor.setStyleSheet(f"background-color: {hex_color};")
            self.canvas_scene.setBackgroundBrush(QBrush(QColor(hex_color)))

    # --- Render settings ---

    def _on_quality_changed(self, text: str):
        """Sync FPS spinbox when quality preset changes."""
        preset = _QUALITY_PRESETS.get(text)
        if preset:
            self.spinRenderFps.setValue(preset[2])

    def _on_browse_output(self):
        """Browse for a custom output directory."""
        from PyQt6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if path:
            self.editOutputDir.setText(path)

    def _fix_widget_enums(self):
        """Set widget properties that use scoped enums (avoids uic XML warnings)."""
        self.canvasView.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.canvasView.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.scenesList.setViewMode(QListView.ViewMode.ListMode)
        self.scenesList.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.animationsList.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def _setup_toolbar_tabs(self):
        """Wire the toolbar selector QTabBar to the toolbar QStackedWidget."""
        self.toolbarSelector.addTab("Design")
        self.toolbarSelector.addTab("Animation")
        self.toolbarSelector.currentChanged.connect(self.toolbarStack.setCurrentIndex)
        self.toolbarSelector.setCurrentIndex(1)  # Animation tab by default

    def _setup_center_tabs(self):
        """Wire the center tab bar to switch between Canvas, Code, and Output views."""
        self.centerTabBar.addTab("Canvas")
        self.centerTabBar.addTab("Code GL")
        self.centerTabBar.addTab("Code CE")
        self.centerTabBar.addTab("Console")
        self.centerTabBar.currentChanged.connect(self.centerStack.setCurrentIndex)

    def _setup_tool_button_group(self):
        """Make design tool buttons mutually exclusive."""
        self.toolGroup = QButtonGroup(self)
        self.toolGroup.setExclusive(True)
        for btn in (
            self.toolSelect,
            self.toolMathTex,
            self.toolText,
            self.toolCircle,
            self.toolRectangle,
            self.toolArrow,
            self.toolLine,
        ):
            self.toolGroup.addButton(btn)

    def _setup_default_proportions(self):
        """Set the default splitter sizes to match the intended layout."""
        self.leftPanelSplitter.setMaximumWidth(350)
        # ~10% left, ~80% center canvas, ~10% right properties
        self.mainSplitter.setSizes([190, 1660, 190])
        self.mainSplitter.setStretchFactor(0, 0)  # left: fixed
        self.mainSplitter.setStretchFactor(1, 1)  # center: stretches
        self.mainSplitter.setStretchFactor(2, 0)  # right: fixed

    def _setup_window_geometry(self):
        """Size and position the window on screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        w, h = 1720, 1130
        self.resize(w, h)
        # Top-left, clamped to available screen area
        self.move(screen.x(), screen.y())

    def _setup_canvas(self):
        """Initialize the QGraphicsScene with black background and a default MathTex."""
        self.canvas_scene = QGraphicsScene(self)
        self.canvas_scene.setSceneRect(-700, -400, 1400, 800)
        self.canvas_scene.setBackgroundBrush(QBrush(QColor("#000000")))
        self.canvasView.setScene(self.canvas_scene)

        # White border showing the renderable scene boundary
        border_pen = QPen(QColor("#FFFFFF"))
        border_pen.setWidthF(2)
        border_pen.setCosmetic(True)  # always 2px regardless of zoom
        self.canvas_scene.addRect(-700, -400, 1400, 800, border_pen)

        # Place default F=ma at the center
        self.statusBar.showMessage("Rendering LaTeX…")
        QApplication.processEvents()
        default_item = MathTexItem(latex="F=ma", color="#FFFFFF")
        self.canvas_scene.addItem(default_item)
        default_item.setPos(0, 0)

        if MathTexItem._latex_available:
            self.statusBar.showMessage("LaTeX rendered successfully", 3000)
        else:
            self.statusBar.showMessage(
                "LaTeX not found — using text fallback (install MiKTeX/TeX Live for full rendering)",
                5000,
            )

        # Listen for tool-click placement on the canvas
        self.canvasView.viewport().installEventFilter(self)
        # Listen for resize to maintain 16:9 aspect ratio via fitInView
        self.canvasView.installEventFilter(self)
        return default_item

    def closeEvent(self, event):
        """Kill subprocesses when the main window closes."""
        self._kill_preview()
        if self._render_proc and self._render_proc.state() != QProcess.ProcessState.NotRunning:
            self._render_proc.kill()
        super().closeEvent(event)

    def showEvent(self, event):
        """Fit the canvas on first show (geometry isn't final until then)."""
        super().showEvent(event)
        self.canvasView.fitInView(
            self.canvas_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
        )

    def eventFilter(self, obj, event):
        """Handle resize → fitInView and mouse clicks for placing objects."""
        if obj is self.canvasView and event.type() == QEvent.Type.Resize:
            self.canvasView.fitInView(
                self.canvas_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
            )
            return False
        if obj is self.canvasView.viewport():
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                active = self.toolGroup.checkedButton()
                if active is self.toolMathTex:
                    pos = self.canvasView.mapToScene(event.pos())
                    name = self.scene_state.next_name("eq")
                    item = MathTexItem(latex="F=ma", color="#FFFFFF")
                    self.canvas_scene.addItem(item)
                    item.setPos(pos.x(), pos.y())
                    tracked = TrackedObject(
                        name=name, obj_type="mathtex",
                        latex="F=ma", color="#FFFFFF",
                    )
                    self.scene_state.register(name, tracked, item)
                    # Auto-add Write animation for the new object
                    entry = AnimationEntry(
                        target_name=name, anim_type="Write",
                        duration=1.0, easing="smooth",
                    )
                    self.scene_state.add_animation(entry)
                    self._refresh_animations_list()
                    self._refresh_code_editors()
                    self.toolSelect.setChecked(True)
                    return True
        return super().eventFilter(obj, event)

    # --- MVP: registration, animations, codegen, delete ---

    def _register_default_item(self, item):
        """Register the default F=ma item created in _setup_canvas."""
        name = self.scene_state.next_name("eq")
        tracked = TrackedObject(
            name=name, obj_type="mathtex", latex="F=ma", color="#FFFFFF"
        )
        self.scene_state.register(name, tracked, item)
        # Auto-add Write animation for the default object
        entry = AnimationEntry(
            target_name=name, anim_type="Write",
            duration=1.0, easing="smooth",
        )
        self.scene_state.add_animation(entry)

    def _setup_animations_panel(self):
        """Wire the animation list buttons and drag-drop reorder sync."""
        self.btnDeleteAnim.clicked.connect(self._delete_animation)
        self.btnMoveAnimUp.clicked.connect(lambda: self._move_animation(-1))
        self.btnMoveAnimDown.clicked.connect(lambda: self._move_animation(1))
        self.btnAddAnimation.clicked.connect(self._add_animation)
        self.animationsList.itemClicked.connect(self._on_animation_clicked)
        # Sync drag-drop reorder back to SceneState
        self.animationsList.model().rowsMoved.connect(self._on_anim_rows_moved)

    def _add_animation(self):
        """Add an animation for the currently selected canvas object."""
        selected = self.canvas_scene.selectedItems()
        if not selected:
            self.statusBar.showMessage("Select an object first", 3000)
            return
        name = self.scene_state.find_name_for_item(selected[0])
        if not name:
            return
        entry = AnimationEntry(
            target_name=name,
            anim_type=self.comboAnimationType.currentText(),
            duration=self.spinDuration.value(),
            easing="smooth",
        )
        self.scene_state.add_animation(entry)
        self._refresh_animations_list()
        self._refresh_code_editors()

    def _on_animation_clicked(self, item):
        """Show animation properties when clicking an already-selected animation."""
        row = self.animationsList.row(item)
        if row >= 0:
            self.props_controller._current_anim_index = row
            self.props_controller._current_name = None
            self.props_controller._show_anim_properties(row)

    def _delete_animation(self):
        row = self.animationsList.currentRow()
        if row >= 0:
            self.scene_state.remove_animation(row)
            self._refresh_animations_list()
            self._refresh_code_editors()

    def _move_animation(self, delta: int):
        row = self.animationsList.currentRow()
        if row >= 0:
            self.scene_state.move_animation(row, delta)
            self._refresh_animations_list()
            self._refresh_code_editors()
            new_row = row + delta
            if 0 <= new_row < self.animationsList.count():
                self.animationsList.setCurrentRow(new_row)

    def _on_anim_rows_moved(self, _src_parent, start, _end, _dst_parent, dest_row):
        """Sync drag-drop reorder in the list widget back to SceneState."""
        # Qt rowsMoved: item at `start`..`end` moves to before `dest_row`.
        # For a single-item drag (start == end), the new index is:
        #   dest_row       if dest_row < start  (moved up)
        #   dest_row - 1   if dest_row > end    (moved down)
        old_idx = start
        new_idx = dest_row if dest_row < start else dest_row - 1
        self.scene_state.move_animation_to(old_idx, new_idx)
        # Renumber all list labels to match the new order
        for i, anim in enumerate(self.scene_state.all_animations()):
            item = self.animationsList.item(i)
            if item:
                item.setText(f"{i + 1}. {anim.anim_type}({anim.target_name}) — {anim.duration:.1f}s")
        # Keep the controller's selection index in sync
        ctrl = self.props_controller
        if ctrl._current_anim_index == old_idx:
            ctrl._current_anim_index = new_idx
        self._refresh_code_editors()

    def _refresh_animations_list(self):
        """Rebuild the animationsList widget from scene state."""
        self.animationsList.clear()
        for i, anim in enumerate(self.scene_state.all_animations()):
            if anim.anim_type == "Add":
                label = f"{i + 1}. Add({anim.target_name})"
            elif anim.anim_type == "Wait":
                label = f"{i + 1}. Wait — {anim.duration:.1f}s"
            else:
                label = f"{i + 1}. {anim.anim_type}({anim.target_name}) — {anim.duration:.1f}s"
            self.animationsList.addItem(label)

    def _setup_code_generation(self):
        """Regenerate code when switching to a Code tab."""
        self._code_gl_manual = False
        self._code_ce_manual = False
        self._updating_code = False
        self._code_sync_timer = QTimer(self)
        self._code_sync_timer.setSingleShot(True)
        self._code_sync_timer.timeout.connect(self._apply_code_to_canvas)
        self.codeEditor.textChanged.connect(self._on_code_gl_edited)
        self.codeEditorCE.textChanged.connect(self._on_code_ce_edited)
        self.centerTabBar.currentChanged.connect(self._on_center_tab_changed)

    def _on_code_gl_edited(self):
        if not self._updating_code:
            self._code_gl_manual = True
            self._code_sync_timer.start(800)

    def _on_code_ce_edited(self):
        if not self._updating_code:
            self._code_ce_manual = True
            self._code_sync_timer.start(800)

    def _setup_delete_action(self):
        """Wire the Delete action (Del key) to remove selected items."""
        self.actionDelete.triggered.connect(self._delete_selected)

    def _setup_copy_paste(self):
        self.actionCopy.triggered.connect(self._copy_selected)
        self.actionPaste.triggered.connect(self._paste_clipboard)
        self.actionSelectAll.triggered.connect(self._select_all)

    def _copy_selected(self):
        focused = QApplication.focusWidget()
        if isinstance(focused, QPlainTextEdit):
            focused.copy()
            return
        selected = self.canvas_scene.selectedItems()
        if len(selected) != 1:
            return
        name = self.scene_state.find_name_for_item(selected[0])
        if not name:
            return
        tracked = self.scene_state.get_tracked(name)
        if not tracked or tracked.obj_type != "mathtex":
            return
        pos = selected[0].pos()
        self._clipboard = {
            "latex": tracked.latex,
            "color": tracked.color,
            "font_size": tracked.font_size,
            "pos_x": pos.x(),
            "pos_y": pos.y(),
        }
        self.statusBar.showMessage("Copied", 2000)

    def _paste_clipboard(self):
        focused = QApplication.focusWidget()
        if isinstance(focused, QPlainTextEdit):
            focused.paste()
            return
        if not self._clipboard:
            return
        cb = self._clipboard

        # Paste at cursor if it's inside the scene rect, otherwise offset from original
        cursor_scene = self.canvasView.mapToScene(
            self.canvasView.mapFromGlobal(QCursor.pos())
        )
        if self.canvas_scene.sceneRect().contains(cursor_scene):
            paste_pos = cursor_scene
        else:
            paste_pos = QPointF(cb["pos_x"] + 30, cb["pos_y"] - 30)

        name = self.scene_state.next_name("eq")
        item = MathTexItem(latex=cb["latex"], color=cb["color"], font_size=cb["font_size"])
        self.canvas_scene.addItem(item)
        item.setPos(paste_pos)
        tracked = TrackedObject(
            name=name, obj_type="mathtex",
            latex=cb["latex"], color=cb["color"], font_size=cb["font_size"],
        )
        self.scene_state.register(name, tracked, item)
        self.canvas_scene.clearSelection()
        item.setSelected(True)
        self.statusBar.showMessage(f"Pasted as {name}", 2000)

    def _delete_selected(self):
        focused = QApplication.focusWidget()
        if focused is self.scenesList:
            self._on_delete_scene()
            return
        if focused is self.animationsList:
            self._delete_animation()
            return
        for item in self.canvas_scene.selectedItems():
            name = self.scene_state.find_name_for_item(item)
            if name:
                self.scene_state.unregister(name)
            self.canvas_scene.removeItem(item)
        self._refresh_animations_list()

    def _select_all(self):
        """Select all canvas objects in the current scene, or all text in a focused editor."""
        focused = QApplication.focusWidget()
        if isinstance(focused, QPlainTextEdit):
            focused.selectAll()
            return
        self.canvas_scene.clearSelection()
        for name, _ in self.scene_state.all_objects():
            item = self.scene_state.get_item(name)
            if item:
                item.setSelected(True)

    def _setup_preview(self):
        """Wire Preview button, Render buttons, Dock toggle, and Export to .py."""
        self._dock_hwnd = None
        self._render_proc = None
        self.btnPreviewScene.clicked.connect(self._preview_scene)
        self.btnRenderScene.clicked.connect(self._render_current_scene)
        self.btnRenderAll.clicked.connect(self._render_all_scenes)
        self.btnDockPreview.toggled.connect(self._on_dock_toggled)
        self.actionExportPy.triggered.connect(self._export_py)

    def _preview_alive(self) -> bool:
        proc = getattr(self, "_preview_proc", None)
        return proc is not None and proc.state() != QProcess.ProcessState.NotRunning

    def _kill_preview(self):
        """Kill the preview process immediately (no blocking wait)."""
        if self._preview_alive():
            self._preview_proc.kill()
        self._preview_proc = None
        self._dock_hwnd = None
        self.btnDockPreview.setChecked(False)

    def _on_dock_toggled(self, checked: bool):
        """Toggle docking the preview window to the main window."""
        if not checked:
            self._dock_hwnd = None
            return

        if not self._preview_alive():
            self.statusBar.showMessage("No preview running", 3000)
            self.btnDockPreview.setChecked(False)
            return

        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, self._current_scene_name())
        if not hwnd:
            self.statusBar.showMessage("Preview window not found", 3000)
            self.btnDockPreview.setChecked(False)
            return

        self._dock_hwnd = hwnd
        self._sync_dock_position()
        self.statusBar.showMessage("Preview docked", 2000)

    def _sync_dock_position(self):
        """Move the docked preview window to the right of the main window."""
        if not self._dock_hwnd:
            return
        import ctypes
        frame = self.frameGeometry()
        ctypes.windll.user32.MoveWindow(
            self._dock_hwnd,
            frame.right() + 1, frame.top(),
            frame.width(), frame.height(),
            True,
        )

    def moveEvent(self, event):
        super().moveEvent(event)
        self._sync_dock_position()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_dock_position()

    def _preview_scene(self):
        """Launch or hot-reload the manimgl preview."""
        if self._preview_alive():
            self._replay_preview()
            self._focus_preview()
        else:
            self._launch_preview()

    def _focus_preview(self):
        """Bring the ManimGL preview window to the foreground."""
        import ctypes
        hwnd = self._dock_hwnd
        if not hwnd:
            hwnd = ctypes.windll.user32.FindWindowW(None, self._current_scene_name())
        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)

    def _launch_preview(self):
        """First launch: spawn manimgl with hot-reload support."""
        tmp_dir = tempfile.gettempdir()
        tmp = os.path.join(tmp_dir, "manim_composer_preview.py")
        launcher = os.path.join(tmp_dir, "manim_composer_launcher.py")
        replay_file = os.path.join(tmp_dir, "manim_composer_replay.py")

        # Remove stale replay file so the watcher doesn't fire immediately
        try:
            os.remove(replay_file)
        except FileNotFoundError:
            pass

        scene_name = self._current_scene_name()
        if self._code_gl_manual:
            # User has manually edited GL code — use it as-is
            code = self.codeEditor.toPlainText()
        else:
            bg_color = self._scenes[self._current_scene_idx].get("bg_color", "#000000")
            code = generate_manimgl_code(
                self.scene_state, scene_name=scene_name,
                interactive=True,
                replay_file=replay_file.replace("\\", "/"),
                bg_color=bg_color,
            )

        with open(tmp, "w", encoding="utf-8") as f:
            f.write(code)

        # Position preview window to the right of the Composer
        frame = self.frameGeometry()
        with open(launcher, "w", encoding="utf-8") as f:
            f.write(_LAUNCHER_TEMPLATE.format(
                scene_file=tmp.replace("\\", "/"),
                scene_name=scene_name,
                win_x=frame.right() + 1,
                win_y=frame.top(),
            ))

        self.statusBar.showMessage("Launching manimgl preview…")
        self.consolePane.clear()

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        # Always use TinyTeX env so it shadows system LaTeX
        qenv = QProcessEnvironment()
        for k, v in latex_manager.get_latex_env().items():
            qenv.insert(k, v)
        proc.setProcessEnvironment(qenv)
        proc.readyReadStandardOutput.connect(self._read_preview_output)
        proc.finished.connect(self._on_preview_finished)
        proc.errorOccurred.connect(self._on_preview_error)
        proc.start(sys.executable, [launcher])
        self._preview_proc = proc

        # Auto-dock after the GL window appears
        self._autodock_attempts = 0
        self._autodock_timer = QTimer(self)
        self._autodock_timer.timeout.connect(self._try_autodock)
        self._autodock_timer.start(500)

    def _try_autodock(self):
        """Poll for the ManimGL window and auto-dock it once found."""
        self._autodock_attempts += 1
        if self._autodock_attempts > 20:  # Give up after 10 seconds
            self._autodock_timer.stop()
            return
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, self._current_scene_name())
        if hwnd:
            self._autodock_timer.stop()
            self.btnDockPreview.setChecked(True)

    def _replay_preview(self):
        """Hot-reload: write replay file, the running preview picks it up."""
        replay = generate_replay_code(self.scene_state)
        tmp_dir = tempfile.gettempdir()
        replay_file = os.path.join(tmp_dir, "manim_composer_replay.py")

        with open(replay_file, "w", encoding="utf-8") as f:
            f.write(replay)

        self.statusBar.showMessage("Preview updated", 3000)

    # --- Rendering (Manim CE) ---

    def _get_ce_code_and_names(self, all_scenes: bool = False) -> tuple[str, list[str]]:
        """Get CE code and scene names, using manual edits if present."""
        if self._code_ce_manual:
            # User has manually edited CE code — use it as-is
            code = self.codeEditorCE.toPlainText()
            if all_scenes:
                names = [s["name"] for s in self._scenes]
            else:
                names = [self._current_scene_name()]
            return code, names
        # Auto-generate fresh
        if all_scenes:
            code = self._generate_all_ce_code()
            names = [s["name"] for s in self._scenes]
        else:
            scene_name = self._current_scene_name()
            bg_color = self._scenes[self._current_scene_idx].get("bg_color", "#000000")
            code = generate_manimce_code(
                self.scene_state, scene_name=scene_name, include_import=True,
                bg_color=bg_color,
            )
            names = [scene_name]
        return code, names

    def _render_current_scene(self):
        """Render the current scene to video using Manim CE."""
        if self._render_proc is not None and self._render_proc.state() != QProcess.ProcessState.NotRunning:
            self.statusBar.showMessage("A render is already in progress", 3000)
            return
        code, names = self._get_ce_code_and_names(all_scenes=False)
        self._start_render(code, names)

    def _render_all_scenes(self):
        """Render all scenes to video using Manim CE."""
        if self._render_proc is not None and self._render_proc.state() != QProcess.ProcessState.NotRunning:
            self.statusBar.showMessage("A render is already in progress", 3000)
            return
        code, names = self._get_ce_code_and_names(all_scenes=True)
        self._start_render(code, names)

    # On Windows, dvisvgm (TeX Live build) crashes when called via
    # Python's subprocess (CreateProcessW).  Replace Manim CE's
    # convert_to_svg with pymupdf so no dvisvgm binary is needed.
    _SVG_PATCH = (
        "import sys as _sys\n"
        "if _sys.platform == 'win32':\n"
        "    import subprocess as _sp, pymupdf as _mu\n"
        "    import manim.utils.tex_file_writing as _tfw\n"
        "    def _convert_to_svg(dvi_file, extension, page=1):\n"
        "        result = dvi_file.with_suffix('.svg')\n"
        "        if result.exists():\n"
        "            return result\n"
        "        src = dvi_file\n"
        "        if extension == '.dvi':\n"
        "            pdf = dvi_file.with_suffix('.pdf')\n"
        "            _sp.run(['dvipdfmx', '-o', str(pdf), str(dvi_file)],\n"
        "                    capture_output=True)\n"
        "            src = pdf\n"
        "        doc = _mu.open(str(src))\n"
        "        result.write_text(doc[page - 1].get_svg_image())\n"
        "        doc.close()\n"
        "        if not result.exists():\n"
        "            raise ValueError(f'SVG conversion failed for {dvi_file}')\n"
        "        return result\n"
        "    _tfw.convert_to_svg = _convert_to_svg\n"
    )

    def _start_render(self, code: str, scene_names: list[str]):
        """Write CE code to temp file and launch manim render."""
        tmp_dir = tempfile.gettempdir()
        render_file = os.path.join(tmp_dir, "manim_composer_render.py")
        with open(render_file, "w", encoding="utf-8") as f:
            f.write(self._SVG_PATCH)
            f.write(code)

        # Read render settings from UI widgets
        quality = self.comboRenderQuality.currentText()
        w, h, _preset_fps = _QUALITY_PRESETS.get(quality, (1920, 1080, 60))
        fps = self.spinRenderFps.value()
        fmt = self.comboRenderFormat.currentText()
        output_dir = self.editOutputDir.text().strip()

        # Always use a known media_dir so we can find the output
        media_dir = output_dir or os.path.join(tmp_dir, "manim_composer_media")
        args = [
            "render",
            "--renderer", "cairo",
            "--resolution", f"{w},{h}",
            "--frame_rate", str(fps),
            "--format", fmt,
            "--media_dir", media_dir,
        ]
        args.append(render_file)
        args.extend(scene_names)

        # Store render info for open-on-completion
        self._render_scene_names = scene_names
        self._render_media_dir = media_dir
        self._render_format = fmt

        label = ", ".join(scene_names)
        self.statusBar.showMessage(f"Rendering {label}...")
        self.consolePane.clear()
        self.centerTabBar.setCurrentIndex(3)  # Switch to Console tab

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        # Always use TinyTeX env so it shadows system LaTeX
        qenv = QProcessEnvironment()
        for k, v in latex_manager.get_latex_env().items():
            qenv.insert(k, v)
        proc.setProcessEnvironment(qenv)
        proc.readyReadStandardOutput.connect(self._read_render_output)
        proc.finished.connect(self._on_render_finished)
        proc.errorOccurred.connect(self._on_render_error)
        proc.start(sys.executable, ["-m", "manim"] + args)
        self._render_proc = proc

    def _read_render_output(self):
        """Append render output to the Console pane."""
        data = self._render_proc.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        cursor = self.consolePane.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.consolePane.setTextCursor(cursor)
        self.consolePane.ensureCursorVisible()

    def _on_render_finished(self, exit_code, _exit_status):
        """Handle render process completion."""
        cursor = self.consolePane.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if exit_code != 0:
            self.statusBar.showMessage(f"Render failed (exit {exit_code})", 5000)
            cursor.insertText(f"\n--- Render FAILED (exit code {exit_code}) ---\n")
        else:
            self.statusBar.showMessage("Render complete!", 5000)
            cursor.insertText("\n--- Render complete! ---\n")
            # Try to open the rendered file(s) if checkbox is checked
            if self.checkOpenOnComplete.isChecked():
                self._open_rendered_files()
        self.consolePane.setTextCursor(cursor)
        self.consolePane.ensureCursorVisible()

    def _open_rendered_files(self):
        """Open rendered video files in the default OS application."""
        media_dir = getattr(self, "_render_media_dir", "")
        fmt = getattr(self, "_render_format", "mp4")
        scene_names = getattr(self, "_render_scene_names", [])
        if not media_dir or not scene_names:
            return
        # Manim CE puts videos in media/videos/<filename>/<quality>/SceneName.ext
        # Find the newest matching file for the last rendered scene
        target_name = scene_names[-1]
        ext = fmt if fmt != "png" else "png"
        best_path = None
        best_mtime = 0
        for root, _dirs, files in os.walk(media_dir):
            for f in files:
                if f == f"{target_name}.{ext}":
                    path = os.path.join(root, f)
                    mtime = os.path.getmtime(path)
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best_path = path
        if best_path:
            os.startfile(best_path)

    def _on_render_error(self, error):
        """Handle render process startup errors."""
        if error == QProcess.ProcessError.FailedToStart:
            self.statusBar.showMessage(
                "Failed to start render — check Manim CE installation (pip install manim)", 5000
            )

    def _read_preview_output(self):
        """Append new output from the preview process to the Console pane."""
        data = self._preview_proc.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        cursor = self.consolePane.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.consolePane.setTextCursor(cursor)
        self.consolePane.ensureCursorVisible()

    def _on_preview_finished(self, exit_code, _exit_status):
        """Handle preview process exit."""
        self._dock_hwnd = None
        self.btnDockPreview.setChecked(False)
        if exit_code != 0:
            self.statusBar.showMessage(f"Preview failed (exit {exit_code})", 5000)
            self.centerTabBar.setCurrentIndex(3)  # switch to Console tab
        else:
            self.statusBar.showMessage("Preview finished", 3000)

    def _on_preview_error(self, error):
        """Handle preview process startup errors."""
        if error == QProcess.ProcessError.FailedToStart:
            self.statusBar.showMessage(
                "Failed to start preview — check Python/manimgl installation", 5000
            )

    def _export_py(self):
        """File → Export to .py"""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export ManimGL Script", "scene.py",
            "Python Files (*.py);;All Files (*)",
        )
        if path:
            if self._code_gl_manual:
                code = self.codeEditor.toPlainText()
            else:
                code = self._generate_all_gl_code()
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            self.statusBar.showMessage(f"Exported to {path}", 5000)

    def _setup_syntax_highlighting(self):
        """Apply Python syntax highlighting to code editors."""
        self._highlighter_code_editor = PythonHighlighter(self.codeEditor.document())
        self._highlighter_code_editor_ce = PythonHighlighter(self.codeEditorCE.document())

    def _on_center_tab_changed(self, index: int):
        """Regenerate code when switching to a Code tab."""
        if index in (1, 2):
            self._refresh_code_editors()

    def _generate_all_gl_code(self) -> str:
        """Generate ManimGL code for all scenes."""
        parts = []
        for i, scene in enumerate(self._scenes):
            code = generate_manimgl_code(
                scene["state"], scene_name=scene["name"],
                include_import=(i == 0),
                bg_color=scene.get("bg_color", "#000000"),
            )
            parts.append(code)
        return "\n".join(parts)

    def _generate_all_ce_code(self) -> str:
        """Generate Manim CE code for all scenes."""
        parts = []
        for i, scene in enumerate(self._scenes):
            code = generate_manimce_code(
                scene["state"], scene_name=scene["name"],
                include_import=(i == 0),
                bg_color=scene.get("bg_color", "#000000"),
            )
            parts.append(code)
        return "\n".join(parts)

    def _refresh_code_editors(self):
        """Update the visible code editor with all scenes (unless manually edited)."""
        self._updating_code = True
        index = self.centerTabBar.currentIndex()
        if index == 1 and not self._code_gl_manual:  # Code GL tab
            self.codeEditor.setPlainText(self._generate_all_gl_code())
        elif index == 2 and not self._code_ce_manual:  # Code CE tab
            self.codeEditorCE.setPlainText(self._generate_all_ce_code())
        self._updating_code = False

    # --- Code → Canvas sync ---

    def _apply_code_to_canvas(self):
        """Parse the active code editor and sync changes back to the canvas."""
        index = self.centerTabBar.currentIndex()
        if index == 1:
            code = self.codeEditor.toPlainText()
        elif index == 2:
            code = self.codeEditorCE.toPlainText()
        else:
            return

        scenes = parse_code(code)
        if not scenes:
            return  # Syntax errors or empty — do nothing

        # Find the parsed scene matching the current scene
        current_name = self._current_scene_name()
        parsed = None
        for i, s in enumerate(scenes):
            if s.name == current_name:
                parsed = s
                break
        # Fallback: use scene at the same index
        if parsed is None and self._current_scene_idx < len(scenes):
            parsed = scenes[self._current_scene_idx]
        if parsed is None:
            return

        self._updating_code = True
        state = self.scene_state
        parsed_names = {obj.name for obj in parsed.objects}
        current_names = set(state.object_names())

        # --- Update / add objects ---
        for pobj in parsed.objects:
            tracked = state.get_tracked(pobj.name)
            item = state.get_item(pobj.name)

            if tracked and item:
                # Update existing object
                if tracked.latex != pobj.latex:
                    tracked.latex = pobj.latex
                    item.set_latex(pobj.latex)
                if tracked.color.upper() != pobj.color.upper():
                    tracked.color = pobj.color
                    item.set_color(pobj.color)
                if tracked.font_size != pobj.font_size:
                    tracked.font_size = pobj.font_size
                    item.set_font_size(pobj.font_size)
                # Position (manim → scene coords)
                new_sx = pobj.pos_x * 100.0
                new_sy = -pobj.pos_y * 100.0
                pos = item.pos()
                if abs(pos.x() - new_sx) > 0.5 or abs(pos.y() - new_sy) > 0.5:
                    item.setPos(new_sx, new_sy)
            else:
                # New object from code
                new_item = MathTexItem(
                    latex=pobj.latex, color=pobj.color,
                    font_size=pobj.font_size,
                )
                self.canvas_scene.addItem(new_item)
                new_item.setPos(pobj.pos_x * 100.0, -pobj.pos_y * 100.0)
                new_tracked = TrackedObject(
                    name=pobj.name, obj_type="mathtex",
                    latex=pobj.latex, color=pobj.color,
                    font_size=pobj.font_size,
                )
                state.register(pobj.name, new_tracked, new_item)

        # --- Remove deleted objects ---
        for name in current_names - parsed_names:
            item = state.get_item(name)
            state.unregister(name)
            if item:
                self.canvas_scene.removeItem(item)

        # --- Sync animations ---
        state._animations.clear()
        for panim in parsed.animations:
            state.add_animation(AnimationEntry(
                target_name=panim.target_name,
                anim_type=panim.anim_type,
                duration=panim.duration,
                easing=panim.easing,
            ))

        # --- Sync scene metadata ---
        scene_data = self._scenes[self._current_scene_idx]
        if parsed.bg_color.upper() != scene_data.get("bg_color", "#000000").upper():
            scene_data["bg_color"] = parsed.bg_color
            self.canvas_scene.setBackgroundBrush(QBrush(QColor(parsed.bg_color)))
        if parsed.name != scene_data["name"]:
            scene_data["name"] = parsed.name
            self._updating_scenes = True
            self.scenesList.item(self._current_scene_idx).setText(parsed.name)
            self._updating_scenes = False

        # Refresh UI
        self._refresh_animations_list()
        # Update properties panel if an object is selected
        ctrl = self.props_controller
        if ctrl._current_name:
            tracked = state.get_tracked(ctrl._current_name)
            if tracked:
                ctrl._show_properties(ctrl._current_name)
            else:
                ctrl._current_name = None
                self.propertiesStack.setCurrentIndex(0)

        self._updating_code = False


def main():
    import signal
    app = QApplication(sys.argv)
    app.setApplicationName("Manim Composer")

    # Let Ctrl+C close the app gracefully
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    window = ManimComposerWindow()
    window.show()

    # Ensure TinyTeX is installed — it's the standard LaTeX for Manim Composer
    if not latex_manager.tinytex_ready():
        if latex_manager.offer_install(window):
            if latex_manager.run_install(window):
                MathTexItem._latex_available = None

    # Put TinyTeX at the front of PATH (shadows system LaTeX)
    latex_manager.ensure_path()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
