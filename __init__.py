bl_info = {
    "name": "Sprite Sheet Maker",
    "author": "Manas R. Makde",
    "version": (5, 1, 3),
    "description": "3D to 2D sprite sheet converter with optional pixelation"
}


import bpy
import os
import json
from datetime import datetime
from .modules.sprite_sheet_utils import *
from .modules.combine_frames import *
from bpy.types import Panel, Operator, PropertyGroup, Object, Action, UIList, Scene
from bpy_extras.io_utils import ExportHelper, ImportHelper
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
DEFAULT_SETTINGS_FILE_NAME = "ssm_settings.json"
PIXELATE_TEST_IMAGE_POSTFIX = "pixelated"
UNTITLED_STRIP_NAME = "<Untitled>"
UNTITLED_LABEL_TEXT = "Untitled"
EXCLUDE_SYNC_PROPERTIES = {"rna_type", "name", "capture_items", "label", "pixelate_image_path", "in_sync"}


# Classes
class SSM_MessagePopup(Operator):
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
class SSM_CaptureItem(PropertyGroup):

    def action_update(self, context):
        for strip in context.scene.animation_strips:
            for it in strip.capture_items:
                if it == self:
                    strip.update_label_from_action()
                    return

    object: PointerProperty(name="Object", type=Object)
    action: PointerProperty(name="Action", type=Action, update=action_update)
    slot: StringProperty(name="Slot", default="")
class SSM_StripInfo(PropertyGroup):

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
    def sync_update(self, context, prop_name):

        strip = get_current_strip()
        if not strip.in_sync:
            return
    
        SSM_OT_sync_strips.sync(context, {prop_name})

    in_sync: BoolProperty(name="Sync Strip", default=True)
    label: StringProperty(name="Label", default="")
    capture_items: CollectionProperty(type=SSM_CaptureItem)
    capture_item_index: IntProperty(default=0)
    
    
    # Camera settings
    custom_camera: PointerProperty(name="Custom Camera", type=Object, poll=lambda self, obj: obj.type == 'CAMERA', update=lambda self, ctx: self.sync_update(ctx, "custom_camera"))
    to_auto_capture: BoolProperty(name="To Auto Capture", default=True, update=lambda self, ctx: self.sync_update(ctx, "to_auto_capture"))
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
        default=CameraDirection.NEG_X.value,
        update=lambda self, ctx: self.sync_update(ctx, "camera_direction")
    )
    h_center_object: PointerProperty(name="Horizontal Center Object", type=Object, update=lambda self, ctx: self.sync_update(ctx, "h_center_object"))
    h_center_bone: StringProperty(name="Horizontal Center Bone", default="")
    v_center_object: PointerProperty(name="Vertical Center Object", type=Object, update=lambda self, ctx: self.sync_update(ctx, "v_center_object"))
    v_center_bone: StringProperty(name="Vertical Center Bone", default="")
    consider_armature_bones: BoolProperty(default=False, update=lambda self, ctx: self.sync_update(ctx, "consider_armature_bones"))
    pixels_per_meter: FloatProperty(name="Pixels Per Meter", default=100.0, min=1.0, soft_max=5000.0, update=lambda self, ctx: self.sync_update(ctx, "pixels_per_meter"))
    camera_padding: FloatProperty(name="Camera Padding", unit='LENGTH', default=0.0, min=0.0, soft_max=10.0, update=lambda self, ctx: self.sync_update(ctx, "camera_padding"))


    # Pixelation settings
    to_pixelate: BoolProperty(name="To Pixelate", default=False, update=lambda self, ctx: self.sync_update(ctx, "to_pixelate"))
    pixelation_amount: FloatProperty(name="Pixelation Amount", default=0.9, precision=5, step=0.001, min=0.0, max=1.0, update=lambda self, ctx: self.sync_update(ctx, "pixelation_amount"))
    color_amount: FloatProperty(name="Pixelation Color Amount", default=50.0, min=0.0, soft_max=1000, update=lambda self, ctx: self.sync_update(ctx, "color_amount"))
    min_alpha: FloatProperty(name="Min Alpha", default=0.0, min=0.0, max=1.1, update=lambda self, ctx: self.sync_update(ctx, "min_alpha"))
    alpha_step: FloatProperty(name="Alpha Step", default=0.0, min=0.0, max=1.1, update=lambda self, ctx: self.sync_update(ctx, "alpha_step"))
    pixelate_image_path: StringProperty(
        name="Pixelate Image Path",
        subtype="FILE_PATH",
        update=lambda self, ctx: self.sync_update(ctx, "pixelate_image_path")
    )
    
    manual_frames: BoolProperty(name="Manual Frame Selection", default=False, update=lambda self, ctx: self.sync_update(ctx, "manual_frames"))
    frame_start: IntProperty(name="Start", default=0, min=-1048574, max=1048574, update=lambda self, ctx: self.sync_update(ctx, "frame_start"))
    frame_end: IntProperty(name="End", default=250, min=-1048574, max=1048574, update=lambda self, ctx: self.sync_update(ctx, "frame_end"))
