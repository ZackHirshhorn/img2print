import io

import numpy as np
import pytest
import trimesh
from PIL import Image

import img2print
from img2print.cli import main


def make_image(mode="L"):
    """200x100 px white image: a solid black square plus a black ring (square with a hole)."""
    a = np.full((100, 200), 255, np.uint8)
    a[20:80, 20:80] = 0          # solid 60x60 square
    a[20:80, 120:180] = 0        # ring: 60x60 outer ...
    a[40:60, 140:160] = 255      # ... with a 20x20 hole
    im = Image.fromarray(a)
    return im.convert(mode)


def test_load_darkness_handles_transparency():
    im = Image.new("RGBA", (10, 10), (0, 0, 0, 0))   # fully transparent black
    im.putpixel((5, 5), (0, 0, 0, 255))
    dark = img2print.load_darkness(im)
    assert dark[5, 5] == pytest.approx(1.0)
    assert dark[0, 0] == pytest.approx(0.0)
    assert img2print.load_darkness(im, invert=True)[5, 5] == pytest.approx(0.0)


def test_load_darkness_accepts_bytes():
    buf = io.BytesIO()
    make_image().save(buf, format="PNG")
    dark = img2print.load_darkness(buf.getvalue())
    assert dark.shape == (100, 200)


def test_trace_scale_and_holes():
    art = img2print.trace_image(make_image(), width=100)   # 0.5 mm per px
    assert (art.width, art.height) == pytest.approx((100, 50))
    # square 30x30 mm + ring 30x30 - 10x10 mm
    assert art.area == pytest.approx(900 + 800, rel=0.02)
    assert len(img2print.geometry.as_polygons(art.geometry)) == 2
    assert sum(len(p.interiors) for p in img2print.geometry.as_polygons(art.geometry)) == 1


def test_trace_is_not_mirrored():
    a = np.zeros((10, 20))
    a[0:5, 0:5] = 1.0   # top-left in the image
    art = img2print.trace(a, width=20)
    minx, miny, maxx, maxy = art.geometry.bounds
    assert minx < 1 and maxy > 9   # top-left in model space (y up)


def test_min_area_drops_specks():
    a = np.zeros((50, 50))
    a[10, 10] = 1.0
    assert img2print.trace(a, width=50, min_area=5).is_empty


@pytest.mark.parametrize("raised", [False, True])
def test_two_color_tile(raised):
    art = img2print.trace_image(make_image(), width=100)
    model = img2print.two_color_tile(art, base=1.0, layer=0.5, corner_radius=0, raised=raised)
    white, black = model["white"].mesh, model["black"].mesh
    assert white.is_watertight and black.is_watertight
    assert black.volume == pytest.approx(art.area * 0.5, rel=1e-3)
    plate_area = 100 * 50
    expected_white = plate_area * 1.0 + (0 if raised else (plate_area - art.area) * 0.5)
    assert white.volume == pytest.approx(expected_white, rel=1e-3)
    assert model.bounds[1][2] == pytest.approx(1.5)


def test_custom_plate_clips_artwork():
    art = img2print.trace_image(make_image(), width=100)
    model = img2print.two_color_tile(art, plate=img2print.rounded_rect(50, 50))   # left half only
    assert model["black"].mesh.bounds[1][0] <= 50 + 1e-6


def test_empty_artwork_raises():
    blank = Image.new("L", (20, 20), 255)
    with pytest.raises(ValueError):
        img2print.image_to_tile(blank)


def test_export(tmp_path):
    model = img2print.image_to_tile(make_image("RGB"), width=50)
    written = model.export(tmp_path / "out" / "logo")
    assert sorted(p.name for p in written) == ["logo.3mf", "logo_black.stl", "logo_white.stl"]
    loaded = trimesh.load(tmp_path / "out" / "logo.3mf")
    assert len(loaded.geometry) == 2


