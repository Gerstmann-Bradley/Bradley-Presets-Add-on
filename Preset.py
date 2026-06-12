import bpy
import re
import shutil
import requests
import time
from pathlib import Path, PurePath
import bpy.utils.previews
from platform import system
from subprocess import Popen
import json
import os

from .constants import BRD_CONST_DATA
from .Logger import log
from .utils import connected_to_internet


def _check_version_and_rate_limit():
    """
    Checks GitHub for the best matching Blender version folder.
    Also handles rate limit detection and caching.
    Returns True if safe to continue, False if we should abort.
    """
    with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
        stuff = json.load(f)

    # If we're still in a rate limit cooldown, skip entirely
    reset_time = stuff.get("__DYN__", {}).get("rate_limit_reset", 0)
    if time.time() < reset_time:
        print("BRD: GitHub rate limit cooldown active, skipping update.")
        return False

    try:
        r = requests.get(
            f"https://api.github.com/repos/{stuff['Github']['Repository']}/contents/",
            timeout=5
        )
    except requests.Timeout:
        print("BRD: Version check timed out.")
        return False
    except requests.RequestException as e:
        print(f"BRD: Version check failed: {e}")
        return False

    if r.status_code in (403, 429):
        reset_at = int(r.headers.get("X-RateLimit-Reset", time.time() + 3600))
        stuff["__DYN__"]["rate_limit_reset"] = reset_at
        with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
            f.write(json.dumps(stuff))
        print(f"BRD: GitHub rate limit reached. Cooldown until {reset_at}.")
        return False

    if r.status_code == 200:
        repo_contents = r.json()
        vers = [
            float(i["name"]) for i in repo_contents
            if re.match(r"^-?\d+(?:\.\d+)$", i["name"])
        ]
        if vers:
            local = float(str(bpy.app.version_string)[0:3])
            best = (
                str(local) if local in vers
                else str(min(vers, key=lambda x: abs(x - local)))
            )
            # Clean up old version folders
            for item in BRD_CONST_DATA.Folder.iterdir():
                if item.is_dir() and item.name != best:
                    shutil.rmtree(item)

    return True


class BRD_Asset(bpy.types.Operator):
    bl_idname = "bradley.add_asset"
    bl_label = "Setup Bradley's Asset Library"
    bl_description = "Setup a custom asset library for Bradley's add-on"

    def execute(self, context):
        is_blender_5_2_or_later = bpy.app.version >= (5, 2, 0)
        is_blender_5_0_or_later = bpy.app.version >= (5, 0, 0)
        asset_libraries = bpy.context.preferences.filepaths.asset_libraries
        target_name = "BRD_Data"
        new_path = str(PurePath(BRD_CONST_DATA.Folder))

        matching_index = None
        for index, asset_library in enumerate(asset_libraries):
            if asset_library.name == target_name:
                matching_index = index
                break

        if matching_index is not None:
            # Library already exists — just update the path
            lib = asset_libraries[matching_index]
            lib.path = new_path
            if is_blender_5_0_or_later:
                lib.import_method = 'PACK'
            print(f"BRD: Asset library '{target_name}' path updated to: {new_path}")
        else:
            # Add new library — use type='LOCAL' on 5.2+ to avoid remote library API
            if is_blender_5_2_or_later:
                bpy.ops.preferences.asset_library_add(
                    directory=new_path,
                    name=target_name,
                    type='LOCAL'
                )
                new_library = bpy.context.preferences.filepaths.asset_libraries[-1]
                new_library.import_method = 'PACK'
            else:
                # Blender < 5.2: old API without type parameter
                bpy.ops.preferences.asset_library_add()
                new_library = bpy.context.preferences.filepaths.asset_libraries[-1]
                new_library.name = target_name
                new_library.path = new_path
                new_library.import_method = 'PACK' if is_blender_5_0_or_later else 'LINK'

            print(f"BRD: Asset library '{target_name}' added at: {new_path}")

        return {"FINISHED"}


class BRD_Remove(bpy.types.Operator):
    bl_idname = "bradley.remove_asset"
    bl_label = "Remove Bradley's Asset Library"
    bl_description = "Remove the asset library path before you disable the add-on"

    def execute(self, context):
        asset_libraries = bpy.context.preferences.filepaths.asset_libraries
        target_name = "BRD_Data"
        matching_index = None

        for index, asset_library in enumerate(asset_libraries):
            if asset_library.name == target_name:
                matching_index = index
                break

        if matching_index is not None:
            bpy.ops.preferences.asset_library_remove(index=matching_index)
            print(f"Asset library '{target_name}' removed.")
        else:
            print(f"No asset library with name '{target_name}' found.")

        return {'FINISHED'}


