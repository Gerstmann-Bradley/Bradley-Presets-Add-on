import bpy
import shutil
import requests
from pathlib import Path, PurePath
import bpy.utils.previews
from platform import system
from subprocess import Popen
import json
import os

from .constants import BRD_CONST_DATA  # Import constants from the add-on
from .Logger import log  # Import logger from the add-on
from .utils import connected_to_internet  # Import utility function from the add-on

class BRD_Asset(bpy.types.Operator):
    bl_idname = "bradley.add_asset"
    bl_label = "Setup Bradley's Asset Library"
    bl_description = "Setup a custom asset library for Bradley's add-on"

    def execute(self, context):

        # Detect version
        is_blender_5 = bpy.app.version >= (5, 0, 0)

        # Get all asset libraries
        asset_libraries = bpy.context.preferences.filepaths.asset_libraries

        # Define constants
        target_name = "BRD_Data"
        new_path = str(PurePath(BRD_CONST_DATA.Folder))

        # Find existing library
        matching_index = None
        for index, asset_library in enumerate(asset_libraries):
            if asset_library.name == target_name:
                matching_index = index
                break

        if matching_index is not None:
            lib = asset_libraries[matching_index]

            # Always update path
            lib.path = new_path

            # Only for Blender ≥ 5.0 → enforce PACK
            if is_blender_5:
                lib.import_method = 'PACK'
                print(
                    f"Asset library '{target_name}' found at index {matching_index}. "
                    f"Path updated to: {new_path}, import method forced to PACK."
                )
            else:
                print(
                    f"Asset library '{target_name}' found at index {matching_index}. "
                    f"Path updated to: {new_path}. (Import method left unchanged)"
                )

        else:
            # Add new asset library
            bpy.ops.preferences.asset_library_add()

            new_library = bpy.context.preferences.filepaths.asset_libraries[-1]

            new_library.name = target_name
            new_library.path = new_path

            # Blender ≥ 5.0 → PACK, older → LINK
            new_library.import_method = 'PACK' if is_blender_5 else 'LINK'

            print(
                f"Asset library '{target_name}' added with path: {new_library.path}, "
                f"import method set to {new_library.import_method}."
            )

        return {'FINISHED'}

class BRD_Remove(bpy.types.Operator):
    bl_idname = "bradley.remove_asset"
    bl_label = "Remove Bradley's Asset Library"
    bl_description = "Remove the asset library path before you disable the add-on"

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

        if matching_index is not None:
            # Remove the asset library
            bpy.ops.preferences.asset_library_remove(index=matching_index)
            print(f"Asset library '{target_name}' removed.")
        else:
            print(f"No asset library with name '{target_name}' found.")

        return {'FINISHED'}

class BRD_Update(bpy.types.Operator):
    bl_idname = "bradley.update"
    bl_label = "bradley update"

    def execute(self, context):
        # Check if there is an internet connection
        if connected_to_internet():
            # Send a request to GitHub to get the repository data
            r = requests.get(BRD_CONST_DATA.Repository)
            repo_contents = r.json()

            # Extract the preset and text file data from the repository
            preset_data = next((item for item in repo_contents if item["name"].endswith(".blend")), None)
            text_files_data = [item for item in repo_contents if item["name"].endswith(".txt")]

            if preset_data:
                sha = preset_data["sha"]
                log.debug(f"sha new -> {sha}")
                log.debug(f"sha current -> {BRD_CONST_DATA.__DYN__.sha}")
                version = preset_data["name"].lower().replace(" ", "")
                file_repo = preset_data["download_url"]

                log.debug(f"Preset github version: {version}")
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
                    or BRD_CONST_DATA.__DYN__.P_Version != version
                    or sha != BRD_CONST_DATA.__DYN__.sha
                    or not a
                ):
                    log.debug("Preset -> Updating")

                    # Remove previous preset file if necessary
                    if (
                        stuff["__DYN__"]["File_Location"]
                        and stuff["__DYN__"]["File_Location"] != "."
                        and a
                    ):
                        Path(stuff["__DYN__"]["File_Location"]).unlink()

                    # Download and save new preset file
                    local_filename = PurePath(
                        BRD_CONST_DATA.Folder,
                        BRD_CONST_DATA.__DYN__.B_Version,
                        "preset.blend",
                    )

                    with requests.get(file_repo, stream=True) as r:
                        with open(str(local_filename), "wb") as f:
                            shutil.copyfileobj(r.raw, f)
                    
                    # Move the file "blender_assets.cats" to BRD_CONST_DATA.Folder
                    for text_file_data in text_files_data:
                        if text_file_data["name"] == "blender_assets.cats.txt":
                            file_url = text_file_data["download_url"]
                            file_path = PurePath(BRD_CONST_DATA.Folder, "blender_assets.cats.txt")

                            with requests.get(file_url, stream=True) as r:
                                lines = r.text.splitlines()  # Split the text into lines
                                with open(str(file_path), "w", encoding="utf-8") as f:
                                    for line in lines:
                                        f.write(line + "\n")  # Write each line followed by a newline character
                        else:
                            # For other text files, move them to BRD_CONST_DATA.Folder/B_VERSION
                            text_file_url = text_file_data["download_url"]
                            text_file_name = text_file_data["name"]
                            text_file_path = PurePath(BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version, text_file_name)

                            with requests.get(text_file_url, stream=True) as r:
                                lines = r.text.splitlines()  # Split the text into lines
                                with open(str(text_file_path), "w", encoding="utf-8") as f:
                                    for line in lines:
                                        f.write(line + "\n")  # Write each line followed by a newline character
                                    
                    # Update add-on settings
                    stuff["__DYN__"] = {
                        "New": False,
                        "P_Version": version,
                        "B_Version": BRD_CONST_DATA.__DYN__.B_Version,
                        "File_Location": str(local_filename),
                        "Debug": BRD_CONST_DATA.__DYN__.Debug,
                        "sha": sha,
                    }

                    with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
                        f.write(json.dumps(stuff))
                    log.debug("Preset -> Updated")
                else:
                    log.debug("Preset -> Up to Date")
            else:
                log.debug("No preset data found in the repository.")
        else:
            log.debug("No internet connection available")
        return {"FINISHED"}

