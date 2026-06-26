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


def _get_rate_limit_status():
    """
    Checks GitHub's actual current rate limit status.
    This call does NOT consume your normal API quota.
    Returns (remaining, reset_at) or (None, None) if the check itself fails.
    """
    try:
        r = requests.get("https://api.github.com/rate_limit", timeout=5)
        if r.status_code == 200:
            data = r.json()
            remaining = data["resources"]["core"]["remaining"]
            reset_at = data["resources"]["core"]["reset"]
            return remaining, reset_at
    except requests.RequestException:
        pass
    return None, None


def _resolve_best_version():
    """
    Checks GitHub root for available version folders and returns the best
    matching version string for the current Blender install.

    Returns the best version string (e.g. "5.2") on success,
    or None if we should abort (rate limited, timed out, no internet, etc).

    Also handles:
    - Rate limit detection and cooldown caching (with live verification —
      a cached cooldown is treated only as a fallback hint, not a hard skip,
      since VPN/IP changes can reset GitHub's per-IP quota early)
    - Cleaning up old version folders that are no longer the best match
    - Creating the best version folder if it doesn't exist yet
    """
    with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
        stuff = json.load(f)

    remaining, live_reset_at = _get_rate_limit_status()

    if remaining is None:
        # Couldn't verify live status — fall back to the cached cooldown as a guess
        cached_reset = stuff.get("__DYN__", {}).get("rate_limit_reset", 0)
        if time.time() < cached_reset:
            print("BRD: Rate limit check unavailable, using cached cooldown.")
            return None
        # Otherwise just proceed and let the real request below tell us if we're limited
    elif remaining <= 0:
        # Genuinely still limited right now, confirmed live
        stuff["__DYN__"]["rate_limit_reset"] = live_reset_at
        with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
            f.write(json.dumps(stuff))
        print(f"BRD: Rate limit confirmed exhausted. Resets at {live_reset_at}.")
        return None
    else:
        # We have quota right now — clear any stale cooldown from a previous IP
        if stuff.get("__DYN__", {}).get("rate_limit_reset", 0) != 0:
            stuff["__DYN__"]["rate_limit_reset"] = 0
            with open(BRD_CONST_DATA.Folder / "settings.json", "w") as f:
                f.write(json.dumps(stuff))
        print(f"BRD: Rate limit OK, {remaining} requests remaining.")

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
        best = str(local)
    else:
        # Find the highest available version that doesn't exceed the current
        # Blender version. Falls back to the closest overall if none are lower.
        lower = [v for v in vers if v <= local]
        if lower:
            best = str(max(lower))
        else:
            best = str(min(vers, key=lambda x: abs(x - local)))

    print(f"BRD: Blender {local} -> using preset version {best}")

    # Create the best version folder if it doesn't exist
    best_folder = Path(PurePath(BRD_CONST_DATA.Folder, best))
    best_folder.mkdir(parents=True, exist_ok=True)

    # Remove all other version folders
    for item in BRD_CONST_DATA.Folder.iterdir():
        if item.is_dir() and item.name != best:
            print(f"BRD: Removing old version folder: {item.name}")
            shutil.rmtree(item)

    return best


def _ensure_asset_library():
    """
    Ensures the BRD_Data asset library entry exists in Blender preferences,
    always pointing at the Data/ root folder.
    Blender scans recursively so it will find preset.blend inside version subfolders.
    blender_assets.cats.txt lives at Data/ root alongside the version subfolders.
    Must be called on the main thread.
    """
    is_blender_5_2_or_later = bpy.app.version >= (5, 2, 0)
    is_blender_5_0_or_later = bpy.app.version >= (5, 0, 0)
    asset_libraries = bpy.context.preferences.filepaths.asset_libraries
    target_name = "BRD_Data"
    root_path = str(BRD_CONST_DATA.Folder)

    for lib in asset_libraries:
        if lib.name == target_name:
            # Already exists — make sure path is correct and leave it alone
            if lib.path != root_path:
                lib.path = root_path
                print(f"BRD: Asset library path corrected to: {root_path}")
            return

    # Doesn't exist yet — create it
    if is_blender_5_2_or_later:
        bpy.ops.preferences.asset_library_add(
            directory=root_path,
            name=target_name,
            type='LOCAL'
        )
        new_library = bpy.context.preferences.filepaths.asset_libraries[-1]
        new_library.import_method = 'PACK'
    else:
        bpy.ops.preferences.asset_library_add()
        new_library = bpy.context.preferences.filepaths.asset_libraries[-1]
        new_library.name = target_name
        new_library.path = root_path
        new_library.import_method = 'PACK' if is_blender_5_0_or_later else 'LINK'

    print(f"BRD: Asset library '{target_name}' created at: {root_path}")