def test_cli(tmp_path, capsys):
    src = tmp_path / "design.png"
    make_image().save(src)
    main([str(src), "--width", "60", "--raised"])
    assert (tmp_path / "design_white.stl").exists()
    assert (tmp_path / "design.3mf").exists()
    assert "watertight=True" in capsys.readouterr().out


# --- more than 2 colours ---

def make_color_image():
    """200x100 px white image with a black square, a red square and a blue bar."""
    a = np.full((100, 200, 3), 255, np.uint8)
    a[20:80, 20:80] = (0, 0, 0)          # 30x30 mm at width 100
    a[20:80, 120:160] = (220, 30, 30)    # 20x30 mm
    a[85:95, 20:180] = (30, 60, 200)     # 80x5 mm
    return Image.fromarray(a)


def test_quantize_finds_colours():
    labels, hexes = img2print.quantize(np.asarray(make_color_image()), colors=4)
    assert sorted(hexes) == sorted(["#ffffff", "#000000", "#dc1e1e", "#1e3cc8"])
    assert labels.shape == (100, 200)
    assert hexes[labels[50, 50]] == "#000000"


def test_quantize_with_palette():
    labels, hexes = img2print.quantize(np.asarray(make_color_image()), palette=["white", "black", "#f00"])
    assert hexes == ["#ffffff", "#000000", "#ff0000"]
    assert hexes[labels[50, 150]] == "#ff0000"
    assert hexes[labels[90, 100]] == "#000000"   # blue is closer to black than to red or white


def test_trace_colors_order_and_areas():
    layers = img2print.trace_colors(make_color_image(), width=100, colors=4)
    assert [a.color for a in layers] == ["#ffffff", "#000000", "#dc1e1e", "#1e3cc8"]
    assert [a.area for a in layers[1:]] == pytest.approx([900, 600, 400], rel=0.02)


def test_trace_colors_background_option():
    layers = img2print.trace_colors(make_color_image(), width=100, colors=4, background="#000")
    assert layers[0].color == "#000000"


@pytest.mark.parametrize("raised", [False, True])
def test_multi_color_tile(raised):
    layers = img2print.trace_colors(make_color_image(), width=100, colors=4)
    model = img2print.multi_color_tile(layers, base=1.0, layer=0.5, corner_radius=0, raised=raised)
    assert [p.name for p in model] == ["white", "black", "red", "blue"]
    assert all(p.mesh.is_watertight for p in model)
    ink = sum(model[n].mesh.volume for n in ("black", "red", "blue"))
    assert ink == pytest.approx(sum(a.area for a in layers[1:]) * 0.5, rel=1e-3)
    plate_area = 100 * 50
    expected_white = plate_area * 1.0 + (0 if raised else plate_area * 0.5 - ink)
    assert model["white"].mesh.volume == pytest.approx(expected_white, rel=1e-3)


def assert_colour_by_layer(meshes, base, layer, floor=0.0):
    """Colour by layer, printable with one nozzle by swapping filament between layers: the
    background from the bed (floor) to base, then each colour in its own band, layer mm thick,
    right above the last. So no two parts share a layer and every colour ends at its own height."""
    bands = [tuple(m.bounds[:, 2]) for m in meshes]
    assert bands[0] == pytest.approx((floor, base))
    for i, band in enumerate(bands[1:]):
        assert band == pytest.approx((base + i * layer, base + (i + 1) * layer))
    tops = [round(hi, 6) for _, hi in bands]
    assert len(set(tops)) == len(tops)
    assert all(m.is_watertight for m in meshes)


