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


def _resolve_best_version():
    """
    Checks GitHub root for available version folders and returns the best
    matching version string for the current Blender install.

    Returns the best version string (e.g. "5.2") on success,
    or None if we should abort (rate limited, timed out, no internet, etc).

    Also handles:
    - Rate limit detection and cooldown caching
    - Cleaning up old version folders that are no longer the best match
    - Creating the best version folder if it doesn't exist yet
    """
    with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
        stuff = json.load(f)

    # Still in a rate limit cooldown — skip entirely
    reset_time = stuff.get("__DYN__", {}).get("rate_limit_reset", 0)
    if time.time() < reset_time:
        print("BRD: GitHub rate limit cooldown active, skipping update.")
        return None

    try:
        r = requests.get(
            f"https://api.github.com/repos/{stuff['Github']['Repository']}/contents/",
            timeout=5
        )
    except requests.Timeout:
        print("BRD: Version check timed out.")
        return None
    except requests.RequestException as e:
        print(f"BRD: Version check failed: {e}")
        return None

    if r.status_code in (403, 429):
        reset_at = int(r.headers.get("X-RateLimit-Reset", time.time() + 3600))
        stuff["__DYN__"]["rate_limit_reset"] = reset_at
        with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
            f.write(json.dumps(stuff))
        print(f"BRD: GitHub rate limit reached. Cooldown until {reset_at}.")
        return None

    if r.status_code != 200:
        print(f"BRD: Unexpected GitHub status {r.status_code} during version check.")
        return None

    repo_contents = r.json()
    vers = [
        float(i["name"]) for i in repo_contents
        if re.match(r"^-?\d+(?:\.\d+)$", i["name"])
    ]

    if not vers:
        print("BRD: No version folders found on GitHub.")
        return None

    local = float(str(bpy.app.version_string)[0:3])

    if local in vers:
        # Exact match — use it directly
        best = str(local)
    else:
        # No exact match — find the highest available version that doesn't
        # exceed the current Blender version (i.e. don't use a future version).
        # Falls back to the closest overall if none are lower.
        lower = [v for v in vers if v <= local]
        if lower:
            best = str(max(lower))
        else:
            best = str(min(vers, key=lambda x: abs(x - local)))

    print(f"BRD: Blender {local} -> using preset version {best}")

    # Create the best version folder if it doesn't exist
    best_folder = Path(PurePath(BRD_CONST_DATA.Folder, best))
    best_folder.mkdir(parents=True, exist_ok=True)

    # Remove all other version folders (old versions, wrong fallbacks, etc)
    for item in BRD_CONST_DATA.Folder.iterdir():
        if item.is_dir() and item.name != best:
            print(f"BRD: Removing old version folder: {item.name}")
            shutil.rmtree(item)

    return best


def _update_asset_library_path(version_folder):
    """Updates the BRD_Data asset library path to point to the correct version folder."""
    is_blender_5_2_or_later = bpy.app.version >= (5, 2, 0)
    is_blender_5_0_or_later = bpy.app.version >= (5, 0, 0)
    asset_libraries = bpy.context.preferences.filepaths.asset_libraries
    target_name = "BRD_Data"
    new_path = str(version_folder)

    matching_index = None
    for index, lib in enumerate(asset_libraries):
        if lib.name == target_name:
            matching_index = index
            break

    if matching_index is not None:
        lib = asset_libraries[matching_index]
        lib.path = new_path
        if is_blender_5_0_or_later:
            lib.import_method = 'PACK'
        print(f"BRD: Asset library path updated to: {new_path}")
    else:
        if is_blender_5_2_or_later:
            bpy.ops.preferences.asset_library_add(
                directory=new_path,
                name=target_name,
                type='LOCAL'
            )
            new_library = bpy.context.preferences.filepaths.asset_libraries[-1]
            new_library.import_method = 'PACK'
        else:
            bpy.ops.preferences.asset_library_add()
            new_library = bpy.context.preferences.filepaths.asset_libraries[-1]
            new_library.name = target_name
            new_library.path = new_path
            new_library.import_method = 'PACK' if is_blender_5_0_or_later else 'LINK'
        print(f"BRD: Asset library added at: {new_path}")


