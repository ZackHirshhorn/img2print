import io
import json
import zipfile
from urllib.parse import quote

import pytest
import trimesh

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import img2print  # noqa: E402
from img2print.cli import main  # noqa: E402
from img2print.settings import Settings  # noqa: E402
from img2print.web import api, cache  # noqa: E402
from img2print.web.server import create_app  # noqa: E402

from test_img2print import SVG, assert_colour_by_layer, make_color_image, make_image, make_pdf  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def png(im=None) -> bytes:
    buf = io.BytesIO()
    (im or make_image()).save(buf, format="PNG")
    return buf.getvalue()


def upload(client, data: bytes, filename="logo.png") -> dict:
    r = client.post("/api/uploads", files={"file": (filename, data)})
    assert r.status_code == 200, r.text
    return r.json()


def error(r) -> str:
    """The error message of a response, whether detail is a string or pydantic's list of {msg}."""
    detail = r.json()["detail"]
    return detail if isinstance(detail, str) else " ".join(d["msg"] for d in detail)


# --- info and uploads ---

def test_info_and_health(client):
    info = client.get("/api/info").json()
    assert info["version"] == img2print.__version__
    assert "PLA" in info["materials"]
    assert info["materials"] and info["max_upload_mb"] == api.MAX_UPLOAD_MB
    assert client.get("/api/health").json() == {"ok": True}


def test_upload_png(client):
    up = upload(client, png())
    assert up["kind"] == "raster"
    assert (up["width"], up["height"], up["pages"]) == (200, 100, 1)
    shares = {s["color"]: s["share"] for s in up["colors"]}
    assert set(shares) == {"#ffffff", "#000000"}
    assert shares["#000000"] == pytest.approx((3600 + 3200) / 20000, abs=0.02)
    assert up["colors"][0]["color"] == "#ffffff"   # largest first


def test_upload_svg(client):
    up = upload(client, SVG, "logo.svg")
    assert up["kind"] == "svg"
    assert (up["width"], up["height"]) == (200, 100)
    assert {"#000000", "#dc1e1e", "#1e3cc8"} <= {s["color"] for s in up["colors"]}


def test_upload_pdf(client):
    data = make_pdf()   # skips without pymupdf
    up = upload(client, data, "logo.pdf")
    assert (up["kind"], up["pages"]) == ("pdf", 1)
    assert (up["width"], up["height"]) == (200, 100)


def test_upload_errors(client, monkeypatch):
    r = client.post("/api/uploads", files={"file": ("empty.png", b"")})
    assert r.status_code == 422
    r = client.post("/api/uploads", files={"file": ("junk.png", b"not an image")})
    assert r.status_code == 422 and "could not read" in error(r)
    monkeypatch.setattr(api, "MAX_UPLOAD_MB", 1)
    r = client.post("/api/uploads", files={"file": ("big.png", b"x" * (2**20 + 1000))})
    assert r.status_code == 413 and "1 MB" in error(r)


def test_unknown_ids(client):
    r = client.post("/api/trace", json={"upload_id": "nope"})
    assert r.status_code == 404 and "upload the file again" in error(r)
    assert client.get("/api/models/nope/model.3mf").status_code == 404
    assert client.get("/api/nothing").status_code == 404


# --- trace ---

def test_trace_two_colour(client):
    up = upload(client, png())
    r = client.post("/api/trace", json={"upload_id": up["id"], "settings": {"width": 100}})
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["width"], t["height"]) == pytest.approx((100, 50))
    assert [(l["name"], l["color"]) for l in t["layers"]] == [("white", "#ffffff"), ("black", "#000000")]
    ink = img2print.trace_image(make_image(), width=100).area
    assert t["layers"][1]["area"] == pytest.approx(ink, rel=1e-6)
    assert t["layers"][0]["area"] == pytest.approx(100 * 50 - ink, rel=1e-3)
    assert t["layers"][1]["path"].startswith("M") and t["layers"][1]["path"].endswith("Z")


def test_trace_colour(client):
    up = upload(client, png(make_color_image()))
    r = client.post("/api/trace", json={"upload_id": up["id"], "settings": {"width": 100, "colors": 4}})
    assert r.status_code == 200, r.text
    layers = r.json()["layers"]
    assert [l["name"] for l in layers] == ["white", "black", "red", "blue"]
    assert [l["area"] for l in layers[1:]] == pytest.approx([900, 600, 400], rel=0.02)