def top_view(mesh):
    """What a part covers seen from above: its upward-facing triangles, flattened."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    up = mesh.face_normals[:, 2] > 0.5
    return unary_union([Polygon(t[:, :2]) for t in mesh.triangles[up]]).buffer(1e-6)


def test_colour_by_layer_tile():
    layers = img2print.trace_colors(make_color_image(), width=100, colors=4)
    model = img2print.multi_color_tile(layers, base=1.0, layer=0.5, corner_radius=0, stacked=True)
    assert [p.name for p in model] == ["white", "black", "red", "blue"]
    assert_colour_by_layer([p.mesh for p in model], base=1.0, layer=0.5)
    assert model.filament_changes == [(1.0, "black"), (1.5, "red"), (2.0, "blue")]
    # From above, each colour shows exactly where it is in the image: every later band covers it
    # nowhere, and its own band is under every later colour, holding it up.
    parts = list(model)
    for i, art in enumerate(layers[1:], 1):
        here = art.geometry.representative_point()
        assert top_view(parts[i].mesh).contains(here)
        assert not any(top_view(p.mesh).contains(here) for p in parts[i + 1:])
        below = parts[i].mesh.volume / 0.5   # the band's area: this colour and all later ones
        assert below == pytest.approx(sum(a.area for a in layers[i:]), rel=0.02)


@pytest.mark.parametrize("colors, raised", [(None, False), (2, True), (4, False), (4, True)])
def test_colour_by_layer_settings(colors, raised):
    """stacking="layers" always means colour by layer, whatever raised says, in both colour modes."""
    from img2print.pipeline import build
    from img2print.settings import Settings
    image = make_color_image() if colors == 4 else make_image()
    model, _ = build(image, Settings(width=100, colors=colors, stacking="layers", base=3, layer=0.6,
                                     corner_radius=8, padding=3, raised=raised))
    assert_colour_by_layer([p.mesh for p in model], base=3, layer=0.6)
    names = [p.name for p in model]
    assert model.filament_changes == [(pytest.approx(3 + i * 0.6), n) for i, n in enumerate(names[1:])]


def test_colour_by_layer_on_a_shape():
    """On a shape the colours stand out of the face, counted from the opposite face on the bed."""
    layers = img2print.trace_colors(make_color_image(), width=30, colors=4)
    model = img2print.shape_with_design(layers, size=(40, 30, 20), face="top", layer=0.5, stacked=True)
    assert_colour_by_layer([p.mesh for p in model], base=20, layer=0.5)
    assert [z for z, _ in model.filament_changes] == pytest.approx([20, 20.5, 21])
    front = img2print.shape_with_design(layers, size=(40, 30, 20), face="front", layer=0.5, stacked=True)
    np.testing.assert_allclose(front.bounds, [[0, 0, 0], [40, 31.5, 20]], atol=1e-6)
    with pytest.raises(ValueError, match="colour by layer"):
        img2print.multi_color_tile(layers, stacked=True, thickness=2)


def test_full_depth_tiles():
    art = img2print.trace_image(make_image(), width=100)
    model = img2print.two_color_tile(art, corner_radius=0, thickness=3)
    assert all(p.mesh.is_watertight for p in model)
    assert model["black"].mesh.volume == pytest.approx(art.area * 3, rel=1e-3)
    assert model["white"].mesh.volume == pytest.approx((100 * 50 - art.area) * 3, rel=1e-3)
    assert model.bounds[0][2] == pytest.approx(0) and model.bounds[1][2] == pytest.approx(3)

    layers = img2print.trace_colors(make_color_image(), width=100, colors=4)
    model = img2print.multi_color_tile(layers, corner_radius=0, thickness=2)
    assert [p.name for p in model] == ["white", "black", "red", "blue"]
    assert sum(p.mesh.volume for p in model) == pytest.approx(100 * 50 * 2, rel=1e-3)


def test_full_depth_from_settings():
    from img2print.pipeline import build
    from img2print.settings import Settings
    model, _ = build(make_image(), Settings(width=100, colors=2, stacking="full", thickness=2.5))
    assert model.bounds[1][2] - model.bounds[0][2] == pytest.approx(2.5)
    with pytest.raises(ValueError, match="thickness"):
        Settings(thickness=0)
    with pytest.raises(ValueError, match="stacking"):
        Settings(stacking="sideways")


def test_padding_keeps_the_plate_size():
    from img2print.pipeline import build
    from img2print.settings import Settings
    plain, plain_layers = build(make_image(), Settings(width=100, colors=2, corner_radius=0))
    model, layers = build(make_image(), Settings(width=100, colors=2, corner_radius=0, padding=5))
    # 100 mm wide in all; the 90 x 45 mm design plus 5 mm all round
    np.testing.assert_allclose(model.bounds[:, :2], [[0, 0], [100, 55]], atol=1e-6)
    assert layers[0].width == pytest.approx(90)
    # the design shrinks to 90 mm and sits 5 mm in from the edge
    assert model["black"].mesh.volume == pytest.approx(plain["black"].mesh.volume * 0.81, rel=1e-2)
    ink_min = model["black"].mesh.bounds[0][:2]
    assert ink_min == pytest.approx(5 + plain["black"].mesh.bounds[0][:2] * 0.9, abs=1e-3)
    with pytest.raises(ValueError, match="padding"):
        Settings(width=10, padding=5)


def test_plain_base_under_coloured_top():
    layers = img2print.trace_colors(make_color_image(), width=100, colors=4)
    model = img2print.multi_color_tile(layers, base=1.0, layer=0.5, corner_radius=0, base_color="grey")
    assert [p.name for p in model] == ["base", "white", "black", "red", "blue"]
    assert model["base"].color == "#808080"
    assert all(p.mesh.is_watertight for p in model)
    assert model["base"].mesh.volume == pytest.approx(100 * 50 * 1.0, rel=1e-3)
    top = sum(p.mesh.volume for p in model if p.name != "base")
    assert top == pytest.approx(100 * 50 * 0.5, rel=1e-3)
    assert min(p.mesh.bounds[0][2] for p in model if p.name != "base") == pytest.approx(1.0)
    # a base in the background colour is just the background, as in "layers"
    same = img2print.multi_color_tile(layers, base=1.0, layer=0.5, corner_radius=0, base_color="#fff")
    assert [p.name for p in same] == ["white", "black", "red", "blue"]

    from img2print.pipeline import build
    from img2print.settings import Settings
    model, _ = build(make_image(), Settings(width=100, stacking="top", base_color="red"))
    assert [p.name for p in model] == ["base", "white", "black"]


def test_multi_color_tile_later_layer_wins():
    from shapely.geometry import box
    bg = img2print.Artwork(box(0, 0, 10, 10), 10, 10, "#ffffff")
    big = img2print.Artwork(box(0, 0, 6, 10), 10, 10, "#000000")
    small = img2print.Artwork(box(4, 0, 8, 10), 10, 10, "#ff0000")
    model = img2print.multi_color_tile([bg, big, small], base=1, layer=1, corner_radius=0)
    assert model["black"].mesh.volume == pytest.approx(40)
    assert model["red"].mesh.volume == pytest.approx(40)
    assert model["white"].mesh.volume == pytest.approx(100 + 20)


def test_multi_color_needs_a_colour():
    with pytest.raises(ValueError):
        img2print.image_to_multi_color_tile(Image.new("RGB", (20, 20), "white"), colors=3)


def test_multi_color_export_names(tmp_path):
    model = img2print.image_to_multi_color_tile(make_color_image(), width=50, colors=4)
    written = model.export(tmp_path / "logo")
    assert sorted(p.name for p in written) == [
        "logo.3mf", "logo_black.stl", "logo_blue.stl", "logo_red.stl", "logo_white.stl"]
    assert len(trimesh.load(tmp_path / "logo.3mf").geometry) == 4


def test_cli_colors(tmp_path, capsys):
    src = tmp_path / "design.png"
    make_color_image().save(src)
    main([str(src), "--width", "60", "--colors", "4"])
    assert (tmp_path / "design_red.stl").exists()
    main([str(src), "--palette", "white, black, red", "--out", str(tmp_path / "pal")])
    assert sorted(p.name for p in tmp_path.glob("pal_*.stl")) == ["pal_black.stl", "pal_red.stl", "pal_white.stl"]
    assert "watertight=False" not in capsys.readouterr().out


# --- output size ---

@pytest.mark.parametrize("size, expected", [
    (dict(width=50), (50, 25)),
    (dict(height=40), (80, 40)),
    (dict(longest=60), (60, 30)),
    ({}, (100, 50)),
])
def test_output_size(size, expected):
    art = img2print.trace_image(make_image(), **size)
    assert (art.width, art.height) == pytest.approx(expected)
    layers = img2print.trace_colors(make_color_image(), colors=4, **size)
    assert (layers[0].width, layers[0].height) == pytest.approx(expected)


def test_output_size_longest_on_tall_image():
    tall = np.zeros((200, 50))
    tall[50:150, 10:40] = 1.0
    art = img2print.trace(tall, longest=80)
    assert (art.width, art.height) == pytest.approx((20, 80))


def test_output_size_conflict():
    with pytest.raises(ValueError):
        img2print.trace_image(make_image(), width=50, height=20)
    with pytest.raises(ValueError):
        img2print.trace_image(make_image(), height=-1)


def test_cli_height(tmp_path, capsys):
    src = tmp_path / "design.png"
    make_image().save(src)
    main([str(src), "--height", "30"])
    assert "60.0 x 30.0 mm" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main([str(src), "--height", "30", "--width", "20"])


# --- vector input ---

# 200 x 100 user units, shown 50 mm wide: 1 unit = 0.25 mm at width=50.
SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <style>.red { fill: #dc1e1e }</style>
  <path d="M20 20 h60 v60 h-60 z M40 40 v20 h20 v-20 z" fill="black" fill-rule="evenodd"/>
  <g transform="translate(120 20)"><rect class="red" width="40" height="60"/></g>
  <line x1="20" y1="90" x2="180" y2="90" stroke="#1e3cc8" stroke-width="10"/>
</svg>"""


