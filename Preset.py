import bpy
import shutil
import requests
from pathlib import Path, PurePath
import bpy.utils.previews
from platform import system
from subprocess import Popen
import json

from .constants import BRD_CONST_DATA
from .Logger import log
from .utils import connected_to_internet

# Define the operator class for updating the add-on
class BRD_Update(bpy.types.Operator):
    bl_idname = "bradley.update"
    bl_label = "bradley update"

    def execute(self, context):
        # Check for internet connection
        if connected_to_internet():
            # Send request to GitHub to get repository data
            self.r = requests.get(BRD_CONST_DATA.Repository)
            self.r = self.r.json()

            # Extract preset data from the repository
            self.preset_data = [i for i in self.r if i["name"].endswith(".blend")][0]
            self.sha = self.preset_data["sha"]
            self.version = self.preset_data["name"].lower().replace(" ", "")

            # Check if the local version is different from the GitHub version
            if (
                BRD_CONST_DATA.__DYN__.P_Version == "__"
                or BRD_CONST_DATA.__DYN__.P_Version != self.version
                or self.sha != BRD_CONST_DATA.__DYN__.sha
                or not Path(BRD_CONST_DATA.Folder / BRD_CONST_DATA.__DYN__.B_Version).iterdir()
            ):
                log.debug("Preset -> Updating")

                # Remove previous preset file if necessary
                with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
                    stuff = json.load(f)
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
                with requests.get(self.preset_data["download_url"], stream=True) as r:
                    with open(str(self.local_filename), "wb") as f:
                        shutil.copyfileobj(r.raw, f)

                # Update add-on settings
                stuff["__DYN__"] = {
                    "New": False,
                    "P_Version": self.version,
                    "B_Version": BRD_CONST_DATA.__DYN__.B_Version,
                    "File_Location": str(self.local_filename),
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

            # Send request to GitHub to get repository data
            self.r = requests.get(BRD_CONST_DATA.Repository)
            self.r = self.r.json()

            # Extract preset data from the repository
            self.preset_data = [i for i in self.r if i["name"].endswith(".blend")][0]
            self.sha = self.preset_data["sha"]
            self.version = self.preset_data["name"].lower().replace(" ", "")

            # Remove previous preset file if necessary
            with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
                stuff = json.load(f)
            if (
                bool(stuff["__DYN__"]["File_Location"])
                and not stuff["__DYN__"]["File_Location"] == "."
            ):
                BRD_CONST_DATA.File_Location().unlink()

            # Download and save new preset file
            self.local_filename = PurePath(
                BRD_CONST_DATA.Folder,
                BRD_CONST_DATA.__DYN__.B_Version,
                "preset.blend",
            )
            with requests.get(self.preset_data["download_url"], stream=True) as r:
                with open(str(self.local_filename), "wb") as f:
                    shutil.copyfileobj(r.raw, f)

            # Update add-on settings
            stuff["__DYN__"] = {
                "New": False,
                "P_Version": self.version,
                "B_Version": BRD_CONST_DATA.__DYN__.B_Version,
                "File_Location": str(self.local_filename),
                "Debug": BRD_CONST_DATA.__DYN__.Debug,
                "sha": self.sha,
            }
            with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
                f.write(json.dumps(stuff))

            log.debug("Preset -> Updated")

            # Reload data
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

        # Open file explorer at the preset folder location

preset_help = [BRD_Folder, BRD_Link, BRD_Update, BRD_Force_Update]