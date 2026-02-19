"""Manim Composer — Entry point."""

import sys
import os
import subprocess
import tempfile

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QButtonGroup, QGraphicsScene,
    QAbstractItemView, QGraphicsView, QListView,
)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtCore import Qt, QEvent
from PyQt6 import uic

from manim_composer.views.canvas_items.mathtex_item import MathTexItem
from manim_composer.models.scene_state import SceneState, TrackedObject, AnimationEntry
from manim_composer.controllers.properties_controller import PropertiesController
from manim_composer.codegen.generator import generate_manimgl_code, generate_replay_code

# Launcher script template for manimgl preview.
# Patches the -no-pdf issue on MiKTeX before running manimgl.
_LAUNCHER_TEMPLATE = r'''
import sys, re, subprocess, tempfile
from pathlib import Path

# Set argv BEFORE importing manimlib — config is parsed at import time
sys.argv = ["manimlib", "{scene_file}", "ComposedScene", "-c", "#000000"]

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
        self.scene_state = SceneState()
        self._register_default_item(default_item)
        self.props_controller = PropertiesController(self, self.scene_state)
        self._setup_animations_panel()
        self._setup_code_generation()
        self._setup_delete_action()
        self._setup_preview()

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
        self.centerTabBar.addTab("Code")
        self.centerTabBar.addTab("Output")
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

    def _setup_animations_panel(self):
        """Wire the animation list buttons."""
        self.btnAddAnim.clicked.connect(self._add_animation)
        self.btnDeleteAnim.clicked.connect(self._delete_animation)
        self.btnMoveAnimUp.clicked.connect(lambda: self._move_animation(-1))
        self.btnMoveAnimDown.clicked.connect(lambda: self._move_animation(1))
        self.btnAddAnimation.clicked.connect(self._add_animation)

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

    def _delete_animation(self):
        row = self.animationsList.currentRow()
        if row >= 0:
            self.scene_state.remove_animation(row)
            self._refresh_animations_list()

    def _move_animation(self, delta: int):
        row = self.animationsList.currentRow()
        if row >= 0:
            self.scene_state.move_animation(row, delta)
            self._refresh_animations_list()
            new_row = row + delta
            if 0 <= new_row < self.animationsList.count():
                self.animationsList.setCurrentRow(new_row)

    def _refresh_animations_list(self):
        """Rebuild the animationsList widget from scene state."""
        self.animationsList.clear()
        for i, anim in enumerate(self.scene_state.all_animations()):
            label = f"{i + 1}. {anim.anim_type}({anim.target_name}) — {anim.duration:.1f}s"
            self.animationsList.addItem(label)

    def _setup_code_generation(self):
        """Regenerate code when switching to the Code tab."""
        self.centerTabBar.currentChanged.connect(self._on_center_tab_changed)

    def _on_center_tab_changed(self, index: int):
        if index == 1:  # Code tab
            code = generate_manimgl_code(self.scene_state)
            self.codeEditor.setPlainText(code)

    def _setup_delete_action(self):
        """Wire the Delete action (Del key) to remove selected items."""
        self.actionDelete.triggered.connect(self._delete_selected)

    def _delete_selected(self):
        for item in self.canvas_scene.selectedItems():
            name = self.scene_state.find_name_for_item(item)
            if name:
                self.scene_state.unregister(name)
            self.canvas_scene.removeItem(item)
        self._refresh_animations_list()

    def _setup_preview(self):
        """Wire Preview button, Dock button, and Export to .py."""
        self.btnPreviewScene.clicked.connect(self._preview_scene)
        self.btnDockPreview.clicked.connect(self._dock_preview)
        self.actionExportPy.triggered.connect(self._export_py)

    def _preview_alive(self) -> bool:
        proc = getattr(self, "_preview_proc", None)
        return proc is not None and proc.poll() is None

    def _kill_preview(self):
        """Terminate any running preview process."""
        if self._preview_alive():
            self._preview_proc.terminate()
            self._preview_proc.wait(timeout=3)
        self._preview_proc = None

    def _dock_preview(self):
        """Reposition the ManimGL preview window to the right of the Composer."""
        if not self._preview_alive():
            self.statusBar.showMessage("No preview running", 3000)
            return
        if sys.platform != "win32":
            self.statusBar.showMessage("Dock is only supported on Windows", 3000)
            return

        import ctypes
        user32 = ctypes.windll.user32

        # Find the ManimGL window by its title ("ComposedScene")
        hwnd = user32.FindWindowW(None, "ComposedScene")
        if not hwnd:
            self.statusBar.showMessage("Preview window not found", 3000)
            return

        frame = self.frameGeometry()
        user32.MoveWindow(
            hwnd,
            frame.right() + 1, frame.top(),
            frame.width(), frame.height(),
            True,
        )
        self.statusBar.showMessage("Preview docked", 2000)

    def _preview_scene(self):
        """Launch or hot-reload the manimgl preview."""
        if self._preview_alive():
            self._replay_preview()
        else:
            self._launch_preview()

    def _launch_preview(self):
        """First launch: spawn manimgl with a new console + GL window."""
        tmp_dir = tempfile.gettempdir()
        tmp = os.path.join(tmp_dir, "manim_composer_preview.py")
        launcher = os.path.join(tmp_dir, "manim_composer_launcher.py")
        replay_file = os.path.join(tmp_dir, "manim_composer_replay.py")

        # Remove stale replay file so the watcher doesn't fire immediately
        try:
            os.remove(replay_file)
        except FileNotFoundError:
            pass

        code = generate_manimgl_code(
            self.scene_state, interactive=True,
            replay_file=replay_file.replace("\\", "/"),
        )

        with open(tmp, "w", encoding="utf-8") as f:
            f.write(code)

        # Position preview window to the right of the Composer
        frame = self.frameGeometry()
        with open(launcher, "w", encoding="utf-8") as f:
            f.write(_LAUNCHER_TEMPLATE.format(
                scene_file=tmp.replace("\\", "/"),
                win_x=frame.right() + 1,
                win_y=frame.top(),
            ))

        self.statusBar.showMessage("Launching manimgl preview…")

        try:
            kwargs: dict = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

            proc = subprocess.Popen(
                [sys.executable, launcher],
                **kwargs,
            )
            self._preview_proc = proc

            from PyQt6.QtCore import QTimer
            QTimer.singleShot(3000, self._check_preview_status)

        except FileNotFoundError:
            self.statusBar.showMessage(
                "manimgl not found — install with: pip install manimgl", 5000
            )

    def _replay_preview(self):
        """Hot-reload: write replay file, the running preview picks it up."""
        replay = generate_replay_code(self.scene_state)
        tmp_dir = tempfile.gettempdir()
        replay_file = os.path.join(tmp_dir, "manim_composer_replay.py")

        with open(replay_file, "w", encoding="utf-8") as f:
            f.write(replay)

        self.statusBar.showMessage("Preview updated", 3000)

    def _check_preview_status(self):
        """Check if the preview process exited early (error)."""
        proc = getattr(self, "_preview_proc", None)
        if proc is None:
            return
        rc = proc.poll()
        if rc is not None and rc != 0:
            self.statusBar.showMessage(f"Preview failed (exit {rc})", 5000)
            self.outputLog.setPlainText(
                f"--- Preview error (exit code {rc}) ---\n\n"
                "Check the console window for details."
            )
            self.centerTabBar.setCurrentIndex(2)  # switch to Output tab
        elif rc == 0:
            self.statusBar.showMessage("Preview finished", 3000)
        # else: still running — all good

    def _export_py(self):
        """File → Export to .py"""
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export ManimGL Script", "scene.py",
            "Python Files (*.py);;All Files (*)",
        )
        if path:
            code = generate_manimgl_code(self.scene_state)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            self.statusBar.showMessage(f"Exported to {path}", 5000)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Manim Composer")

    window = ManimComposerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
