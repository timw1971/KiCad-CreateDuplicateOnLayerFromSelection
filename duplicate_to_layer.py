"""KiCad Action Plugin: duplicate selected PCB graphics to another layer.

Designed for KiCad 9.x SWIG pcbnew Python bindings.
"""

import os
import re

import wx
import pcbnew


SUPPORTED_CLASS_NAMES = {
    "PCB_SHAPE",
    "PCB_TEXT",
    "PCB_TEXTBOX",
    "PCB_DIM_ALIGNED",
    "PCB_DIM_ORTHOGONAL",
    "PCB_DIM_CENTER",
    "PCB_DIM_RADIAL",
    "PCB_DIM_LEADER",
    "PCB_TARGET",
    "PCB_TABLE",
}

# KiCad's item formatter includes a unique identifier in each item's
# s-expression.  Identical graphics have different UUIDs, so UUID/tstamp
# fields must be ignored when comparing an intended copy with graphics that
# are already present on the destination layer.
_ID_FIELD_RE = re.compile(
    r"\((?:uuid|tstamp)\s+(?:\"[^\"]*\"|[^()\s]+)\)",
    flags=re.IGNORECASE,
)


def _class_name(item):
    try:
        return str(item.GetClass())
    except Exception:
        return item.__class__.__name__.split(".")[-1]


def _walk_supported_item(item, output, seen):
    """Append supported items, recursively expanding selected groups."""
    identity = id(item)
    if identity in seen:
        return
    seen.add(identity)

    name = _class_name(item)
    if name == "PCB_GROUP":
        try:
            children = item.GetItems()
        except Exception:
            children = item.GetItemsDeque()
        for child in children:
            _walk_supported_item(child, output, seen)
    elif name in SUPPORTED_CLASS_NAMES:
        output.append(item)


def _collect_selected_graphics(board):
    selected = []
    seen = set()

    for item in board.GetDrawings():
        try:
            if item.IsSelected():
                _walk_supported_item(item, selected, seen)
        except Exception:
            continue

    return selected


def _collect_all_graphics(board):
    """Return all supported board graphics, including members of groups."""
    graphics = []
    seen = set()

    for item in board.GetDrawings():
        try:
            _walk_supported_item(item, graphics, seen)
        except Exception:
            continue

    return graphics


def _available_layers(board):
    """Return enabled board layers in KiCad's normal UI order."""
    enabled = board.GetEnabledLayers()

    try:
        layer_ids = list(enabled.UIOrder())
    except Exception:
        try:
            layer_ids = list(enabled.Seq())
        except Exception:
            layer_ids = [
                layer_id
                for layer_id in range(int(pcbnew.PCB_LAYER_ID_COUNT))
                if enabled.Contains(layer_id)
            ]

    layers = []
    seen = set()
    for layer_id in layer_ids:
        layer_id = int(layer_id)
        if layer_id in seen or not enabled.Contains(layer_id):
            continue
        seen.add(layer_id)
        try:
            name = str(board.GetLayerName(layer_id))
        except Exception:
            continue
        if name:
            layers.append((name, layer_id))
    return layers


def _duplicate_board_item(item):
    """Duplicate a board item while retaining an editable BOARD_ITEM wrapper."""
    duplicate = item.Duplicate()
    if duplicate is None:
        raise RuntimeError("KiCad returned no duplicate")
    return duplicate


def _new_item_formatter():
    """Create KiCad's native s-expression formatter for exact item comparison."""
    return pcbnew.PCB_IO_KICAD_SEXPR()


def _item_signature(item, formatter):
    """Return an exact, UUID-independent representation of a board item."""
    # Clear anything left in the formatter from a previous call.
    formatter.GetStringOutput(True)
    formatter.Format(item)
    text = str(formatter.GetStringOutput(True))
    return _ID_FIELD_RE.sub("", text).strip()


def _items_are_equivalent(first, second):
    """Fallback comparison for an item type that cannot be formatted."""
    if _class_name(first) != _class_name(second):
        return False

    try:
        return float(first.Similarity(second)) >= 0.999999
    except Exception:
        return False


class DestinationIndex:
    """Index graphics already present on one destination layer."""

    def __init__(self, board, destination):
        self._formatter = None
        self._signatures = set()
        self._fallback_items = []

        try:
            self._formatter = _new_item_formatter()
        except Exception:
            self._formatter = None

        for item in _collect_all_graphics(board):
            try:
                if int(item.GetLayer()) != int(destination):
                    continue
            except Exception:
                continue
            self.add(item)

    def contains(self, item):
        if self._formatter is not None:
            try:
                return _item_signature(item, self._formatter) in self._signatures
            except Exception:
                # Retain a fallback route rather than allowing one unsupported
                # object type to disable duplicate detection for the whole run.
                pass

        return any(_items_are_equivalent(item, other) for other in self._fallback_items)

    def add(self, item):
        if self._formatter is not None:
            try:
                self._signatures.add(_item_signature(item, self._formatter))
                return
            except Exception:
                pass

        self._fallback_items.append(item)


