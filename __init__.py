bl_info = {
    "name": "Sprite Sheet Maker",
    "author": "Manas R. Makde",
    "version": (1, 0, 0),
    "description": "Creates Sprite Sheet from actions",
    "warning": "Requires internet access for one-time pip package installation and Blender restart"
}


import bpy
import os
from .install_dependencies import *
from .sprite_sheet_maker_utils import *
from bpy.types import Panel, Operator, PropertyGroup, UIList
from bpy.props import (
    StringProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
    CollectionProperty,
    IntProperty,
    EnumProperty,
)


# Constants
DEFAULT_DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
SPRITE_SHEET_MAKER = SpriteSheetMaker()
SINGLE_SPRITE_NAME = "sprite.png"
SPRITE_SHEET_NAME = "sprite_sheet.png"
PIXELATE_TEST_IMAGE_POSTFIX = "pixelated"
has_dep_cache = False


# Enums
class DependencyStatus(Enum):
    PENDING = ('PENDING', "Pending Install", "Waiting to install dependencies")
    INSTALLING = ('INSTALLING', "Installing...", "Currently installing dependencies")
    ERROR = ('ERROR', "Installation Error", "Failed to install dependencies")
    INSTALLED = ('INSTALLED', "Installed", "installed dependencies")


# Classes
class SpriteSheetMakerMessagePopup(bpy.types.Operator):
    bl_idname = "spritesheetmaker.message_popup"
    bl_label = "SpriteSheetMaker Message"
    message_heading: bpy.props.StringProperty(name="Heading", default="")
    message_icon: bpy.props.StringProperty(name="Icon", default="INFO")

    def execute(self, context):
        return {'FINISHED'}
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=500)
    def draw(self, context):
        layout = self.layout
        lines = self.message_heading.split("\n")
        for i, line in enumerate(lines):
            layout.label(
                text=line,
                icon=self.message_icon if i == 0 else 'BLANK1'
            )

class SpriteSheetMakerObjectItem(PropertyGroup):
    obj: PointerProperty(name="Object", type=bpy.types.Object)

class SpriteSheetMakerActionItem(PropertyGroup):
    action: PointerProperty(name="Action", type=bpy.types.Action)

