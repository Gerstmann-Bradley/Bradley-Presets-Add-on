from pathlib import Path, PurePath
import bpy
from .Dtcls import BRD_Datas, __DYN__, Social
import json

Folder = Path(Path(__file__).parents[0], "Data")

with open(PurePath(Folder, "settings.json"), "r") as f:
    stuff = json.loads(f.read())

repo = stuff["Github"]["Repository"]

# Always use local Blender version — no network call here
version = str(bpy.app.version_string)[0:3]

# Make sure the folder exists
Path(PurePath(Folder, version)).mkdir(parents=True, exist_ok=True)

BRD_CONST_DATA = BRD_Datas(
    __package__,
    [Social(**i) for i in stuff["Socials"]],
    f"https://api.github.com/repos/{repo}/contents/{version}",
    Folder,
    __DYN__(
        stuff["__DYN__"]["P_Version"],
        version,
        stuff["__DYN__"]["New"],
        stuff["__DYN__"]["Debug"],
        stuff["__DYN__"]["sha"],
    ),
)