def test_svg_two_colour_exact_area(tmp_path):
    path = tmp_path / "logo.svg"
    path.write_bytes(SVG)
    for source in (path, str(path), SVG, io.BytesIO(SVG)):
        art = img2print.trace_image(source, width=50)
        assert (art.width, art.height) == pytest.approx((50, 25))
        # ring 15x15 - 5x5, red 10x15 (darkness 0.6 > 0.5), blue bar 40x2.5
        assert art.area == pytest.approx(200 + 150 + 100, rel=1e-6)


def test_svg_is_not_mirrored():
    # The blue bar is near the bottom of the SVG (y = 85..95, y pointing down).
    art = img2print.trace_image(SVG, width=200)
    assert art.geometry.bounds == pytest.approx((20, 5, 180, 80))


def test_svg_colours():
    layers = img2print.trace_colors(SVG, width=50, colors=4)
    assert [a.color for a in layers] == ["#ffffff", "#000000", "#dc1e1e", "#1e3cc8"]
    assert [a.area for a in layers[1:]] == pytest.approx([200, 150, 100], rel=1e-6)
    assert layers[0].area == pytest.approx(50 * 25 - 450, rel=1e-6)
    model = img2print.multi_color_tile(layers, corner_radius=0)
    assert all(p.mesh.is_watertight for p in model)