def test_trace_is_reused_for_plate_options(client, monkeypatch):
    up = upload(client, png())
    calls = []
    real = api.trace_layers
    monkeypatch.setattr(api, "trace_layers", lambda *a: calls.append(1) or real(*a))
    for base in (1.0, 2.0):
        body = {"upload_id": up["id"], "settings": {"width": 77, "base": base, "raised": base > 1}}
        assert client.post("/api/trace", json=body).status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize("settings, message", [
    ({"width": 50, "height": 20}, "only one of width"),
    ({"threshold": 3}, "threshold must be between 0 and 1"),
    ({"colors": 1}, "at least 2"),
    ({"palette": ["white", "notacolour"]}, "notacolour"),
])
def test_bad_settings(client, settings, message):
    up = upload(client, png())
    r = client.post("/api/trace", json={"upload_id": up["id"], "settings": settings})
    assert r.status_code == 422
    assert message in error(r)


def test_blank_image(client):
    from PIL import Image
    up = upload(client, png(Image.new("L", (20, 20), 255)))
    r = client.post("/api/trace", json={"upload_id": up["id"]})
    assert r.status_code == 200 and r.json()["layers"][1]["area"] == 0   # nothing to show yet
    r = client.post("/api/models", json={"upload_id": up["id"]})
    assert r.status_code == 422                                          # but nothing to print either


# --- build and downloads ---

def get_file(client, url: str) -> bytes:
    r = client.get(url)
    assert r.status_code == 200, r.text
    return r.content