class SpriteSheetMakerProperties(PropertyGroup):

    # Dependency info
    dependency_status: EnumProperty(
        items=[member.value for member in DependencyStatus],
        name="Pillow Installation Status",
        description="Current status of the Pillow installation",
        default=DependencyStatus.PENDING.name
    )

    # Objects info
    objects_to_use: CollectionProperty(type=SpriteSheetMakerObjectItem)
    objects_index: IntProperty(default=0)
    consider_armature_bones: BoolProperty(name="Consider Armature Bones", default=False)

    # Actions info
    actions_to_capture: CollectionProperty(type=SpriteSheetMakerActionItem)
    actions_index: IntProperty(default=0)

    # Camera info
    auto_camera: BoolProperty(name="Auto Camera", default=True)
    camera_direction: EnumProperty(
        name="Camera Direction",
        items = [
            (CameraDirection.X.value, "X", "Camera pointing along the X axis"),
            (CameraDirection.Y.value, "Y", "Camera pointing along the Y axis"),
            (CameraDirection.Z.value, "Z", "Camera pointing along the Z axis"),
            (CameraDirection.NEG_X.value, "-X", "Camera pointing along the negative X axis"),
            (CameraDirection.NEG_Y.value, "-Y", "Camera pointing along the negative Y axis"),
            (CameraDirection.NEG_Z.value, "-Z", "Camera pointing along the negative Z axis")
        ],
        default=CameraDirection.NEG_X.value
    )
    camera_object: PointerProperty(name="Camera Object", type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')
    pixels_per_meter: IntProperty(name="Pixels Per Meter", default=500, min=1, soft_max=5000)
    camera_padding: FloatProperty(name="Camera Padding", unit='LENGTH', default=0.05, min=0.0, soft_max=10.0)

    # Pixelation info
    to_pixelate: BoolProperty(name="To Pixelate", default=False)
    pixelation_amount: FloatProperty(name="Pixelation Amount", default=0.9, precision=5, step=0.001, min=0.0, max=1.0)
    shrink_interp: EnumProperty(
        name="Shrink Interpolation",
        items=[
            (ScaleInterpType.NEAREST.value, "Nearest", "Nearest"),
            (ScaleInterpType.BILINEAR.value, "Bilinear", "Bilinear"),
            (ScaleInterpType.BICUBIC.value, "Bicubic", "Bicubic"),
            (ScaleInterpType.ANISOTROPIC.value, "Anisotropic", "Anisotropic")
        ],
        default=ScaleInterpType.NEAREST.value
    )
    color_amount: FloatProperty(name="Pixelation Color Amount", default=50.0, min=0.0, soft_max=1000)
    min_alpha: FloatProperty(name="Min Alpha", default=0.0, min=0.0, max=1.0)
    alpha_step: FloatProperty(name="Alpha Step", default=0.33, min=0.0, max=1.0)
    pixelate_image_path: StringProperty(
        name="Pixelate Image Path",
        subtype="FILE_PATH"
    )

    # Collapsible section toggles
    show_camera_settings: BoolProperty(name="Show Camera Settings", default=False)
    show_pixelation_settings: BoolProperty(name="Show Pixelation Settings", default=False)
    show_output_settings: BoolProperty(name="Show Output Settings", default=False)

    # Exporting options
    label_font_size: IntProperty(name="Label Font Size", default=24, min=0, soft_max=1000)
    frame_margin: IntProperty(name="Frame Margin", default=15, min=0, soft_max=1000)
    output_path: StringProperty(
        name="Output Folder",
        subtype="DIR_PATH",
        default=DEFAULT_DESKTOP if os.path.isdir(DEFAULT_DESKTOP) else ""
    )
    delete_temp_folder: BoolProperty(name="Delete Temp Folder", default=True)

class SPRITESHEETMAKER_OT_dependencies(bpy.types.Operator):
    bl_idname = "dependencies.install"
    bl_label = "Install Dependencies"
    bl_options = {'REGISTER'}

    def execute(self, context):

        # Get props
        props = context.scene.sprite_sheet_maker_props


        # Return if already has dependencies
        if has_dependencies():
            print("[SpriteSheetMaker] Dependencies are already installed")
            props.dependency_status = DependencyStatus.INSTALLED.name
            return {'FINISHED'}
        

        # Set the state to installing
        props.dependency_status = DependencyStatus.INSTALLING.name
        

        # Force a redraw
        if context.area:
            context.area.tag_redraw()
        

        # Deferred function to install all dependencies and update panel accordingly
        def install_dep():

            # Final status to be set
            install_status = DependencyStatus.PENDING.name


            # Invoke actual installation function
            try:
                install_all_dependencies(context)
                install_status = DependencyStatus.INSTALLED.name if has_dependencies() else DependencyStatus.ERROR.name
            except:
                install_status = DependencyStatus.ERROR.name


            # Set new install status
            props = context.scene.sprite_sheet_maker_props
            props.dependency_status = install_status


            # Force Redraw
            for window in context.window_manager.windows:
                screen = window.screen
                for area in screen.areas:
                    if area.type in {'VIEW_3D', 'INFO', 'PROPERTIES'}: 
                        area.tag_redraw()
            

        # Intentionally deferred so that UI has time to update
        bpy.app.timers.register(install_dep, first_interval=0.1)
        

        return {'FINISHED'}

class SPRITESHEETMAKER_UL_ObjectList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "obj", text="", emboss=True)

class SPRITESHEETMAKER_UL_ActionsToCapture(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "action", text="", emboss=True)

