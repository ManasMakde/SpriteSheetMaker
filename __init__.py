bl_info = {
    "name": "Sprite Sheet Maker",
    "author": "Manas R. Makde",
    "version": (4, 0, 2),
    "description": "3D to 2D sprite sheet converter with optional pixelation"
}


import bpy
import os
from datetime import datetime
from .modules.sprite_sheet_maker_utils import *
from .modules.combine_frames import *
from bpy.types import Panel, Operator, PropertyGroup, UIList
from bpy.props import (
    StringProperty,
    FloatProperty,
    BoolProperty,
    PointerProperty,
    CollectionProperty,
    IntProperty,
    EnumProperty
)


# Constants
SPRITE_SHEET_MAKER = SpriteSheetMaker()
SINGLE_SPRITE_NAME = "sprite"
SPRITE_SHEET_NAME = "sprite_sheet"
DEFAULT_OUTPUT_FOLDER_NAME = "SpriteSheetMaker"
PIXELATE_TEST_IMAGE_POSTFIX = "pixelated"
UNTITLED_STRIP_NAME = "<Untitled>"
UNTITLED_LABEL_TEXT = "Untitled"


# Classes
class SpriteSheetMakerMessagePopup(bpy.types.Operator):
    bl_idname = "spritesheetmaker.message_popup"
    bl_label = "SpriteSheetMaker Message"
    message_heading: StringProperty(name="Heading", default="")
    message_icon: StringProperty(name="Icon", default="INFO")

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

class SpriteSheetMakerCaptureItem(bpy.types.PropertyGroup):

    def action_update(self, context):
        for strip in context.scene.animation_strips:
            for it in strip.capture_items:
                if it == self:
                    strip.update_label_from_action()
                    return

    object: PointerProperty(name="Object", type=bpy.types.Object)
    action: PointerProperty(name="Action", type=bpy.types.Action, update=action_update)
    slot: StringProperty(name="Slot", default="")

class SpriteSheetMakerStripInfo(bpy.types.PropertyGroup):
    label: StringProperty(name="Label", default="")
    capture_items: CollectionProperty(type=SpriteSheetMakerCaptureItem)
    capture_item_index: IntProperty(default=0)
    manual_frames: BoolProperty(name="Manual Frame Selection", default=False)
    frame_start: IntProperty(name="Start", default=0, min=-1048574, max=1048574)
    frame_end: IntProperty(name="End", default=250, min=-1048574, max=1048574)

    def update_label_from_action(self):
        # Iterate through all items
        action_count = 0
        new_label = ""
        for item in self.capture_items:
            if item.action:
                new_label = item.action.name
                action_count +=1
            
            if action_count > 1:
                break
        

        # Assign new label if only 1 action or empty label
        if(action_count <= 1 or self.label.strip() == ""):
            self.label = new_label

