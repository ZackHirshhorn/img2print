# img2print

Turn flat graphic designs (logos, signage, illustrations) into multi-colour 3D prints.

A black-and-white image becomes a **2-colour plate**, and a colour image becomes a plate
with **one filament per colour**. By default it is built **colour by layer**, so any printer
with one nozzle can print it by swapping filament at a few heights; flush inlays and full-depth
plates are there for multi-material printers. Each model is exported as one STL per colour plus
a combined 3MF (Bambu Studio, PrusaSlicer, Orca). SVG and PDF files are read as shapes, so edges
stay exact.

## Install

```
pip install -e .            # from this folder
pip install -e .[pdf]       # + PDF input (PyMuPDF)
pip install -e .[dev]       # + pytest
```

## Command line

```
img2print logo.png                          # 100 mm wide, colour by layer: prints where to swap filament
img2print logo.png --base-color white       # a flush inlay tile instead (needs a multi-material printer)
img2print logo.png --width 80 --raised      # letters stand 0.8 mm above the plate
img2print logo.png --thickness 2            # every colour runs the full 2 mm, instead of a base + colour layer
img2print logo.png --padding 5              # 5 mm blank border; the plate stays 100 mm wide
img2print logo.png --height 40              # or size by height ...
img2print logo.png --longest 120            # ... or by the longer side
img2print logo.svg --colors 3               # vector input: SVG or PDF (--page 2 for another PDF page)
img2print logo.png --colors 3 --base-color grey  # plain grey base, the full design only in the top layer
img2print logo.png --invert --threshold 0.4 # light-on-dark artwork
img2print logo.png --colors 4              # colour artwork: find 4 colours (background included)
img2print logo.png --palette white,black,#d42a1f   # or name the filaments yourself
img2print logo.png --shape box --shape-size 40x30x20 --face front   # the design on a box's front face
img2print logo.png --shape cylinder --shape-size 50x10 --raised     # standing out of a cylinder's top
img2print logo.png --padding 12 --text "פיצה טובה" --font "Secular One"   # text in its own colour
img2print logo.png --text "Napoli" --text-style engrave --text-color surface # text cut into the plate
img2print --help
```

Writes `<name>_white.stl`, `<name>_black.stl` and `<name>.3mf` next to the image (or at `--out`).
In colour mode, each STL is named after its nearest colour (`<name>_red.stl`, `<name>_blue.stl`, ...).

### Colour by layer (the default)

For a printer with one nozzle and no automatic colour changer, where every layer of the print
can only be one colour:

- The background is the base, `--base` thick (default 1.2 mm). Each other colour then gets its
  own band, `--layer` thick (default 0.8 mm), right above the last, so the colours end at
  different heights and no layer mixes two filaments.
- A colour's band also runs under every later colour, holding it up, so from above each area
  shows its own colour. Larger colours come first.
- The command prints the heights, e.g. `pause at 1.2 mm and load black`. In the slicer, add a
  filament change (pause / M600) at the first layer at each height. A band thickness that is a
  multiple of your layer height keeps the changes on layer boundaries.
- `--base-color` (inlaid in the top layer) and `--thickness` (full depth) build for
  multi-material printers instead.

### Vector input (SVG, PDF)

- Shapes are read directly instead of traced from pixels, so curves and corners are exact
  and `--smooth` is not needed.
- Fills and strokes in flat colours are supported, with transforms, CSS classes, opacity and
  both fill rules. The size is the document's page / artboard; the unpainted page counts as white.
- In 2-colour mode a shape is black filament when its colour is darker than `--threshold`.
  In colour mode its colours are grouped like pixel colours.
- Not supported: gradients, embedded images, clip paths and masks. SVG text is skipped with a
  warning: convert text to outlines (paths) before exporting. Text in a PDF is kept.
- PDF input needs PyMuPDF (`pip install img2print[pdf]`); note it is AGPL-licensed.

### Colour mode

- `--colors N` groups the image's colours into N filaments (k-means). `--palette` gives the
  exact colours instead (`#rrggbb`, `#rgb` or a name such as `red`, `navy`, `gold`). Every pixel goes to the nearest one.
- The **background** colour forms the base plate and fills any gap between the others. By
  default it is the colour around the image border; use `--background` to choose it.
- `--smooth` (pixels, default 0.6) blurs each colour mask before tracing, so edges are smooth
  rather than stepped. Use 0 for pixel art.
- Ask for only as many colours as the artwork has. Extra colours pick up the anti-aliased
  pixels along edges and turn them into thin slivers.

### On a shape

- `--shape box` or `--shape cylinder` starts from a solid instead of a flat plate, and puts the
  design on one face: `--face top|bottom|front|back|left|right` (a cylinder: top or bottom only,
  since its side is curved). The design reads correctly when you look at that face from outside.