class SSM_Properties(PropertyGroup):

    def update_temp_folder(self, context):
        if self.temp_folder.startswith("//"):
            self.temp_folder = bpy.path.abspath(self.temp_folder)
    def update_output_folder(self, context):
        if self.output_folder.startswith("//"):
            self.output_folder = bpy.path.abspath(self.output_folder)
    

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
    temp_folder: StringProperty(
        name="Temp Folder",
        subtype="DIR_PATH",
        update=update_temp_folder
    )
    delete_temp_folder: BoolProperty(name="Delete Temp Folder", default=True)
    output_folder: StringProperty(
        name="Output Folder",
        subtype="DIR_PATH",
        update=update_output_folder
    )

    # Collapsible section toggles
    show_strip_info: BoolProperty(name="Show Strip Info", default=False)
    show_output_settings: BoolProperty(name="Show Output Settings", default=False)
class SSM_OT_key_listener(Operator):
    bl_idname = "spritesheetmaker.key_listener"
    bl_label = "Listen for Keys"
    
    is_alt_pressed = False

    def modal(self, context, event):

        # Check if event is alt key
        is_alt = event.type in {'LEFT_ALT', 'RIGHT_ALT'}
        if not is_alt:
            return {'PASS_THROUGH'}


        # Check if alt key pressed or released
        if event.value == 'PRESS' and not self.is_alt_pressed:
            SSM_OT_key_listener.is_alt_pressed = True
        elif event.value == 'RELEASE' and self.is_alt_pressed:
            SSM_OT_key_listener.is_alt_pressed = False

        return {'PASS_THROUGH'}
    def invoke(self, context, event):

        # Return if requirements are not met
        if not context.window_manager:
            log("Window manager not found for key listener!")
            return {'CANCELLED'}


        log("Starting key listener...")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
class SSM_OT_export_settings(Operator, ExportHelper):
    bl_idname = "spritesheetmaker.export_settings"
    bl_label = "Export"
    bl_description = "Export saved settings"
    bl_options = {'UNDO'}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def get_export_data(self, context):
        props = context.scene.sprite_sheet_maker_props
        export_data = { "strips": [], "props": {} }
        

        # Store all strips
        for strip in context.scene.animation_strips:

            # Store all basic properties e.g. label, custom_camera, etc
            s_data = {}
            for p in strip.rna_type.properties:
                if not p.is_readonly and p.identifier not in {"capture_items", "name"}:
                    s_data[p.identifier] = getattr(strip, p.identifier)
            
            
            # Store all capture items
            s_data["capture_items"] = []
            for item in strip.capture_items:
                i_data = {}
                i_data["object"] = item.object.name if item.object else ""
                i_data["action"] = item.action.name if item.action else ""
                i_data["slot"] =  item.slot
                s_data["capture_items"].append(i_data)
            

            # Add to all strips data 
            export_data["strips"].append(s_data)

        
        # Store all common properties
        for p in props.rna_type.properties:
            if not p.is_readonly and p.identifier not in EXCLUDE_SYNC_PROPERTIES:
                export_data["props"][p.identifier] = getattr(props, p.identifier)


        return export_data
    def invoke(self, context, event):
        self.filepath = DEFAULT_SETTINGS_FILE_NAME
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    def execute(self, context):

        # Return if file path not set
        if not self.filepath:
            log("Export path is empty", True, "ERROR")
            return {'CANCELLED'}


        # Store into json file
        try:
            export_data = self.get_export_data(context)
            with open(self.filepath, 'w') as file:
                json.dump(export_data, file, indent=4)

            log(f"Exported settings to {self.filepath}", True)
            return {'FINISHED'}
        except Exception as e:
            log(f"Failed to export settings Error {e} \n {traceback.format_exc()}", True, "CANCEL")
            return {'CANCELLED'}
class SSM_OT_import_settings(Operator, ImportHelper):
    bl_idname = "spritesheetmaker.import_settings"
    bl_label = "Import"
    bl_description = "Import saved settings"
    bl_options = {'UNDO'}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def load_import_data(self, context, data):
        
        # Get props & scene
        props = context.scene.sprite_sheet_maker_props
        scene = context.scene


        # Clear previous animation strips
        scene.animation_strips.clear()  


        # Create all new strips
        for strip_data in data.get("strips", []):

            # Add new strip
            strip = scene.animation_strips.add()

            # Load all basic properties e.g. label, custom_camera, etc
            for key, val in strip_data.items():
                if key != "capture_items" and hasattr(strip, key):
                    setattr(strip, key, val)
            
            # Load all capture items
            for item_data in strip_data.get("capture_items", []):
                item = strip.capture_items.add()
                item.object = bpy.data.objects[item_data["object"]] if item_data.get("object") in bpy.data.objects else None
                item.action = bpy.data.actions[item_data["action"]] if item_data.get("action") in bpy.data.actions else None
                item.slot = item_data.get("slot", "")


        # Load all common properties
        for key, val in data.get("props", {}).items():
            if hasattr(props, key):
                setattr(props, key, val)
    def invoke(self, context, event):
        self.filepath = DEFAULT_SETTINGS_FILE_NAME
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    def execute(self, context):

        # Return if file path does not exist
        if not os.path.exists(self.filepath):
            log("Import path does not exist", True, "ERROR")
            return {'CANCELLED'}
        

        # Load from json file
        try:
            with open(self.filepath, 'r') as file:
                data = json.load(file)
            
            self.load_import_data(context, data)
            log(f"Imported settings from {self.filepath}")
            return {'FINISHED'}
        except Exception as e:
            log(f"Failed to import settings Error {e} \n {traceback.format_exc()}", True, "CANCEL")
            return {'CANCELLED'}
