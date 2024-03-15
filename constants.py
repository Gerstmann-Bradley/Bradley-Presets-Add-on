# Import required modules
from pathlib import Path, PurePath
import re
import bpy
import requests

# Import custom classes and functions from the add-on
from .Dtcls import BRD_Datas, __DYN__, Social
from .utils import connected_to_internet
import json

# Set the "Folder" variable to the path of the "Data" folder within the add-on directory
Folder = Path(Path(__file__).parents[0], "Data")

# Read the contents of the "settings.json" file into the "stuff" dictionary
with open(PurePath(Folder, "settings.json"), "r") as f:
    stuff = json.loads(f.read())

# Get the GitHub repository URL from the "settings.json" file
repo = stuff["Github"]["Repository"]

# Initialize the "version" variable as a floating-point number
version = float()

try:
    # Check if there is an internet connection
    if connected_to_internet():

        # Send a request to the GitHub repository API to get the contents
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/").json()

        # Extract the versions from the repository contents using regular expressions
        vers = [float(i["name"]) for i in r if re.match(r"^-?\d+(?:\.\d+)$", i["name"])]

        # Determine the Blender version based on the installed version and the available versions in the repository
        version = (
            str(bpy.app.version_string)[0:3]
            if float(str(bpy.app.version_string)[0:3]) in vers
            else str(
                min(
                    vers,
                    key=lambda x: abs(x - float(float(str(bpy.app.version_string)[0:3]))),
                )
            )
        )
    else:
        # If there is no internet connection, set a default version "3.1"
        version = "3.1"
except Exception as e:
    print(f"An error occurred while fetching GitHub repository contents: {e}")
    # Set a default version "3.1" if the request fails
    version = "3.1"

# Remove all existing folders within the "Data" directory except for the one corresponding to the desired version
for item in Folder.iterdir():
    if item.is_dir() and item.name != version:
        # Delete only directories, skip files
        try:
            item.rmdir()
        except OSError as e:
            print(f"Failed to remove directory {item}: {e}")

# Create a directory with the version number within the "Data" folder
Path(PurePath(Folder, version)).mkdir(parents=True, exist_ok=True)

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
    new_path = str(Folder)
    asset_libraries[matching_index].path = new_path
    print(f"Asset library '{target_name}' found at index {matching_index}. Path updated to: {new_path}")
else:
    print(f"No asset library with name '{target_name}' found.")

# Initialize the "BRD_CONST_DATA" object using the custom classes and information gathered above
BRD_CONST_DATA = BRD_Datas(
    __package__,
    [Social(**i) for i in stuff["Socials"]],
    stuff["Custom_Category"],
    f"https://api.github.com/repos/{repo}/contents/{version}",
    Folder,
    __DYN__(
        stuff["__DYN__"]["P_Version"],
        version,
        # Path(stuff["__DYN__"]["File_Location"]),
        stuff["__DYN__"]["New"],
        stuff["__DYN__"]["Debug"],
        stuff["__DYN__"]["sha"],
    ),
)