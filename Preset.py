import bpy
import shutil
import requests
from pathlib import Path, PurePath
import bpy.utils.previews
from platform import system
from subprocess import Popen
import json

from .constants import BRD_CONST_DATA  # Import constants from the add-on
from .Logger import log  # Import logger from the add-on
from .utils import connected_to_internet  # Import utility function from the add-on

class BRD_Asset(bpy.types.Operator):
    bl_idname = "bradley.add_asset"
    bl_label = "Setup Bradley's Asset Library"
    bl_description = "Setup a custom asset library for Bradley's add-on"

    def execute(self, context):
        # Get all asset libraries
        asset_libraries = bpy.context.preferences.filepaths.asset_libraries

        # Define the target name you want to find (e.g., "Data")
        target_name = "Data"

        # Initialize the index
        matching_index = None

        # Iterate through asset libraries
        for index, asset_library in enumerate(asset_libraries):
            if asset_library.name == target_name:
                matching_index = index
                break

        # Set a new path for the asset library
        if matching_index is not None:
            new_path = str(PurePath(BRD_CONST_DATA.Folder))
            asset_libraries[matching_index].path = new_path
            print(f"Asset library '{target_name}' found at index {matching_index}. Path updated to: {new_path}")
        else:
            # Add a new asset library
            bpy.ops.preferences.asset_library_add()

            # Get the newly added library (which is the last one in the list)
            new_library = bpy.context.preferences.filepaths.asset_libraries[-1]

            # Set a custom name for the asset library
            new_library.name = "Data"

            # Set the import method to "LINK" (instead of the default "APPEND_REUSE")
            new_library.import_method = 'LINK'

            # Set the asset library path to the "Data" folder
            new_library.path = str(PurePath(BRD_CONST_DATA.Folder))
            print(f"Asset library '{target_name}' added with path: {str(PurePath(BRD_CONST_DATA.Folder))}")

        return {'FINISHED'}

# Define the operator class for updating the add-on
class BRD_Update(bpy.types.Operator):
    bl_idname = "bradley.update"
    bl_label = "bradley update"

    def execute(self, context):
        # Check if there is an internet connection
        if connected_to_internet():
            # Send a request to GitHub to get the repository data
            self.r = requests.get(BRD_CONST_DATA.Repository)
            self.r = self.r.json()

            # Extract the preset data from the repository
            self.preset_data = [i for i in self.r if i["name"].endswith(".blend")][0]
            self.sha = self.preset_data["sha"]
            log.debug(f"sha new -> {self.sha}")
            log.debug(f"sha current -> {BRD_CONST_DATA.__DYN__.sha}")
            self.version = self.preset_data["name"].lower().replace(" ", "")
            self.file_repo = self.preset_data["download_url"]

            log.debug(f"Preset github version: {self.version}")
            log.debug(f"Preset local version: {BRD_CONST_DATA.__DYN__.P_Version}")

            with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
                stuff = json.load(f)
            a = [
                i
                for i in Path(
                    PurePath(BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version)
                ).iterdir()
                if i.name.endswith(".blend")
            ]

            # Check if the preset needs updating
            if (
                BRD_CONST_DATA.__DYN__.P_Version == "__"
                or BRD_CONST_DATA.__DYN__.P_Version != self.version
                or self.sha != BRD_CONST_DATA.__DYN__.sha
                or a == []
            ):
                log.debug("Preset -> Updating")

                # Remove previous preset file if necessary
                if (
                    bool(stuff["__DYN__"]["File_Location"])
                    and not stuff["__DYN__"]["File_Location"] == "."
                    and a != []
                ):
                    BRD_CONST_DATA.File_Location().unlink()

                # Download and save new preset file
                self.local_filename = PurePath(
                    BRD_CONST_DATA.Folder,
                    BRD_CONST_DATA.__DYN__.B_Version,
                    "preset.blend",
                )

                File_Location = str(self.local_filename)
                P_Version = self.version

                with requests.get(self.file_repo, stream=True) as r:
                    with open(str(self.local_filename), "wb") as f:
                        shutil.copyfileobj(r.raw, f)

                # Update add-on settings
                stuff["__DYN__"] = {
                    "New": False,
                    "P_Version": P_Version,
                    "B_Version": BRD_CONST_DATA.__DYN__.B_Version,
                    "File_Location": File_Location,
                    "Debug": BRD_CONST_DATA.__DYN__.Debug,
                    "sha": self.sha,
                }

                with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
                    f.write(json.dumps(stuff))

                log.debug("Preset -> Updated")

            else:
                log.debug("Preset -> Up to Date")
        else:
            log.debug("No internet connection available")
        return {"FINISHED"}