class SSM_UL_AnimationStrips(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.label(text=item.label if item.label != "" else UNTITLED_STRIP_NAME, icon='SEQ_STRIP_DUPLICATE')
class SSM_OT_duplicate_strip(Operator):
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
        
        # Copy basic properties dynamically
        for prop in original_strip.rna_type.properties:
            if not prop.is_readonly and prop.identifier != "capture_items":
                setattr(new_strip, prop.identifier, getattr(original_strip, prop.identifier))
        
        # Duplicate collection items dynamically
        new_strip.capture_items.clear()
        for item in original_strip.capture_items:
            dst_item = new_strip.capture_items.add()
            for prop in item.rna_type.properties:
                if not prop.is_readonly:
                    setattr(dst_item, prop.identifier, getattr(item, prop.identifier))


        # Set index of strip
        new_index = len(strips) - 1
        target_index = idx + 1
        strips.move(new_index, target_index)
        scene.strip_index = target_index


        return {'FINISHED'}
class SSM_OT_add_strip(Operator):
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
class SSM_OT_remove_strip(Operator):
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
class SSM_OT_move_strip(Operator):
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
class SSM_OT_sync_strips(Operator):
    bl_idname = "spritesheetmaker.sync_strips"
    bl_label = "Sync Strips"
    bl_description = "Sync all animation strips"
    bl_options = {'UNDO'}
    
    _is_syncing = False


    @staticmethod
    def _copy_properties(src_strip, dest_strip, properties=None):

        # Assign all if no properties provided
        properties = set(properties) if properties else set()
        if not properties: 
            for p in src_strip.rna_type.properties:
                if not p.is_readonly and p.identifier not in EXCLUDE_SYNC_PROPERTIES:
                    properties.add(p.identifier)
        

        # Copy paste all properties from src to dest
        for prop in properties:
            if hasattr(dest_strip, prop):
                setattr(dest_strip, prop, getattr(src_strip, prop))


    @staticmethod
    def _sync_impl(context, properties=None):
        
        # Return if no strips
        scene = context.scene
        strips = scene.animation_strips
        curr_idx = scene.strip_index
        if curr_idx < 0 or curr_idx >= len(strips) or len(strips) <= 1:
            return


        # Sync properties to all other strips
        curr_strip = strips[curr_idx]
        for i, dest_strip in enumerate(strips):
            if i == curr_idx or not dest_strip.in_sync:
                continue
            
            SSM_OT_sync_strips._copy_properties(curr_strip, dest_strip, properties)
            

    @staticmethod
    def sync(context, properties=None):

        # To avoid infinite recursion
        if SSM_OT_sync_strips._is_syncing:
            return
        

        # Mark as sync started
        SSM_OT_sync_strips._is_syncing = True


        # Sync
        try:
            SSM_OT_sync_strips._sync_impl(context, properties)
            log(f"Synced '{properties}' across all strips!")

        except Exception as e:
            log(f"Failed to sync properties '{properties}' across all strips! Error: {e} \n {traceback.format_exc()}")

    
        # Mark as sync complete
        SSM_OT_sync_strips._is_syncing = False


    def execute(self, context):

        # Toggle in sync button
        curr_strip = get_current_strip()
        if(curr_strip):
            curr_strip.in_sync = not curr_strip.in_sync
        

        # Return if toggled off or nothing to sync
        if(not curr_strip.in_sync or not are_any_in_sync()):
            return {'FINISHED'}
        

        # If alt pressed; synchronize all other strips with this strip
        if(SSM_OT_key_listener.is_alt_pressed):
            SSM_OT_sync_strips.sync(context)
            return {'FINISHED'}


        # Sync properties of this strip with others
        synced_strip = get_synced_strip()
        SSM_OT_sync_strips._copy_properties(synced_strip, curr_strip)


        return {'FINISHED'}
class SSM_UL_CaptureItems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):

        split = layout.split(factor=1/3, align=True)
        col_obj = split.column(align=True)
        col_action = split.column(align=True)
        col_slot = split.column(align=True)

        col_obj.prop(item, "object", text="")
        col_action.prop(item, "action", text="")
        col_slot.prop(item, "slot", text="Slot")
