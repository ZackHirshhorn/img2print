import io
import json

import pytest
from PIL import Image
from shapely.geometry import box

import img2print
from img2print import fonts
from img2print.geometry import as_polygons
from img2print.pipeline import build, build_model, trace_layers
from img2print.settings import Settings
from img2print.text import Text, _nonzero, _visual_runs, text_shape

from test_img2print import make_color_image, make_image

HEEBO = fonts.BUNDLED_DIR / "Heebo[wght].ttf"


def blank(w=200, h=100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


# --- shaping and outlines ------------------------------------------------------------------------

def test_letter_height_is_the_size():
    for size in (5, 12):
        x0, y0, x1, y1 = text_shape("H", size=size).bounds
        assert y1 - y0 == pytest.approx(size, rel=0.01)
        assert (x0 + x1) / 2 == pytest.approx(0, abs=0.05 * size)
        assert (y0 + y1) / 2 == pytest.approx(0, abs=0.01 * size)   # centred on its letters


def test_empty_text_has_no_shape():
    assert text_shape("").is_empty
    assert text_shape("  \n ").is_empty


def test_holes_in_letters():
    o = text_shape("O", size=10)
    assert len(o.interiors) == 1


def test_hebrew_reads_right_to_left():
    """The first letter typed is the rightmost: a shin before four vavs ends up on the right."""
    def shin_x(text):
        return max(as_polygons(text_shape(text, size=10)), key=lambda p: p.area).centroid.x
    assert shin_x("שוווו") > 5
    assert shin_x("ווווש") < -5


@pytest.mark.parametrize("line, runs", [
    ("שלום עולם", [("שלום עולם", True)]),
    ("Hello world", [("Hello world", False)]),
    ("שלום abc 123", [("abc 123", False), ("שלום ", True)]),
    ("abc שלום def", [("abc ", False), ("שלום", True), (" def", False)]),
    ("מחיר 12.50 ש\"ח", [(" ש\"ח", True), ("12.50", False), ("מחיר ", True)]),
    ("שלום (1)", [(")", True), ("1", False), ("שלום (", True)]),
    ("שָׁלוֹם", [("שָׁלוֹם", True)]),
])
def test_bidi_runs(line, runs):
    assert _visual_runs(line) == runs


def test_niqqud_does_not_widen_the_word():
    plain = text_shape("שלום", size=10).bounds
    pointed = text_shape("שָׁלוֹם", size=10).bounds
    assert pointed[2] - pointed[0] == pytest.approx(plain[2] - plain[0], rel=0.05)
    assert pointed[1] < plain[1] or pointed[3] > plain[3]   # the points sit above or below


def test_overlapping_contours_fill_with_nonzero():
    """Two overlapping squares wound the same way are one solid, not a square with a hole."""
    a = [(0, 0), (2, 0), (2, 2), (0, 2)]
    b = [(1, 1), (3, 1), (3, 3), (1, 3)]
    assert _nonzero([a, b]).area == pytest.approx(7)
    hole = [(0.5, 0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)]   # wound the other way: a hole
    assert _nonzero([a, hole]).area == pytest.approx(3)


def test_weights_of_a_variable_font():
    thin = text_shape("שלום abc", size=10, weight=100).area
    black = text_shape("שלום abc", size=10, weight=900).area
    assert black > 2 * thin


def test_lines_and_alignment():
    one = text_shape("abc", size=10)
    two = text_shape("abc\nabc", size=10)
    assert two.area == pytest.approx(2 * one.area, rel=1e-3)
    assert (two.bounds[3] - two.bounds[1]) > 2 * (one.bounds[3] - one.bounds[1])
    left = text_shape("abcdef\nab", size=10, align="left")
    right = text_shape("abcdef\nab", size=10, align="right")
    short = lambda g: g.intersection(box(-100, -100, 100, g.bounds[1] + 5))   # the second line
    assert short(left).bounds[0] < short(right).bounds[0]


def test_letter_spacing_widens():
    plain = text_shape("abc", size=10).bounds
    spaced = text_shape("abc", size=10, letter_spacing=2).bounds
    assert (spaced[2] - spaced[0]) - (plain[2] - plain[0]) == pytest.approx(4, abs=0.2)


def test_font_by_path():
    assert text_shape("abc", str(HEEBO), size=10).area == pytest.approx(text_shape("abc", "Heebo", size=10).area,
                                                                         rel=0.05)


def test_text_placement_and_rotation():
    t = Text("H", size=10, x=0.25, y=0.2)
    cx, cy = t.shape(100, 50).centroid.coords[0]
    assert (cx, cy) == pytest.approx((25, 40), abs=0.3)     # y counts from the top
    tall = Text("HHHH", size=10, rotation=90).shape(100, 50).bounds
    assert tall[3] - tall[1] > tall[2] - tall[0]


@pytest.mark.parametrize("kwargs, message", [
    (dict(style="paint", color=None), "needs a colour"),
    (dict(style="wavy"), "unknown text style"),
    (dict(size=0), "size must be positive"),
    (dict(color="nope"), "not a colour"),
])
def test_text_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Text("a", **kwargs)


# --- fonts -----------------------------------------------------------------------------------------

def test_bundled_font_and_weights():
    path, axes = fonts.font_file("heebo", weight=700)
    assert path == HEEBO and axes == {"wght": 700.0}
    assert fonts.font_file("Heebo", weight=2000)[1] == {"wght": 900.0}   # clamped to the font's range
    heebo = next(f for f in fonts.list_fonts() if f.family == "Heebo")
    assert heebo.source == "bundled" and "hebrew" in heebo.subsets and "100" in heebo.variants


def test_unknown_font_offline():
    with pytest.raises(ValueError, match="unknown font"):
        fonts.font_file("No Such Font")


def test_add_font(tmp_path):
    family = fonts.add_font(HEEBO.read_bytes(), "my font.ttf")
    assert family.family == "Heebo" and family.source == "local"
    assert len(list((tmp_path / "fonts" / "added").glob("*.ttf"))) == 1
    fonts.add_font(HEEBO.read_bytes(), "again.ttf")
    with pytest.raises(ValueError, match="could not read"):
        fonts.add_font(b"not a font", "bad.ttf")


def test_fonts_in_the_font_folder(tmp_path):
    folder = tmp_path / "fonts" / "mine"
    folder.mkdir(parents=True)
    (folder / "x.ttf").write_bytes(HEEBO.read_bytes())
    assert fonts.font_file("Heebo")[0].parent == folder   # your own copy wins over the bundled one


def test_google_fonts(monkeypatch, tmp_path):
    """A Google family is listed from the catalogue, then downloaded once on first use."""
    monkeypatch.setenv("IMG2PRINT_GOOGLE_FONTS", "1")
    calls = []

    def fake_get(url):
        calls.append(url)
        if url == fonts.GOOGLE_METADATA_URL:
            return b")]}'\n" + json.dumps({"familyMetadataList": [
                {"family": "Secular One", "category": "Sans Serif", "subsets": ["menu", "hebrew", "latin"],
                 "fonts": {"400": {}}, "popularity": 300}]}).encode()
        if url.startswith(fonts.GOOGLE_CSS_URL):
            assert "Secular%20One%3Aital%2Cwght%400%2C400" in url
            return b"@font-face { src: url(https://fonts.gstatic.com/s/secular/v1/x.ttf) format('truetype'); }"
        assert url == "https://fonts.gstatic.com/s/secular/v1/x.ttf"
        return HEEBO.read_bytes()

    monkeypatch.setattr(fonts, "_get", fake_get)
    listed = {f.family: f for f in fonts.list_fonts()}
    assert listed["Secular One"].source == "google" and listed["Secular One"].subsets == ["hebrew", "latin"]
    path, axes = fonts.font_file("secular one", weight=700)
    assert path.name == "Secular_One-400.ttf" and axes == {}
    assert text_shape("שלום", "Secular One", size=10).area > 0
    fonts.font_file("Secular One")
    assert len(calls) == 3   # the catalogue and the font, once each
    monkeypatch.setattr(fonts, "_catalog", None)
    monkeypatch.setenv("IMG2PRINT_GOOGLE_FONTS", "0")
    assert "Secular One" in {f.family for f in fonts.list_fonts()}   # the saved catalogue, offline


# --- on the model ----------------------------------------------------------------------------------

def text_settings(**text) -> dict:
    return dict(texts=[dict(dict(text="שלום", size=12, x=0.5, y=0.5), **text)])


def text_area(width=100, height=50, **text):
    return Text(**dict(dict(text="שלום", size=12, x=0.5, y=0.5), **text)).shape(width, height).area


def test_painted_text_gets_its_own_filament():
    model, _ = build(blank(), Settings(width=100, stacking="top", **text_settings(color="red")))
    assert [p.name for p in model] == ["white", "red"]
    assert model["red"].mesh.volume == pytest.approx(text_area() * 0.8, rel=0.01)
    assert model["red"].mesh.is_watertight


def test_text_in_a_colour_of_the_design_joins_that_part():
    s = Settings(width=100, stacking="top", **text_settings(color="#000000", x=0.3))
    model, layers = build(make_image(), s)
    assert [p.name for p in model] == ["white", "black"]
    ink = layers[1].geometry.union(s.texts[0].shape(layers[0].width, layers[0].height))
    assert model["black"].mesh.volume == pytest.approx(ink.area * 0.8, rel=0.01)


def plate_volume(thickness, width=100, height=50, radius=10):
    return img2print.rounded_rect(width, height, radius).area * thickness


def test_embossed_text_takes_the_surface_colour():
    model, _ = build(blank(), Settings(width=100, stacking="top", **text_settings(style="emboss", color=None, depth=1)))
    assert [p.name for p in model] == ["white"]
    assert model["white"].mesh.volume - plate_volume(2) == pytest.approx(text_area(), rel=0.02)
    assert model.bounds[1][2] == pytest.approx(2 + 1)
    assert model["white"].mesh.is_watertight


def test_engraved_text_is_cut_in():
    model, _ = build(blank(), Settings(width=100, stacking="full", thickness=3,
                                       **text_settings(style="engrave", color=None, depth=1)))
    assert plate_volume(3) - model["white"].mesh.volume == pytest.approx(text_area(), rel=0.02)
    assert model["white"].mesh.is_watertight


def test_engraved_coloured_text_shows_its_colour_at_the_bottom():
    model, _ = build(blank(), Settings(width=100, stacking="top", layer=0.8,
                                       **text_settings(style="engrave", color="black", depth=0.5)))
    black = model["black"].mesh
    assert tuple(black.bounds[:, 2]) == pytest.approx((1.2, 1.5))   # 0.3 mm of black under the cut
    assert black.volume == pytest.approx(text_area() * 0.3, rel=0.02)


def test_text_when_colour_by_layer():
    """By layers the text's colour gets its own band on top, so every layer still holds one filament."""
    layers = img2print.trace_colors(make_color_image(), width=100, colors=4)
    s = Settings(width=100, colors=4, stacking="layers", base=1, layer=0.5, corner_radius=0,
                 **text_settings(color="#00ff00", style="emboss", depth=0.6, y=0.85))
    model = build_model(layers, s)
    green = [p for p in model if p.color == "#00ff00"][0]
    assert model.filament_changes[-1] == (pytest.approx(1 + 3 * 0.5), green.name)
    assert green.mesh.bounds[1][2] == pytest.approx(1 + 4 * 0.5 + 0.6)
    tops = sorted(round(p.mesh.bounds[1][2], 6) for p in model)
    assert len(set(tops)) == len(tops)
    # Without a colour, embossed text takes the top band's colour.
    s = Settings(width=100, colors=4, stacking="layers", **text_settings(color=None, style="emboss"))
    model = build_model(layers, s)
    assert len(list(model)) == 4 and model.bounds[1][2] == pytest.approx(1.2 + 3 * 0.8 + 0.6)


def test_text_on_a_shape():
    s = Settings(recipe="shape", shape="box", shape_width=40, shape_depth=30, shape_height=20, face="front",
                 stacking="top", **text_settings(style="emboss", color="red", size=6, depth=1))
    model, _ = build(blank(), s)
    assert "red" in [p.name for p in model]
    # The model is moved to start at the origin: the text stands 1 mm out in front of the box.
    assert model["red"].mesh.bounds[0][1] == pytest.approx(0)
    assert model["white"].mesh.bounds[0][1] == pytest.approx(1)
    assert model.bounds[1].tolist() == pytest.approx([40, 31, 20])


def test_text_outside_the_plate_is_cut_off():
    s = Settings(width=100, stacking="top", **text_settings(color="red", x=0.98))
    model, _ = build(blank(), s)
    assert model["red"].mesh.bounds[1][0] <= 100 + 1e-6
    assert model["red"].mesh.volume < 0.8 * text_area(x=0.98) * 0.8


def test_text_only_plate_in_two_colour_mode():
    s = Settings(width=100, colors=None, stacking="layers", **text_settings(color="black"))
    model, layers = build(blank(), s)
    assert [p.name for p in model] == ["white", "black"] and layers[1].is_empty
    assert model.filament_changes == [(1.2, "black")]


def test_settings_with_texts_round_trip(tmp_path):
    s = Settings(width=80, **text_settings(style="engrave", color=None, font="Heebo", rotation=10))
    s.save(tmp_path / "s.json")
    loaded = Settings.load(tmp_path / "s.json")
    assert loaded == s and isinstance(loaded.texts[0], Text)
    with pytest.raises(ValueError, match="bad text"):
        Settings.from_dict({"texts": [{"text": "a", "colour": "red"}]})
    with pytest.raises(ValueError, match="needs a colour"):
        Settings.from_dict({"texts": [{"text": "a", "color": None}]})


def test_extrude_survives_points_a_hair_apart():
    """Clipping text to the surface can leave points 1e-14 mm apart; the mesh must stay closed."""
    from shapely.geometry import Polygon
    assert img2print.extrude(Polygon([(0, 0), (4, 0), (4, 1e-14), (4, 3), (2, 4), (0, 3)]), 1).is_volume


def test_trace_ignores_texts():
    a = trace_layers(make_image(), Settings(width=100))
    b = trace_layers(make_image(), Settings(width=100, **text_settings()))
    assert [x.area for x in a] == [x.area for x in b]


def test_extrude_falls_back_when_the_triangulation_fails(monkeypatch):
    """Earcut can leave an edge shared by four faces (seen with letters cut by the plate edge);
    then manifold's triangulation builds the solid instead."""
    import trimesh
    from shapely.geometry import Polygon
    broken = trimesh.creation.box((1, 1, 1))
    broken.faces = broken.faces[:-1]   # an open mesh, as earcut's bad output is not a volume
    monkeypatch.setattr(trimesh.creation, "extrude_polygon", lambda poly, height: broken)
    plate = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(2, 2), (4, 2), (4, 4), (2, 4)]])
    mesh = img2print.extrude(plate, 2)
    assert mesh.is_volume and mesh.volume == pytest.approx(96 * 2)