class BRD_Link(bpy.types.Operator):
    bl_idname = "bradley.link"
    bl_label = "bradley link"

    def execute(self, context):
        # Check if the preset is already linked
        if [
            i
            for i in Path(
                PurePath(BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version)
            ).iterdir()
            if i.name.endswith(".blend")
        ][0] in bpy.data.libraries.keys():
            return {"FINISHED"}

        self.installed = [i.name for i in bpy.data.node_groups]
        self.por = []

        # Load preset and link node groups
        with bpy.data.libraries.load(
            str(BRD_CONST_DATA.File_Location().resolve()),
            link=True,
        ) as (data_from, data_to):
            for i in data_from.node_groups:
                if i.startswith("G_") or i.startswith("S_"):
                    if not i in self.installed:
                        self.por.append(i)
            log.debug("Linking node groups")
            log.debug(
                "Node Imports :\n" + "\n".join(["- " + i for i in self.por]),
                multi_line=True,
            )
            data_to.node_groups = self.por

        return {"FINISHED"}


class BRD_Force_Update(bpy.types.Operator):
    bl_idname = "bradley.force_update"
    bl_label = "BRD_Force_Update"

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        # Check for internet connection
        if connected_to_internet():
            log.debug("Force Update")

            self.r = requests.get(BRD_CONST_DATA.Repository)
            self.r = self.r.json()

            self.preset_data = [i for i in self.r if i["name"].endswith(".blend")][0]

            self.sha = self.preset_data["sha"]
            log.debug(f"sha new -> {self.sha}")
            log.debug(f"sha current -> {BRD_CONST_DATA.__DYN__.sha}")
            self.version = self.preset_data["name"].lower().replace(" ", "")

            self.file_repo = self.preset_data["download_url"]

            log.debug(f"Preset github version: {self.version}")
            log.debug(f"Preset local version: {BRD_CONST_DATA.__DYN__.P_Version}")

            with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
                stuff = json.load(f)

                log.debug("Preset -> Updating")

                if (
                    bool(stuff["__DYN__"]["File_Location"])
                    and not stuff["__DYN__"]["File_Location"] == "."
                ):

                    BRD_CONST_DATA.File_Location().unlink()

                self.local_filename = PurePath(
                    BRD_CONST_DATA.Folder,
                    BRD_CONST_DATA.__DYN__.B_Version,
                    "preset.blend",
                )

                File_Location = str(self.local_filename)
                P_Version = self.version

                with requests.get(self.file_repo, stream=True) as r:
                    with open(str(self.local_filename), "wb") as f:
                        shutil.copyfileobj(r.raw, f)

                stuff["__DYN__"] = {
                    "New": False,
                    "P_Version": P_Version,
                    "B_Version": BRD_CONST_DATA.__DYN__.B_Version,
                    "File_Location": File_Location,
                    "Debug": BRD_CONST_DATA.__DYN__.Debug,
                    "sha": self.sha,
                }

                with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
                    f.write(json.dumps(stuff))

                log.debug("Preset -> Updated")

                a = [
                    s
                    for s in [i.name for i in bpy.data.libraries]
                    if "preset.blend" in s
                ][0]

                log.debug(f"Reloading data")

                bpy.data.libraries[a].reload()

        else:
            log.debug("no internet connection available")

        return {"FINISHED"}


class BRD_Folder(bpy.types.Operator):
    bl_idname = "bradley.folder"
    bl_label = "bradley folder"

    def execute(self, context):

        self.place = str(BRD_CONST_DATA.File_Location().resolve())
        log.debug(f"Opening {self.place}")

        if system() == "Windows":
            Popen(["explorer", "/select,", str(self.place)])

        elif system() == "Darwin":
            Popen(["open", str(self.place)])

        else:
            Popen(["xdg-open", str(self.place)])

        return {"FINISHED"}


# List of operators provided by the add-on
preset_help = [BRD_Folder, BRD_Link, BRD_Asset, BRD_Update, BRD_Force_Update]