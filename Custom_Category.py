# Import necessary modules and classes from Blender and Python standard library
import bpy
import json
from pathlib import Path, PurePath
import bpy.utils.previews
import re
from bpy.props import StringProperty

# Import custom classes and functions from the add-on
from .Logger import log
from .constants import BRD_CONST_DATA
from .utils import flatten

# Function to add a button to the Geometry Node editor menu
def add_button(self, context):
    if context.area.ui_type == "GeometryNodeTree":
        # Add a menu item to the menu named "Bradley's preset" with a specific icon
        self.layout.menu(
            "NODE_MT_GEO", text="Bradley's preset", icon="KEYTYPE_JITTER_VEC"
        )

# Function to generate the custom node category in the Geometry Node editor
def geo_cat_generator():
    log.debug("Generating Custom category")

    # Get the custom node group data from the BRD_CONST_DATA
    BRD_GRP_Cache = BRD_CONST_DATA.Custom_Category

    # Extract known_groups from the BRD_GRP_Cache
    known_groups = flatten([BRD_GRP_Cache[i] for i in BRD_GRP_Cache])

    # Load node groups from the preset.blend file in the BRD_CONST_DATA folder
    with bpy.data.libraries.load(
        str(
            PurePath(
                BRD_CONST_DATA.Folder, BRD_CONST_DATA.__DYN__.B_Version, "preset.blend"
            )
        )
    ) as (
        data_from,
        __,
    ):
        kiki = []

        # Find node groups that start with "G_" in the loaded data
        for i in data_from.node_groups:
            if i.startswith("G_"):
                kiki.append(i)

        # Determine the unknown groups that are not in the known_groups list
        if _ap := list(set(kiki) - set(known_groups)):
            BRD_GRP_Cache["Unknown"] = _ap
            log.debug("uncategorised groups :" + "\n".join(["- " + i for i in _ap]))

    # Log the generated node category in the BRD_GRP_Cache
    log.debug(
        "Node category :\n" + str(json.dumps(BRD_GRP_Cache, indent=2)),
        multi_line=True,
    )

    # Generate a menu for each item in the BRD_GRP_Cache
    for item in BRD_GRP_Cache.items():

        # Custom draw function for each generated menu
        def custom_draw(self, context):
            layout = self.layout

            # Iterate through group names in the BRD_GRP_Cache
            for group_name in BRD_GRP_Cache[self.bl_label]:
                # Add an operator with the name of the node group (without "G_") to the menu
                props = layout.operator(
                    NODE_OT_Add.bl_idname,
                    text=re.sub(r".*?_", "", group_name),
                )
                props.group_name = group_name

        # Generate a new menu type dynamically using type()
        menu_type = type(
            "NODE_MT_category_" + item[0],
            (bpy.types.Menu,),
            {
                "bl_idname": "NODE_MT_category_" + "_BRD_" + item[0].replace(" ", "_"),
                "bl_space_type": "NODE_EDITOR",
                "bl_label": item[0],
                "draw": custom_draw,
            },
        )

        # Function to generate the menu draw dynamically
        def generate_menu_draw(name, label):
            def draw_menu(self, context):
                self.layout.menu(name, text=label)
                # Add a separator to the menu if the label contains "_"
                if "_" in label:
                    self.layout.separator(factor=1.0)

            return draw_menu

        # Register the dynamically generated menu type
        bpy.utils.register_class(menu_type)

        # Append the dynamically generated menu draw function to the NODE_MT_GEO menu
        bpy.types.NODE_MT_GEO.append(
            generate_menu_draw(menu_type.bl_idname, menu_type.bl_label),
        )

# Custom menu class for the "Bradley Preset" menu in the Geometry Node editor
class NODE_MT_GEO(bpy.types.Menu):
    bl_label = "bradley Preset"
    bl_idname = "NODE_MT_GEO"

    @classmethod
    def poll(cls, context):
        # Polling function to check if the context supports the menu display
        return (
            context.space_data.type == "NODE_EDITOR"
            and context.space_data.tree_type == "GeometryNodeTree"
        )

    def draw(self, context):
        pass

# Custom operator class for adding node groups to the Geometry Node editor
class NODE_OT_Add(bpy.types.Operator):
    bl_idname = "bradley.bradley_node_ot_add"
    bl_label = "Add node group"
    bl_options = {"REGISTER", "UNDO"}

    group_name: StringProperty()

    @classmethod
    def poll(cls, context):
        # Polling function to check if the context supports the operator execution
        return context.space_data.node_tree

    def execute(self, context):
        # Execute function to add a node group to the active node tree
        bpy.ops.node.add_node(type="GeometryNodeGroup")

        # Get the newly added node and set its node tree to the selected node group
        node = context.selected_nodes[0]
        node.node_tree = bpy.data.node_groups[self.group_name]

        # Invoke the default translation for the node
        bpy.ops.transform.translate("INVOKE_DEFAULT")

        return {"FINISHED"}