def _download_preset(best_version, best_version_folder):
    """
    Pure file I/O + network. Safe to call from a background thread.
    Downloads preset.blend into Data/<version>/
    Downloads blender_assets.cats.txt into Data/ root (next to version folders)
    so that Blender finds it when scanning the Data/ root asset library.
    Returns True on success, False on failure.
    """
    with open(BRD_CONST_DATA.Folder / "settings.json", "r") as f:
        stuff = json.load(f)

    repo_url = f"https://api.github.com/repos/{stuff['Github']['Repository']}/contents/{best_version}"

    try:
        r = requests.get(repo_url, timeout=(3, 10))
        if r.status_code != 200:
            print(f"BRD: GitHub returned {r.status_code} for version {best_version}")
            return False
        repo_contents = r.json()
    except requests.RequestException as e:
        print(f"BRD: GitHub request failed: {e}")
        return False

    preset_data = next((item for item in repo_contents if item["name"].endswith(".blend")), None)
    text_files_data = [item for item in repo_contents if item["name"].endswith(".txt")]

    if not preset_data:
        print("BRD: No preset .blend found in the repository.")
        return False

    sha = preset_data["sha"]
    version = preset_data["name"].lower().replace(" ", "")
    file_repo = preset_data["download_url"]

    log.debug(f"sha new -> {sha}")
    log.debug(f"sha current -> {BRD_CONST_DATA.__DYN__.sha}")
    log.debug(f"Preset github version: {version}")
    log.debug(f"Preset local version: {BRD_CONST_DATA.__DYN__.P_Version}")

    a = [i for i in best_version_folder.iterdir() if i.name.endswith(".blend")]

    needs_update = (
        BRD_CONST_DATA.__DYN__.P_Version == "__"
        or BRD_CONST_DATA.__DYN__.P_Version != version
        or sha != BRD_CONST_DATA.__DYN__.sha
        or best_version != BRD_CONST_DATA.__DYN__.B_Version
        or not a
    )

    if not needs_update:
        log.debug("Preset -> Up to Date")
        return True

    log.debug("Preset -> Updating")

    # Remove old preset file if it exists
    if (
        stuff["__DYN__"]["File_Location"]
        and stuff["__DYN__"]["File_Location"] != "."
        and a
    ):
        Path(stuff["__DYN__"]["File_Location"]).unlink(missing_ok=True)

    local_filename = best_version_folder / "preset.blend"

    try:
        with requests.get(file_repo, stream=True, timeout=(3, 30)) as r:
            r.raise_for_status()
            with open(str(local_filename), "wb") as f:
                shutil.copyfileobj(r.raw, f)
    except requests.RequestException as e:
        print(f"BRD: Failed to download preset: {e}")
        return False

    for text_file_data in text_files_data:
        try:
            if text_file_data["name"] == "blender_assets.cats.txt":
                # Always saved to Data/ root so Blender finds it at the library root
                file_path = BRD_CONST_DATA.Folder / "blender_assets.cats.txt"
            else:
                # Other text files go into the version subfolder
                file_path = best_version_folder / text_file_data["name"]

            with requests.get(text_file_data["download_url"], stream=True, timeout=(3, 30)) as r:
                r.raise_for_status()
                with open(str(file_path), "w", encoding="utf-8") as f:
                    for line in r.text.splitlines():
                        f.write(line + "\n")
        except requests.RequestException as e:
            print(f"BRD: Failed to download {text_file_data['name']}: {e}")

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

    log.debug("Preset -> Updated")
    return True


class BRD_Asset(bpy.types.Operator):
    bl_idname = "bradley.add_asset"
    bl_label = "Setup Bradley's Asset Library"
    bl_description = "Setup a custom asset library for Bradley's add-on"

    def execute(self, context):
        _ensure_asset_library()
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
            print(f"BRD: Asset library '{target_name}' removed.")
        else:
            print(f"BRD: No asset library with name '{target_name}' found.")

        return {'FINISHED'}


class BRD_Update(bpy.types.Operator):
    bl_idname = "bradley.update"
    bl_label = "bradley update"

    def execute(self, context):
        """
        Called from a background thread — all work must be pure file I/O
        and network only. bpy calls are not safe here.
        _ensure_asset_library() was already called on the main thread by
        BRD_Asset before this thread started, so no bpy work needed here.
        """
        if not connected_to_internet():
            log.debug("No internet connection available")
            return {"FINISHED"}

        best_version = _resolve_best_version()
        if best_version is None:
            return {"FINISHED"}

        best_version_folder = Path(PurePath(BRD_CONST_DATA.Folder, best_version))
        _download_preset(best_version, best_version_folder)

        return {"FINISHED"}


class BRD_Force_Update(bpy.types.Operator):
    bl_idname = "bradley.force_update"
    bl_label = "BRD_Force_Update"

    def execute(self, context):
        """
        Called from a UI button — runs on the main thread.
        Forces re-download regardless of sha/version match.
        """
        if not connected_to_internet():
            log.debug("No internet connection available")
            return {"FINISHED"}

        best_version = _resolve_best_version()
        if best_version is None:
            return {"FINISHED"}

        best_version_folder = Path(PurePath(BRD_CONST_DATA.Folder, best_version))

        # Force re-download by temporarily clearing the sha
        original_sha = BRD_CONST_DATA.__DYN__.sha
        BRD_CONST_DATA.__DYN__.sha = ""
        _download_preset(best_version, best_version_folder)
        BRD_CONST_DATA.__DYN__.sha = original_sha

        # Also ensure library entry is correct while we're on the main thread
        _ensure_asset_library()

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