- `--shape-size` is `WxDxH` for a box and `DIAMETERxH` for a cylinder, in mm (default 40x40x40).
- By default the design is colour by layer: each colour stands out of the face in its own
  `--layer` band (default 0.8 mm). Print the shape with that face up; the heights printed count
  from the opposite face, on the bed. `--base-color grey` instead inlays the whole face flush in
  the coloured layer of a plain body (`--raised` lifts it out); `--thickness` (any value) runs
  every colour right through the shape.
- By default the design fits the face, `--padding` in from its edges (on a cylinder: the
  largest square inside the circle). `--width`, `--height` or `--longest` size it yourself; it is
  centred on the face and clipped to it.

### Text

- Text goes on the design in any font. Hebrew (with niqqud), mixed Hebrew / English lines and
  numbers come out in reading order; text is shaped with HarfBuzz.
- Three styles: **paint** (flush, set apart only by its colour), **emboss** (stands `depth` mm out)
  and **engrave** (cut `depth` mm in). Embossed or engraved text without a colour keeps the colour
  of the surface; engraved text with a colour shows it at the bottom of the letters.
- `thicken` (mm) widens every stroke, for thin fonts or small letters: strokes under a 0.4 mm
  nozzle may not print. The web app warns when a text has them.
- Text in a colour the design already has prints in that filament; a new colour adds a part.
  By layers, the text's colour gets the top band, so every layer still holds one filament.
- Fonts: Heebo is bundled. Any Google Fonts family works by name and is downloaded on first use
  (`IMG2PRINT_GOOGLE_FONTS=0` turns that off). Your own `.ttf` / `.otf` files go in the font folder,
  `IMG2PRINT_FONT_DIR` (default `%LOCALAPPDATA%\img2print\fonts` or `~/.cache/img2print/fonts`),
  or are added in the web app.
- The command line puts one `--text` in the middle. For several texts, their position (`x`, `y`
  as fractions of the design from its top-left), size, rotation and spacing, use the `"texts"`
  list in a `--settings` file:

```json
{"texts": [{"text": "שלום", "font": "Frank Ruhl Libre", "weight": 700, "size": 8,
            "x": 0.5, "y": 0.85, "style": "emboss", "color": null, "depth": 0.6}]}
```

In the web app, add texts in the Text section and drag them on the Design view (scroll to zoom,
drag the background to pan).

## Python API

```python
import img2print

# one call
model = img2print.image_to_tile("logo.png", width=100, raised=True)
model.export("out/logo")
model = img2print.image_to_tile("logo.svg", height=40)              # SVG / PDF, sized by height

# step by step
art = img2print.trace_image("logo.png", width=100, threshold=0.5)    # vector Artwork in mm
print(art.width, art.height, art.area)
model = img2print.two_color_tile(
    art,
    base=1.2, layer=0.8,
    plate=art.geometry.buffer(3),          # any shapely polygon: here a 3 mm outline around the design
    ink=("gold", "#d4af37"), paper=("navy", "#1b2a4a"),
)

# more than 2 colours
layers = img2print.trace_colors("logo.png", width=100, colors=4)   # background first
for art in layers:
    print(art.color, art.area)
model = img2print.multi_color_tile(layers, raised=True)            # parts named "white", "red", ...
model = img2print.image_to_multi_color_tile("logo.png", palette=["white", "black", "#d42a1f"])

# the design on the front face of a 40 x 30 x 20 mm box, inlaid 1 mm deep
model = img2print.shape_with_design(layers, shape="box", size=(40, 30, 20), face="front", layer=1.0)

# in-memory output, e.g. for a web server
data_3mf = model.to_3mf()
stl_bytes = model["gold"].to_stl()
```

Inputs can be a path, raw bytes, a file object or a PIL image. Transparent backgrounds count as paper.
Every tracing function and one-call recipe takes one of `width`, `height` or `longest` (mm); the
default is 100 mm wide. SVG and PDF (path, bytes or file object) work wherever an image does.

### Layers

| module      | role                                                           |
|-------------|----------------------------------------------------------------|
| `image`     | load any image into a darkness map (1 = ink, 0 = paper), or group its colours (`quantize`) |
| `colors`    | colour parsing and friendly names for parts                    |
| `vector`    | SVG / PDF -> painted shapes (`load_vector`), no pixels involved |
| `trace`     | darkness map / mask / vector shapes -> `Artwork` (shapely geometry in mm); `trace_colors` for colour images |
| `geometry`  | 2D shapes (`rounded_rect`), `extrude`, boolean `union`         |
| `model`     | `Part` / `Model`: multi-material bodies, STL/3MF export        |
| `recipes`   | complete products: `two_color_tile`, `multi_color_tile`, `image_to_tile`, `image_to_multi_color_tile`, `shape_with_design` |

New products (keychains, coasters, lithophanes...) belong in `recipes` and reuse the lower layers.

## Tests

```
pytest
```

## License

MIT, see [LICENSE](LICENSE). The optional PDF support uses PyMuPDF, which is AGPL-3.0;
installing `img2print[pdf]` brings those terms into anything you distribute or host with it.
