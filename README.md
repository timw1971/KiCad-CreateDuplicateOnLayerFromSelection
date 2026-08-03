# Duplicate graphics to layer — KiCad 9 Action Plugin

Duplicates selected non-electrical PCB graphics at exactly the same coordinates,
changing only the destination layer.

## Supported items

- PCB shapes (lines, arcs, circles, rectangles, polygons and curves)
- Board text and text boxes
- Dimensions
- Targets
- Tables
- Selected groups containing supported objects

Tracks, vias, zones, footprints and pads are deliberately excluded.

## Installation

Replace the existing plugin folder with the `duplicate_to_layer` folder from the
ZIP. For a Plugin and Content Manager-style installation, the location is normally:

    Documents\KiCad\9.0\3rdparty\plugins\duplicate_to_layer

Fully restart PCB Editor after replacing the files.

The command is available from the PCB Editor toolbar and from:

    Tools -> External Plugins -> Create Duplicate on Layer from Selection...

## Version 1.5

- The skip option now detects an **identical graphic already present on the
  destination layer**, rather than merely checking whether the selected source
  item is itself on that layer.
- Repeat runs therefore do not create stacked duplicates when **Skip matching
  graphics already present on the destination layer** is enabled.
- A clear warning is displayed when all selected source items are already on the
  chosen destination layer.
- If same-layer duplicate detection is disabled, the user must explicitly confirm
  before overlapping copies are created.

Duplicate detection compares KiCad's native serialized representation of each
board item while ignoring its unique identifier. A `Similarity()` comparison is
used as a fallback for an item that cannot be serialized.
