bl_info = {
    "name": "Sprite Sheet Maker",
    "author": "Manas R. Makde",
    "version": (5, 1, 3),
    "description": "3D to 2D sprite sheet converter with optional pixelation"
}


import bpy
import os
import json
from bpy.types import Panel, Operator, PropertyGroup, Object, Action, UIList, Scene
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, FloatProperty,BoolProperty, PointerProperty, CollectionProperty, IntProperty, EnumProperty, FloatVectorProperty
from .modules.sprite_sheet_utils import *
from .modules.combine_frames import *
from .modules.logging import *


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
NON_SERIALIZABLE_PROPERTIES = {"custom_camera", "h_center_object", "v_center_object"} 


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

    object: PointerProperty(name="Object", type=Object, description="Target object to be rendered within strip")
    action: PointerProperty(name="Action", type=Action, description="Animation to be captured in the strip", update=action_update)
    slot: StringProperty(name="Slot", default="", description="(Optional)")
class SSM_StripInfo(PropertyGroup):

    def update_label_from_action(self):
        
        # Return if label already assigned
        if(self.label != ""):
            return

        
        # Get first non empty action name 
        for item in self.capture_items:
            if not item.action or item.action.name == "":
                continue
            
            self.label = item.action.name
            return
    def sync_update(self, context, prop_name):

        strip = get_current_strip()
        if not strip.in_sync:
            return
    
        SSM_OT_SyncStrips.sync(context, {prop_name})

    in_sync: BoolProperty(name="Sync Strip", default=False)
    label: StringProperty(name="Label", default="", description="The text that will be added on top of the strip in the sprite sheet")
    capture_items: CollectionProperty(type=SSM_CaptureItem)
    capture_item_index: IntProperty(default=0, description="Pointer tracking active item inside collection")
    
    
    # Camera settings
    custom_camera: PointerProperty(name="Custom Camera", type=Object, poll=lambda self, obj: obj.type == 'CAMERA', description="Custom camera object to use for rendering this strip", update=lambda self, ctx: self.sync_update(ctx, "custom_camera"))
    to_auto_capture: BoolProperty(name="To Auto Capture", default=True, description="Automatically calculate and position camera bounding box", update=lambda self, ctx: self.sync_update(ctx, "to_auto_capture"))
    camera_direction: EnumProperty(
        name="Camera Direction",
        description="Direction from which the camera will look toward the targeted objects",
        items = [
            (CameraDirection.X.value, "X", "Camera pointing along the X axis"),
            (CameraDirection.Y.value, "Y", "Camera pointing along the Y axis"),
            (CameraDirection.Z.value, "Z", "Camera pointing along the Z axis"),
            (CameraDirection.NEG_X.value, "-X", "Camera pointing along the negative X axis"),
            (CameraDirection.NEG_Y.value, "-Y", "Camera pointing along the negative Y axis"),
            (CameraDirection.NEG_Z.value, "-Z", "Camera pointing along the negative Z axis"),
            (CameraDirection.CUSTOM.value, "Custom", "Custom camera orientation")
        ],
        default=CameraDirection.NEG_X.value,
        update=lambda self, ctx: self.sync_update(ctx, "camera_direction")
    )
    camera_orbit_z: FloatProperty(name="Orbit-Z", default=0.0, subtype='ANGLE', description="Orbit rotation around Z axis of capture objects")
    camera_orbit_x: FloatProperty(name="Orbit-X", default=0.0, subtype='ANGLE', description="Orbit rotation around X axis of capture objects")
    camera_roll: FloatProperty(name="Roll", default=0.0, subtype='ANGLE', description="Roll rotation around cameras on pointing axis")

    h_center_object: PointerProperty(name="Horizontal Center Object", type=Object, description="Object whose origin will be used as the horizontal center for each sprite frame", update=lambda self, ctx: self.sync_update(ctx, "h_center_object"))
    h_center_bone: StringProperty(name="Horizontal Center Bone", default="", description="Bone whose origin will be used as the horizontal center for each sprite frame", update=lambda self, ctx: self.sync_update(ctx, "h_center_bone"))
    v_center_object: PointerProperty(name="Vertical Center Object", type=Object, description="Object whose origin will be used as the vertically center for each sprite frame", update=lambda self, ctx: self.sync_update(ctx, "v_center_object"))
    v_center_bone: StringProperty(name="Vertical Center Bone", default="", description="Bone whose origin will be used as the vertically center for each sprite frame", update=lambda self, ctx: self.sync_update(ctx, "v_center_bone"))
    
    consider_armature_bones: BoolProperty(default=False, description="Include all armature bones when calculating auto-capture camera bounds to ensure they remain within camera view", update=lambda self, ctx: self.sync_update(ctx, "consider_armature_bones"))
    pixels_per_meter: FloatProperty(name="Pixels Per Meter", default=100.0, min=1.0, soft_max=5000.0, description="Number of pixels rendered per one world space meter unit", update=lambda self, ctx: self.sync_update(ctx, "pixels_per_meter"))
    camera_padding_h: FloatProperty(name="Camera Padding", unit='LENGTH', default=0.0, min=0.0, soft_max=10.0, description="Extra margin around camera view", update=lambda self, ctx: self.sync_update(ctx, "camera_padding_h"))
    camera_padding_v: FloatProperty(name="Camera Padding", unit='LENGTH', default=0.0, min=0.0, soft_max=10.0, description="Extra margin around camera view", update=lambda self, ctx: self.sync_update(ctx, "camera_padding_v"))


    # Pixelation settings
    to_pixelate: BoolProperty(name="To Pixelate", default=False, description="If enabled the strip is pixelated", update=lambda self, ctx: self.sync_update(ctx, "to_pixelate"))
    pixelation_amount: FloatProperty(name="Pixelation Amount", default=0.9, precision=5, step=0.001, min=0.0, max=1.0, description="By how much amount to pixelate the strip", update=lambda self, ctx: self.sync_update(ctx, "pixelation_amount"))
    color_amount: FloatProperty(name="Pixelation Color Amount", default=50.0, min=0.0, soft_max=1000, description="How much amount of color to keep within the strip", update=lambda self, ctx: self.sync_update(ctx, "color_amount"))
    min_alpha: FloatProperty(name="Min Alpha", default=0.0, min=0.0, max=1.1, description="If any pixel in the strip has a transparency less than this amount then it is discarded\nSet as 1.0 if to remove all semi-transparent pixel", update=lambda self, ctx: self.sync_update(ctx, "min_alpha"))
    alpha_step: FloatProperty(name="Alpha Step", default=0.0, min=0.0, max=1.1, description="Ensures that all pixels have a transparency which is a multiple of this amount", update=lambda self, ctx: self.sync_update(ctx, "alpha_step"))
    pixelate_image_path: StringProperty(
        name="Pixelate Image Path",
        subtype="FILE_PATH",
        description="Target image to pixelate",
        update=lambda self, ctx: self.sync_update(ctx, "pixelate_image_path")
    )
    
    
    # Flip settings
    to_flip_h: BoolProperty(name="To Flip H", default=False, description="If enabled the rendered image is flipped horizontally before saving into temp folder", update=lambda self, ctx: self.sync_update(ctx, "to_flip_h"))
    to_flip_v: BoolProperty(name="To Flip V", default=False, description="If enabled the rendered image is flipped vertically before saving into temp folder", update=lambda self, ctx: self.sync_update(ctx, "to_flip_v"))
    
    
    # Manual frame settings
    manual_frames: BoolProperty(name="Manual Frame Selection", default=False, description="If enabled, The Start & End frames (inclusive) can be manually assigned for the strip\nIf disabled, the start & end frame of longest action will be taken")
    frame_start: IntProperty(name="Start", default=0, min=-1048574, max=1048574)
    frame_end: IntProperty(name="End", default=250, min=-1048574, max=1048574)