def test_svg_later_shapes_cover_earlier():
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect width="10" height="10" fill="#000"/><rect x="5" width="5" height="10" fill="#fff"/></svg>"""
    assert img2print.trace_image(svg, width=10).area == pytest.approx(50)


def test_svg_fill_rules():
    # Two squares drawn the same direction, overlapping: nonzero fills the overlap, evenodd does not.
    d = "M0 0 h6 v6 h-6 z M4 4 h6 v6 h-6 z"
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><path d="{}" fill-rule="{}"/></svg>'
    nonzero = img2print.trace_image(svg.format(d, "nonzero").encode(), width=10, min_area=0)
    evenodd = img2print.trace_image(svg.format(d, "evenodd").encode(), width=10, min_area=0)
    assert nonzero.area == pytest.approx(36 + 36 - 4)
    assert evenodd.area == pytest.approx(36 + 36 - 8)
    # A hole drawn the other way round stays a hole under nonzero (how fonts draw letters).
    hole = "M0 0 h10 v10 h-10 z M3 3 v4 h4 v-4 z"
    assert img2print.trace_image(svg.format(hole, "nonzero").encode(), width=10).area == pytest.approx(84)


def test_svg_curves_are_smooth():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="40"/></svg>'
    art = img2print.trace_image(svg, width=100)
    assert art.area == pytest.approx(np.pi * 40 ** 2, rel=1e-3)


def test_svg_warns_about_text():
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect width="5" height="5"/><text x="1" y="9">Hi</text></svg>"""
    with pytest.warns(UserWarning, match="text"):
        img2print.trace_image(svg, width=10)