class SPRITESHEETMAKER_OT_AddObject(Operator):
    bl_idname = "spritesheetmaker.objects_add"
    bl_label = "Add Object"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        props.objects_to_use.add()
        props.objects_index = len(props.objects_to_use) - 1
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_RemoveObject(Operator):
    bl_idname = "spritesheetmaker.objects_remove"
    bl_label = "Remove Object"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        if props.objects_to_use:
            props.objects_to_use.remove(props.objects_index)
            props.objects_index = max(0, props.objects_index - 1)
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_AddAllObjects(Operator):
    bl_idname = "spritesheetmaker.objects_add_all"
    bl_label = "Add All Objects"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        props.objects_to_use.clear()
        for obj in bpy.data.objects:
            if obj.type not in {'LIGHT', 'CAMERA', 'EMPTY', 'CURVE', 'SPEAKER'}:
                item = props.objects_to_use.add()
                item.obj = obj
        props.objects_index = 0
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_RemoveAllObjects(Operator):
    bl_idname = "spritesheetmaker.objects_remove_all"
    bl_label = "Remove All Objects"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        props.objects_to_use.clear()
        props.objects_index = 0
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_AddAction(Operator):
    bl_idname = "spritesheetmaker.actions_add"
    bl_label = "Add Action"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        props.actions_to_capture.add()
        props.actions_index = len(props.actions_to_capture) - 1
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_RemoveAction(Operator):
    bl_idname = "spritesheetmaker.actions_remove"
    bl_label = "Remove Action"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        if props.actions_to_capture:
            props.actions_to_capture.remove(props.actions_index)
            props.actions_index = max(0, props.actions_index - 1)
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_AddAllActions(Operator):
    bl_idname = "spritesheetmaker.actions_add_all"
    bl_label = "Add All Actions"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        props.actions_to_capture.clear()
        for action in bpy.data.actions:
            item = props.actions_to_capture.add()
            item.action = action
        props.actions_index = 0
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_RemoveAllActions(Operator):
    bl_idname = "spritesheetmaker.actions_remove_all"
    bl_label = "Remove All Actions"

    def execute(self, context):
        props = context.scene.sprite_sheet_maker_props
        props.actions_to_capture.clear()
        props.actions_index = 0
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_PixelateImage(Operator):
    bl_idname = "spritesheetmaker.pixelate_image"
    bl_label = "Pixelate Image"
    bl_description = "Pixelate given image"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get all props
        props = bpy.context.scene.sprite_sheet_maker_props

        
        # Return if invalid output path
        if(not os.path.exists(props.pixelate_image_path)):
            popup("'Test image' is invalid!", "CANCEL")
            return {'FINISHED'}


        # Combine images together into single file and paste in output
        try:
            # Generate param
            param = sprite_param_from_props()

            # Add '_pixelated' postfix to the file name
            dir_name, file_name = os.path.split(props.pixelate_image_path)
            name, ext = os.path.splitext(file_name)
            new_name = f"{name}_{PIXELATE_TEST_IMAGE_POSTFIX}{ext}"
            pixelated_image_path = os.path.join(dir_name, new_name)

            # Pixelate the image
            pixelate_image(props.pixelate_image_path, param.pixelate_param, pixelated_image_path)

            # Notify success
            popup(f"Pixelated image successfully at {pixelated_image_path}")
        
        except Exception as e:
            popup("Error occurred while pixelating image! Make sure you have passed a valid image\nCheck console for more information")
            print(f"[SpriteSheetMaker] Failed to pixelate image: {e} \n {traceback.format_exc()}")
     

        return {'FINISHED'}