class LayerDialog(wx.Dialog):
    def __init__(self, parent, layers, initial_layer=None):
        super().__init__(parent, title="Duplicate selected graphics to layer")
        self._layers = layers

        message = wx.StaticText(
            self,
            label=(
                "The selected graphics will be copied at exactly the same "
                "coordinates. Only the copies' layer will change."
            ),
        )
        self.choice = wx.Choice(self, choices=[name for name, _ in layers])

        initial_index = 0
        if initial_layer is not None:
            for index, (_, layer_id) in enumerate(layers):
                if layer_id == initial_layer:
                    initial_index = index
                    break
        self.choice.SetSelection(initial_index)

        buttons = self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL)

        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(message, 0, wx.ALL | wx.EXPAND, 12)
        layout.Add(wx.StaticText(self, label="Destination layer:"), 0, wx.LEFT | wx.RIGHT, 12)
        layout.Add(self.choice, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 12)

        self.skip_existing = wx.CheckBox(
            self,
            label="Skip matching graphics already present on the destination layer",
        )
        self.skip_existing.SetValue(True)
        self.skip_existing.SetToolTip(
            "Prevents repeated runs from adding another identical copy at the same coordinates."
        )
        layout.Add(self.skip_existing, 0, wx.ALL, 12)

        if buttons:
            layout.Add(buttons, 0, wx.ALL | wx.EXPAND, 8)
        self.SetSizerAndFit(layout)
        self.SetMinSize((520, self.GetSize().height))
        self.CentreOnParent()

    def selected_layer(self):
        index = self.choice.GetSelection()
        if index == wx.NOT_FOUND:
            return None
        return self._layers[index][1]

    def should_skip_existing(self):
        return self.skip_existing.GetValue()


class DuplicateToLayerPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Create Duplicate on Layer from Selection..."
        self.category = "Modify PCB graphics"
        self.description = (
            "Clone selected PCB graphics at identical coordinates and put the "
            "copies on another layer."
        )
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "duplicate_to_layer.png")

    def Run(self):
        board = pcbnew.GetBoard()
        if board is None:
            wx.MessageBox("No PCB is open.", self.name, wx.OK | wx.ICON_ERROR)
            return

        items = _collect_selected_graphics(board)
        if not items:
            wx.MessageBox(
                "Select one or more board graphics, text items, dimensions, "
                "tables, targets, or a group containing them, then run the plugin again.",
                self.name,
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        layers = _available_layers(board)
        if not layers:
            wx.MessageBox(
                "KiCad did not report any enabled PCB layers.",
                self.name,
                wx.OK | wx.ICON_ERROR,
            )
            return

        try:
            initial_layer = items[0].GetLayer()
        except Exception:
            initial_layer = None

        dialog = LayerDialog(None, layers, initial_layer)
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return
            destination = dialog.selected_layer()
            skip_existing = dialog.should_skip_existing()
        finally:
            dialog.Destroy()

        if destination is None:
            return

        destination_name = str(board.GetLayerName(destination))
        on_destination = 0
        for item in items:
            try:
                if int(item.GetLayer()) == int(destination):
                    on_destination += 1
            except Exception:
                pass

        # A same-layer copy creates perfectly overlapping objects.  Warn
        # explicitly rather than relying on the skip option's final summary.
        if on_destination == len(items):
            if skip_existing:
                wx.MessageBox(
                    f"The destination layer ({destination_name}) is the same as the "
                    "source layer for all selected items.\n\n"
                    "Because duplicate detection is enabled, nothing will be copied.",
                    self.name,
                    wx.OK | wx.ICON_WARNING,
                )
                return

            answer = wx.MessageBox(
                f"The destination layer ({destination_name}) is the same as the "
                "source layer for all selected items.\n\n"
                "This will create overlapping duplicates on the same layer. Continue?",
                self.name,
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            )
            if answer != wx.YES:
                return

        elif on_destination and not skip_existing:
            answer = wx.MessageBox(
                f"{on_destination} of the {len(items)} selected items are already on "
                f"{destination_name}.\n\n"
                "Continuing may create overlapping duplicates for those items. Continue?",
                self.name,
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
            )
            if answer != wx.YES:
                return

        duplicated = 0
        skipped_existing = 0
        failures = []
        destination_index = DestinationIndex(board, destination) if skip_existing else None

        for item in items:
            try:
                clone = _duplicate_board_item(item)
                clone.SetLayer(destination)

                if destination_index is not None and destination_index.contains(clone):
                    skipped_existing += 1
                    continue

                try:
                    clone.ClearSelected()
                except Exception:
                    pass

                board.Add(clone)
                duplicated += 1

                if destination_index is not None:
                    # Also index copies made during this run, preventing two
                    # identical selected source objects from creating stacked copies.
                    destination_index.add(clone)
            except Exception as exc:
                failures.append(f"{_class_name(item)}: {exc}")

        if duplicated:
            pcbnew.Refresh()

        if duplicated == 0 and skipped_existing == len(items) and not failures:
            wx.MessageBox(
                f"Matching copies of all {skipped_existing} selected item(s) already "
                f"exist on {destination_name}.\nNothing was duplicated.",
                self.name,
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        skipped_text = (
            f"\nSkipped {skipped_existing} item(s) because matching graphics already "
            f"exist on {destination_name}."
            if skipped_existing
            else ""
        )

        if failures:
            details = "\n".join(failures[:8])
            if len(failures) > 8:
                details += f"\n...and {len(failures) - 8} more"
            wx.MessageBox(
                f"Duplicated {duplicated} item(s) to {destination_name}."
                f"{skipped_text}\n\n"
                f"Failed to duplicate {len(failures)} item(s):\n{details}",
                self.name,
                wx.OK | wx.ICON_WARNING,
            )
        else:
            wx.MessageBox(
                f"Duplicated {duplicated} item(s) to {destination_name}."
                f"{skipped_text}\n"
                "The copies retain the originals' exact coordinates.",
                self.name,
                wx.OK | wx.ICON_INFORMATION,
            )
