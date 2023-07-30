from ...constants import BRD_CONST_DATA
import bpy


class Experimental_Poll:
    @classmethod
    def poll(cls, context):

        return (
            context.space_data.type == "NODE_EDITOR"
            and context.space_data.tree_type == "GeometryNodeTree"
            and context.preferences.addons[
                BRD_CONST_DATA.Package_name
            ].preferences.experimental
        )


class Experimental_Panel(Experimental_Poll):
    bl_parent_id = "BRD_EXPERIMENTAL_PT_Panel"

    bl_region_type = "UI"
    bl_space_type = "NODE_EDITOR"
    bl_category = "Bradley"


class BRD_EXPERIMENTAL_PT_Panel(Experimental_Poll, bpy.types.Panel):
    bl_idname = "BRD_EXPERIMENTAL_PT_Panel"
    bl_label = "Experimental Functions"

    bl_region_type = "UI"
    bl_space_type = "NODE_EDITOR"
    bl_category = "Bradley"

    def draw(self, context):
        pass