class BRD_Force_Update(bpy.types.Operator):
    bl_idname = "bradley.force_update"
    bl_label = "BRD_Force_Update"

    def execute(self, context):
        # Check if there is an internet connection
        if connected_to_internet():
            # Send a request to GitHub to get the repository data
            r = requests.get(BRD_CONST_DATA.Repository)
            repo_contents = r.json()

            # Extract the preset and text file data from the repository
            preset_data = next((item for item in repo_contents if item["name"].endswith(".blend")), None)
            text_files_data = [item for item in repo_contents if item["name"].endswith(".txt")]

            if preset_data:
                sha = preset_data["sha"]
                log.debug(f"sha new -> {sha}")
                log.debug(f"sha current -> {BRD_CONST_DATA.__DYN__.sha}")
                version = preset_data["name"].lower().replace(" ", "")
                file_repo = preset_data["download_url"]

                log.debug(f"Preset github version: {version}")
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

                # Remove previous preset file if necessary
                if (
                    stuff["__DYN__"]["File_Location"]
                    and stuff["__DYN__"]["File_Location"] != "."
                    and a
                ):
                    Path(stuff["__DYN__"]["File_Location"]).unlink()

                # Download and save new preset file
                local_filename = PurePath(
                    BRD_CONST_DATA.Folder,
                    BRD_CONST_DATA.__DYN__.B_Version,
                    "preset.blend",
                )

                with requests.get(file_repo, stream=True) as r:
                    with open(str(local_filename), "wb") as f:
                        shutil.copyfileobj(r.raw, f)
                    
                # Move the file "blender_assets.cats" to BRD_CONST_DATA.Folder
                for text_file_data in text_files_data:
                    if text_file_data["name"] == "blender_assets.cats.txt":
                        file_url = text_file_data["download_url"]
                        file_path = PurePath(BRD_CONST_DATA.Folder, "blender_assets.cats.txt")

                        with requests.get(file_url, stream=True) as r:
                            lines = r.text.splitlines()  # Split the text into lines
                            with open(str(file_path), "w", encoding="utf-8") as f:
                                for line in lines:
                                    f.write(line + "\n")  # Write each line followed by a newline character
                    else:
                        # For other text files, move them to BRD_CONST_DATA.Folder/B_VERSION
                        text_file_url = text_file_data["download_url"]
                        text_file_name = text_file_data["name"]
                        text_file_path = PurePath(BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version, text_file_name)

                        with requests.get(text_file_url, stream=True) as r:
                            lines = r.text.splitlines()  # Split the text into lines
                            with open(str(text_file_path), "w", encoding="utf-8") as f:
                                for line in lines:
                                    f.write(line + "\n")  # Write each line followed by a newline character

                    # Update add-on settings
                    stuff["__DYN__"] = {
                        "New": False,
                        "P_Version": version,
                        "B_Version": BRD_CONST_DATA.__DYN__.B_Version,
                        "File_Location": str(local_filename),
                        "Debug": BRD_CONST_DATA.__DYN__.Debug,
                        "sha": sha,
                    }

                    with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
                        f.write(json.dumps(stuff))
                    log.debug("Preset -> Updated")
            else:
                log.debug("No preset data found in the repository.")
        else:
            log.debug("No internet connection available")

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
preset_help = [BRD_Folder, BRD_Asset, BRD_Remove, BRD_Update, BRD_Force_Update]