class SSM_Properties(PropertyGroup):

    def update_temp_folder(self, context):
        if self.temp_folder.startswith("//"):
            self.temp_folder = bpy.path.abspath(self.temp_folder)
    def update_output_folder(self, context):
        if self.output_folder.startswith("//"):
            self.output_folder = bpy.path.abspath(self.output_folder)
    

    # Output settings
    label_font_size: IntProperty(name="Label Font Size", default=24, min=0, soft_max=1000, description="Font size of label text")
    label_color: FloatVectorProperty(name="Label Color", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, description="Color of the label text on top of each strip")
    background_color: FloatVectorProperty(name="Background Color", subtype='COLOR', size=4, default=(0.0, 0.0, 0.0, 0.0), min=0.0, max=1.0, description="Background color for entire sheet (or strips, or images based on combine mode)")
    surrounding_margin_top: IntProperty(name="Surrounding Margin Top", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the top of the sprite sheet")
    surrounding_margin_right: IntProperty(name="Surrounding Margin Right", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the right of the sprite sheet")
    surrounding_margin_bottom: IntProperty(name="Surrounding Margin Bottom", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the bottom of the sprite sheet")
    surrounding_margin_left: IntProperty(name="Surrounding Margin Left", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the left of the sprite sheet")
    label_margin: IntProperty(name="Label Margin", default=15, min=0, soft_max=1000, description="Vertical margin gap (in pixels) between the label and the images")
    image_margin: IntProperty(name="Image Margin", default=15, min=0, soft_max=1000, description="Horizonal margin gap (in pixels) between images within a row/strip")
    sprite_consistency: EnumProperty(
        name="Sprite Align",
        description="Dictates the dimension of sprites throughout the sprite sheet",
        items=[
            (SpriteConsistency.INDIVIDUAL.value, "Individual Consistent", "Each sprite fits it's own content"),
            (SpriteConsistency.ROW.value, "Row Consistent", "All sprites in a row have the same dimensions"),
            (SpriteConsistency.ALL.value, "All Consistent", "All sprites throughout the sheet have the same dimensions")
        ],
        default=SpriteConsistency.INDIVIDUAL.value
    )
    sprite_align: EnumProperty(
        name="Sprite Align",
        description="Dictates how the content should be aligned within the sprite",
        items=[
            (SpriteAlign.TOP_LEFT.value, "Top Left", "Align content to vertical top & horizontal left"),
            (SpriteAlign.TOP_CENTER.value, "Top Center", "Align content to vertical top & horizontal center"),
            (SpriteAlign.TOP_RIGHT.value, "Top Right", "Align content to vertical top & horizontal right"),
            (SpriteAlign.MIDDLE_LEFT.value, "Middle Left", "Align content to vertical middle & horizontal left"),
            (SpriteAlign.MIDDLE_CENTER.value, "Middle Center", "Align content to vertical middle & horizontal center"),
            (SpriteAlign.MIDDLE_RIGHT.value, "Middle Right", "Align content to vertical middle & horizontal right"),
            (SpriteAlign.BOTTOM_LEFT.value, "Bottom Left", "Align content to vertical bottom & horizontal left"),
            (SpriteAlign.BOTTOM_CENTER.value, "Bottom Center", "Align content to vertical bottom & horizontal center"),
            (SpriteAlign.BOTTOM_RIGHT.value, "Bottom Right", "Align content to vertical bottom & horizontal right"),
        ],
        default=SpriteAlign.BOTTOM_CENTER.value
    )
    combine_mode: EnumProperty(
        name="Combine Mode",
        description="Dictates how all the rendered frames will be stitched together",
        items=[
            (CombineMode.IMAGES.value, "Images", "Render out individual images"),
            (CombineMode.STRIPS.value, "Strips", "Render out separate strips for each action"),
            (CombineMode.SHEET.value, "Sheet", "Render out a single sprite sheet"),
        ],
        default=CombineMode.SHEET.value
    )
    delete_temp_folder: BoolProperty(name="Delete Temp Folder", default=True, description="Whether to delete the cache folder after sprite sheet is made\nHowever the folder will not be deleted incase of any error even if this is enabled")
    temp_folder: StringProperty(
        name="Temp Folder",
        subtype="DIR_PATH",
        description="Folder to use as input for 'Combine Sprites'",
        update=update_temp_folder
    )
    output_folder: StringProperty(
        name="Output Folder",
        subtype="DIR_PATH",
        description="Folder in which the generated sprite sheet is saved into",
        update=update_output_folder
    )

    # Collapsible section toggles
    show_strip_info: BoolProperty(name="Show Strip Info", default=False)
    show_output_settings: BoolProperty(name="Show Output Settings", default=False)
class SSM_UL_AnimationStrips(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.label(text=item.label if item.label != "" else UNTITLED_STRIP_NAME, icon='SEQ_STRIP_DUPLICATE')
class SSM_UL_CaptureItems(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):

        split = layout.split(factor=1/3, align=True)
        col_obj = split.column(align=True)
        col_action = split.column(align=True)
        col_slot = split.column(align=True)

        col_obj.prop(item, "object", text="")
        col_action.prop(item, "action", text="")
        col_slot.prop(item, "slot", text="Slot")
class SSM_OT_KeyListener(Operator):
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
            SSM_OT_KeyListener.is_alt_pressed = True
        elif event.value == 'RELEASE' and self.is_alt_pressed:
            SSM_OT_KeyListener.is_alt_pressed = False

        return {'PASS_THROUGH'}
    def invoke(self, context, event):

        # Return if requirements are not met
        if not context.window_manager:
            log("Window manager not found for key listener!")
            return {'CANCELLED'}


        log("Starting key listener...")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


# Side Bar Buttons
class SSM_OT_DuplicateStrip(Operator):
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
class SSM_OT_AddStrip(Operator):
    bl_idname = "spritesheetmaker.add_strip"
    bl_label = "Add Strip"
    bl_description = "Add new animation strip"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        scene.animation_strips.add()
        # new.frame_start = 1
        # new.frame_end = 250
        SSM_OT_SyncStrips.sync(context)
        scene.strip_index = len(scene.animation_strips) - 1
        return {'FINISHED'}
class SSM_OT_RemoveStrip(Operator):
    bl_idname = "spritesheetmaker.remove_strip"
    bl_label = "Remove Strip"
    bl_description = "Remove selected animation strip"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        idx = scene.strip_index
        if 0 <= idx < len(scene.animation_strips):
            scene.animation_strips.remove(idx)
            scene.strip_index = max(0, min(len(scene.animation_strips) - 1, idx - 1))
        return {'FINISHED'}
class SSM_OT_MoveStrip(Operator):
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
class SSM_OT_SyncStrips(Operator):
    bl_idname = "spritesheetmaker.sync_strips"
    bl_label = "Sync Strips"
    bl_description = "All strips which have this enabled will have their properties in sync with each other\nAlt + Click to assign properties of current strip to all other strips which are in sync"
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
        
        # Get synced strip
        scene = context.scene
        strips = scene.animation_strips
        curr_idx = scene.strip_index
        if(strips[curr_idx].in_sync):
            synced_strip = strips[curr_idx]
        else:
            _, synced_strip = get_synced_strip()


        # Return if no synced strip
        if(synced_strip == None):
            return


        # Sync properties to all other strips
        for i, dest_strip in enumerate(strips):
            if i == curr_idx or not dest_strip.in_sync:
                continue
            
            SSM_OT_SyncStrips._copy_properties(synced_strip, dest_strip, properties)
            

    @staticmethod
    def sync(context, properties=None):

        # To avoid infinite recursion
        if SSM_OT_SyncStrips._is_syncing:
            return
        

        # Mark as sync started
        SSM_OT_SyncStrips._is_syncing = True


        # Sync
        try:
            SSM_OT_SyncStrips._sync_impl(context, properties)
            log(f"Synced {properties if properties != None else 'All'} across all strips!")

        except Exception as e:
            log(f"Failed to sync properties '{properties}' across all strips! Error: {e} \n {traceback.format_exc()}")

    
        # Mark as sync complete
        SSM_OT_SyncStrips._is_syncing = False


    def execute(self, context):

        # Toggle in sync button
        curr_strip = get_current_strip()
        if(not curr_strip):
            return {'FINISHED'}


        curr_strip.in_sync = not curr_strip.in_sync
        

        # Return if toggled off or nothing to sync
        if(not curr_strip.in_sync or not are_any_in_sync()):
            return {'FINISHED'}
        

        # If alt pressed; synchronize all other strips with this strip
        if(SSM_OT_KeyListener.is_alt_pressed):
            SSM_OT_SyncStrips.sync(context)
            return {'FINISHED'}


        # Sync properties of this strip with others
        _, synced_strip = get_synced_strip()
        SSM_OT_SyncStrips._copy_properties(synced_strip, curr_strip)


        return {'FINISHED'}
class SSM_OT_PlayCaptureItems(Operator):
    bl_idname = "spritesheetmaker.play_capture_items"
    bl_label = "Play Capture Items"
    bl_description = "Preview all animations associated with this strip"
    bl_options = {'UNDO'}

    def execute(self, context):

        # Return if no valid strip selected
        scene = context.scene
        si = scene.strip_index
        if si < 0 or si >= len(scene.animation_strips):
            log("No valid strip selected to play capture items!")
            return {'CANCELLED'}

        
        # Return if no capture items
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

            # Assign user provided slot else default slot
            slot_name = f"OB{item.slot}"
            if item.slot != "" and slot_name in item.action.slots:
                item.object.animation_data.action_slot = item.action.slots[slot_name]
            elif hasattr(item.object.animation_data, "action_suitable_slots") and len(item.object.animation_data.action_suitable_slots) > 0:
                item.object.animation_data.action_slot = item.object.animation_data.action_suitable_slots[0]

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
class SSM_OT_AddCaptureItem(Operator):
    bl_idname = "spritesheetmaker.add_capture_item"
    bl_label = "Add New Capture Item"
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
class SSM_OT_RemoveCaptureItem(Operator):
    bl_idname = "spritesheetmaker.remove_capture_item"
    bl_label = "Remove Selected Capture Item"
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
class SSM_OT_ExportSettings(Operator, ExportHelper):
    bl_idname = "spritesheetmaker.export_settings"
    bl_label = "Export"
    bl_description = "Save current settings as .json file to import later"
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
                if not p.is_readonly and p.identifier not in {"capture_items", "name"} and p.identifier not in NON_SERIALIZABLE_PROPERTIES:
                    s_data[p.identifier] = getattr(strip, p.identifier)
            

            # Store object pointer properties as names since objects are not json serializable
            for prop_name in NON_SERIALIZABLE_PROPERTIES:
                obj = getattr(strip, prop_name)
                s_data[prop_name] = obj.name if obj else ""
            
            
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
                prop_value = getattr(props, p.identifier)
                export_data["props"][p.identifier] = list(prop_value) if getattr(p, "is_array", False) else prop_value

                
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
class SSM_OT_ImportSettings(Operator, ImportHelper):
    bl_idname = "spritesheetmaker.import_settings"
    bl_label = "Import"
    bl_description = "Import saved settings from .json file"
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

            # Load all basic properties e.g. label, etc
            for key, val in strip_data.items():
                if key != "capture_items" and key not in NON_SERIALIZABLE_PROPERTIES and hasattr(strip, key):
                    setattr(strip, key, val)

            # Load object pointer properties by resolving stored name back to object
            for prop_name in NON_SERIALIZABLE_PROPERTIES:
                obj_name = strip_data.get(prop_name, "")
                setattr(strip, prop_name, bpy.data.objects[obj_name] if obj_name in bpy.data.objects else None)
            
            # Load all capture items
            for item_data in strip_data.get("capture_items", []):
                item = strip.capture_items.add()

                # Add object to capture item
                if(item_data.get("object") in bpy.data.objects):
                    item.object = bpy.data.objects[item_data["object"]]
                else:
                    missing_obj = item_data.get('object')
                    log(f"Missing object '{missing_obj}' found while importing!")
                    item.object = None


                # Add action to capture item
                if(item_data.get("action") in bpy.data.actions):
                    item.action = bpy.data.actions[item_data["action"]]
                else:
                    missing_action = item_data.get('action')
                    log(f"Missing action '{missing_action}' found while importing!")
                    item.action = None

                
                # Add slot to capture item
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
class SSM_OT_CreateAutoCamera(Operator):
    bl_idname = "spritesheetmaker.create_auto_camera"
    bl_label = "Create Auto Camera"
    bl_description = "Create camera from given auto capture parameters"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get assigned custom camera
        curr_strip = get_current_strip()
        cam_obj = curr_strip.custom_camera


        # Return if any invalid property in strip
        curr_strip = get_current_strip()
        if(not SSM_OT_CreateSheet.check_strip(curr_strip)):
            return {'FINISHED'}
        

        # Set it up based on auto parameters
        param = gen_auto_capture_param(curr_strip)
        setup_auto_camera(cam_obj, param)


        return {'FINISHED'}
class SSM_OT_PixelateImage(Operator):
    bl_idname = "spritesheetmaker.pixelate_image"
    bl_label = "Pixelate Image"
    bl_description = "Pixelate given test image based on the pixelation properties assigned"
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
            param = gen_pixelate_param(curr_strip)
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
    bl_description = "Combine all sprites from Temp Folder into a single sprite sheet"
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
    bl_description = "Render out a single sprite of currently selected strip\nUseful for verifying settings before rendering the full sheet"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        
        # Get Scene & props
        scene = bpy.context.scene
        props = context.scene.sprite_sheet_maker_props


        # Return if no strips
        if(len(scene.animation_strips) == 0):
            log("Empty 'Animation Strips'!", True, "CANCEL")
            return {'FINISHED'}


        # Return if any invalid property in strip
        curr_strip = get_current_strip()
        if(not SSM_OT_CreateSheet.check_strip(curr_strip)):
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
    bl_description = "Render out the entire sprite sheet"
    bl_options = {'REGISTER', 'UNDO'}


    @staticmethod
    def check_strip(strip, check_actions = True):

        # Return if empty capture items
        objects = get_objects_to_capture(strip)
        if(strip.to_auto_capture and len(objects) == 0):
            log(f"Empty or Invalid 'Capture Items' in '{get_strip_label(strip)}' Strip!", True, "CANCEL")
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


        # Return if neither auto capture nor custom camera has been set
        if(not strip.to_auto_capture and (strip.custom_camera is None)):
            log(f"Either set a valid 'Custom Camera' or enable 'To Auto Capture'\nin '{get_strip_label(strip)}' Strip!", True, "CANCEL")
            return False
        

        # Return if invalid custom camera
        if(not strip.to_auto_capture and not is_valid(strip.custom_camera, False)):
            log(f"Invalid 'Custom Camera' in '{get_strip_label(strip)}' Strip!", True, "CANCEL")
            return False


        # Return if invalid center obj H
        if(strip.to_auto_capture and (strip.h_center_object is not None) and (not is_valid(strip.h_center_object))):
            log(f"Invalid 'Center Obj H' in '{get_strip_label(strip)}' Strip!", True, "CANCEL")  # Return if invalid Center Obj H
            return False


        # Return if invalid center obj V
        if(strip.to_auto_capture and (strip.v_center_object is not None) and (not is_valid(strip.v_center_object))):
            log(f"Invalid 'Center Obj V' in '{get_strip_label(strip)}' Strip!", True, "CANCEL")
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

            # Custom Direction
            if strip.camera_direction == CameraDirection.CUSTOM.value:
                sub_col.prop(strip, "camera_orbit_z")
                sub_col.prop(strip, "camera_orbit_x")
                sub_col.prop(strip, "camera_roll")

            # Horizontal Center Object
            split = sub_col.split(factor=0.40)
            split.label(text="Center Obj H")
            col = split.column(align=True)
            col.prop(strip, "h_center_object", text="")
            if strip.h_center_object and strip.h_center_object.type == 'ARMATURE':
                col.prop_search(strip, "h_center_bone", strip.h_center_object.pose, "bones", text="Bone")

            # Vertical Center Object
            split = sub_col.split(factor=0.40)
            split.label(text="Center Obj V")
            col = split.column(align=True)
            col.prop(strip, "v_center_object", text="")
            if strip.v_center_object and strip.v_center_object.type == 'ARMATURE':
                col.prop_search(strip, "v_center_bone", strip.v_center_object.pose, "bones", text="Bone")

            # Consider Armature Bones
            sub_col.prop(strip, "consider_armature_bones", text="Consider Armature Bones")
            sub_col.prop(strip, "camera_padding_h", text="Camera Padding H")  # Camera Padding Horizontal
            sub_col.prop(strip, "camera_padding_v", text="Camera Padding V")  # Camera Padding Vertical
            sub_col.prop(strip, "pixels_per_meter", text="Pixels Per Meter")  # Pixels Per Meter 

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


        # To Flip H & V
        row_box.prop(strip, "to_flip_h")
        row_box.prop(strip, "to_flip_v")
        

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
        box.prop(props, "show_strip_info", icon="TRIA_DOWN" if props.show_strip_info else "TRIA_RIGHT", emboss=False, text=f"Strip Info{'' if has_strip else ' (Add atleast one strip)'}")
        if(props.show_strip_info):
            box.enabled = has_strip
            if has_strip:
                self.draw_strip_info(context, scene, box)


        # Output Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_output_settings", icon="TRIA_DOWN" if props.show_output_settings else "TRIA_RIGHT", emboss=False, text="Output Settings")
        if props.show_output_settings:

            # Label Font Size
            box.prop(props, "label_font_size", text="Label Font Size")

            # Label Color
            row = box.row()
            split = row.split(factor=0.45)
            split.label(text="Label Color")
            split.prop(props, "label_color", text="")

            # Background Color
            row = box.row()
            split = row.split(factor=0.45)
            split.label(text="Background Color")
            split.prop(props, "background_color", text="")

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
    for prop in param.__dict__:
        if hasattr(props, prop) and prop not in ["surrounding_margin", "consistency", "align", "combine_mode", "label_color", "background_color"]:
            setattr(param, prop, getattr(props, prop))
    

    # Manual overrides for Enums and Tuples
    param.surrounding_margin = (props.surrounding_margin_top, props.surrounding_margin_right, props.surrounding_margin_bottom, props.surrounding_margin_left)
    param.consistency = SpriteConsistency(props.sprite_consistency)
    param.align = SpriteAlign(props.sprite_align)
    param.combine_mode = CombineMode(props.combine_mode)
    param.font_size = props.label_font_size
    param.label_color = tuple(props.label_color)
    param.background_color = tuple(props.background_color)


    return param
def gen_auto_capture_param(strip):

    param = AutoCaptureParam()
    param.objects = get_objects_to_capture(strip)
    

    # Auto copy matching properties
    for prop in param.__dict__:
        if hasattr(strip, prop) and prop not in ["objects", "camera_direction"]:
            setattr(param, prop, getattr(strip, prop))
            

    # Manual override for Enum
    param.camera_direction = CameraDirection(strip.camera_direction)


    return param
def gen_pixelate_param(strip):

    param = PixelateParam()
    

    # Auto copy all matching properties
    for prop in param.__dict__:
        if hasattr(strip, prop):
            setattr(param, prop, getattr(strip, prop))


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
def is_valid(obj, check_for_none = True):

    # Check if the variable is None
    if check_for_none and obj is None:
        return False
        
    # Check if the object was structurally deleted (dead pointer)
    try:
        obj_name = obj.name
    except ReferenceError:
        return False
        
    # Check if it is actively linked to the current scene's view layer
    return obj_name in bpy.context.view_layer.objects
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
        base_name = f"{SINGLE_SPRITE_NAME}.{file_ext}"
    else:
        base_name = f"{SPRITE_SHEET_NAME}.{file_ext}" if mode == CombineMode.SHEET.value else DEFAULT_OUTPUT_FOLDER_NAME


    # Get full path
    sprite_sheet_path = unique_path(f"{props.output_folder}/{base_name}")


    return sprite_sheet_path
def get_objects_to_capture(strip):

    # Get objects in strip
    objects = set()
    for item in strip.capture_items:

        # Skip if invalid object or if not to consider armature
        if(not is_valid(item.object) or (item.object.type == 'ARMATURE' and not strip.consider_armature_bones)):
            continue
        
        objects.add(item.object)


    return objects
def get_synced_strip():
    scene = bpy.context.scene
    strips = scene.animation_strips

    for i, strip in enumerate(strips):
        if(strip.in_sync):
            return i, strip

    return -1, None
def are_any_in_sync():
    scene = bpy.context.scene
    strips = scene.animation_strips

    for strip in strips:
        if(strip.in_sync):
            return True

    return False


# Initialize Classes
classes = (
    SSM_MessagePopup,
    SSM_Properties,
    SSM_CaptureItem,
    SSM_StripInfo,
    SSM_OT_KeyListener,
    SSM_OT_ImportSettings,
    SSM_OT_ExportSettings,
    SSM_UL_AnimationStrips,
    SSM_UL_CaptureItems,
    SSM_OT_DuplicateStrip,
    SSM_OT_AddStrip,
    SSM_OT_RemoveStrip,
    SSM_OT_MoveStrip,
    SSM_OT_PlayCaptureItems,
    SSM_OT_AddCaptureItem,
    SSM_OT_RemoveCaptureItem,
    SSM_OT_SyncStrips,
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


if __name__ == "__main__":
    register()