class BRD_Asset(bpy.types.Operator):
    bl_idname = "bradley.add_asset"
    bl_label = "Setup Bradley's Asset Library"
    bl_description = "Setup a custom asset library for Bradley's add-on"

    def execute(self, context):
        # Point to the Data folder itself as a starting point —
        # _resolve_best_version() will refine the path to the correct version subfolder
        # during BRD_Update. This just ensures the library entry exists.
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
            lib = asset_libraries[matching_index]
            lib.path = new_path
            if is_blender_5_0_or_later:
                lib.import_method = 'PACK'
            print(f"BRD: Asset library '{target_name}' path updated to: {new_path}")
        else:
            if is_blender_5_2_or_later:
                bpy.ops.preferences.asset_library_add(
                    directory=new_path,
                    name=target_name,
                    type='LOCAL'
                )
                new_library = bpy.context.preferences.filepaths.asset_libraries[-1]
                new_library.import_method = 'PACK'
            else:
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

        # Resolve best version from GitHub — returns None if we should abort
        best_version = _resolve_best_version()
        if best_version is None:
            return {"FINISHED"}

        best_version_folder = Path(PurePath(BRD_CONST_DATA.Folder, best_version))

        # Fetch the versioned repo contents for the preset
        repo_url = f"https://api.github.com/repos/{BRD_CONST_DATA.Repository.split('contents/')[0].split('repos/')[1]}contents/{best_version}"
        # Rebuild cleanly from the base repo name stored in settings
        with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
            stuff = json.load(f)
        repo_url = f"https://api.github.com/repos/{stuff['Github']['Repository']}/contents/{best_version}"

        try:
            r = requests.get(repo_url, timeout=(3, 10))
            if r.status_code != 200:
                log.debug(f"GitHub returned {r.status_code} for version {best_version}")
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

        a = [i for i in best_version_folder.iterdir() if i.name.endswith(".blend")]

        # Only download if something has actually changed
        if (
            BRD_CONST_DATA.__DYN__.P_Version == "__"
            or BRD_CONST_DATA.__DYN__.P_Version != version
            or sha != BRD_CONST_DATA.__DYN__.sha
            or best_version != BRD_CONST_DATA.__DYN__.B_Version
            or not a
        ):
            log.debug("Preset -> Updating")

            if (
                stuff["__DYN__"]["File_Location"]
                and stuff["__DYN__"]["File_Location"] != "."
                and a
            ):
                Path(stuff["__DYN__"]["File_Location"]).unlink(missing_ok=True)

            local_filename = PurePath(best_version_folder, "preset.blend")

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
                    text_file_path = PurePath(best_version_folder, text_file_name)
                    with requests.get(text_file_url, stream=True, timeout=(3, 30)) as r:
                        r.raise_for_status()
                        lines = r.text.splitlines()
                        with open(str(text_file_path), "w", encoding="utf-8") as f:
                            for line in lines:
                                f.write(line + "\n")

            stuff["__DYN__"] = {
                "New": False,
                "P_Version": version,
                "B_Version": best_version,
                "File_Location": str(local_filename),
                "Debug": BRD_CONST_DATA.__DYN__.Debug,
                "sha": sha,
            }
            with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
                f.write(json.dumps(stuff))

            # Update asset library to point at the correct version folder
            _update_asset_library_path(best_version_folder)

            log.debug("Preset -> Updated")
        else:
            log.debug("Preset -> Up to Date")
            # Even if preset is up to date, ensure library path is correct
            _update_asset_library_path(best_version_folder)

        return {"FINISHED"}


class BRD_Force_Update(bpy.types.Operator):
    bl_idname = "bradley.force_update"
    bl_label = "BRD_Force_Update"

    def execute(self, context):
        if not connected_to_internet():
            log.debug("No internet connection available")
            return {"FINISHED"}

        # Resolve best version from GitHub
        best_version = _resolve_best_version()
        if best_version is None:
            return {"FINISHED"}

        best_version_folder = Path(PurePath(BRD_CONST_DATA.Folder, best_version))

        with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
            stuff = json.load(f)
        repo_url = f"https://api.github.com/repos/{stuff['Github']['Repository']}/contents/{best_version}"

        try:
            r = requests.get(repo_url, timeout=(3, 10))
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
        version = preset_data["name"].lower().replace(" ", "")
        file_repo = preset_data["download_url"]

        log.debug(f"sha new -> {sha}")
        log.debug(f"sha current -> {BRD_CONST_DATA.__DYN__.sha}")
        log.debug(f"Preset github version: {version}")
        log.debug(f"Preset local version: {BRD_CONST_DATA.__DYN__.P_Version}")

        a = [i for i in best_version_folder.iterdir() if i.name.endswith(".blend")]

        if (
            stuff["__DYN__"]["File_Location"]
            and stuff["__DYN__"]["File_Location"] != "."
            and a
        ):
            Path(stuff["__DYN__"]["File_Location"]).unlink(missing_ok=True)

        local_filename = PurePath(best_version_folder, "preset.blend")

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
                text_file_path = PurePath(best_version_folder, text_file_name)
                with requests.get(text_file_url, stream=True, timeout=(3, 30)) as r:
                    r.raise_for_status()
                    lines = r.text.splitlines()
                    with open(str(text_file_path), "w", encoding="utf-8") as f:
                        for line in lines:
                            f.write(line + "\n")

        stuff["__DYN__"] = {
            "New": False,
            "P_Version": version,
            "B_Version": best_version,
            "File_Location": str(local_filename),
            "Debug": BRD_CONST_DATA.__DYN__.Debug,
            "sha": sha,
        }
        with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
            f.write(json.dumps(stuff))

        # Update asset library to point at the correct version folder
        _update_asset_library_path(best_version_folder)

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