class SpriteSheetMakerProperties(PropertyGroup):
    def update_output_folder(self, context):
        if self.output_folder.startswith("//"):
            self.output_folder = bpy.path.abspath(self.output_folder)

            
    # Camera settings
    custom_camera: PointerProperty(name="Custom Camera", type=bpy.types.Object, poll=lambda self, obj: obj.type == 'CAMERA')
    to_auto_capture: BoolProperty(name="To Auto Capture", default=True)
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
    pixels_per_meter: FloatProperty(name="Pixels Per Meter", default=100.0, min=1.0, soft_max=5000.0)
    camera_padding: FloatProperty(name="Camera Padding", unit='LENGTH', default=0.05, min=0.0, soft_max=10.0)
    consider_armature_bones: BoolProperty(default=False)

    # Pixelation settings
    to_pixelate: BoolProperty(name="To Pixelate", default=False)
    pixelation_amount: FloatProperty(name="Pixelation Amount", default=0.9, precision=5, step=0.001, min=0.0, max=1.0)
    color_amount: FloatProperty(name="Pixelation Color Amount", default=50.0, min=0.0, soft_max=1000)
    min_alpha: FloatProperty(name="Min Alpha", default=0.0, min=0.0, max=1.1)
    alpha_step: FloatProperty(name="Alpha Step", default=0.0, min=0.0, max=1.1)
    pixelate_image_path: StringProperty(
        name="Pixelate Image Path",
        subtype="FILE_PATH"
    )

    # Output settings
    label_font_size: IntProperty(name="Label Font Size", default=24, min=0, soft_max=1000)
    surrounding_margin_top: IntProperty(name="Surrounding Margin Top", default=15, min=0, soft_max=1000)
    surrounding_margin_right: IntProperty(name="Surrounding Margin Right", default=15, min=0, soft_max=1000)
    surrounding_margin_bottom: IntProperty(name="Surrounding Margin Bottom", default=15, min=0, soft_max=1000)
    surrounding_margin_left: IntProperty(name="Surrounding Margin Left", default=15, min=0, soft_max=1000)
    label_margin: IntProperty(name="Label Margin", default=15, min=0, soft_max=1000)
    image_margin: IntProperty(name="Image Margin", default=15, min=0, soft_max=1000)
    sprite_consistency: EnumProperty(
        name="Sprite Align",
        items=[
            (SpriteConsistency.INDIVIDUAL.value, "Individual Consistent", "Each sprite fits it's own content"),
            (SpriteConsistency.ROW.value, "Row Consistent", "All sprites in a row have the same dimensions"),
            (SpriteConsistency.ALL.value, "All Consistent", "All sprites in the sheet have the same dimensions")
        ],
        default=SpriteConsistency.INDIVIDUAL.value
    )
    sprite_align: EnumProperty(
        name="Sprite Align",
        items=[
            (SpriteAlign.TOP_LEFT.value, "Top Left", "Align sprite to vertical top & horizontal left"),
            (SpriteAlign.TOP_CENTER.value, "Top Center", "Align sprite to vertical top & horizontal center"),
            (SpriteAlign.TOP_RIGHT.value, "Top Right", "Align sprite to vertical top & horizontal right"),
            (SpriteAlign.MIDDLE_LEFT.value, "Middle Left", "Align sprite to vertical middle & horizontal left"),
            (SpriteAlign.MIDDLE_CENTER.value, "Middle Center", "Align sprite to vertical middle & horizontal center"),
            (SpriteAlign.MIDDLE_RIGHT.value, "Middle Right", "Align sprite to vertical middle & horizontal right"),
            (SpriteAlign.BOTTOM_LEFT.value, "Bottom Left", "Align sprite to vertical bottom & horizontal left"),
            (SpriteAlign.BOTTOM_CENTER.value, "Bottom Center", "Align sprite to vertical bottom & horizontal center"),
            (SpriteAlign.BOTTOM_RIGHT.value, "Bottom Right", "Align sprite to vertical bottom & horizontal right"),
        ],
        default=SpriteAlign.BOTTOM_CENTER.value
    )
    combine_mode: EnumProperty(
        name="Combine Mode",
        items=[
            (CombineMode.IMAGES.value, "Images", "Render out individual images"),
            (CombineMode.STRIPS.value, "Strips", "Render out separate strips for each action"),
            (CombineMode.SHEET.value, "Sheet", "Render out a single sprite sheet"),
        ],
        default=CombineMode.SHEET.value
    )
    delete_temp_folder: BoolProperty(name="Delete Temp Folder", default=True)
    output_folder: StringProperty(
        name="Output Folder",
        subtype="DIR_PATH",
        update=update_output_folder
    )

    # Collapsible section toggles
    show_camera_settings: BoolProperty(name="Show Camera Settings", default=False)
    show_pixelation_settings: BoolProperty(name="Show Pixelation Settings", default=False)
    show_output_settings: BoolProperty(name="Show Output Settings", default=False)