class SPRITESHEETMAKER_OT_CombineSprites(Operator):
    bl_idname = "spritesheetmaker.combine_sprites"
    bl_label = "Combine Sprites"
    bl_description = "Combine multiple sprites into a single sprite sheet"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get all props
        props = bpy.context.scene.sprite_sheet_maker_props

        
        # Return if invalid output path
        if(not os.path.exists(props.output_path)):
            popup("'Output Folder' is invalid!", "CANCEL")
            return {'FINISHED'}


        # Combine images together into single file and paste in output
        try:
            props = bpy.context.scene.sprite_sheet_maker_props
            param = sprite_param_from_props()
            from .combine_frames import assemble_sprite_sheet
            assemble_sprite_sheet(props.output_path, param.output_file_path, param.label_font_size, param.frame_margin)
        except Exception as e:
            popup("Error occurred while combining sprites! Make sure your folder follows this structure:\nMyFolder\n   - 1_MyAction\n      - 1.png\n      - 2.png\n   - 2_MyOtherAction\n      - 1.png\n      - 2.png\n\nCheck console for more information")
            print(f"[SpriteSheetMaker] Failed to assemble frames into single sprite sheet: {e} \n {traceback.format_exc()}")
            return {'FINISHED'}
     

        # Notify success
        popup(f"Combined sprites successfully at {param.output_file_path}")
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_CreateSingleSprite(bpy.types.Operator):
    bl_idname = "spritesheetmaker.create_single"
    bl_label = "Create Single Sprite"
    bl_description = "Capture the selected object as a single sprite"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Get all props & params
        props = bpy.context.scene.sprite_sheet_maker_props
        param = sprite_param_from_props(False)


        # Return if no objects given
        if(len(param.objects) == 0):
            popup("Empty or invalid objects!", "CANCEL")
            return {'FINISHED'}

            
        # Return if manual cameras has not been set
        if(not props.auto_camera and ((props.camera_object is None) or (props.camera_object.type != 'CAMERA'))):
            popup("'Camera Object' invalid!", "CANCEL")
            return {'FINISHED'}


        # Return if invalid output path
        if(not os.path.exists(props.output_path)):
            popup("'Output Folder' is invalid!", "CANCEL")
            return {'FINISHED'}
        

        # Create single sprite
        SPRITE_SHEET_MAKER.create_sprite(param)


        # Notify success
        popup(f"Created single sprite successfully at {param.output_file_path}")
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_CreateSheet(Operator):
    bl_idname = "spritesheetmaker.create_sheet"
    bl_label = "Create Sprite Sheet"

    def execute(self, context):

        # Get params and props
        param = sprite_param_from_props()
        props = bpy.context.scene.sprite_sheet_maker_props


        # Check for valid actions
        if(len(param.actions) == 0):
            popup("Empty or invalid actions!", "CANCEL")
            return {'FINISHED'}


        # Checks based on auto camera on or off
        if(props.auto_camera):
            if(len(param.objects) == 0):
                popup("Empty or invalid objects!", "CANCEL")
                return {'FINISHED'}
        else:
            # Return if manual cameras has not been set
            if((props.camera_object is None) or (props.camera_object.type != 'CAMERA')):
                popup("'Camera Object' invalid!", "CANCEL")
                return {'FINISHED'}


        # Return if invalid output path
        if(not os.path.exists(props.output_path)):
            popup("'Output Folder' is invalid!", "CANCEL")
            return {'FINISHED'}

        
        # Get the window manager and create a progress bar
        wm = bpy.context.window_manager
        

        # Create sprie sheet
        try:
            def begin_row_progress(action_name, total_frame):
                wm.progress_begin(0, total_frame)  # Start progress bar

            def update_frame_progress(action_name, frame):
                wm.progress_update(frame)  # Update progress bar
            
            SPRITE_SHEET_MAKER.on_sheet_row_creating.subscribe(begin_row_progress)
            SPRITE_SHEET_MAKER.on_sheet_frame_creating.subscribe(update_frame_progress)
            sprite_sheet_path = SPRITE_SHEET_MAKER.create_sprite_sheet(param, props.output_path)
            popup(f"Created sprite sheet successfully at {sprite_sheet_path}")
        except Exception as e:
            popup("Error occurred while trying to create sprite sheet!\nCheck console for more information")
            print(f"[SpriteSheetMaker] Failed to assemble frames into single sprite sheet: {e} \n {traceback.format_exc()}")
            return {'FINISHED'}
     

        # Finish the progress bar
        wm.progress_end()
        return {'FINISHED'}