def test_cli_svg(tmp_path, capsys):
    src = tmp_path / "design.svg"
    src.write_bytes(SVG)
    main([str(src), "--longest", "80", "--colors", "4"])
    assert (tmp_path / "design_red.stl").exists()
    assert "80.0 x 40.0 mm" in capsys.readouterr().out


def make_pdf():
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.draw_rect(pymupdf.Rect(20, 20, 80, 80), color=None, fill=(0, 0, 0))
    page.draw_rect(pymupdf.Rect(120, 20, 160, 80), color=None, fill=(220 / 255, 30 / 255, 30 / 255))
    page.insert_text((20, 95), "Hi", fontsize=14)
    return doc.tobytes()


def test_pdf_input(tmp_path):
    data = make_pdf()
    art = img2print.trace_image(data, width=50, threshold=0.7)   # black square + text
    assert art.area > 225
    assert (art.width, art.height) == pytest.approx((50, 25))
    layers = img2print.trace_colors(data, width=50, colors=3)
    assert layers[0].color == "#ffffff"
    assert layers[2].area == pytest.approx(150, rel=1e-3)
    src = tmp_path / "design.pdf"
    src.write_bytes(data)
    with pytest.raises(ValueError):
        img2print.trace_image(src, page=3)


# --- a design on a face of a shape ---

def corner_image():
    """100x100 px white image with a black square in its top-left quarter."""
    a = np.full((100, 100), 255, np.uint8)
    a[10:40, 10:40] = 0
    return Image.fromarray(a)