class SPRITESHEETMAKER_UL_AnimationStrips(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.label(text=item.label if item.label != "" else UNTITLED_STRIP_NAME, icon='SEQ_STRIP_DUPLICATE')

class SPRITESHEETMAKER_UL_CaptureItems(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):

        split = layout.split(factor=1/3, align=True)
        col_obj = split.column(align=True)
        col_action = split.column(align=True)
        col_slot = split.column(align=True)

        col_obj.prop(item, "object", text="")
        col_action.prop(item, "action", text="")
        col_slot.prop(item, "slot", text="Slot")

class SPRITESHEETMAKER_OT_duplicate_strip(bpy.types.Operator):
    bl_idname = "spritesheetmaker.duplicate_strip"
    bl_label = "Duplicate Strip"
    bl_description = "Duplicate the selected animation strip"
    bl_options = {'UNDO'}

    def execute(self, context):
        # Get essentials
        scene = context.scene
        strips = scene.animation_strips
        idx = scene.strip_index


        # Return if no strips exist
        if idx < 0 or idx >= len(strips):
            return bpy.ops.spritesheetmaker.add_strip()


        # Store original strip
        original_strip = strips[idx]


        # Create new strip
        new_strip = strips.add()
        new_strip.label = original_strip.label
        new_strip.capture_items.clear()
        for item in original_strip.capture_items:
            dst_item = new_strip.capture_items.add()
            dst_item.object = item.object
            dst_item.action = item.action
            dst_item.slot = item.slot
        new_strip.manual_frames = original_strip.manual_frames
        new_strip.frame_start = original_strip.frame_start
        new_strip.frame_end = original_strip.frame_end


        # Set index of strip
        new_index = len(strips) - 1
        target_index = idx + 1
        strips.move(new_index, target_index)
        scene.strip_index = target_index


        return {'FINISHED'}

class SPRITESHEETMAKER_OT_add_strip(bpy.types.Operator):
    bl_idname = "spritesheetmaker.add_strip"
    bl_label = "Add Strip"
    bl_description = "Add new animation strip"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        new = scene.animation_strips.add()
        new.frame_start = 1
        new.frame_end = 250
        scene.strip_index = len(scene.animation_strips) - 1
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_remove_strip(bpy.types.Operator):
    bl_idname = "spritesheetmaker.remove_strip"
    bl_label = "Remove Strip"
    bl_description = "Delete animation strip"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        idx = scene.strip_index
        if 0 <= idx < len(scene.animation_strips):
            scene.animation_strips.remove(idx)
            scene.strip_index = max(0, min(len(scene.animation_strips) - 1, idx - 1))
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_move_strip(bpy.types.Operator):
    bl_idname = "spritesheetmaker.move_strip"
    bl_label = "Move Strip"
    bl_description = "Move animation strip up or down"
    bl_options = {'UNDO'}

    direction: EnumProperty(
        items=[
            ("UP", "Up", ""),
            ("DOWN", "Down", "")
        ]
    )

    def execute(self, context):
        scene = context.scene
        idx = scene.strip_index
        strips = scene.animation_strips

        if self.direction == "UP" and idx > 0:
            strips.move(idx, idx - 1)
            scene.strip_index -= 1

        elif self.direction == "DOWN" and idx < len(strips) - 1:
            strips.move(idx, idx + 1)
            scene.strip_index += 1

        return {"FINISHED"}

class SPRITESHEETMAKER_OT_add_capture_item(bpy.types.Operator):
    bl_idname = "spritesheetmaker.add_capture_item"
    bl_label = "Add Capture Item"
    bl_description = "Add capture item"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        si = scene.strip_index
        if si < 0 or si >= len(scene.animation_strips):
            return {'CANCELLED'}
        
        strip = scene.animation_strips[si]
        strip.capture_items.add()
        strip.capture_item_index = len(strip.capture_items) - 1
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_remove_capture_item(bpy.types.Operator):
    bl_idname = "spritesheetmaker.remove_capture_item"
    bl_label = "Remove Capture Item"
    bl_description = "Remove capture item"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        si = scene.strip_index
        if si < 0 or si >= len(scene.animation_strips):
            return {'CANCELLED'}
        strip = scene.animation_strips[si]
        ii = strip.capture_item_index
        if 0 <= ii < len(strip.capture_items):
            strip.capture_items.remove(ii)
            strip.capture_item_index = max(0, ii - 1)
        return {'FINISHED'}


# Primary Buttons
class SPRITESHEETMAKER_OT_CreateAutoCamera(Operator):
    bl_idname = "spritesheetmaker.create_auto_camera"
    bl_label = "Create Auto Camera"
    bl_description = "Create camera from given auto capture parameters"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get assigned custom camera
        props = bpy.context.scene.sprite_sheet_maker_props
        cam_obj = props.custom_camera


        # Create new camera if no custom camera assigned
        if(cam_obj is None):
            cam_name = f"New{CAMERA_NAME}"
            cam_data = bpy.data.cameras.new(name=cam_name)
            cam_obj = bpy.data.objects.new(cam_name, cam_data)
            bpy.context.collection.objects.link(cam_obj)


        # Set it up based on auto parameters
        param = auto_capture_param_from_props()
        setup_auto_camera(param, cam_obj)


        return {'FINISHED'}

class SPRITESHEETMAKER_OT_PixelateImage(Operator):
    bl_idname = "spritesheetmaker.pixelate_image"
    bl_label = "Pixelate Image"
    bl_description = "Pixelate given image"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get props
        props = bpy.context.scene.sprite_sheet_maker_props

        
        # Return if invalid test image path
        if(not os.path.exists(props.pixelate_image_path)):
            popup("'Test image' is invalid!", "CANCEL")
            return {'FINISHED'}


        # Combine images together into single file and paste in output
        try:
            # Generate param
            param = pixelate_param_from_props()

            # Pixelate the image
            pixelated_output_path = get_pixelated_img_path()
            pixelate_images({ props.pixelate_image_path:pixelated_output_path }, param)

            # Notify success
            popup(f"Pixelated image successfully at {pixelated_output_path}")
        except Exception as e:
            error_msg = f"Error occurred while pixelating image! Make sure you have passed a valid image \n {e} \n {traceback.format_exc()}"
            popup(error_msg)
            print(f"[SpriteSheetMaker {datetime.now()}] {error_msg}")
     

        return {'FINISHED'}

class SPRITESHEETMAKER_OT_CombineSprites(Operator):
    bl_idname = "spritesheetmaker.combine_sprites"
    bl_label = "Combine Sprites"
    bl_description = "Combine multiple sprites into a single sprite sheet"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get props
        props = bpy.context.scene.sprite_sheet_maker_props

        
        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            popup("'Output Folder' is invalid!", "CANCEL")
            return {'FINISHED'}


        # Combine images together into single file and paste in output
        try:
            param = assemble_param_from_props()
            assemble_images(param)
        except Exception as e:
            error_msg = f"Error occurred while combining sprites!\nMake sure the provided 'Output Folder' follows this structure:\nMyFolder\n   - 1_Walking\n      - 1.png\n      - 2.png\n   - 2_Attacking\n      - 1.png\n      - 2.png\n\nFailed to assemble frames into single sprite sheet: {e} \n {traceback.format_exc()}"
            popup(error_msg)
            print(f"[SpriteSheetMaker {datetime.now()}] {error_msg}")
            return {'FINISHED'}
     

        # Notify success
        popup(f"Combined sprites successfully at {os.path.normpath(param.output_path)}")
        return {'FINISHED'}

class SPRITESHEETMAKER_OT_CreateSingleSprite(bpy.types.Operator):
    bl_idname = "spritesheetmaker.create_single"
    bl_label = "Create Single Sprite"
    bl_description = "Render out a single sprite"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        
        # Get props
        props = context.scene.sprite_sheet_maker_props


        # Return if no objects given
        objects_to_capture = get_objects_to_capture() if props.to_auto_capture else []
        if(props.to_auto_capture and len(objects_to_capture) == 0):
            popup("Empty or invalid objects in 'Capture Items'!", "CANCEL")
            return {'FINISHED'}

            
        # Return if manual cameras has not been set
        if(not props.to_auto_capture and ((props.custom_camera is None) or (props.custom_camera.type != 'CAMERA'))):
            popup("Either set 'Custom Camera' or enable 'To Auto Capture' first!", "CANCEL")
            return {'FINISHED'}


        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            popup("'Output Folder' is invalid!", "CANCEL")
            return {'FINISHED'}
        

        # Create single sprite
        try:
            # Create sprite
            param = sprite_param_from_props()
            SPRITE_SHEET_MAKER.create_sprite(param)

            # Add image and margin
            assemble_param = assemble_param_from_props()
            add_label_to_image(param.output_file_path, get_label_text(), assemble_param)

            popup(f"Created single sprite successfully at {os.path.normpath(param.output_file_path)}")
            return {'FINISHED'}
        except Exception as e:
            error_msg = f"Error occurred while creating single sprite!\n {e} \n {traceback.format_exc()}"
            popup(error_msg)
            print(f"[SpriteSheetMaker {datetime.now()}] {error_msg}")
            return {'FINISHED'}

class SPRITESHEETMAKER_OT_CreateSheet(Operator):
    bl_idname = "spritesheetmaker.create_sheet"
    bl_label = "Create Sprite Sheet"
    bl_description = "Create entire sheet"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get Scene & props
        scene = bpy.context.scene
        props = context.scene.sprite_sheet_maker_props


        # Return if no strips
        if(len(scene.animation_strips) == 0):
            popup("Empty 'Animation Strips'!", "CANCEL")
            return {'FINISHED'}


        # Return in case of anything invalid in strip
        for strip_item in scene.animation_strips:

            # Return if empty capture items
            if(len(strip_item.capture_items) == 0):
                popup(f"Empty 'Capture Items' in '{strip_item.label if strip_item.label!='' else UNTITLED_STRIP_NAME}' Strip!", "CANCEL")
                return {'FINISHED'}

            # Return if any invalid objects or actions
            valid_action_count = 0
            for capture_item in strip_item.capture_items:
                if (not capture_item.object):
                    popup(f"Invalid Object in 'Capture Items' of '{strip_item.label if strip_item.label!='' else UNTITLED_STRIP_NAME}' Strip!", "CANCEL")
                    return {'FINISHED'}
                
                try:  # To ensure "ReferenceError: StructRNA of type Action has been removed" does not occur
                    if(capture_item.action != None):
                        capture_item.action.name
                        valid_action_count += 1
                except ReferenceError as e:
                    popup(f"Invalid Action in 'Capture Items' of '{strip_item.label if strip_item.label!='' else UNTITLED_STRIP_NAME}' Strip!", "CANCEL")
                    return {'FINISHED'}
            
            # Return if not a single valid action was providede
            if(valid_action_count == 0):
                popup(f"Not a single Action provided in 'Capture Items' of '{strip_item.label if strip_item.label!='' else UNTITLED_STRIP_NAME}' Strip!", "CANCEL")
                return {'FINISHED'}
            
        
        # Return if manual cameras has not been set
        if(not props.to_auto_capture and ((props.custom_camera is None) or (props.custom_camera.type != 'CAMERA'))):
            popup("Either set 'Custom Camera' or enable 'To Auto Capture' first!", "CANCEL")
            return {'FINISHED'}


        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            popup("'Output Folder' is invalid!", "CANCEL")
            return {'FINISHED'}


        # Get the window manager and create a progress bar
        wm = bpy.context.window_manager


        # Create sprie sheet
        try:
            def begin_row_progress(strip_label, total_frame):
                wm.progress_begin(0, total_frame)  # Start progress bar

            def update_frame_progress(strip_label, frame):
                wm.progress_update(frame)  # Update progress bar
            
            SPRITE_SHEET_MAKER.on_sheet_row_creating.subscribe(begin_row_progress)
            SPRITE_SHEET_MAKER.on_sheet_frame_creating.subscribe(update_frame_progress)

            param = sprite_sheet_param_from_props()
            SPRITE_SHEET_MAKER.create_sprite_sheet(param)
            popup(f"Created successfully at {os.path.normpath(param.assemble_param.output_path)}")
        except Exception as e:
            error_msg = f"Error occurred while trying to create sprite sheet!\n{e}\n{traceback.format_exc()}"
            popup(error_msg)
            print(f"[SpriteSheetMaker {datetime.now()}] {error_msg}")
            return {'FINISHED'}
    

        # Finish the progress bar
        wm.progress_end()
        return {'FINISHED'}


# Main Panel
class SPRITESHEETMAKER_PT_MainPanel(Panel):
    bl_label = "SpriteSheetMaker"
    bl_idname = "SPRITESHEETMAKER_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SpriteSheetMaker'


    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = context.scene.sprite_sheet_maker_props


        # Animation Strips
        box = layout.box()
        box.label(text="Animation Strips")
        row = box.row()
        row.template_list(
            "SPRITESHEETMAKER_UL_AnimationStrips",
            "",
            scene,
            "animation_strips",
            scene,
            "strip_index",
            rows=4,
            maxrows=4
        )


        # Strips Add & Remove buttons
        ops = row.column(align=True)
        ops.operator("spritesheetmaker.duplicate_strip", icon='DUPLICATE', text='')
        ops.separator()
        ops.operator('spritesheetmaker.add_strip', icon='ADD', text='')
        ops.operator('spritesheetmaker.remove_strip', icon='REMOVE', text='')


        # Strips Up & Down buttons
        ops.separator()
        ops.operator('spritesheetmaker.move_strip', icon='TRIA_UP', text="").direction = 'UP'
        ops.operator('spritesheetmaker.move_strip', icon='TRIA_DOWN', text="").direction = 'DOWN'


        # Strip Info
        row_box = layout.box()
        has_strip = len(scene.animation_strips) > 0 and 0 <= scene.strip_index < len(scene.animation_strips)
        row_box.enabled = has_strip
        row_box.label(text=f"Strip Info{'' if has_strip else ' (Add Strip First)'}")

        if has_strip:

            # Label
            strip = scene.animation_strips[scene.strip_index]
            split = row_box.split(factor=0.25)
            split.label(text="Label")
            split.prop(strip, 'label', text='')

            # Capture Items
            row_box.label(text="Capture Items")
            row_layout = row_box.row()
            row_layout.template_list('SPRITESHEETMAKER_UL_CaptureItems', '', strip, 'capture_items', strip, 'capture_item_index', rows=3, maxrows=3)
            col = row_layout.column(align=True)
            col.operator('spritesheetmaker.add_capture_item', icon='ADD', text='')
            col.operator('spritesheetmaker.remove_capture_item', icon='REMOVE', text='')

            # Manual Frames
            row_box.prop(strip, "manual_frames")

            # Frame Start & End
            if strip.manual_frames:
                row2 = row_box.row(align=True)
                split = row2.split(factor=0.5)
                split.prop(strip, 'frame_start', text='Frame Start')
                split.prop(strip, 'frame_end', text='Frame End')
        else:

            # Dummy Stuff
            split = row_box.split(factor=0.25)
            split.label(text="Label")
            split.prop(scene, 'dummy_label', text='')
            row_box.label(text="Capture Items")
            row_layout = row_box.row()
            row_layout.template_list('SPRITESHEETMAKER_UL_CaptureItems', '', scene, 'dummy_items', scene, 'dummy_index', rows=3, maxrows=3)
            col = row_layout.column(align=True)
            col.operator('spritesheetmaker.add_capture_item', icon='ADD', text='')
            col.operator('spritesheetmaker.remove_capture_item', icon='REMOVE', text='')
            row_box.prop(scene, "dummy_manual_frames")


        # Camera Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_camera_settings", icon="TRIA_DOWN" if props.show_camera_settings else "TRIA_RIGHT", emboss=False, text="Camera Settings")
        if props.show_camera_settings:
            row = box.row()
            row.separator(factor=0.05)

            # Custom Camera
            split = row.split(factor=0.55)
            split.label(text="Custom Camera")
            split.prop(props, "custom_camera", text="")
            
            # To Auto Capture
            box.prop(props, "to_auto_capture")
            if props.to_auto_capture:
                row = box.row()
                row.separator(factor=0.05)

                # Camera Direction
                split = row.split(factor=0.60)
                split.label(text="Camera Direction")
                split.prop(props, "camera_direction", text="")

                # Pixels Per Meter 
                box.prop(props, "pixels_per_meter", text="Pixels Per Meter")

                # Camera Padding 
                box.prop(props, "camera_padding", text="Camera Padding")

                # Consider Armature Bones
                box.prop(props, "consider_armature_bones", text="Consider Armature Bones")

                # Create Auto Camera Button
                box.separator(factor=0.25)
                row = box.row()
                button_text = "Create Auto Camera" if props.custom_camera == None else "Modify Custom Camera"
                row.operator("spritesheetmaker.create_auto_camera", text=button_text, icon="OUTLINER_OB_CAMERA")
                

        # Pixelation Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_pixelation_settings", icon="TRIA_DOWN" if props.show_pixelation_settings else "TRIA_RIGHT", emboss=False, text="Pixelation Settings")
        if props.show_pixelation_settings:

            # To Pixelate
            box.prop(props, "to_pixelate")
            if props.to_pixelate:

                # Pixelation
                box.prop(props, "pixelation_amount", text="Pixelation")

                # Color Amount
                box.prop(props, "color_amount", text="Color Amount")

                # Min Alpha
                box.prop(props, "min_alpha", text="Min Alpha")

                # Alpha Step
                box.prop(props, "alpha_step", text="Alpha Step")

                # Test Image
                row = box.row()
                split = row.split(factor=0.45)
                split.label(text="Test Image")
                split.prop(props, "pixelate_image_path", text="")

                # Pixelate Test Image Button
                box.separator(factor=0.25)
                row = box.row()
                row.operator("spritesheetmaker.pixelate_image", text="Pixelate Test Image", icon="MOD_REMESH")


        # Output Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_output_settings", icon="TRIA_DOWN" if props.show_output_settings else "TRIA_RIGHT", emboss=False, text="Output Settings")
        if props.show_output_settings:

            # Label Font Size
            box.prop(props, "label_font_size", text="Label Font Size")

            # Surrounding Margins
            box.label(text="Surrounding Margins")
            row = box.row(align=True)  # Create a row layout
            row.prop(props, "surrounding_margin_top", text="Top")
            row.prop(props, "surrounding_margin_right", text="Right")
            row.prop(props, "surrounding_margin_bottom", text="Bottom")
            row.prop(props, "surrounding_margin_left", text="Left")

            # Label Margin
            box.prop(props, "label_margin", text="Label Margin")

            # Image Margin
            box.prop(props, "image_margin", text="Image Margin")
            
            # Sprite Consistency
            row = box.row()
            split = row.split(factor=0.60)
            split.label(text="Sprite Consistency")
            split.prop(props, "sprite_consistency", text="")

            # Sprite Align
            row = box.row()
            split = row.split(factor=0.60)
            split.label(text="Sprite Align")
            split.prop(props, "sprite_align", text="")

            # Combine Mode
            row = box.row()
            split = row.split(factor=0.60)
            split.label(text="Combine Mode")
            split.prop(props, "combine_mode", text="")

            # Delete Temp Folder
            box.prop(props, "delete_temp_folder", text="Delete Temp Folder")
        

        # Output folder
        layout.separator(factor=0.5)
        row = layout.row()
        split = row.split(factor=0.45)
        split.label(text="Output Folder")
        split.prop(props, "output_folder", text="")


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
        if props.combine_mode == CombineMode.SHEET.value:
            create_btn_text = "Create Sprite Sheet"
        elif props.combine_mode == CombineMode.STRIPS.value:
            create_btn_text = "Create Sprite Strips"
        else:
            create_btn_text = "Create Sprite Images"

        layout.separator(factor=0.25)
        row = layout.row()
        row.scale_y = 1.5
        row.operator("spritesheetmaker.create_sheet", text=create_btn_text, icon="RENDER_ANIMATION")


# Param Methods
def assemble_param_from_props():

    # Get all props
    props = bpy.context.scene.sprite_sheet_maker_props


    # Set assemble parameters
    param = AssembleParam()
    param.input_folder_path = props.output_folder

    if(props.combine_mode == CombineMode.SHEET.value):
        param.output_path = get_sprite_sheet_path()
    elif(props.combine_mode == CombineMode.STRIPS.value):
        param.output_path = get_sprite_strips_path()
    elif(props.combine_mode == CombineMode.IMAGES.value):
        param.output_path = get_sprite_images_path()

    param.font_size = props.label_font_size
    param.surrounding_margin = (props.surrounding_margin_top, props.surrounding_margin_right, props.surrounding_margin_bottom, props.surrounding_margin_left)
    param.label_margin = props.label_margin
    param.image_margin = props.image_margin
    param.consistency = SpriteConsistency(props.sprite_consistency)
    param.align = SpriteAlign(props.sprite_align)
    param.combine_mode = CombineMode(props.combine_mode)

    return param

def auto_capture_param_from_props():

    # Get all props & scene
    props = bpy.context.scene.sprite_sheet_maker_props
    scene = bpy.context.scene


    # Set auto capture parameters
    param = AutoCaptureParam()
    param.objects = get_objects_to_capture()
    param.consider_armature_bones = props.consider_armature_bones
    param.camera_direction = CameraDirection(props.camera_direction)
    param.pixels_per_meter = props.pixels_per_meter
    param.camera_padding = props.camera_padding


    return param

def pixelate_param_from_props():

    # Get all props
    props = bpy.context.scene.sprite_sheet_maker_props


    # Set pixelation parameters
    param = PixelateParam()
    param.pixelation_amount = props.pixelation_amount
    param.color_amount = props.color_amount
    param.min_alpha = props.min_alpha
    param.alpha_step = props.alpha_step


    return param

def sprite_param_from_props():

    # Get all props
    props = bpy.context.scene.sprite_sheet_maker_props


    # Set sprite parameters
    param = SpriteParam()
    param.output_file_path = get_sprite_path()
    param.camera = props.custom_camera


    # Set Auto capture
    param.to_auto_capture = props.to_auto_capture
    if props.to_auto_capture:
        param.auto_capture_param = auto_capture_param_from_props()


    # Set Pixelation    
    param.to_pixelate = props.to_pixelate
    if(param.to_pixelate):
        param.pixelate_param = pixelate_param_from_props()


    return param

def sprite_sheet_param_from_props():

    # Get all props & scene
    props = bpy.context.scene.sprite_sheet_maker_props
    scene = bpy.context.scene


    # Iterate and get all strips
    animation_strips:list[StripParam] = []
    for strip_item in scene.animation_strips:
        strip_param = StripParam()
        strip_param.label = strip_item.label
        strip_param.capture_items = [(capture_item.object, capture_item.action, capture_item.slot) for capture_item in strip_item.capture_items]
        strip_param.manual_frames = strip_item.manual_frames
        strip_param.frame_start = strip_item.frame_start
        strip_param.frame_end = strip_item.frame_end
        animation_strips.append(strip_param)


    # Set sheet parameters
    param = SpriteSheetParam()
    param.animation_strips = animation_strips
    param.temp_folder_path = props.output_folder
    param.delete_temp_folder = props.delete_temp_folder


    # Set sprite parameters
    param.sprite_param = sprite_param_from_props()


    # Set assemble parameters
    param.assemble_param = assemble_param_from_props()


    return param


# Helper Methods
def get_label_text():

    # Get the label text of the first strip 
    scene = bpy.context.scene
    for strip_item in scene.animation_strips:
        if(strip_item.label == ""):
            continue
    
        return strip_item.label
    
    return UNTITLED_LABEL_TEXT

def get_pixelated_img_path():

    # Get all props
    props = bpy.context.scene.sprite_sheet_maker_props
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()


    # Add postfix to the file name
    dir_name, file_name = os.path.split(props.pixelate_image_path)
    name, ext = os.path.splitext(file_name)
    pixelated_output_path = os.path.join(dir_name, f"{name}_{PIXELATE_TEST_IMAGE_POSTFIX}.{file_ext}")
    

    return unique_path(pixelated_output_path)

def get_sprite_sheet_path():

    # Get initial path
    props = bpy.context.scene.sprite_sheet_maker_props
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()
    sprite_sheet_path = unique_path(f"{props.output_folder}/{SPRITE_SHEET_NAME}.{file_ext}")


    return sprite_sheet_path

def get_sprite_strips_path():
    
    # Get initial path
    props = bpy.context.scene.sprite_sheet_maker_props
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()
    sprite_sheet_path = unique_path(f"{props.output_folder}/{DEFAULT_OUTPUT_FOLDER_NAME}")


    return sprite_sheet_path

def get_sprite_images_path():

    # Get initial path
    props = bpy.context.scene.sprite_sheet_maker_props
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()
    sprite_sheet_path = unique_path(f"{props.output_folder}/{DEFAULT_OUTPUT_FOLDER_NAME}")


    return sprite_sheet_path

def get_sprite_path():

    # Get initial path
    props = bpy.context.scene.sprite_sheet_maker_props
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()
    sprite_path = unique_path(f"{props.output_folder}/{SINGLE_SPRITE_NAME}.{file_ext}")


    return sprite_path

def get_objects_to_capture():

    # Get scene
    scene = bpy.context.scene


    # Get objects in strip
    objects = set()
    for strip in scene.animation_strips:
        for item in strip.capture_items:
            if(item.object is None):
                continue
            
            objects.add(item.object)


    return objects

def popup(message, icon="INFO"):
    bpy.ops.spritesheetmaker.message_popup('INVOKE_DEFAULT', **{ "message_heading": message,  "message_icon" : icon })


# Initialize Classes
classes = (
    SpriteSheetMakerMessagePopup,
    SpriteSheetMakerProperties,
    SpriteSheetMakerCaptureItem,
    SpriteSheetMakerStripInfo,
    SPRITESHEETMAKER_UL_AnimationStrips,
    SPRITESHEETMAKER_UL_CaptureItems,
    SPRITESHEETMAKER_OT_duplicate_strip,
    SPRITESHEETMAKER_OT_add_strip,
    SPRITESHEETMAKER_OT_remove_strip,
    SPRITESHEETMAKER_OT_move_strip,
    SPRITESHEETMAKER_OT_add_capture_item,
    SPRITESHEETMAKER_OT_remove_capture_item,
    SPRITESHEETMAKER_OT_CreateAutoCamera,
    SPRITESHEETMAKER_OT_PixelateImage,
    SPRITESHEETMAKER_OT_CombineSprites,
    SPRITESHEETMAKER_OT_CreateSingleSprite,
    SPRITESHEETMAKER_OT_CreateSheet,
    SPRITESHEETMAKER_PT_MainPanel,
)


# Initialize Methods
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.sprite_sheet_maker_props = PointerProperty(type=SpriteSheetMakerProperties)

    bpy.types.Scene.animation_strips = CollectionProperty(type=SpriteSheetMakerStripInfo)
    bpy.types.Scene.strip_index = IntProperty(default=0)

    bpy.types.Scene.dummy_label = StringProperty(name='Dummy Label', default='')
    bpy.types.Scene.dummy_items = CollectionProperty(type=SpriteSheetMakerCaptureItem)
    bpy.types.Scene.dummy_index = IntProperty(default=0)
    bpy.types.Scene.dummy_manual_frames = BoolProperty(name="Manual Frame Selection", default=False)
    bpy.types.Scene.dummy_start = IntProperty(name='Dummy Start', default=0, min=-1048574, max=1048574)
    bpy.types.Scene.dummy_end = IntProperty(name='Dummy End', default=250, min=-1048574, max=1048574)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

    del bpy.types.Scene.sprite_sheet_maker_props

    del bpy.types.Scene.animation_strips
    del bpy.types.Scene.strip_index
    del bpy.types.Scene.dummy_label
    del bpy.types.Scene.dummy_items
    del bpy.types.Scene.dummy_index
    del bpy.types.Scene.dummy_manual_frames
    del bpy.types.Scene.dummy_start
    del bpy.types.Scene.dummy_end


if __name__ == "__main__":
    register()