class SPRITESHEETMAKER_PT_MainPanel(Panel):
    bl_label = "SpriteSheetMaker"
    bl_idname = "SPRITESHEETMAKER_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SpriteSheetMaker'


    def main_panel(self, context):
        layout = self.layout
        props = context.scene.sprite_sheet_maker_props

        # Objects to Capture
        box = layout.box()
        box.label(text="Objects to Capture")
        row = box.row()
        row.template_list("SPRITESHEETMAKER_UL_ObjectList", "", props, "objects_to_use", props, "objects_index", rows=3)
        col = row.column(align=True)
        col.operator("spritesheetmaker.objects_add", icon='ADD', text="")
        col.operator("spritesheetmaker.objects_remove", icon='REMOVE', text="")
        row = box.row(align=True)
        row.operator("spritesheetmaker.objects_add_all", text="Add All")
        row.operator("spritesheetmaker.objects_remove_all", text="Remove All")
        box.prop(props, "consider_armature_bones")


        # Actions to Capture
        box = layout.box()
        box.label(text="Actions to Capture")
        row = box.row()
        row.template_list("SPRITESHEETMAKER_UL_ActionsToCapture", "", props, "actions_to_capture", props, "actions_index", rows=3)
        col = row.column(align=True)
        col.operator("spritesheetmaker.actions_add", icon='ADD', text="")
        col.operator("spritesheetmaker.actions_remove", icon='REMOVE', text="")
        row = box.row(align=True)
        row.operator("spritesheetmaker.actions_add_all", text="Add All")
        row.operator("spritesheetmaker.actions_remove_all", text="Remove All")


        # Camera Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_camera_settings", icon="TRIA_DOWN" if props.show_camera_settings else "TRIA_RIGHT", emboss=False, text="Camera Settings")
        if props.show_camera_settings:
            box.prop(props, "auto_camera")
            if props.auto_camera:
                row = box.row()
                row.separator(factor=0.05)
                split = row.split(factor=0.60)
                split.label(text="Camera Direction")
                split.prop(props, "camera_direction", text="")
                box.prop(props, "pixels_per_meter", text="Pixels Per Meter")
                box.prop(props, "camera_padding", text="Camera Padding")
            else:
                row = box.row()
                row.separator(factor=0.05)
                split = row.split(factor=0.50)
                split.label(text="Camera Object")
                split.prop(props, "camera_object", text="")


        # Pixelation Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_pixelation_settings", icon="TRIA_DOWN" if props.show_pixelation_settings else "TRIA_RIGHT", emboss=False, text="Pixelation Settings")
        if props.show_pixelation_settings:
            box.prop(props, "to_pixelate")
            if props.to_pixelate:
                box.prop(props, "pixelation_amount", text="Pixelation Amount")
                box.prop(props, "color_amount", text="Pixelation Color Amount")
                box.prop(props, "min_alpha", text="Min Alpha")
                box.prop(props, "alpha_step", text="Alpha Step")
                
                row = box.row()
                split = row.split(factor=0.40)
                split.label(text="Shrink Interp")
                split.prop(props, "shrink_interp", text="")

                row = box.row()
                split = row.split(factor=0.45)
                split.label(text="Test Image")
                split.prop(props, "pixelate_image_path", text="")

                box.separator(factor=0.25)
                row = box.row()
                row.operator("spritesheetmaker.pixelate_image", text="Pixelate Test Image", icon="MOD_REMESH")


        # Output Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_output_settings", icon="TRIA_DOWN" if props.show_output_settings else "TRIA_RIGHT", emboss=False, text="Output Settings")
        if props.show_output_settings:
            box.prop(props, "label_font_size", text="Label Font Size")
            box.prop(props, "frame_margin", text="Frame Margin")
            row = box.row()
            split = row.split(factor=0.45)
            split.label(text="Output Folder")
            split.prop(props, "output_path", text="")
            box.prop(props, "delete_temp_folder", text="Delete Temp Folder")


        # Combine Sprites Button
        layout.separator(factor=0.75)
        row = layout.row()
        row.scale_y = 1.5
        row.operator("spritesheetmaker.combine_sprites", text="Combine Sprites", icon="TEXTURE")


        # Create Single Sprite Button
        layout.separator(factor=0.25)
        row = layout.row()
        row.scale_y = 1.5
        row.operator("spritesheetmaker.create_single", text="Create Single Sprite", icon="FILE_IMAGE")


        # Create Sprite Sheet Button
        layout.separator(factor=0.25)
        row = layout.row()
        row.scale_y = 1.5
        row.operator("spritesheetmaker.create_sheet", text="Create Sprite Sheet", icon="RENDER_ANIMATION")

    def dependencies_panel(self, context):
        layout = self.layout
        col = layout.column(align=True)
        props = context.scene.sprite_sheet_maker_props


        # Show if installation ongoing
        if props.dependency_status == DependencyStatus.INSTALLING.name:
            col.label(text="Installing...", icon='PREFERENCES')
            col.label(text="(This may take a minute)")
        else:  # Show if pending or error
            if(props.dependency_status == DependencyStatus.ERROR.name):
                col.label(text="Error installing", icon='ERROR')
                col.label(text="Check console for details")
            else:
                col.label(text="Dependencies are NOT installed")
            

            col.separator(factor=1.0)

            box = col.box()
            box.label(text="Notes:")
            box.label(text="1. Installs pip pillow package")
            box.label(text="2. Will require internet access")
            box.label(text="3. See system console for progress")

            col.separator(factor=1.0)

            col.operator('dependencies.install', icon='IMPORT')

    def draw(self, context):
        # Check and store if dependencies are met in cache
        global has_dep_cache
        if not has_dep_cache:
            has_dep_cache = has_dependencies()


        # Render panel based on status
        if has_dep_cache:
            self.main_panel(context)
        else:
            self.dependencies_panel(context)