class BRD_Update(bpy.types.Operator):
    bl_idname = "bradley.update"
    bl_label = "bradley update"

    def execute(self, context):
        if not connected_to_internet():
            log.debug("No internet connection available")
            return {"FINISHED"}

        # Version detection + rate limit check (moved here from constants.py)
        if not _check_version_and_rate_limit():
            return {"FINISHED"}

        # Fetch the versioned repo contents for the preset
        try:
            r = requests.get(BRD_CONST_DATA.Repository, timeout=(3, 10))
            if r.status_code != 200:
                log.debug(f"GitHub returned {r.status_code}")
                return {'CANCELLED'}
            repo_contents = r.json()
        except requests.RequestException as e:
            log.debug(f"GitHub request failed: {e}")
            return {'CANCELLED'}

        preset_data = next((item for item in repo_contents if item["name"].endswith(".blend")), None)
        text_files_data = [item for item in repo_contents if item["name"].endswith(".txt")]

        if not preset_data:
            log.debug("No preset data found in the repository.")
            return {"FINISHED"}

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
            i for i in Path(
                PurePath(BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version)
            ).iterdir()
            if i.name.endswith(".blend")
        ]

        # Only download if something has actually changed
        if (
            BRD_CONST_DATA.__DYN__.P_Version == "__"
            or BRD_CONST_DATA.__DYN__.P_Version != version
            or sha != BRD_CONST_DATA.__DYN__.sha
            or not a
        ):
            log.debug("Preset -> Updating")

            if (
                stuff["__DYN__"]["File_Location"]
                and stuff["__DYN__"]["File_Location"] != "."
                and a
            ):
                Path(stuff["__DYN__"]["File_Location"]).unlink()

            local_filename = PurePath(
                BRD_CONST_DATA.Folder,
                BRD_CONST_DATA.__DYN__.B_Version,
                "preset.blend",
            )

            with requests.get(file_repo, stream=True, timeout=(3, 30)) as r:
                r.raise_for_status()
                with open(str(local_filename), "wb") as f:
                    shutil.copyfileobj(r.raw, f)

            for text_file_data in text_files_data:
                if text_file_data["name"] == "blender_assets.cats.txt":
                    file_url = text_file_data["download_url"]
                    file_path = PurePath(BRD_CONST_DATA.Folder, "blender_assets.cats.txt")
                    with requests.get(file_url, stream=True, timeout=(3, 30)) as r:
                        r.raise_for_status()
                        lines = r.text.splitlines()
                        with open(str(file_path), "w", encoding="utf-8") as f:
                            for line in lines:
                                f.write(line + "\n")
                else:
                    text_file_url = text_file_data["download_url"]
                    text_file_name = text_file_data["name"]
                    text_file_path = PurePath(
                        BRD_CONST_DATA.Folder,
                        BRD_CONST_DATA.__DYN__.B_Version,
                        text_file_name
                    )
                    with requests.get(text_file_url, stream=True, timeout=(3, 30)) as r:
                        r.raise_for_status()
                        lines = r.text.splitlines()
                        with open(str(text_file_path), "w", encoding="utf-8") as f:
                            for line in lines:
                                f.write(line + "\n")

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

        return {"FINISHED"}


class BRD_Force_Update(bpy.types.Operator):
    bl_idname = "bradley.force_update"
    bl_label = "BRD_Force_Update"

    def execute(self, context):
        if not connected_to_internet():
            log.debug("No internet connection available")
            return {"FINISHED"}

        try:
            r = requests.get(BRD_CONST_DATA.Repository, timeout=(3, 10))
            if r.status_code != 200:
                log.debug(f"GitHub returned {r.status_code}")
                return {'CANCELLED'}
            repo_contents = r.json()
        except requests.RequestException as e:
            log.debug(f"GitHub request failed: {e}")
            return {'CANCELLED'}

        preset_data = next((item for item in repo_contents if item["name"].endswith(".blend")), None)
        text_files_data = [item for item in repo_contents if item["name"].endswith(".txt")]

        if not preset_data:
            log.debug("No preset data found in the repository.")
            return {"FINISHED"}

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
            i for i in Path(
                PurePath(BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version)
            ).iterdir()
            if i.name.endswith(".blend")
        ]

        if (
            stuff["__DYN__"]["File_Location"]
            and stuff["__DYN__"]["File_Location"] != "."
            and a
        ):
            Path(stuff["__DYN__"]["File_Location"]).unlink()

        local_filename = PurePath(
            BRD_CONST_DATA.Folder,
            BRD_CONST_DATA.__DYN__.B_Version,
            "preset.blend",
        )

        with requests.get(file_repo, stream=True, timeout=(3, 30)) as r:
            r.raise_for_status()
            with open(str(local_filename), "wb") as f:
                shutil.copyfileobj(r.raw, f)

        for text_file_data in text_files_data:
            if text_file_data["name"] == "blender_assets.cats.txt":
                file_url = text_file_data["download_url"]
                file_path = PurePath(BRD_CONST_DATA.Folder, "blender_assets.cats.txt")
                with requests.get(file_url, stream=True, timeout=(3, 30)) as r:
                    r.raise_for_status()
                    lines = r.text.splitlines()
                    with open(str(file_path), "w", encoding="utf-8") as f:
                        for line in lines:
                            f.write(line + "\n")
            else:
                text_file_url = text_file_data["download_url"]
                text_file_name = text_file_data["name"]
                text_file_path = PurePath(
                    BRD_CONST_DATA.Folder,
                    BRD_CONST_DATA.__DYN__.B_Version,
                    text_file_name
                )
                with requests.get(text_file_url, stream=True, timeout=(3, 30)) as r:
                    r.raise_for_status()
                    lines = r.text.splitlines()
                    with open(str(text_file_path), "w", encoding="utf-8") as f:
                        for line in lines:
                            f.write(line + "\n")

        # FIX: was incorrectly inside the for loop, causing repeated writes
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


preset_help = [BRD_Folder, BRD_Asset, BRD_Remove, BRD_Update, BRD_Force_Update]