class SSM_OT_play_capture_items(Operator):
    bl_idname = "spritesheetmaker.play_capture_items"
    bl_label = "Play Capture Items"
    bl_description = "Preview strip animations simultaneously"
    bl_options = {'UNDO'}

    def execute(self, context):

        # Return if no capture items
        scene = context.scene
        si = scene.strip_index
        strip = scene.animation_strips[si]
        if si < 0 or si >= len(scene.animation_strips) or len(strip.capture_items) == 0:
            return {'CANCELLED'}
        

        # Assign all actions to respective Objects
        min_frame = float('inf')
        max_frame = float('-inf')
        has_valid_action = False
        for item in strip.capture_items:
            if not item.object or not item.action or not item.object.animation_data:
                continue
        
            item.object.animation_data.action = item.action
            if item.action.frame_range:
                min_frame = min(min_frame, item.action.frame_range[0])
                max_frame = max(max_frame, item.action.frame_range[1])
                has_valid_action = True
        

        # Set start and end frame
        if has_valid_action:
            scene.frame_start = int(min_frame)
            scene.frame_end = int(max_frame)
            scene.frame_current = int(min_frame)
        

        # Play animations
        if not context.screen.is_animation_playing:
            bpy.ops.screen.animation_play() 
        
        
        return {'FINISHED'}
class SSM_OT_add_capture_item(Operator):
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
class SSM_OT_remove_capture_item(Operator):
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
class SSM_OT_CreateAutoCamera(Operator):
    bl_idname = "spritesheetmaker.create_auto_camera"
    bl_label = "Create Auto Camera"
    bl_description = "Create camera from given auto capture parameters"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get assigned custom camera
        curr_strip = get_current_strip()
        cam_obj = curr_strip.custom_camera


        # Create new camera if no custom camera assigned
        if(cam_obj is None):
            cam_data = bpy.data.cameras.new(name=AUTO_CAMERA_NAME)
            cam_obj = bpy.data.objects.new(AUTO_CAMERA_NAME, cam_data)
            bpy.context.collection.objects.link(cam_obj)


        # Set it up based on auto parameters
        param = auto_capture_param_from_props()
        setup_auto_camera(param, cam_obj)


        return {'FINISHED'}
class SSM_OT_PixelateImage(Operator):
    bl_idname = "spritesheetmaker.pixelate_image"
    bl_label = "Pixelate Image"
    bl_description = "Pixelate given image"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get props
        curr_strip = get_current_strip()

        
        # Return if invalid test image path
        if(not os.path.exists(curr_strip.pixelate_image_path)):
            log("'Test image' is invalid!", True, "CANCEL")
            return {'FINISHED'}


        # Combine images together into single file and paste in output
        try:
            # Generate param
            param = gen_pixelate_param()
            pixelated_output_path = get_pixelated_img_path()
            pixelate_images({ curr_strip.pixelate_image_path:pixelated_output_path }, param)

            # Notify success
            log(f"Pixelated image successfully at {pixelated_output_path}", True)
        except Exception as e:
            log(f"Error occurred while pixelating image! Make sure you have passed a valid image \n {e} \n {traceback.format_exc()}", True)
     

        return {'FINISHED'}
class SSM_OT_CombineSprites(Operator):
    bl_idname = "spritesheetmaker.combine_sprites"
    bl_label = "Combine Sprites"
    bl_description = "Combine multiple sprites into a single sprite sheet"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get props
        props = bpy.context.scene.sprite_sheet_maker_props
        

        # Return if invalid temp folder
        if(props.temp_folder == "" or not os.path.exists(props.temp_folder)):
            log("'Temp Folder' is invalid!", True, "CANCEL")
            return {'FINISHED'}


        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            log("'Output Folder' is invalid!", True, "CANCEL")
            return {'FINISHED'}
        

        # Combine sprites from temp folder
        try:
            param = gen_assemble_param()
            input_folder_path = props.temp_folder
            output_path = get_sprite_sheet_path(props.combine_mode)
            assemble_images(param, input_folder_path, output_path)
            log(f"Combined sprites successfully at {os.path.normpath(output_path)}", True)
        except Exception as e:
            log(f"Error occurred while combining sprites!\nMake sure the provided 'Output Folder' follows this structure:\nMyFolder\n   - 1_Walking\n      - 1.png\n      - 2.png\n   - 2_Attacking\n      - 1.png\n      - 2.png\n\nFailed to assemble frames into single sprite sheet: {e} \n {traceback.format_exc()}", True)
     

        return {'FINISHED'}
