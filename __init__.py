# Import necessary modules and classes from Blender and Python standard library
import bpy
from pathlib import Path, PurePath
from bpy.app.handlers import persistent
import bpy.utils.previews
import json
import threading

# Import local modules from the add-on
from .Preset import preset_help
from .constants import BRD_CONST_DATA
from .utils import flatten

# Import Panels module from the add-on (not used in the code)
from . import Panels

# Define information about the add-on (name, description, version, etc.)
bl_info = {
    "name": "Bradley's Geo Node Presets",
    "description": "This is a geometry node preset made by Bradley's animation, and possibly ferret",
    "author": "Possibly Ferret | Bradley",
    "version": (2, 1, 0),
    "blender": (5, 0, 0),
    "location": "GeometryNode",
    "support": "COMMUNITY",
    "category": "Node",
    "warning": "Restart Blender after First Installation & Activation. Disregard this warning if you've done that already.",
}

# Initialize an empty dictionary to store preview collections for custom icons
BRD_preview_collections = {}

# Global variable to track whether the Blender session is starting
BRD_SESSION = True

# Define an updater function for the BRD_Preference class
# It will save the "debugging" property to a JSON settings file when updated
def updater(self, context):
    print(self.debugging)
    with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
        stuff = json.load(f)
        stuff["__DYN__"]["Debug"] = self.debugging
        with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
            f.write(json.dumps(stuff))

# Custom Blender preference panel (AddonPreferences) for the add-on
class BRD_Preference(bpy.types.AddonPreferences):
    bl_idname = __name__

    # Enum property to switch between "Socials" and "Settings" tabs
    ui_tab: bpy.props.EnumProperty(
        name="Preferences Tab",
        items=[
            ("Socials", "Socials", ""),
            ("Settings", "Settings", ""),
        ],
        default="Settings",
    )

    # Boolean property for debugging, which calls the updater function when updated
    debugging: bpy.props.BoolProperty(update=updater, default=False)

    # Boolean property for experimental features
    experimental: bpy.props.BoolProperty(default=False)

    # Method to draw the preferences UI
    def draw(self, context):
        layout = self.layout

        # Create a row with the "ui_tab" property as a switch
        row = layout.row()
        row.prop(self, "ui_tab", expand=True)
        box = layout.box()

        # If the "Socials" tab is selected, show social media links
        if self.ui_tab == "Socials":
            col = box.column()

            for i in BRD_CONST_DATA.Socials:
                op = col.operator(
                    "wm.url_open",
                    text=i.Name,
                    emboss=True,
                    depress=False,
                    icon_value=BRD_preview_collections["Social_icons"][i.Name].icon_id,
                )
                op.url = i.Url

        # If the "Settings" tab is selected, show various settings options
        elif self.ui_tab == "Settings":
            col = box.column()
            row = col.row()
            row.operator(
                "bradley.folder",
                text="Open Folder of Presets File ",
                icon="FILE_FOLDER",
            )
            row = col.row()
            row.operator("bradley.force_update", text="Force Update Presets")
            row = col.row()
            row.operator("bradley.remove_asset", text="Remove Asset Library Path", icon="PANEL_CLOSE")
            row = col.row()
            row.prop(self, "debugging", toggle=True)
            row.prop(self, "experimental", toggle=True)


def _do_network_update():
    """Runs in background thread — no bpy calls allowed here"""
    try:
        bpy.ops.bradley.update()
    except Exception as e:
        print(f"BRD: Background update failed: {e}")


@persistent
def run_after_load(*dummy):
    global BRD_SESSION

    # Relocate library — must stay on main thread (uses bpy)
    if any("preset.blend" in a for a in [i.name for i in bpy.data.libraries]):
        bpy.ops.wm.lib_relocate(
            library=[s for s in [i.name for i in bpy.data.libraries] if "preset.blend" in s][0],
            directory=str(PurePath(BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version)),
            filename="preset.blend",
        )

    if BRD_SESSION:
        BRD_SESSION = False  # only run once on first startup, not on every file open
        bpy.ops.bradley.add_asset()  # keep on main thread (touches bpy preferences)

        # Spin up the network update in the background — won't block Blender
        thread = threading.Thread(target=_do_network_update, daemon=True)
        thread.start()


# Flatten a nested list of classes into a single list
classes = flatten(
    [
        BRD_Preference,
    ]
    + preset_help
    + Panels.panels
)


def register():
    print("=" * 20)
    print(__package__)
    print("=" * 20)

    # Create a new previews collection to store custom icons for social media links
    pcoll = bpy.utils.previews.new()
    icon_dir = PurePath(Path(__file__).parents[0], "icons")

    for i in BRD_CONST_DATA.Socials:
        pcoll.load(i.Name, str(PurePath(icon_dir, i.Icon)), "IMAGE")

    BRD_preview_collections["Social_icons"] = pcoll

    for i in classes:
        bpy.utils.register_class(i)

    bpy.app.handlers.load_post.append(run_after_load)


def unregister():
    for i in classes:
        bpy.utils.unregister_class(i)

    # FIX: was incorrectly using append instead of remove
    if run_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(run_after_load)


if __name__ == "__main__":
    register()