classes = (
    SpriteSheetMakerMessagePopup,
    SpriteSheetMakerObjectItem,
    SpriteSheetMakerActionItem,
    SpriteSheetMakerProperties,
    SPRITESHEETMAKER_OT_dependencies,
    SPRITESHEETMAKER_UL_ObjectList,
    SPRITESHEETMAKER_UL_ActionsToCapture,
    SPRITESHEETMAKER_OT_AddObject,
    SPRITESHEETMAKER_OT_RemoveObject,
    SPRITESHEETMAKER_OT_AddAllObjects,
    SPRITESHEETMAKER_OT_RemoveAllObjects,
    SPRITESHEETMAKER_OT_AddAction,
    SPRITESHEETMAKER_OT_RemoveAction,
    SPRITESHEETMAKER_OT_AddAllActions,
    SPRITESHEETMAKER_OT_RemoveAllActions,
    SPRITESHEETMAKER_OT_PixelateImage,
    SPRITESHEETMAKER_OT_CombineSprites,
    SPRITESHEETMAKER_OT_CreateSingleSprite,
    SPRITESHEETMAKER_OT_CreateSheet,
    SPRITESHEETMAKER_PT_MainPanel,
)


def sprite_param_from_props(is_sheet = True):

    # Get all props
    props = bpy.context.scene.sprite_sheet_maker_props


    # Create sprite param
    param = SpriteParam()


    # Set path to where sprite should be created
    param.output_file_path = f"{props.output_path}/{SPRITE_SHEET_NAME if is_sheet else SINGLE_SPRITE_NAME}"


    # Get all actions
    actions = []
    for item in props.actions_to_capture:
        if not item.action:
            continue

        # To ensure "ReferenceError: StructRNA of type Action has been removed" does not occur
        try: 
            item.action.name
        except ReferenceError as e:
            continue

        actions.append(item.action)
        

    # Set rest of the properties
    param.objects = {item.obj for item in props.objects_to_use if item.obj}
    param.actions = actions
    if props.auto_camera:
        param.camera = None
        param.camera_direction = CameraDirection(props.camera_direction)  # Map camera direction from enum
    else:
        param.camera = props.camera_object
        param.camera_direction = None  # No camera direction if explicit camera is used
    param.camera_padding = props.camera_padding
    param.pixels_per_meter = props.pixels_per_meter
    param.to_pixelate = props.to_pixelate
    param.pixelate_param.pixelation_amount = props.pixelation_amount
    param.pixelate_param.color_amount = props.color_amount
    param.pixelate_param.min_alpha = props.min_alpha
    param.pixelate_param.alpha_step = props.alpha_step
    param.pixelate_param.shrink_interp = ScaleInterpType(props.shrink_interp)  # Ensure shrink interpolation is properly set
    param.consider_armature_bones = props.consider_armature_bones
    param.delete_temp_folder = props.delete_temp_folder
    param.label_font_size = props.label_font_size
    param.frame_margin = props.frame_margin

    return param

def popup(message, icon="INFO"):
    bpy.ops.spritesheetmaker.message_popup('INVOKE_DEFAULT', **{ "message_heading": message,  "message_icon" : icon })

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sprite_sheet_maker_props = PointerProperty(type=SpriteSheetMakerProperties)

def unregister():
    del bpy.types.Scene.sprite_sheet_maker_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()