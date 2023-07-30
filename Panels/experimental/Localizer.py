import bpy
from ...Logger import log
from .utils import Experimental_Poll, Experimental_Panel


class BRD_Node_Localizer(Experimental_Poll, bpy.types.Operator):
    bl_idname = "bradley.node_localize_used"
    bl_label = "Simple Node Operator"

    noodles = []

    def recursive_find(self, context):
        for n in context.node_tree.nodes:
            if hasattr(n, "node_tree"):
                self.noodles.append(n.node_tree.name)
                self.recursive_find(n)

    def execute(self, context):

        tree = context.space_data
        self.recursive_find(tree)

        for i in self.noodles:
            bpy.data.node_groups[str(i)].make_local()
            bpy.data.node_groups[str(i)].use_fake_user = True

        log.debug(
            "Made Local :\n" + "\n".join(["- " + i for i in self.noodles]),
            multi_line=True,
        )

        self.noodles = []
        return {"FINISHED"}


class BRD_Node_Localizer_All(Experimental_Poll, bpy.types.Operator):
    bl_idname = "bradley.node_localize_all"
    bl_label = "Simple Node Operator"

    def execute(self, context):

        self.asd = [
            i
            for i in bpy.data.node_groups
            if i.name.startswith("G_") and i.type == "GEOMETRY"
        ]

        for i in self.asd:
            i.make_local()
            i.use_fake_user = True

        log.debug(
            "Made Local :\n" + "\n".join(["- " + i.name for i in self.asd]),
            multi_line=True,
        )

        return {"FINISHED"}


class BRD_PT_Localizer(Experimental_Panel, bpy.types.Panel):
    bl_idname = "BRD_PT_Localizer"
    bl_label = "Localize"

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.operator(
            "bradley.node_localize_used", text="Localize Used Only", icon="SORT_ASC"
        )
        col.operator(
            "bradley.node_localize_all",
            text="Localize All Presets",
            icon="IMPORT",
        )
        col.scale_y = 3.0


localizer_panels = [BRD_Node_Localizer, BRD_PT_Localizer, BRD_Node_Localizer_All]
