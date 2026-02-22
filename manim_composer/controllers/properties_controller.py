"""Properties panel controller — wires right-panel widgets to SceneState."""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QColorDialog, QMainWindow
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QObject, QTimer

if TYPE_CHECKING:
    from manim_composer.models.scene_state import SceneState


class PropertiesController(QObject):
    """Wires the Properties panel widgets to the SceneState."""

    def __init__(self, window: QMainWindow, scene_state: SceneState):
        super().__init__(window)
        self.w = window
        self._current_name: str | None = None
        self._current_anim_index: int | None = None
        self._updating = False

        self._latex_timer = QTimer(self)
        self._latex_timer.setSingleShot(True)
        self._latex_timer.timeout.connect(self._apply_latex_change)

        self._connect_signals()

    @property
    def state(self):
        return self.w.scene_state

    def _connect_signals(self):
        self.w.canvas_scene.selectionChanged.connect(self._on_selection_changed)
        self.w.canvas_scene.changed.connect(self._on_scene_changed)

        # Object property widgets
        self.w.editObjName.editingFinished.connect(self._on_name_edited)
        self.w.editLatexCode.textChanged.connect(self._on_latex_edited)
        self.w.btnTextColor.clicked.connect(self._on_color_btn_clicked)
        self.w.spinFontSize.valueChanged.connect(self._on_font_size_changed)
        self.w.spinPosX.valueChanged.connect(self._on_position_changed)
        self.w.spinPosY.valueChanged.connect(self._on_position_changed)

        # Animation list selection
        self.w.animationsList.currentRowChanged.connect(self._on_animation_row_changed)

        # Animation property widgets
        self.w.comboAnimTarget.currentTextChanged.connect(self._on_anim_target_changed)
        self.w.comboAnimTypeProps.currentTextChanged.connect(self._on_anim_type_changed)
        self.w.spinAnimDuration.valueChanged.connect(self._on_anim_duration_changed)
        self.w.comboEasing.currentTextChanged.connect(self._on_anim_easing_changed)

    # --- Canvas selection ---

    def _on_selection_changed(self):
        try:
            selected = self.w.canvas_scene.selectedItems()
        except RuntimeError:
            return  # scene already deleted during shutdown
        if len(selected) == 1:
            name = self.state.find_name_for_item(selected[0])
            if name:
                self._current_anim_index = None
                self._show_properties(name)
                return
        self._current_name = None
        # If an animation is being edited, leave the anim panel visible
        if self._current_anim_index is not None:
            return
        self.w.propertiesStack.setCurrentIndex(0)

    def _show_properties(self, name: str):
        self._current_name = name
        tracked = self.state.get_tracked(name)
        item = self.state.get_item(name)
        if not tracked or not item:
            return

        self._updating = True
        self.w.propertiesStack.setCurrentIndex(1)  # propsTextPage
        self.w.editObjName.setText(name)
        self.w.editLatexCode.setPlainText(tracked.latex)
        self.w.btnTextColor.setText(tracked.color)
        self.w.btnTextColor.setStyleSheet(f"background-color: {tracked.color};")
        self.w.spinFontSize.setValue(tracked.font_size)

        pos = item.pos()
        self.w.spinPosX.setValue(pos.x() / 100.0)
        self.w.spinPosY.setValue(-pos.y() / 100.0)
        self._updating = False

    # --- Object property edits ---

    def _on_name_edited(self):
        if self._updating or not self._current_name:
            return
        new_name = self.w.editObjName.text().strip()
        if not new_name or new_name == self._current_name:
            return
        if new_name in self.state.object_names():
            self.w.editObjName.setText(self._current_name)
            return

        tracked = self.state.get_tracked(self._current_name)
        item = self.state.get_item(self._current_name)
        # Update animation references before unregister removes them
        for anim in self.state.all_animations():
            if anim.target_name == self._current_name:
                anim.target_name = new_name
        self.state.unregister(self._current_name)
        tracked.name = new_name
        self.state.register(new_name, tracked, item)
        self._current_name = new_name

    def _on_latex_edited(self):
        if self._updating or not self._current_name:
            return
        self._latex_timer.start(500)

    def _apply_latex_change(self):
        if not self._current_name:
            return
        tracked = self.state.get_tracked(self._current_name)
        item = self.state.get_item(self._current_name)
        if tracked and item:
            new_latex = self.w.editLatexCode.toPlainText()
            tracked.latex = new_latex
            item.set_latex(new_latex)

    def _on_color_btn_clicked(self):
        if not self._current_name:
            return
        tracked = self.state.get_tracked(self._current_name)
        item = self.state.get_item(self._current_name)
        if not tracked or not item:
            return
        color = QColorDialog.getColor(QColor(tracked.color), self.w, "Text Color")
        if color.isValid():
            hex_color = color.name()
            tracked.color = hex_color
            item.set_color(hex_color)
            self.w.btnTextColor.setText(hex_color)
            self.w.btnTextColor.setStyleSheet(f"background-color: {hex_color};")
            self.w._refresh_code_editors()

    def _on_font_size_changed(self, value: int):
        if self._updating or not self._current_name:
            return
        tracked = self.state.get_tracked(self._current_name)
        item = self.state.get_item(self._current_name)
        if tracked and item:
            tracked.font_size = value
            item.set_font_size(value)
            self.w._refresh_code_editors()

    def _on_position_changed(self):
        if self._updating or not self._current_name:
            return
        item = self.state.get_item(self._current_name)
        if item:
            x = self.w.spinPosX.value() * 100.0
            y = -self.w.spinPosY.value() * 100.0
            item.setPos(x, y)
            self.w._refresh_code_editors()

    # --- Drag sync ---

    def _on_scene_changed(self, _regions):
        if not self._current_name or self._updating:
            return
        try:
            item = self.state.get_item(self._current_name)
            if item:
                self._updating = True
                pos = item.pos()
                self.w.spinPosX.setValue(pos.x() / 100.0)
                self.w.spinPosY.setValue(-pos.y() / 100.0)
                self._updating = False
                self.w._refresh_code_editors()
        except RuntimeError:
            return

    # --- Animation selection ---

    def _on_animation_row_changed(self, row: int):
        if row < 0:
            self._current_anim_index = None
            # Fall back to showing the selected canvas object if any
            try:
                selected = self.w.canvas_scene.selectedItems()
            except RuntimeError:
                return
            if len(selected) == 1:
                name = self.state.find_name_for_item(selected[0])
                if name:
                    self._show_properties(name)
                    return
            if not self._current_name:
                self.w.propertiesStack.setCurrentIndex(0)
            return

        anims = self.state.all_animations()
        if row >= len(anims):
            return

        self._current_anim_index = row
        self._current_name = None  # canvas object props yield to animation props
        self._show_anim_properties(row)

    def _show_anim_properties(self, row: int):
        anims = self.state.all_animations()
        if row >= len(anims):
            return
        anim = anims[row]

        self._updating = True
        self.w.propertiesStack.setCurrentIndex(3)  # propsAnimPage

        # Repopulate target combo with current object names
        self.w.comboAnimTarget.clear()
        for name in self.state.object_names():
            self.w.comboAnimTarget.addItem(name)
        self.w.comboAnimTarget.setCurrentText(anim.target_name)

        self.w.comboAnimTypeProps.setCurrentText(anim.anim_type)
        self.w.spinAnimDuration.setValue(anim.duration)
        self.w.comboEasing.setCurrentText(anim.easing)

        # Hide irrelevant fields for Wait/Add
        is_wait = anim.anim_type == "Wait"
        is_add = anim.anim_type == "Add"
        self.w.comboEasing.setEnabled(not is_wait and not is_add)
        self.w.spinAnimDuration.setEnabled(not is_add)
        self.w.comboAnimTarget.setEnabled(not is_wait)
        self._updating = False

    # --- Animation property edits ---

    def _on_anim_target_changed(self, text: str):
        if self._updating or self._current_anim_index is None or not text:
            return
        anims = self.state.all_animations()
        if 0 <= self._current_anim_index < len(anims):
            anims[self._current_anim_index].target_name = text
            self._refresh_anim_list_item(self._current_anim_index)
            self.w._refresh_code_editors()

    def _on_anim_type_changed(self, text: str):
        if self._updating or self._current_anim_index is None or not text:
            return
        anims = self.state.all_animations()
        if 0 <= self._current_anim_index < len(anims):
            anims[self._current_anim_index].anim_type = text
            # Toggle field availability based on type
            is_wait = text == "Wait"
            is_add = text == "Add"
            self.w.comboEasing.setEnabled(not is_wait and not is_add)
            self.w.spinAnimDuration.setEnabled(not is_add)
            self.w.comboAnimTarget.setEnabled(not is_wait)
            self._refresh_anim_list_item(self._current_anim_index)
            self.w._refresh_code_editors()

    def _on_anim_duration_changed(self, value: float):
        if self._updating or self._current_anim_index is None:
            return
        anims = self.state.all_animations()
        if 0 <= self._current_anim_index < len(anims):
            anims[self._current_anim_index].duration = value
            self._refresh_anim_list_item(self._current_anim_index)
            self.w._refresh_code_editors()

    def _on_anim_easing_changed(self, text: str):
        if self._updating or self._current_anim_index is None or not text:
            return
        anims = self.state.all_animations()
        if 0 <= self._current_anim_index < len(anims):
            anims[self._current_anim_index].easing = text
            self.w._refresh_code_editors()

    def _refresh_anim_list_item(self, row: int):
        """Update a single animation list row's display text."""
        anims = self.state.all_animations()
        if 0 <= row < len(anims):
            anim = anims[row]
            list_item = self.w.animationsList.item(row)
            if list_item:
                if anim.anim_type == "Add":
                    text = f"{row + 1}. Add({anim.target_name})"
                elif anim.anim_type == "Wait":
                    text = f"{row + 1}. Wait — {anim.duration:.1f}s"
                else:
                    text = f"{row + 1}. {anim.anim_type}({anim.target_name}) — {anim.duration:.1f}s"
                list_item.setText(text)