@pytest.mark.parametrize("image, settings, names", [
    (make_image, {"width": 100, "raised": True}, ["white", "black"]),
    (make_color_image, {"width": 100, "colors": 4}, ["white", "black", "red", "blue"]),
])
def test_build_and_download(client, image, settings, names):
    up = upload(client, png(image()))
    r = client.post("/api/models", json={"upload_id": up["id"], "settings": settings, "material": "PETG"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["material"] == "PETG"
    assert m["size"][:2] == pytest.approx([100, 50])
    assert [p["name"] for p in m["parts"]] == names
    assert all(p["watertight"] and p["grams"] > 0 for p in m["parts"])
    assert len(m["trace"]["layers"]) == len(names)

    glb = trimesh.load(io.BytesIO(get_file(client, m["glb_url"])), file_type="glb")
    assert len(glb.geometry) == len(names)
    threemf = trimesh.load(io.BytesIO(get_file(client, m["threemf_url"])), file_type="3mf")
    assert len(threemf.geometry) == len(names)
    for part in m["parts"]:
        mesh = trimesh.load(io.BytesIO(get_file(client, part["stl_url"])), file_type="stl")
        assert mesh.is_watertight
        assert mesh.volume == pytest.approx(part["volume"], rel=1e-3)
    with zipfile.ZipFile(io.BytesIO(get_file(client, m["zip_url"]))) as z:
        assert sorted(z.namelist()) == sorted(["logo.3mf"] + [f"logo_{n}.stl" for n in names])

    assert client.get(m["glb_url"].replace("preview.glb", "parts/nope.stl")).status_code == 404


def test_build_shape(client):
    up = upload(client, png(make_color_image()))
    settings = {"recipe": "shape", "shape": "box", "shape_width": 40, "shape_depth": 30, "shape_height": 20,
                "face": "front", "colors": 4, "width": None, "stacking": "top", "base_color": "white"}
    r = client.post("/api/models", json={"upload_id": up["id"], "settings": settings})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["size"] == pytest.approx([40, 30, 20])
    assert [p["name"] for p in m["parts"]] == ["white", "black", "red", "blue"]
    assert all(p["watertight"] for p in m["parts"])
    assert (m["trace"]["width"], m["trace"]["height"]) == pytest.approx((40, 20))   # fits the face
    r = client.post("/api/trace", json={"upload_id": up["id"], "settings": dict(settings, shape="cylinder")})
    assert r.status_code == 422 and "curved" in error(r)


@pytest.mark.parametrize("image, settings, floor_to_base", [
    (make_image, {"colors": 2}, 3),
    (make_color_image, {"colors": 4}, 3),
    (make_color_image, {"colors": 4, "recipe": "shape", "shape_height": 20, "face": "top", "width": None}, 20),
])
def test_by_layers_is_colour_by_layer(client, image, settings, floor_to_base):
    """Whatever else it sends, "By layers" from the client builds colour by layer: every colour in
    its own band above the last, so one nozzle prints it by swapping filament at the given heights."""
    up = upload(client, png(image()))
    settings = {"width": 100, "stacking": "layers", "raised": False, "base": 3, "layer": 0.6,
                "corner_radius": 8, "padding": 3, **settings}
    r = client.post("/api/models", json={"upload_id": up["id"], "settings": settings})
    assert r.status_code == 200, r.text
    m = r.json()
    meshes = [trimesh.load(io.BytesIO(get_file(client, p["stl_url"])), file_type="stl") for p in m["parts"]]
    assert_colour_by_layer(meshes, base=floor_to_base, layer=0.6)
    assert [(c["height"], c["name"], c["color"]) for c in m["filament_changes"]] == [
        (pytest.approx(floor_to_base + i * 0.6), p["name"], p["color"]) for i, p in enumerate(m["parts"][1:])]


def test_build_unknown_material(client):
    up = upload(client, png())
    r = client.post("/api/models", json={"upload_id": up["id"], "material": "wood"})
    assert r.status_code == 422 and "unknown material" in error(r)


def test_hebrew_file_name(client):
    up = upload(client, png(), "לוגו.png")
    assert up["filename"] == "לוגו.png"
    m = client.post("/api/models", json={"upload_id": up["id"]}).json()
    r = client.get(m["threemf_url"])
    disposition = r.headers["content-disposition"]
    assert disposition.isascii()
    assert f"filename*=UTF-8''{quote('לוגו.3mf')}" in disposition


def test_frontend_fallback(client):
    r = client.get("/")
    assert r.status_code == 200 and "img2print" in r.text


# --- Settings, Cache and the CLI's settings files ---

def test_settings_round_trip(tmp_path):
    s = Settings(height=40, raised=True, palette=["white", "black", "#f00"], page=2)
    assert Settings.from_json(s.to_json()) == s
    s.save(tmp_path / "s.json")
    assert Settings.load(tmp_path / "s.json") == s
    assert s.color_mode and not Settings().color_mode
    assert s.size() == {"width": None, "height": 40, "longest": None, "page": 1}


def test_settings_rejects_unknown_and_invalid():
    with pytest.raises(ValueError, match="unknown setting.*colour"):
        Settings.from_dict({"colour": 3})
    for bad in ({"width": 1, "longest": 2}, {"base": 0}, {"simplify": -1}, {"page": 0}, {"recipe": "mug"}):
        with pytest.raises(ValueError):
            Settings(**bad)


def test_cache_evicts_least_recently_used():
    c = cache.Cache(max_bytes=10)
    c.put("a", 1, 4)
    c.put("b", 2, 4)
    assert c.get("a") == 1          # a is now newer than b
    c.put("c", 3, 4)
    assert (c.get("a"), c.get("b"), c.get("c")) == (1, None, 3)
    assert c.size == 8
    c.put("huge", 4, 100)           # the newest item stays even when over budget
    assert len(c) == 1 and c.get("huge") == 4


def test_cache_ttl(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    c = cache.Cache(max_bytes=100, ttl=10)
    c.put("a", 1, 1)
    now[0] += 5
    assert c.get("a") == 1          # use refreshes the timer
    now[0] += 8
    assert c.get("a") == 1
    now[0] += 11
    assert c.get("a") is None and len(c) == 0


def test_cli_settings_file(tmp_path, capsys):
    src = tmp_path / "design.png"
    make_image().save(src)
    first = tmp_path / "first.json"
    main([str(src), "--width", "80", "--raised", "--save-settings", str(first)])
    assert json.loads(first.read_text())["width"] == 80
    assert "80.0 x 40.0 mm" in capsys.readouterr().out

    # Flags given override the file; a size flag replaces the file's size; the rest is kept.
    second = tmp_path / "second.json"
    main([str(src), "--settings", str(first), "--height", "30", "--save-settings", str(second)])
    assert "60.0 x 30.0 mm" in capsys.readouterr().out
    saved = Settings.load(second)
    assert (saved.width, saved.height, saved.raised) == (None, 30, True)

    bad = tmp_path / "bad.json"
    bad.write_text('{"colour": 3}')
    with pytest.raises(SystemExit):
        main([str(src), "--settings", str(bad)])
