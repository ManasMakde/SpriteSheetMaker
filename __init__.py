bl_info = {
    "name": "Sprite Sheet Maker",
    "author": "Manas R. Makde",
    "version": (5, 2, 2),
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
UNTITLED_ROW_NAME = "<Untitled>"
UNTITLED_LABEL_TEXT = "Untitled"
EXCLUDE_EXPORT_PROPERTIES = {"rna_type", "name", "capture_items", "label", "pixelate_image_path", "enabled"}
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

        # Get row in which action was updated
        self_row = None
        for row in context.scene.animation_rows:
            for it in row.capture_items:
                if it == self:
                    self_row = row
                    break
        

        # Return if row not found
        if(self_row is None):
            return
        
        
        # Updated label of the row
        self_row.update_label_from_action(self.previous_action_name)


        # Store action name of row
        self.previous_action_name = self.action.name if self.action else ""
        

    object: PointerProperty(name="Object", type=Object, description="Target object to be rendered within row")
    action: PointerProperty(name="Action", type=Action, description="Animation to be captured in the row", update=action_update)
    slot: StringProperty(name="Slot", default="", description="(Optional)")
    previous_action_name: StringProperty(default="", description="Tracks last assigned action name to detect when it gets removed")
class SSM_RowInfo(PropertyGroup):

    _is_propagating = False  # used to avoid recursion while propagating property to all rows

    def update_label_from_action(self, removed_action_name=""):

        # Clear label if it matches the action that was just removed
        if(self.label != "" and self.label == removed_action_name):
            self.label = ""


        # Return if label already assigned
        if(self.label != ""):
            return

        
        # Get first non empty action name 
        for item in self.capture_items:
            if not item.action or item.action.name == "":
                continue
            
            self.label = item.action.name
            break
    def alt_sync_update(self, context, prop_name):

        # Return if alt key not held
        if not SSM_OT_KeyListener.is_alt_pressed:
            return

        # Return if already propagating to avoid recursion
        if SSM_RowInfo._is_propagating:
            return


        # Mark as propagating
        SSM_RowInfo._is_propagating = True

        # Copy this property to all other rows
        try:
            new_value = getattr(self, prop_name)
            for row in context.scene.animation_rows:
                if row == self or not hasattr(row, prop_name):
                    continue

                setattr(row, prop_name, new_value)

            log(f"Propagated '{prop_name}' across all rows!")
        except Exception as e:
            log(f"Failed to propagate '{prop_name}' across all rows Error {e} \n {traceback.format_exc()}")

        # Mark propagating as complete
        SSM_RowInfo._is_propagating = False


    enabled: BoolProperty(name="Enabled", default=True, description="If disabled this row will not be included while creating the sprite sheet\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "enabled"))
    label: StringProperty(name="Label", default="", description="The text that will be added on top of the row in the sprite sheet")
    capture_items: CollectionProperty(type=SSM_CaptureItem)
    capture_item_index: IntProperty(default=0, description="Pointer tracking active item inside collection")
    
    
    # Camera settings
    custom_camera: PointerProperty(name="Custom Camera", type=Object, poll=lambda self, obj: obj.type == 'CAMERA', description="Custom camera object to use for rendering this row\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "custom_camera"))
    to_auto_capture: BoolProperty(name="To Auto Capture", default=True, description="Automatically calculate and position camera bounding box\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "to_auto_capture"))
    camera_direction: EnumProperty(
        name="Camera Direction",
        description="Direction from which the camera will look toward the targeted objects\nHold Alt & change to sync across all rows",
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
        update=lambda self, ctx: self.alt_sync_update(ctx, "camera_direction")
    )
    camera_orbit_z: FloatProperty(name="Orbit-Z", default=0.0, subtype='ANGLE', description="Orbit rotation around Z axis of capture objects\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "camera_orbit_z"))
    camera_orbit_x: FloatProperty(name="Orbit-X", default=0.0, subtype='ANGLE', description="Orbit rotation around X axis of capture objects\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "camera_orbit_x"))
    camera_roll: FloatProperty(name="Roll", default=0.0, subtype='ANGLE', description="Roll rotation around cameras on pointing axis\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "camera_roll"))

    h_center_object: PointerProperty(name="Horizontal Center Object", type=Object, description="Object whose origin will be used as the horizontal center for each sprite frame\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "h_center_object"))
    h_center_bone: StringProperty(name="Horizontal Center Bone", default="", description="Bone whose origin will be used as the horizontal center for each sprite frame\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "h_center_bone"))
    v_center_object: PointerProperty(name="Vertical Center Object", type=Object, description="Object whose origin will be used as the vertically center for each sprite frame\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "v_center_object"))
    v_center_bone: StringProperty(name="Vertical Center Bone", default="", description="Bone whose origin will be used as the vertically center for each sprite frame\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "v_center_bone"))
    
    consider_armature_bones: BoolProperty(default=False, description="Include all armature bones when calculating auto-capture camera bounds to ensure they remain within camera view\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "consider_armature_bones"))
    pixels_per_meter: FloatProperty(name="Pixels Per Meter", default=100.0, min=1.0, soft_max=5000.0, description="Number of pixels rendered per one world space meter unit\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "pixels_per_meter"))
    camera_padding_h: FloatProperty(name="Camera Padding", unit='LENGTH', default=0.0, min=0.0, soft_max=10.0, description="Extra margin around camera view\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "camera_padding_h"))
    camera_padding_v: FloatProperty(name="Camera Padding", unit='LENGTH', default=0.0, min=0.0, soft_max=10.0, description="Extra margin around camera view\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "camera_padding_v"))


    # Pixelation settings
    to_pixelate: BoolProperty(name="To Pixelate", default=False, description="If enabled the row is pixelated\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "to_pixelate"))
    pixelation_amount: FloatProperty(name="Pixelation Amount", default=0.9, precision=5, step=0.001, min=0.0, max=1.0, description="By how much amount to pixelate the row\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "pixelation_amount"))
    color_amount: FloatProperty(name="Pixelation Color Amount", default=50.0, min=0.0, soft_max=1000, description="How much amount of color to keep within the row\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "color_amount"))
    min_alpha: FloatProperty(name="Min Alpha", default=0.0, min=0.0, max=1.1, description="If any pixel in the row has a transparency less than this amount then it is discarded\nSet as 1.0 if to remove all semi-transparent pixel\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "min_alpha"))
    alpha_step: FloatProperty(name="Alpha Step", default=0.0, min=0.0, max=1.1, description="Ensures that all pixels have a transparency which is a multiple of this amount\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "alpha_step"))
    pixelate_image_path: StringProperty(
        name="Pixelate Image Path",
        subtype="FILE_PATH",
        description="Target image to pixelate\nHold Alt & change to sync across all rows",
        update=lambda self, ctx: self.alt_sync_update(ctx, "pixelate_image_path")
    )
    
    
    # Flip settings
    to_flip_h: BoolProperty(name="To Flip H", default=False, description="If enabled the rendered image is flipped horizontally before saving into temp folder\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "to_flip_h"))
    to_flip_v: BoolProperty(name="To Flip V", default=False, description="If enabled the rendered image is flipped vertically before saving into temp folder\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "to_flip_v"))
    
    
    # Manual frame settings
    frame_selection_mode: EnumProperty(
        name="Frame Selection",
        description="Dictates which frames are captured for this row\nHold Alt & change to sync across all rows",
        items = [
            (FrameSelectionMode.ALL_FRAMES.value, "All Frames", "Captures the full frame range of the longest assigned action"),
            (FrameSelectionMode.CUSTOM_RANGE.value, "Custom Range", "Captures a manually assigned start and end frame range"),
            (FrameSelectionMode.CUSTOM_COUNT.value, "Custom Count", "Scales assigned actions to fit a desired frame count")
        ],
        default=FrameSelectionMode.ALL_FRAMES.value,
        update=lambda self, ctx: self.alt_sync_update(ctx, "frame_selection_mode")
    )
    frame_start: IntProperty(name="Start", default=0, min=-1048574, soft_max=1048574, description="Frame to start capturing from\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "frame_start"))
    frame_end: IntProperty(name="End", default=250, min=-1048574, soft_max=1048574, description="Frame to stop capturing at (inclusive)\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "frame_end"))
    frame_count: IntProperty(name="Count", default=10, min=1, soft_max=1048574, description="Desired frame count after scaling assigned actions\nHold Alt & change to sync across all rows", update=lambda self, ctx: self.alt_sync_update(ctx, "frame_count"))
class SSM_Properties(PropertyGroup):

    def update_temp_folder(self, context):
        if self.temp_folder.startswith("//"):
            self.temp_folder = bpy.path.abspath(self.temp_folder)
    def update_output_folder(self, context):
        if self.output_folder.startswith("//"):
            self.output_folder = bpy.path.abspath(self.output_folder)
    

    # Output settings
    label_font_size: IntProperty(name="Label Font Size", default=24, min=0, soft_max=1000, description="Font size of label text")
    label_color: FloatVectorProperty(name="Label Color", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0, description="Color of the label text on top of each row")
    background_color: FloatVectorProperty(name="Background Color", subtype='COLOR', size=4, default=(0.0, 0.0, 0.0, 0.0), min=0.0, max=1.0, description="Background color for entire sheet (or rows, or images based on combine mode)")
    surrounding_margin_top: IntProperty(name="Surrounding Margin Top", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the top of the sprite sheet")
    surrounding_margin_right: IntProperty(name="Surrounding Margin Right", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the right of the sprite sheet")
    surrounding_margin_bottom: IntProperty(name="Surrounding Margin Bottom", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the bottom of the sprite sheet")
    surrounding_margin_left: IntProperty(name="Surrounding Margin Left", default=15, min=0, soft_max=1000, description="Margin (in pixels) to add to the left of the sprite sheet")
    label_margin: IntProperty(name="Label Margin", default=15, min=0, soft_max=1000, description="Vertical margin gap (in pixels) between the label and the images")
    image_margin: IntProperty(name="Image Margin", default=15, min=0, soft_max=1000, description="Horizonal margin gap (in pixels) between images within a row/row")
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
            (CombineMode.STRIPS.value, "Rows", "Render out separate row strips"),
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
    show_row_info: BoolProperty(name="Show Row Info", default=False)
    show_output_settings: BoolProperty(name="Show Output Settings", default=False)
class SSM_UL_AnimationRows(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "enabled", text="")
        layout.label(text=item.label if item.label != "" else UNTITLED_ROW_NAME, icon='SEQ_STRIP_DUPLICATE')
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
class SSM_OT_DuplicateRow(Operator):
    bl_idname = "spritesheetmaker.duplicate_row"
    bl_label = "Duplicate Row"
    bl_description = "Duplicate the selected row"
    bl_options = {'UNDO'}

    def execute(self, context):
        # Get essentials
        scene = context.scene
        rows = scene.animation_rows
        idx = scene.row_index


        # Return if no rows exist
        if idx < 0 or idx >= len(rows):
            return bpy.ops.spritesheetmaker.add_row()


        # Store original row
        original_row = rows[idx]


        # Create new row
        new_row = rows.add()
        
        # Copy basic properties dynamically
        for prop in original_row.rna_type.properties:
            if not prop.is_readonly and prop.identifier != "capture_items":
                setattr(new_row, prop.identifier, getattr(original_row, prop.identifier))
        
        # Duplicate collection items dynamically
        new_row.capture_items.clear()
        for item in original_row.capture_items:
            dst_item = new_row.capture_items.add()
            for prop in item.rna_type.properties:
                if not prop.is_readonly:
                    setattr(dst_item, prop.identifier, getattr(item, prop.identifier))


        # Set index of row
        new_index = len(rows) - 1
        target_index = idx + 1
        rows.move(new_index, target_index)
        scene.row_index = target_index


        return {'FINISHED'}
class SSM_OT_AddRow(Operator):
    bl_idname = "spritesheetmaker.add_row"
    bl_label = "Add Row"
    bl_description = "Add new animation row"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        scene.animation_rows.add()
        # new.frame_start = 1
        # new.frame_end = 250
        scene.row_index = len(scene.animation_rows) - 1
        return {'FINISHED'}
class SSM_OT_RemoveRow(Operator):
    bl_idname = "spritesheetmaker.remove_row"
    bl_label = "Remove Row"
    bl_description = "Remove selected animation row"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        idx = scene.row_index
        if 0 <= idx < len(scene.animation_rows):
            scene.animation_rows.remove(idx)
            scene.row_index = max(0, min(len(scene.animation_rows) - 1, idx - 1))
        return {'FINISHED'}
class SSM_OT_MoveRow(Operator):
    bl_idname = "spritesheetmaker.move_row"
    bl_label = "Move Row"
    bl_description = "Move animation row up or down"
    bl_options = {'UNDO'}

    direction: EnumProperty(
        items=[
            ("UP", "Up", ""),
            ("DOWN", "Down", "")
        ]
    )

    def execute(self, context):
        scene = context.scene
        idx = scene.row_index
        rows = scene.animation_rows

        if self.direction == "UP" and idx > 0:
            rows.move(idx, idx - 1)
            scene.row_index -= 1

        elif self.direction == "DOWN" and idx < len(rows) - 1:
            rows.move(idx, idx + 1)
            scene.row_index += 1

        return {"FINISHED"}
class SSM_OT_PlayCaptureItems(Operator):
    bl_idname = "spritesheetmaker.play_capture_items"
    bl_label = "Play Capture Items"
    bl_description = "Preview all animations associated with this row"
    bl_options = {'UNDO'}

    def execute(self, context):

        # Return if no valid row selected
        scene = context.scene
        si = scene.row_index
        if si < 0 or si >= len(scene.animation_rows):
            log("No valid row selected to play capture items!")
            return {'CANCELLED'}

        
        # Return if no capture items
        row = scene.animation_rows[si]
        if si < 0 or si >= len(scene.animation_rows) or len(row.capture_items) == 0:
            return {'CANCELLED'}
        

        # Assign all actions to respective Objects
        min_frame = float('inf')
        max_frame = float('-inf')
        has_valid_action = False
        for item in row.capture_items:
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
        si = scene.row_index
        if si < 0 or si >= len(scene.animation_rows):
            return {'CANCELLED'}
        
        row = scene.animation_rows[si]
        row.capture_items.add()
        row.capture_item_index = len(row.capture_items) - 1
        return {'FINISHED'}
class SSM_OT_RemoveCaptureItem(Operator):
    bl_idname = "spritesheetmaker.remove_capture_item"
    bl_label = "Remove Selected Capture Item"
    bl_description = "Remove capture item"
    bl_options = {'UNDO'}

    def execute(self, context):
        scene = context.scene
        si = scene.row_index
        if si < 0 or si >= len(scene.animation_rows):
            return {'CANCELLED'}
        row = scene.animation_rows[si]
        ii = row.capture_item_index
        if 0 <= ii < len(row.capture_items):

            # Capture removed action name before deleting item
            removed_item = row.capture_items[ii]
            removed_action_name = removed_item.action.name if removed_item.action else ""

            # Remove capture item
            row.capture_items.remove(ii)
            row.capture_item_index = max(0, ii - 1)

            # Update label
            row.update_label_from_action(removed_action_name)
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
        export_data = { "rows": [], "props": {} }
        

        # Store all rows
        for row in context.scene.animation_rows:

            # Store all basic properties e.g. label, custom_camera, etc
            s_data = {}
            for p in row.rna_type.properties:
                if not p.is_readonly and p.identifier not in {"capture_items", "name"} and p.identifier not in NON_SERIALIZABLE_PROPERTIES:
                    s_data[p.identifier] = getattr(row, p.identifier)
            

            # Store object pointer properties as names since objects are not json serializable
            for prop_name in NON_SERIALIZABLE_PROPERTIES:
                obj = getattr(row, prop_name)
                s_data[prop_name] = obj.name if obj else ""
            
            
            # Store all capture items
            s_data["capture_items"] = []
            for item in row.capture_items:
                i_data = {}
                i_data["object"] = item.object.name if item.object else ""
                i_data["action"] = item.action.name if item.action else ""
                i_data["slot"] =  item.slot
                s_data["capture_items"].append(i_data)
            

            # Add to all rows data 
            export_data["rows"].append(s_data)

        
        # Store all common properties
        for p in props.rna_type.properties:
            if not p.is_readonly and p.identifier not in EXCLUDE_EXPORT_PROPERTIES:
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


        # Clear previous animation rows
        scene.animation_rows.clear()  


        # Create all new rows
        for row_data in data.get("rows", []):

            # Add new row
            row = scene.animation_rows.add()

            # Load all basic properties e.g. label, etc
            for key, val in row_data.items():
                if key != "capture_items" and key not in NON_SERIALIZABLE_PROPERTIES and hasattr(row, key):
                    setattr(row, key, val)

            # Load object pointer properties by resolving stored name back to object
            for prop_name in NON_SERIALIZABLE_PROPERTIES:
                obj_name = row_data.get(prop_name, "")
                setattr(row, prop_name, bpy.data.objects[obj_name] if obj_name in bpy.data.objects else None)
            
            # Load all capture items
            for item_data in row_data.get("capture_items", []):
                item = row.capture_items.add()

                # Add object to capture item
                obj_name = item_data.get("object", "")
                if obj_name == "":
                    item.object = None
                elif obj_name in bpy.data.objects:
                    item.object = bpy.data.objects[obj_name]
                else:
                    log(f"Missing object '{obj_name}' found while importing!")
                    item.object = None


                # Add action to capture item
                action_name = item_data.get("action", "")
                if action_name == "":
                    item.action = None
                elif action_name in bpy.data.actions:
                    item.action = bpy.data.actions[action_name]
                else:
                    log(f"Missing action '{action_name}' found while importing!")
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
        curr_row = get_current_row()
        cam_obj = curr_row.custom_camera


        # Return if any invalid property in row
        curr_row = get_current_row()
        if(not SSM_OT_CreateSheet.check_row(curr_row)):
            return {'FINISHED'}
        

        # Set it up based on auto parameters
        param = gen_auto_capture_param(curr_row)
        setup_auto_camera(cam_obj, param)


        return {'FINISHED'}
class SSM_OT_PixelateImage(Operator):
    bl_idname = "spritesheetmaker.pixelate_image"
    bl_label = "Pixelate Image"
    bl_description = "Pixelate given test image based on the pixelation properties assigned"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # Get props
        curr_row = get_current_row()

        
        # Return if invalid test image path
        if(not os.path.exists(curr_row.pixelate_image_path)):
            log("'Test image' is invalid!", True, "CANCEL")
            return {'FINISHED'}


        # Combine images together into single file and paste in output
        try:
            # Generate param
            param = gen_pixelate_param(curr_row)
            pixelated_output_path = get_pixelated_img_path()
            pixelate_images({ curr_row.pixelate_image_path:pixelated_output_path }, param)

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
    bl_description = "Render out a single sprite of currently selected row\nUseful for verifying settings before rendering the full sheet"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        
        # Get Scene & props
        scene = bpy.context.scene
        props = context.scene.sprite_sheet_maker_props


        # Return if no rows
        if(len(scene.animation_rows) == 0):
            log("Empty 'Rows'!", True, "CANCEL")
            return {'FINISHED'}


        # Return if any invalid property in row
        curr_row = get_current_row()
        if(not SSM_OT_CreateSheet.check_row(curr_row)):
            return {'FINISHED'}
        

        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            log("'Output Folder' is invalid!", True, "CANCEL")
            return {'FINISHED'}
        

        # Create single sprite by making a sheet with only 1 row/row with only 1 frame
        try:

            # Row parameters            
            row_param = gen_row_param(get_current_row())
            row_param.frame_selection_mode = FrameSelectionMode.CUSTOM_RANGE
            row_param.frame_start = bpy.context.scene.frame_current
            row_param.frame_end = bpy.context.scene.frame_current


            # Sheet parameters
            sheet_param:SpriteSheetParam = gen_sprite_sheet_param()
            sheet_param.assemble_param.combine_mode = CombineMode.SHEET
            sheet_param.animation_rows = [row_param]
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
    def check_row(row):

        # Return if empty capture items
        objects = get_objects_to_capture(row)
        if(row.to_auto_capture and len(objects) == 0):
            log(f"Empty or Invalid 'Capture Items' in '{get_row_label(row)}' Row!", True, "CANCEL")
            return False

            
        # Return if any invalid objects or actions
        for capture_item in row.capture_items:
            if (not capture_item.object):
                log(f"Invalid Object in 'Capture Items' of '{get_row_label(row)}' Row!", True, "CANCEL")
                return False
            
            try:  # To ensure "ReferenceError: StructRNA of type Action has been removed" does not occur
                if(capture_item.action != None):
                    capture_item.action.name
            except ReferenceError as e:
                log(f"Invalid Action in 'Capture Items' of '{get_row_label(row)}' Row!", True, "CANCEL")
                return False


        # Return if neither auto capture nor custom camera has been set
        if(not row.to_auto_capture and (row.custom_camera is None)):
            log(f"Either set a valid 'Custom Camera' or enable 'To Auto Capture'\nin '{get_row_label(row)}' Row!", True, "CANCEL")
            return False
        

        # Return if invalid custom camera
        if(not row.to_auto_capture and not is_valid(row.custom_camera, False)):
            log(f"Invalid 'Custom Camera' in '{get_row_label(row)}' Row!", True, "CANCEL")
            return False


        # Return if invalid center obj H
        if(row.to_auto_capture and (row.h_center_object is not None) and (not is_valid(row.h_center_object))):
            log(f"Invalid 'Center Obj H' in '{get_row_label(row)}' Row!", True, "CANCEL")  # Return if invalid Center Obj H
            return False


        # Return if invalid center obj V
        if(row.to_auto_capture and (row.v_center_object is not None) and (not is_valid(row.v_center_object))):
            log(f"Invalid 'Center Obj V' in '{get_row_label(row)}' Row!", True, "CANCEL")
            return False


        return True
    def execute(self, context):

        # Get Scene & props
        scene = bpy.context.scene
        props = context.scene.sprite_sheet_maker_props


        # Return if no rows
        if(len(scene.animation_rows) == 0):
            log("Empty 'Rows'!", True, "CANCEL")
            return {'FINISHED'}


        # Return if no rows are enabled
        if(not any(row.enabled for row in scene.animation_rows)):
            log("No 'Rows' are enabled!", True, "CANCEL")
            return {'FINISHED'}
        

        # Return in case of anything invalid in row
        for row in scene.animation_rows:

            if(not row.enabled):
                continue
    
            if(not SSM_OT_CreateSheet.check_row(row)):
                return {'FINISHED'}
            

        # Return if invalid output folder
        if(props.output_folder == "" or not os.path.exists(props.output_folder)):
            log("'Output Folder' is invalid!", True, "CANCEL")
            return {'FINISHED'}


        # Create sprite sheet
        try:
            wm = bpy.context.window_manager   # Get the window manager & create a progress bar

            def begin_row_progress(row_label, total_frame):
                wm.progress_begin(0, total_frame)  # Start progress bar
            def update_frame_progress(row_label, frame):
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


    def draw_row_info(self, context, scene, ui_box):

        # Label
        row = scene.animation_rows[scene.row_index]
        split = ui_box.split(factor=0.25)
        split.label(text="Label")
        split.prop(row, 'label', text='')


        # Capture Items
        ui_box.label(text="Capture Items")
        ui_capture_line = ui_box.row()
        ui_capture_line.template_list('SSM_UL_CaptureItems', '', row, 'capture_items', row, 'capture_item_index', rows=3, maxrows=3)
        col = ui_capture_line.column(align=True)
        col.operator('spritesheetmaker.play_capture_items', icon='PLAY', text='')
        col.separator()
        col.operator('spritesheetmaker.add_capture_item', icon='ADD', text='')
        col.operator('spritesheetmaker.remove_capture_item', icon='REMOVE', text='')
        
        
        # Custom Camera
        split = ui_box.split(factor=0.40)
        split.label(text="Custom Camera")
        split.prop(row, "custom_camera", text="")
        

        # To Auto Capture
        ui_box.prop(row, "to_auto_capture")
        if row.to_auto_capture:

            # Indent sub props
            sub_box = ui_box.row().split(factor=0.02)
            sub_box.label(text="")
            sub_col = sub_box.column()

            # Camera Direction
            split = sub_col.split(factor=0.40)
            split.label(text="Camera Direction")
            split.prop(row, "camera_direction", text="")

            # Custom Direction
            if row.camera_direction == CameraDirection.CUSTOM.value:
                sub_col.prop(row, "camera_orbit_z")
                sub_col.prop(row, "camera_orbit_x")
                sub_col.prop(row, "camera_roll")

            # Horizontal Center Object
            split = sub_col.split(factor=0.40)
            split.label(text="Center Obj H")
            col = split.column(align=True)
            col.prop(row, "h_center_object", text="")
            if row.h_center_object and row.h_center_object.type == 'ARMATURE':
                col.prop_search(row, "h_center_bone", row.h_center_object.pose, "bones", text="Bone")

            # Vertical Center Object
            split = sub_col.split(factor=0.40)
            split.label(text="Center Obj V")
            col = split.column(align=True)
            col.prop(row, "v_center_object", text="")
            if row.v_center_object and row.v_center_object.type == 'ARMATURE':
                col.prop_search(row, "v_center_bone", row.v_center_object.pose, "bones", text="Bone")

            # Consider Armature Bones
            sub_col.prop(row, "consider_armature_bones", text="Consider Armature Bones")
            sub_col.prop(row, "camera_padding_h", text="Camera Padding H")  # Camera Padding Horizontal
            sub_col.prop(row, "camera_padding_v", text="Camera Padding V")  # Camera Padding Vertical
            sub_col.prop(row, "pixels_per_meter", text="Pixels Per Meter")  # Pixels Per Meter 

            # Create Auto Camera Button
            sub_col.separator(factor=0.25)
            ui_line = sub_col.row()
            button_text = "Create Auto Camera" if row.custom_camera == None else "Modify Custom Camera"
            ui_line.operator("spritesheetmaker.create_auto_camera", text=button_text, icon="OUTLINER_OB_CAMERA")


        # To Pixelate
        ui_box.prop(row, "to_pixelate")
        if row.to_pixelate:
            # Indent sub props
            sub_box = ui_box.row().split(factor=0.02)
            sub_box.label(text="")
            sub_col = sub_box.column()
            
            sub_col.prop(row, "pixelation_amount", text="Pixelation")  # Pixelation
            sub_col.prop(row, "color_amount", text="Color Amount")  # Color Amount
            sub_col.prop(row, "min_alpha", text="Min Alpha")  # Min Alpha
            sub_col.prop(row, "alpha_step", text="Alpha Step")  # Alpha Step

            # Test Image
            ui_line = sub_col.row()
            split = ui_line.split(factor=0.45)
            split.label(text="Test Image")
            split.prop(row, "pixelate_image_path", text="")

            # Pixelate Test Image Button
            ui_line = sub_col.row()
            ui_line.operator("spritesheetmaker.pixelate_image", text="Pixelate Test Image", icon="MOD_REMESH")


        # To Flip H & V
        ui_box.prop(row, "to_flip_h")
        ui_box.prop(row, "to_flip_v")
        

        # Frame Selection
        split = ui_box.split(factor=0.40)
        split.label(text="Frame Selection")
        split.prop(row, "frame_selection_mode", text="")
        if row.frame_selection_mode == FrameSelectionMode.CUSTOM_RANGE.value:  # Frame Start & End
            ui_line2 = ui_box.row(align=True)
            split = ui_line2.split(factor=0.50)
            split.prop(row, 'frame_start', text='Start')
            split.prop(row, 'frame_end', text='End')
        elif row.frame_selection_mode == FrameSelectionMode.CUSTOM_COUNT.value:  # Frame Count
            ui_box.prop(row, 'frame_count', text='Count')
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        props = context.scene.sprite_sheet_maker_props


        # Import & Export Buttons
        ui_line = layout.row(align=True)
        ui_line.operator("spritesheetmaker.export_settings", icon='EXPORT', text="Export")
        ui_line.operator("spritesheetmaker.import_settings", icon='IMPORT', text="Import")
        layout.separator(factor=0.5)
        

        # Rows
        box = layout.box()
        box.label(text="Rows")
        ui_line = box.row()
        ui_line.template_list(
            "SSM_UL_AnimationRows",
            "",
            scene,
            "animation_rows",
            scene,
            "row_index",
            rows=4,
            maxrows=4
        )


        # Rows Add & Remove buttons
        ops = ui_line.column(align=True)
        ops.operator("spritesheetmaker.duplicate_row", icon='DUPLICATE', text='')
        ops.separator()
        ops.operator('spritesheetmaker.add_row', icon='ADD', text='')
        ops.operator('spritesheetmaker.remove_row', icon='REMOVE', text='')


        # Rows Up & Down buttons
        ops.separator()
        ops.operator('spritesheetmaker.move_row', icon='TRIA_UP', text="").direction = 'UP'
        ops.operator('spritesheetmaker.move_row', icon='TRIA_DOWN', text="").direction = 'DOWN'


        # Row Info
        has_row = len(scene.animation_rows) > 0 and 0 <= scene.row_index < len(scene.animation_rows)
        box = layout.box()
        box.prop(props, "show_row_info", icon="TRIA_DOWN" if props.show_row_info else "TRIA_RIGHT", emboss=False, text=f"Row Info{'' if has_row else ' (Add atleast one row)'}")
        if(props.show_row_info):
            box.enabled = has_row
            if has_row:
                self.draw_row_info(context, scene, box)


        # Output Settings (Collapsible)
        box = layout.box()
        box.prop(props, "show_output_settings", icon="TRIA_DOWN" if props.show_output_settings else "TRIA_RIGHT", emboss=False, text="Output Settings")
        if props.show_output_settings:

            # Label Font Size
            box.prop(props, "label_font_size", text="Label Font Size")

            # Label Color
            ui_line = box.row()
            split = ui_line.split(factor=0.45)
            split.label(text="Label Color")
            split.prop(props, "label_color", text="")

            # Background Color
            ui_line = box.row()
            split = ui_line.split(factor=0.45)
            split.label(text="Background Color")
            split.prop(props, "background_color", text="")

            # Surrounding Margins
            box.label(text="Surrounding Margins")
            ui_line = box.row(align=True)  # Create a row layout
            ui_line.prop(props, "surrounding_margin_top", text="Top")
            ui_line.prop(props, "surrounding_margin_right", text="Right")
            ui_line.prop(props, "surrounding_margin_bottom", text="Bottom")
            ui_line.prop(props, "surrounding_margin_left", text="Left")

            # Label Margin
            box.prop(props, "label_margin", text="Label Margin")

            # Image Margin
            box.prop(props, "image_margin", text="Image Margin")
            
            # Sprite Consistency
            ui_line = box.row()
            split = ui_line.split(factor=0.60)
            split.label(text="Sprite Consistency")
            split.prop(props, "sprite_consistency", text="")

            # Sprite Align
            ui_line = box.row()
            split = ui_line.split(factor=0.60)
            split.label(text="Sprite Align")
            split.prop(props, "sprite_align", text="")

            # Combine Mode
            ui_line = box.row()
            split = ui_line.split(factor=0.60)
            split.label(text="Combine Mode")
            split.prop(props, "combine_mode", text="")

            # Delete Temp Folder
            box.prop(props, "delete_temp_folder", text="Delete Temp Folder")
        
            # Temp Folder
            ui_line = box.row()
            split = ui_line.split(factor=0.45)
            split.label(text="Temp Folder")
            split.prop(props, "temp_folder", text="")

            # Combine Sprites Button
            ui_line = box.row()
            ui_line.operator("spritesheetmaker.combine_sprites", text="Combine Sprites", icon="TEXTURE")


        # Output folder
        layout.separator(factor=0.5)
        ui_line = layout.row()
        split = ui_line.split(factor=0.45)
        split.label(text="Output Folder")
        split.prop(props, "output_folder", text="")


        # Create Single Sprite Button
        layout.separator(factor=0.25)
        ui_line = layout.row()
        ui_line.scale_y = 1.5
        ui_line.operator("spritesheetmaker.create_single", text="Create Single Sprite", icon="FILE_IMAGE")


        # Create Sprite Sheet Button
        if props.combine_mode == CombineMode.SHEET.value:
            create_btn_text = "Create Sprite Sheet"
        elif props.combine_mode == CombineMode.STRIPS.value:
            create_btn_text = "Create Sprite Rows"
        else:
            create_btn_text = "Create Sprite Images"

        layout.separator(factor=0.25)
        ui_line = layout.row()
        ui_line.scale_y = 1.5
        ui_line.operator("spritesheetmaker.create_sheet", text=create_btn_text, icon="RENDER_ANIMATION")


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
def gen_auto_capture_param(row):

    param = AutoCaptureParam()
    param.objects = get_objects_to_capture(row)
    

    # Auto copy matching properties
    for prop in param.__dict__:
        if hasattr(row, prop) and prop not in ["objects", "camera_direction"]:
            setattr(param, prop, getattr(row, prop))
            

    # Manual override for Enum
    param.camera_direction = CameraDirection(row.camera_direction)


    return param
def gen_pixelate_param(row):

    param = PixelateParam()
    

    # Auto copy all matching properties
    for prop in param.__dict__:
        if hasattr(row, prop):
            setattr(param, prop, getattr(row, prop))


    return param
def gen_row_param(row):
    row_param = RowParam()
    row_param.capture_items = [(capture_item.object, capture_item.action, capture_item.slot) for capture_item in row.capture_items]
    

    # Auto copy row properties
    for prop in row_param.__dict__:
        if hasattr(row, prop) and prop not in ["capture_items", "frame_selection_mode"]:
            setattr(row_param, prop, getattr(row, prop))


    # Manual override for Enum
    row_param.frame_selection_mode = FrameSelectionMode(row.frame_selection_mode)


    # Assign sub params
    row_param.auto_capture_param = gen_auto_capture_param(row) if row.to_auto_capture else AutoCaptureParam()
    row_param.pixelate_param = gen_pixelate_param(row) if row.to_pixelate else PixelateParam()

    return row_param
def gen_sprite_sheet_param():

    # Get all props & scene
    props = bpy.context.scene.sprite_sheet_maker_props
    scene = bpy.context.scene
    param = SpriteSheetParam()


    # Auto copy top level matching properties
    for prop in param.__dict__:
        if hasattr(props, prop):
            setattr(param, prop, getattr(props, prop))


    # Assign rows
    param.animation_rows = []
    for row in scene.animation_rows:

        # Skip disabled rows
        if(not row.enabled):
            continue

        row_param = gen_row_param(row)
        param.animation_rows.append(row_param)


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
def get_current_row():
    scene = bpy.context.scene
    rows = scene.animation_rows
    if(len(rows) == 0):
        return None

    idx = scene.row_index
    return rows[idx]
def get_row_label(row):
    return row.label if row.label!='' else UNTITLED_ROW_NAME
def get_label_text():

    # Get the label text of the first row 
    scene = bpy.context.scene
    for row in scene.animation_rows:
        if(row.label == ""):
            continue
    
        return row.label
    
    return UNTITLED_LABEL_TEXT
def get_pixelated_img_path():

    # Get all props
    curr_row = get_current_row()
    file_ext = bpy.context.scene.render.image_settings.file_format.lower()


    # Add postfix to the file name
    dir_name, file_name = os.path.split(curr_row.pixelate_image_path)
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
def get_objects_to_capture(row):

    # Get objects in row
    objects = set()
    for item in row.capture_items:

        # Skip if invalid object or if not to consider armature
        if(not is_valid(item.object) or (item.object.type == 'ARMATURE' and not row.consider_armature_bones)):
            continue
        
        objects.add(item.object)


    return objects


# Initialize Classes
classes = (
    SSM_MessagePopup,
    SSM_Properties,
    SSM_CaptureItem,
    SSM_RowInfo,
    SSM_OT_KeyListener,
    SSM_OT_ImportSettings,
    SSM_OT_ExportSettings,
    SSM_UL_AnimationRows,
    SSM_UL_CaptureItems,
    SSM_OT_DuplicateRow,
    SSM_OT_AddRow,
    SSM_OT_RemoveRow,
    SSM_OT_MoveRow,
    SSM_OT_PlayCaptureItems,
    SSM_OT_AddCaptureItem,
    SSM_OT_RemoveCaptureItem,
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
    Scene.animation_rows = CollectionProperty(type=SSM_RowInfo)
    Scene.row_index = IntProperty(default=0)


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
    del Scene.animation_rows
    del Scene.row_index


if __name__ == "__main__":
    register()