class SSM_OT_CreateSingleSprite(Operator):
    bl_idname = "spritesheetmaker.create_single"
    bl_label = "Create Single Sprite"
    bl_description = "Render out a single sprite"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        
        # Get Scene & props
        scene = bpy.context.scene
        props = context.scene.sprite_sheet_maker_props


        # Return if no strips
        if(len(scene.animation_strips) == 0):
            log("Empty 'Animation Strips'!", True, "CANCEL")
            return {'FINISHED'}


        # Return if empty capture items
        curr_strip = get_current_strip()
        if(not SSM_OT_CreateSheet.check_strip(curr_strip, False)):
            return {'FINISHED'}
        

        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            log("'Output Folder' is invalid!", True, "CANCEL")
            return {'FINISHED'}
        

        # Create single sprite by making a sheet with only 1 strip/row with only 1 frame
        try:

            # Strip parameters            
            strip_param  = gen_strip_param(get_current_strip())
            strip_param.manual_frames = True
            strip_param.frame_start = bpy.context.scene.frame_current
            strip_param.frame_end = bpy.context.scene.frame_current


            # Sheet parameters
            sheet_param:SpriteSheetParam = gen_sprite_sheet_param()
            sheet_param.assemble_param.combine_mode = CombineMode.SHEET
            sheet_param.animation_strips = [strip_param]
            sheet_param.delete_temp_folder = True


            # Generate Spritesheet as single sprite
            output_path = get_sprite_sheet_path(props.combine_mode, True)
            SPRITE_SHEET_MAKER.create_sprite_sheet(sheet_param, output_path)
            log(f"Created single sprite successfully at {os.path.normpath(output_path)}", True)
            return {'FINISHED'}
        except Exception as e:
            error_msg = f"Error occurred while creating single sprite!\n {e} \n {traceback.format_exc()}"
            log(error_msg, True)
            return {'FINISHED'}
class SSM_OT_CreateSheet(Operator):
    bl_idname = "spritesheetmaker.create_sheet"
    bl_label = "Create Sprite Sheet"
    bl_description = "Create entire sheet"
    bl_options = {'REGISTER', 'UNDO'}


    @staticmethod
    def check_strip(strip, check_actions = True):

        # Return if empty capture items
        if(len(strip.capture_items) == 0):
            log(f"Empty 'Capture Items' in '{get_strip_label(strip)}' Strip!", True, "CANCEL")
            return False

            
        # Return if any invalid objects or actions
        valid_action_count = 0
        for capture_item in strip.capture_items:
            if (not capture_item.object):
                log(f"Invalid Object in 'Capture Items' of '{get_strip_label(strip)}' Strip!", True, "CANCEL")
                return False
            
            try:  # To ensure "ReferenceError: StructRNA of type Action has been removed" does not occur
                if(capture_item.action != None):
                    capture_item.action.name
                    valid_action_count += 1
            except ReferenceError as e:
                log(f"Invalid Action in 'Capture Items' of '{get_strip_label(strip)}' Strip!", True, "CANCEL")
                return False


        # Return if not a single valid action was providede
        if(check_actions and valid_action_count == 0):
            log(f"Not a single Action provided in 'Capture Items' of '{get_strip_label(strip)}' Strip!", True, "CANCEL")
            return False
        

        # Return if manual cameras has not been set
        if(not strip.to_auto_capture and ((strip.custom_camera is None) or (strip.custom_camera.type != 'CAMERA'))):
            log(f"Either set 'Custom Camera'\nor enable 'To Auto Capture'\nin '{get_strip_label(strip)}' Strip!", True, "CANCEL")
            return False


        return True
    def execute(self, context):

        # Get Scene & props
        scene = bpy.context.scene
        props = context.scene.sprite_sheet_maker_props


        # Return if no strips
        if(len(scene.animation_strips) == 0):
            log("Empty 'Animation Strips'!", True, "CANCEL")
            return {'FINISHED'}


        # Return in case of anything invalid in strip
        for strip in scene.animation_strips:
            if(not SSM_OT_CreateSheet.check_strip(strip)):
                return {'FINISHED'}
            

        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            log("'Output Folder' is invalid!", True, "CANCEL")
            return {'FINISHED'}


        # Create sprite sheet
        try:
            wm = bpy.context.window_manager   # Get the window manager & create a progress bar

            def begin_row_progress(strip_label, total_frame):
                wm.progress_begin(0, total_frame)  # Start progress bar
            def update_frame_progress(strip_label, frame):
                wm.progress_update(frame)  # Update progress bar
            
            SPRITE_SHEET_MAKER.on_sheet_row_creating.subscribe(begin_row_progress)
            SPRITE_SHEET_MAKER.on_sheet_frame_creating.subscribe(update_frame_progress)

            param = gen_sprite_sheet_param()
            output_path = get_sprite_sheet_path(props.combine_mode)
            SPRITE_SHEET_MAKER.create_sprite_sheet(param, output_path)
            log(f"Created successfully at {os.path.normpath(output_path)}", True)
        except Exception as e:
            error_msg = f"Error occurred while trying to create sprite sheet!\n{e}\n{traceback.format_exc()}"
            log(error_msg, True)
            return {'FINISHED'}
        finally:
            wm.progress_end() # Finish the progress bar
        

        return {'FINISHED'}


