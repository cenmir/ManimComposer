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

    def _add_scene_entry(self, name: str) -> None:
        """Create a new scene and add it to the scenes list."""
        self._scenes.append({"name": name, "state": SceneState()})
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
        self.scenesList.itemChanged.connect(self._on_scene_renamed)
        self.scenesList.model().rowsMoved.connect(self._on_scene_rows_moved)
        # Select the first scene by default
        self.scenesList.setCurrentRow(0)

    def _on_add_scene(self):
        """Add a new scene, duplicating current scene's objects with Add animations."""
        old_state = self.scene_state
        old_objects = old_state.all_objects()

        self._scene_counter += 1
        name = f"Scene{self._scene_counter}"
        # Hide current scene items
        self._hide_scene_items(self._current_scene_idx)
        self._add_scene_entry(name)
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
        # Clear properties panel selection
        self.canvas_scene.clearSelection()

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

    def _setup_center_tabs(self):
        """Wire the center tab bar to switch between Canvas, Code, and Output views."""
        self.centerTabBar.addTab("Canvas")
        self.centerTabBar.addTab("Code GL")
        self.centerTabBar.addTab("Code CE")
        self.centerTabBar.addTab("Output")
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
        """Kill the preview subprocess when the main window closes."""
        self._kill_preview()
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
        self.centerTabBar.currentChanged.connect(self._on_center_tab_changed)

    def _setup_delete_action(self):
        """Wire the Delete action (Del key) to remove selected items."""
        self.actionDelete.triggered.connect(self._delete_selected)

    def _setup_copy_paste(self):
        self.actionCopy.triggered.connect(self._copy_selected)
        self.actionPaste.triggered.connect(self._paste_clipboard)
        self.actionSelectAll.triggered.connect(self._select_all)

    def _copy_selected(self):
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
        """Select all canvas objects in the current scene."""
        self.canvas_scene.clearSelection()
        for name, _ in self.scene_state.all_objects():
            item = self.scene_state.get_item(name)
            if item:
                item.setSelected(True)

    def _setup_preview(self):
        """Wire Preview button, Dock toggle, and Export to .py."""
        self._dock_hwnd = None
        self.btnPreviewScene.clicked.connect(self._preview_scene)
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
        code = generate_manimgl_code(
            self.scene_state, scene_name=scene_name,
            interactive=True,
            replay_file=replay_file.replace("\\", "/"),
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
        # Ensure TinyTeX binaries are on PATH for the preview subprocess
        latex_env = latex_manager.get_latex_env()
        if latex_env:
            qenv = QProcessEnvironment()
            for k, v in latex_env.items():
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
            self.centerTabBar.setCurrentIndex(4)  # switch to Console tab
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
            parts = []
            for i, scene in enumerate(self._scenes):
                parts.append(generate_manimgl_code(
                    scene["state"], scene_name=scene["name"],
                    include_import=(i == 0),
                ))
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(parts))
            self.statusBar.showMessage(f"Exported to {path}", 5000)

    def _setup_syntax_highlighting(self):
        """Apply Python syntax highlighting to code editors."""
        self._highlighter_code_editor = PythonHighlighter(self.codeEditor.document())
        self._highlighter_code_editor_ce = PythonHighlighter(self.codeEditorCE.document())

    def _on_center_tab_changed(self, index: int):
        """Regenerate code when switching to a Code tab."""
        if index in (1, 2):
            self._refresh_code_editors()

    def _refresh_code_editors(self):
        """Update the visible code editor with all scenes."""
        index = self.centerTabBar.currentIndex()
        if index == 1:  # Code GL tab
            parts = []
            for i, scene in enumerate(self._scenes):
                code = generate_manimgl_code(
                    scene["state"], scene_name=scene["name"],
                    include_import=(i == 0),
                )
                parts.append(code)
            self.codeEditor.setPlainText("\n".join(parts))
        elif index == 2:  # Code CE tab
            parts = []
            for i, scene in enumerate(self._scenes):
                code = generate_manimce_code(
                    scene["state"], scene_name=scene["name"],
                    include_import=(i == 0),
                )
                parts.append(code)
            self.codeEditorCE.setPlainText("\n".join(parts))


def main():
    import signal
    app = QApplication(sys.argv)
    app.setApplicationName("Manim Composer")

    # Let Ctrl+C close the app gracefully
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # Configure PATH for a local TinyTeX install (fast, no-op if system LaTeX)
    latex_manager.ensure_path()

    window = ManimComposerWindow()
    window.show()

    # Offer to install TinyTeX if no LaTeX distribution is found
    if latex_manager.detect() == latex_manager.NONE:
        if latex_manager.offer_install(window):
            if latex_manager.run_install(window):
                # Reset render cache so the canvas retries LaTeX
                MathTexItem._latex_available = None

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
