"""Example: the Pinocchio pizza logo as a raised sign with a contour-following plate.

Run from the img2print folder:  python examples/pinocchio_sign.py
"""

from pathlib import Path

from shapely.geometry import Polygon

import img2print

here = Path(__file__).resolve().parent
logo = next(here.parent.parent.glob("*.png"))   # the logo next to this project

art = img2print.trace_image(logo, width=120)
plate = art.geometry.buffer(4).buffer(-1).buffer(1)   # 4 mm outline, small details smoothed away
plate = max(img2print.geometry.as_polygons(plate), key=lambda p: p.area)  # keep the main outline
plate = Polygon(plate.exterior)    # fill holes so the plate is one solid piece

model = img2print.two_color_tile(art, plate=plate, base=2.0, layer=1.0, raised=True)
print(model.summary())
for path in model.export(here / "output" / "pinocchio_sign"):
    print("wrote", path)