# Main Panel
class SSM_PT_MainPanel(Panel):
    bl_label = "SpriteSheetMaker"
    bl_idname = "SSM_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SpriteSheetMaker'


    def draw_strip_info(self, context, scene, row_box):

        # Label
        strip = scene.animation_strips[scene.strip_index]
        split = row_box.split(factor=0.25)
        split.label(text="Label")
        row_label = split.row(align=False)
        col_label_prop = row_label.column(align=True)
        col_label_prop.prop(strip, 'label', text='')


        # Sync Button
        col_sync_btn = row_label.column(align=True)
        curr_strip = get_current_strip()
        col_sync_btn.operator("spritesheetmaker.sync_strips", text="", icon='INTERNET', depress=curr_strip.in_sync)


        # Capture Items
        row_box.label(text="Capture Items")
        row_layout = row_box.row()
        row_layout.template_list('SSM_UL_CaptureItems', '', strip, 'capture_items', strip, 'capture_item_index', rows=3, maxrows=3)
        col = row_layout.column(align=True)
        col.operator('spritesheetmaker.play_capture_items', icon='PLAY', text='')
        col.separator()
        col.operator('spritesheetmaker.add_capture_item', icon='ADD', text='')
        col.operator('spritesheetmaker.remove_capture_item', icon='REMOVE', text='')
        
        
        # Custom Camera
        split = row_box.split(factor=0.55)
        split.label(text="Custom Camera")
        split.prop(strip, "custom_camera", text="")
        

        # To Auto Capture
        row_box.prop(strip, "to_auto_capture")
        if strip.to_auto_capture:
            # Indent sub props
            sub_box = row_box.row().split(factor=0.02)
            sub_box.label(text="")
            sub_col = sub_box.column()

            # Camera Direction
            split = sub_col.split(factor=0.60)
            split.label(text="Camera Direction")
            split.prop(strip, "camera_direction", text="")

            # Horizontal Center Object
            split = sub_col.split(factor=0.40)
            split.label(text="H Center Obj")
            col = split.column(align=True)
            col.prop(strip, "h_center_object", text="")
            if strip.h_center_object and strip.h_center_object.type == 'ARMATURE':
                col.prop_search(strip, "h_center_bone", strip.h_center_object.pose, "bones", text="Bone")

            # Vertical Center Object
            split = sub_col.split(factor=0.40)
            split.label(text="V Center Obj")
            col = split.column(align=True)
            col.prop(strip, "v_center_object", text="")
            if strip.v_center_object and strip.v_center_object.type == 'ARMATURE':
                col.prop_search(strip, "v_center_bone", strip.v_center_object.pose, "bones", text="Bone")
            
            # Consider Armature Bones
            sub_col.prop(strip, "consider_armature_bones", text="Consider Armature Bones")
            sub_col.prop(strip, "pixels_per_meter", text="Pixels Per Meter")  # Pixels Per Meter 
            sub_col.prop(strip, "camera_padding", text="Camera Padding")  # Camera Padding 

            # Create Auto Camera Button
            sub_col.separator(factor=0.25)
            row = sub_col.row()
            button_text = "Create Auto Camera" if strip.custom_camera == None else "Modify Custom Camera"
            row.operator("spritesheetmaker.create_auto_camera", text=button_text, icon="OUTLINER_OB_CAMERA")


        # To Pixelate
        row_box.prop(strip, "to_pixelate")
        if strip.to_pixelate:
            # Indent sub props
            sub_box = row_box.row().split(factor=0.02)
            sub_box.label(text="")
            sub_col = sub_box.column()
            
            sub_col.prop(strip, "pixelation_amount", text="Pixelation")  # Pixelation
            sub_col.prop(strip, "color_amount", text="Color Amount")  # Color Amount
            sub_col.prop(strip, "min_alpha", text="Min Alpha")  # Min Alpha
            sub_col.prop(strip, "alpha_step", text="Alpha Step")  # Alpha Step

            # Test Image
            row = sub_col.row()
            split = row.split(factor=0.45)
            split.label(text="Test Image")
            split.prop(strip, "pixelate_image_path", text="")

            # Pixelate Test Image Button
            row = sub_col.row()
            row.operator("spritesheetmaker.pixelate_image", text="Pixelate Test Image", icon="MOD_REMESH")


        # Manual Frames
        row_box.prop(strip, "manual_frames")
        if strip.manual_frames:  # Frame Start & End
            
            # Indent sub props
            sub_box = row_box.row().split(factor=0.02)
            sub_box.label(text="")
            sub_col = sub_box.column()
            
            row2 = sub_col.row(align=True)
            split = row2.split(factor=0.5)
            split.prop(strip, 'frame_start', text='Start')
            split.prop(strip, 'frame_end', text='End')
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = context.scene.sprite_sheet_maker_props


        # Import & Export Buttons
        row = layout.row(align=True)
        row.operator("spritesheetmaker.export_settings", icon='EXPORT', text="Export")
        row.operator("spritesheetmaker.import_settings", icon='IMPORT', text="Import")
        layout.separator(factor=0.5)
        

        # Animation Strips
        box = layout.box()
        box.label(text="Animation Strips")
        row = box.row()
        row.template_list(
            "SSM_UL_AnimationStrips",
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
        has_strip = len(scene.animation_strips) > 0 and 0 <= scene.strip_index < len(scene.animation_strips)
        box = layout.box()
        box.prop(props, "show_strip_info", icon="TRIA_DOWN" if props.show_strip_info else "TRIA_RIGHT", emboss=False, text=f"Strip Info{'' if has_strip else ' (Add Strip First)'}")
        if(props.show_strip_info):
            box.enabled = has_strip
            if has_strip:
                self.draw_strip_info(context, scene, box)
            else:
                # Dummy Stuff
                split = box.split(factor=0.25)
                split.label(text="Label")
                row_label = split.row(align=False)
                col_label_prop = row_label.column(align=True)
                col_label_prop.prop(scene, 'dummy_label', text='')
                col_sync_btn = row_label.column(align=True)
                col_sync_btn.operator("spritesheetmaker.sync_strips", text="", icon='INTERNET')
                box.label(text="Capture Items")
                row_layout = box.row()
                row_layout.template_list('SSM_UL_CaptureItems', '', scene, 'dummy_items', scene, 'dummy_index', rows=3, maxrows=3)
                col = row_layout.column(align=True)
                col.operator('spritesheetmaker.play_capture_items', icon='PLAY', text='')
                col.separator()
                col.operator('spritesheetmaker.add_capture_item', icon='ADD', text='')
                col.operator('spritesheetmaker.remove_capture_item', icon='REMOVE', text='')


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
        
            # Temp Folder
            row = box.row()
            split = row.split(factor=0.45)
            split.label(text="Temp Folder")
            split.prop(props, "temp_folder", text="")

            # Combine Sprites Button
            row = box.row()
            row.operator("spritesheetmaker.combine_sprites", text="Combine Sprites", icon="TEXTURE")


        # Output folder
        layout.separator(factor=0.5)
        row = layout.row()
        split = row.split(factor=0.45)
        split.label(text="Output Folder")
        split.prop(props, "output_folder", text="")


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
def gen_assemble_param():

    # Get all props
    props = bpy.context.scene.sprite_sheet_maker_props


    # Set assemble parameters
    param = AssembleParam()
    param.font_size = props.label_font_size
    param.surrounding_margin = (props.surrounding_margin_top, props.surrounding_margin_right, props.surrounding_margin_bottom, props.surrounding_margin_left)
    param.label_margin = props.label_margin
    param.image_margin = props.image_margin
    param.consistency = SpriteConsistency(props.sprite_consistency)
    param.align = SpriteAlign(props.sprite_align)
    param.combine_mode = CombineMode(props.combine_mode)

    return param
def gen_auto_capture_param(strip):

    param = AutoCaptureParam()
    param.objects = get_objects_to_capture(strip)
    param.camera_direction = CameraDirection(strip.camera_direction)
    param.h_center_object = strip.h_center_object
    param.h_center_bone = strip.h_center_bone
    param.v_center_object = strip.v_center_object
    param.v_center_bone = strip.v_center_bone
    param.consider_armature_bones = strip.consider_armature_bones
    param.pixels_per_meter = strip.pixels_per_meter
    param.camera_padding = strip.camera_padding

    return param
def gen_pixelate_param(strip):

    param = PixelateParam()
    param.pixelation_amount = strip.pixelation_amount
    param.color_amount = strip.color_amount
    param.min_alpha = strip.min_alpha
    param.alpha_step = strip.alpha_step


    return param
def gen_strip_param(strip):
    strip_param = StripParam()
    strip_param.capture_items = [(capture_item.object, capture_item.action, capture_item.slot) for capture_item in strip.capture_items]
    

    # Auto copy strip properties
    for prop in strip_param.__dict__:
        if hasattr(strip, prop) and prop not in ["capture_items"]:
            setattr(strip_param, prop, getattr(strip, prop))


    # Assign sub params
    strip_param.auto_capture_param = gen_auto_capture_param(strip) if strip.to_auto_capture else AutoCaptureParam()
    strip_param.pixelate_param = gen_pixelate_param(strip) if strip.to_pixelate else PixelateParam()

    return strip_param
def gen_sprite_sheet_param():

    # Get all props & scene
    props = bpy.context.scene.sprite_sheet_maker_props
    scene = bpy.context.scene
    param = SpriteSheetParam()


    # Auto copy top level matching properties
    for prop in param.__dict__:
        if hasattr(props, prop):
            setattr(param, prop, getattr(props, prop))


    # Assign strips
    param.animation_strips = []
    for strip in scene.animation_strips:
        strip_param = gen_strip_param(strip)
        param.animation_strips.append(strip_param)


    # Assign Assemble param
    param.assemble_param = gen_assemble_param()


    return param


# Helper Methods
def get_current_strip():
    scene = bpy.context.scene
    strips = scene.animation_strips
    if(len(strips) == 0):
        return None

    idx = scene.strip_index
    return strips[idx]
def get_strip_label(strip):
    return strip.label if strip.label!='' else UNTITLED_STRIP_NAME
def get_label_text():

    # Get the label text of the first strip 
    scene = bpy.context.scene
    for strip in scene.animation_strips:
        if(strip.label == ""):
            continue
    
        return strip.label
    
    return UNTITLED_LABEL_TEXT
def get_pixelated_img_path():

    # Get all props
    curr_strip = get_current_strip()
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()


    # Add postfix to the file name
    dir_name, file_name = os.path.split(curr_strip.pixelate_image_path)
    name, ext = os.path.splitext(file_name)
    pixelated_output_path = os.path.join(dir_name, f"{name}_{PIXELATE_TEST_IMAGE_POSTFIX}.{file_ext}")
    

    return unique_path(pixelated_output_path)
def get_sprite_sheet_path(mode, single_sprite = False):
    props = bpy.context.scene.sprite_sheet_maker_props
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()

    # Assign file/folder name
    if(single_sprite):
        base_name = SINGLE_SPRITE_NAME
    else:
        base_name = SPRITE_SHEET_NAME if mode == CombineMode.SHEET.value else DEFAULT_OUTPUT_FOLDER_NAME


    # Get full path
    sprite_sheet_path = unique_path(f"{props.output_folder}/{base_name}.{file_ext}")


    return sprite_sheet_path
def get_objects_to_capture(strip):

    # Get objects in strip
    objects = set()
    for item in strip.capture_items:
        if(item.object is None):
            continue
        
        objects.add(item.object)


    return objects
def get_synced_strip():
    scene = bpy.context.scene
    strips = scene.animation_strips

    for strip in strips:
        if(strip.in_sync):
            return strip

    return None
def are_any_in_sync():
    scene = bpy.context.scene
    strips = scene.animation_strips

    for strip in strips:
        if(strip.in_sync):
            return True

    return False
def log(message, show_popup = False, icon="INFO"):

    print(f"[SpriteSheetMaker {datetime.now()}] {message}")

    if(show_popup):
        bpy.ops.spritesheetmaker.message_popup('INVOKE_DEFAULT', **{ "message_heading": message,  "message_icon" : icon })


# Initialize Classes
classes = (
    SSM_MessagePopup,
    SSM_Properties,
    SSM_CaptureItem,
    SSM_StripInfo,
    SSM_OT_key_listener,
    SSM_OT_import_settings,
    SSM_OT_export_settings,
    SSM_UL_AnimationStrips,
    SSM_UL_CaptureItems,
    SSM_OT_duplicate_strip,
    SSM_OT_add_strip,
    SSM_OT_remove_strip,
    SSM_OT_move_strip,
    SSM_OT_play_capture_items,
    SSM_OT_add_capture_item,
    SSM_OT_remove_capture_item,
    SSM_OT_sync_strips,
    SSM_OT_CreateAutoCamera,
    SSM_OT_PixelateImage,
    SSM_OT_CombineSprites,
    SSM_OT_CreateSingleSprite,
    SSM_OT_CreateSheet,
    SSM_PT_MainPanel,
)


# Initialize Methods
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    
    Scene.sprite_sheet_maker_props = PointerProperty(type=SSM_Properties)
    Scene.animation_strips = CollectionProperty(type=SSM_StripInfo)
    Scene.strip_index = IntProperty(default=0)
    Scene.dummy_label = StringProperty(name='Dummy Label', default='')
    Scene.dummy_items = CollectionProperty(type=SSM_CaptureItem)
    Scene.dummy_index = IntProperty(default=0)
    Scene.dummy_manual_frames = BoolProperty(name="Manual Frame Selection", default=False)
    Scene.dummy_start = IntProperty(name='Dummy Start', default=0, min=-1048574, max=1048574)
    Scene.dummy_end = IntProperty(name='Dummy End', default=250, min=-1048574, max=1048574)


    # Start listening for "Alt" key
    def run_auto_listener():
        if hasattr(bpy.ops, "spritesheetmaker"):
            bpy.ops.spritesheetmaker.key_listener('INVOKE_DEFAULT')
        else:
            log("Failed to listen for Alt Key!")
        return None
    bpy.app.timers.register(run_auto_listener, first_interval=0.5) 
def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

    del Scene.sprite_sheet_maker_props

    del Scene.animation_strips
    del Scene.strip_index
    del Scene.dummy_label
    del Scene.dummy_items
    del Scene.dummy_index
    del Scene.dummy_manual_frames
    del Scene.dummy_start
    del Scene.dummy_end


if __name__ == "__main__":
    register()
