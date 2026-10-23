# img2print

Turn flat graphic designs (logos, signage, illustrations) into multi-colour 3D prints.

A black-and-white image becomes a **2-colour plate**, and a colour image becomes a plate
with **one filament per colour**. Either way you get a flush inlay tile or raised artwork,
exported as one STL per colour plus a combined 3MF ready for multi-material slicers
(Bambu Studio, PrusaSlicer, Orca). SVG and PDF files are read as shapes, so edges stay exact.

## Install

```
pip install -e .            # from this folder
pip install -e .[pdf]       # + PDF input (PyMuPDF)
pip install -e .[dev]       # + pytest
```

## Command line

```
img2print logo.png                          # 100 mm wide flush tile
img2print logo.png --width 80 --raised      # letters stand 0.8 mm above the plate
img2print logo.png --height 40              # or size by height ...
img2print logo.png --longest 120            # ... or by the longer side
img2print logo.svg --colors 3               # vector input: SVG or PDF (--page 2 for another PDF page)
img2print logo.png --face-down              # colour face prints on the bed (smooth / textured PEI finish)
img2print logo.png --invert --threshold 0.4 # light-on-dark artwork
img2print logo.png --colors 4              # colour artwork: find 4 colours (background included)
img2print logo.png --palette white,black,#d42a1f   # or name the filaments yourself
img2print --help
```

Writes `<name>_white.stl`, `<name>_black.stl` and `<name>.3mf` next to the image (or at `--out`).
In colour mode, each STL is named after its nearest colour (`<name>_red.stl`, `<name>_blue.stl`, ...).

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
| `recipes`   | complete products: `two_color_tile`, `multi_color_tile`, `image_to_tile`, `image_to_multi_color_tile` |

New products (keychains, coasters, lithophanes...) belong in `recipes` and reuse the lower layers.

## Tests

```
pytest
```

## License

MIT, see [LICENSE](LICENSE). The optional PDF support uses PyMuPDF, which is AGPL-3.0;
installing `img2print[pdf]` brings those terms into anything you distribute or host with it.