# Unit vectors of the image's right and up on each face of a box, seen from outside.
@pytest.mark.parametrize("face, right, up, out", [
    ("top", (1, 0, 0), (0, 1, 0), (0, 0, 1)),
    ("bottom", (1, 0, 0), (0, -1, 0), (0, 0, -1)),
    ("front", (1, 0, 0), (0, 0, 1), (0, -1, 0)),
    ("back", (-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ("right", (0, 1, 0), (0, 0, 1), (1, 0, 0)),
    ("left", (0, -1, 0), (0, 0, 1), (-1, 0, 0)),
])
def test_shape_faces_read_from_outside(face, right, up, out):
    from img2print.pipeline import build
    from img2print.settings import Settings
    model, _ = build(corner_image(), Settings(recipe="shape", face=face, shape_width=40, shape_depth=30,
                                              shape_height=20, stacking="top", base_color="white"))
    assert [p.name for p in model] == ["white", "black"]
    assert all(p.mesh.is_watertight for p in model)
    np.testing.assert_allclose(model.bounds, [[0, 0, 0], [40, 30, 20]], atol=1e-6)
    offset = model["black"].mesh.centroid - np.array([20, 15, 10])
    assert offset @ right < 0 and offset @ up > 0           # top-left of the image
    ink = model["black"].mesh.bounds
    side = np.abs(out) @ ink[1 if sum(out) > 0 else 0]       # the ink is flush with the face
    assert side == pytest.approx(np.abs(out) @ ([40, 30, 20] if sum(out) > 0 else [0, 0, 0]))


def test_shape_inlaid_and_raised():
    layers = img2print.trace_colors(make_color_image(), width=30, colors=4)
    inlaid = img2print.shape_with_design(layers, size=(40, 30, 20), face="front", layer=1.0)
    assert [p.name for p in inlaid] == ["white", "black", "red", "blue"]
    assert sum(p.mesh.volume for p in inlaid) == pytest.approx(40 * 30 * 20, rel=1e-3)
    assert inlaid["black"].mesh.volume == pytest.approx(9 * 9 * 1.0, rel=0.02)   # 30 x 30 px at 0.3 mm
    raised = img2print.shape_with_design(layers, size=(40, 30, 20), face="front", layer=1.0, raised=True)
    assert raised["white"].mesh.volume == pytest.approx(40 * 30 * 20, rel=1e-3)
    np.testing.assert_allclose(raised.bounds, [[0, 0, 0], [40, 31, 20]], atol=1e-6)
    # every colour right through the box, 30 mm from front to back
    through = img2print.shape_with_design(layers, size=(40, 30, 20), face="front", full_depth=True)
    assert through["black"].mesh.volume == pytest.approx(9 * 9 * 30, rel=0.02)


def test_shape_cylinder_and_plain_body():
    from img2print.pipeline import build
    from img2print.settings import Settings
    model, layers = build(make_image(), Settings(recipe="shape", shape="cylinder", shape_width=50,
                                                 shape_height=10, stacking="top", base_color="grey"))
    assert [p.name for p in model] == ["base", "white", "black"]
    assert all(p.mesh.is_watertight for p in model)
    np.testing.assert_allclose(model.bounds, [[0, 0, 0], [50, 50, 10]], atol=1e-3)
    assert sum(p.mesh.volume for p in model) == pytest.approx(np.pi * 25 ** 2 * 10, rel=1e-3)
    assert layers[0].width == pytest.approx(50 / 2 ** 0.5)   # fits the square inside the top
    with pytest.raises(ValueError, match="curved"):
        Settings(recipe="shape", shape="cylinder", face="front")


def test_shape_design_size():
    from img2print.pipeline import trace_layers
    from img2print.settings import Settings
    # By default the 2:1 design fits the 40 x 20 mm front face inside the padding ...
    fit = trace_layers(make_image(), Settings(recipe="shape", shape_height=20, face="front", padding=3))
    assert (fit[0].width, fit[0].height) == pytest.approx((28, 14))
    fit = trace_layers(make_image(), Settings(recipe="shape", shape_width=60, shape_height=40, face="front"))
    assert (fit[0].width, fit[0].height) == pytest.approx((60, 30))
    # ... or takes the size given, clipped to the face
    sized = trace_layers(make_image(), Settings(recipe="shape", width=25, padding=3))
    assert sized[0].width == pytest.approx(25)
    with pytest.raises(ValueError, match="deep"):
        Settings(recipe="shape", face="front", shape_depth=0.5, layer=0.8, stacking="top")
    with pytest.raises(ValueError, match="face"):
        Settings(recipe="shape", face="inside")
    with pytest.raises(ValueError, match="padding"):
        Settings(recipe="shape", padding=20)


def test_cli_shape(tmp_path, capsys):
    src = tmp_path / "design.png"
    make_image().save(src)
    main([str(src), "--shape", "box", "--shape-size", "40x30x20", "--face", "front", "--colors", "2",
          "--base-color", "white"])
    out = capsys.readouterr().out
    assert "40.0 x 20.0 mm" in out          # the design fits the face
    mesh = trimesh.load(tmp_path / "design_white.stl")
    np.testing.assert_allclose(mesh.bounds, [[0, 0, 0], [40, 30, 20]], atol=1e-6)
    main([str(src), "--shape", "cylinder", "--shape-size", "30x5", "--base-color", "white"])
    assert trimesh.load(tmp_path / "design_white.stl").bounds[1] == pytest.approx([30, 30, 5])
    with pytest.raises(SystemExit):
        main([str(src), "--shape", "cylinder", "--shape-size", "30x30x5"])
    assert "DIAMETERxHEIGHT" in capsys.readouterr().err
