import bpy
import os
from mathutils import Vector
from enum import Enum
import shutil
import weakref
import traceback


TEMP_FOLDER_NAME = "SpriteSheetMakerTemp"
CAMERA_NAME = "SpriteSheetMakerCamera"
PIXELATE_COMPOSITOR_NAME = "SpriteSheetMakerPixelate"
SPRITE_SHEET_MAKER_BLEND_FILE = "SpriteSheetMaker.blend"
IMAGE_INPUT_NODE = "ImageInput"
PIXELATION_AMOUNT_NODE = "PixelationAmount"
SHRINK_SCALE_NODE = "ShrinkScale"
COLOR_AMOUNT_NODE = "ColorAmount"
MIN_ALPHA_NODE = "MinAlpha"
ALPHA_STEP_NODE = "AlphaStep"


class CameraDirection(Enum):
    X = "x"
    Y = "y"
    Z = "z"
    NEG_X = "-x"
    NEG_Y = "-y"
    NEG_Z = "-z"

class ScaleInterpType(Enum):
    NEAREST = "Nearest"
    BILINEAR = "Bilinear"
    BICUBIC = "Bicubic"
    ANISOTROPIC = "Anisotropic"

class PixelateParam():
    pixelation_amount: float = 0.9
    shrink_interp:ScaleInterpType = ScaleInterpType.NEAREST
    color_amount: float = 50.0
    min_alpha: float = 0.0
    alpha_step: float = 0.25  # Ensures alpha of color is rounded down to the nearest multiple of "step" (helps reducing gradients)

class SpriteParam():
    output_file_path: str = ""
    objects:set = set({})
    actions = []
    camera = None
    camera_direction: CameraDirection = CameraDirection.NEG_X
    camera_padding: float = 0.05
    pixels_per_meter: int = 500
    to_pixelate: bool = False
    consider_armature_bones: bool = False
    pixelate_param: PixelateParam = PixelateParam()
    delete_temp_folder: bool = True
    label_font_size: int = 24  # in pixels
    frame_margin: int = 15  # in pixels

class Event:
    def __init__(self):
        self._subscribers = weakref.WeakSet()

    def subscribe(self, func):
        self._subscribers.add(func)

    def unsubscribe(self, func):
        self._subscribers.discard(func)

    def broadcast(self, *args, **kwargs):
        for func in list(self._subscribers):
            func(*args, **kwargs)

def setup_camera(bounding_box: tuple[Vector, Vector] = (Vector(), Vector()), direction: CameraDirection = CameraDirection.NEG_X, pixels_per_meter: int = 500):

    # Split bounding box into min & max vertices
    min_v, max_v = bounding_box


    # Calculate camera properties based on direction
    if direction.value in [CameraDirection.X.value, CameraDirection.NEG_X.value]:
        is_positive = direction.value == CameraDirection.X.value
        face_x = max_v.x if is_positive else min_v.x
        cam_pos = Vector((face_x, (min_v.y + max_v.y) / 2, (min_v.z + max_v.z) / 2))
        cam_normal = Vector((1, 0, 0)) if is_positive else Vector((-1, 0, 0))
        height = max_v.z - min_v.z
        width = max_v.y - min_v.y
        
    elif direction.value in [CameraDirection.Y.value, CameraDirection.NEG_Y.value]:
        is_positive = direction.value == CameraDirection.Y.value
        face_y = max_v.y if is_positive else min_v.y
        cam_pos = Vector(((min_v.x + max_v.x) / 2, face_y, (min_v.z + max_v.z) / 2))
        cam_normal = Vector((0, 1, 0)) if is_positive else Vector((0, -1, 0))
        height = max_v.z - min_v.z
        width = max_v.x - min_v.x
        
    elif direction.value in [CameraDirection.Z.value, CameraDirection.NEG_Z.value]:
        is_positive = direction.value == CameraDirection.Z.value
        face_z = max_v.z if is_positive else min_v.z
        cam_pos = Vector(((min_v.x + max_v.x) / 2, (min_v.y + max_v.y) / 2, face_z))
        cam_normal = Vector((0, 0, 1)) if is_positive else Vector((0, 0, -1))
        height = max_v.y - min_v.y
        width = max_v.x - min_v.x
    
    else:
        raise ValueError(f"Invalid direction: {direction}")


    # get existing camera
    cam_obj = bpy.data.objects.get(CAMERA_NAME)
    

    # If no existing camera found then create one
    if cam_obj is None:
        cam_data = bpy.data.cameras.new(name=CAMERA_NAME)
        cam_obj = bpy.data.objects.new(CAMERA_NAME, cam_data)
        bpy.context.collection.objects.link(cam_obj)


    # Get camera data
    cam_data = cam_obj.data


    # Set as scene camera to render from
    bpy.context.scene.camera = cam_obj


    # Set properties of camera
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(width, height) 
    cam_obj.location = cam_pos + cam_normal * 1.0
    direction_vector = (cam_pos - cam_obj.location).normalized()
    rot_quat = direction_vector.to_track_quat('-Z', 'Y')
    cam_obj.rotation_mode = 'QUATERNION'
    cam_obj.rotation_quaternion = rot_quat
    cam_obj.rotation_mode = 'XYZ'
    

    # Set clipping
    bbox_center_loc = (min_v + max_v) / 2
    camera_to_bbox_dist = (cam_obj.location - bbox_center_loc).length
    bbox_diagonal_dist =  (min_v - max_v).length
    cam_data.clip_start = 0.1
    cam_data.clip_end = camera_to_bbox_dist + bbox_diagonal_dist  # This is done to ensure an extra safe margin no matter the camera direction
        

    # Determine resolution
    res_x = int(width * pixels_per_meter)
    res_y = int(height * pixels_per_meter)
    bpy.context.scene.render.resolution_x = res_x
    bpy.context.scene.render.resolution_y = res_y
    bpy.context.scene.render.resolution_percentage = 100 # Ensuring complete resolution

    return cam_obj

def get_bounding_box(objects, ignore_armatures = True):

    # Return if no objects
    if(len(objects) == 0):
        return Vector(), Vector()
    

    # Iterate through all objects and get min/max corners
    min_corner = Vector((float('inf'), float('inf'), float('inf')))
    max_corner = Vector((float('-inf'), float('-inf'), float('-inf')))
    for obj in objects:
        if obj.type == 'ARMATURE' and ignore_armatures:
            continue
        
        # Check if object has bounding box property
        if hasattr(obj, 'bound_box') and obj.bound_box:
            for vert in obj.bound_box:
                # Transform the local bound_box vertex to world space
                v_world = obj.matrix_world @ Vector(vert)
                
                # Update the overall bounding box
                min_corner.x = min(min_corner.x, v_world.x)
                min_corner.y = min(min_corner.y, v_world.y)
                min_corner.z = min(min_corner.z, v_world.z)
                
                max_corner.x = max(max_corner.x, v_world.x)
                max_corner.y = max(max_corner.y, v_world.y)
                max_corner.z = max(max_corner.z, v_world.z)
        
        # Object has location property instead
        elif hasattr(obj, 'location'):
            # Directly assigning since location is already world space
            v_world = obj.location 
            
            # Treat the location as a single point for the bounding box
            min_corner.x = min(min_corner.x, v_world.x)
            min_corner.y = min(min_corner.y, v_world.y)
            min_corner.z = min(min_corner.z, v_world.z)
            
            max_corner.x = max(max_corner.x, v_world.x)
            max_corner.y = max(max_corner.y, v_world.y)
            max_corner.z = max(max_corner.z, v_world.z)

    return min_corner, max_corner

def extend_bounding_box(bounding_box: tuple[Vector, Vector], extend_by):

    # Get corners of bounding box
    min_corner, max_corner = bounding_box
    

    # Create the extension vector
    extension_vector = Vector((extend_by, extend_by, extend_by))
    

    # Apply the extension/shrinking
    extended_min_corner = min_corner - extension_vector
    extended_max_corner = max_corner + extension_vector
    

    return extended_min_corner, extended_max_corner

def render(output_file_path: str):

    # Set Output File Location
    bpy.context.scene.render.filepath = output_file_path

    # Start Render
    bpy.ops.render.render(write_still=True)

def pixelate_image(image_path: str, param: PixelateParam, output_image_path = None):  # If output_image_path is None then will replace original image

    # if pixelate compositor does not exist then import from sprit maker blend file
    if PIXELATE_COMPOSITOR_NAME not in bpy.data.node_groups:
        
        # Get absolute path to blend file
        current_file_path = os.path.abspath(__file__)
        current_dir = os.path.dirname(current_file_path)
        blend_file_path = sibling_file_path = os.path.join(current_dir, SPRITE_SHEET_MAKER_BLEND_FILE)

        # Check if blend file exists
        if not os.path.exists(blend_file_path):
            print(f"[SpriteSheetMaker] Blend file for importing compositor not found: {blend_file_path}")
            return
        
        # Append the node tree from the external blend file
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            if PIXELATE_COMPOSITOR_NAME in data_from.node_groups:
                print(f"[SpriteSheetMaker] Importing node group '{PIXELATE_COMPOSITOR_NAME}' from '{blend_file_path}'")
                data_to.node_groups = [PIXELATE_COMPOSITOR_NAME]
            else:
                print(f"[SpriteSheetMaker] Node group '{PIXELATE_COMPOSITOR_NAME}' not found in {blend_file_path}")
                return
    

    # Get compositor & make sure it's a compositor node tree
    pixelate_tree = bpy.data.node_groups[PIXELATE_COMPOSITOR_NAME]
    if pixelate_tree.bl_idname != "CompositorNodeTree":
        print(f"[SpriteSheetMaker] '{PIXELATE_COMPOSITOR_NAME}' is not a CompositorNodeTree!")
        return
    

    # Save old values
    old_compositor = bpy.context.scene.compositing_node_group
    old_resolution_x = bpy.context.scene.render.resolution_x
    old_resolution_y = bpy.context.scene.render.resolution_y
    

    # Set pixelate compositor
    bpy.context.scene.compositing_node_group = pixelate_tree


    # Assign image which is to be pixelated
    image_node = pixelate_tree.nodes.get(IMAGE_INPUT_NODE)
    if image_node is not None:
        image = bpy.data.images.load(image_path)
        image_node.image = image


    # Assign pixelation amount
    pixel_node = pixelate_tree.nodes.get(PIXELATION_AMOUNT_NODE)
    if pixel_node is not None:
        pixel_node.outputs[0].default_value = (1.0 - param.pixelation_amount)


    # Assign shrink interpolation
    shrink_scale_node = pixelate_tree.nodes.get(SHRINK_SCALE_NODE)
    if shrink_scale_node is not None:
        shrink_scale_node.inputs[5].default_value = param.shrink_interp.value


    # Assign color amount
    color_amount_node = pixelate_tree.nodes.get(COLOR_AMOUNT_NODE)
    if color_amount_node is not None:
        color_amount_node.outputs[0].default_value = param.color_amount


    # Assign minimum alpha
    min_alpha_node = pixelate_tree.nodes.get(MIN_ALPHA_NODE)
    if min_alpha_node is not None:
        min_alpha_node.outputs[0].default_value = param.min_alpha


    # Assign alpha step
    alpha_step_node = pixelate_tree.nodes.get(ALPHA_STEP_NODE)
    if alpha_step_node is not None:
        alpha_step_node.outputs[0].default_value = param.alpha_step


    # Render image
    print(f"[SpriteSheetMaker] Rendering pixelated sprite")
    bpy.context.scene.render.resolution_x = int(old_resolution_x * (1.0 - param.pixelation_amount))  # Shrink resolution before rendering
    bpy.context.scene.render.resolution_y = int(old_resolution_y * (1.0 - param.pixelation_amount))
    render(image_path if (output_image_path is None) else output_image_path)


    # Set back old values
    bpy.context.scene.render.resolution_x = old_resolution_x 
    bpy.context.scene.render.resolution_y = old_resolution_y 
    bpy.context.scene.compositing_node_group = old_compositor if (old_compositor != pixelate_tree) else None

def create_folder(at_path, folder_name):

    # Make sure the name is safe for folder creation
    folder_name = bpy.path.clean_name(folder_name)

    # complete folder path
    folder_path = os.path.join(at_path, folder_name)

    # If folder exists, add numeric suffix
    if os.path.exists(folder_path):
        counter = 1
        while True:
            new_name = f"{folder_name}_{counter}"
            new_path = os.path.join(at_path, new_name)
            if not os.path.exists(new_path):
                folder_path = new_path
                break
            counter += 1

    # Create folder
    os.makedirs(folder_path)

    return folder_path

def hide_visible_objects(ignore_objects = set()):
    hidden_objects = set()

    # Iterate through all visible objects and hide whichever aren't to be ignored
    visible_objects = set(obj for obj in bpy.context.view_layer.objects if obj.visible_get())
    for obj in visible_objects:
        if obj in ignore_objects:
            continue

        obj.hide_render = True
        obj.hide_viewport = True
        hidden_objects.add(obj)
    
    return hidden_objects

def unhide_objects(objects):
    for obj in objects:
        obj.hide_render = False
        obj.hide_viewport = False

class SpriteSheetMaker():
    def __init__(self):
        self.on_sprite_creating = Event()  # param
        self.on_sprite_created = Event()   # param
        self.on_sheet_row_creating = Event()  # action_name, total_frames
        self.on_sheet_row_created = Event()  # action_name, total_frames
        self.on_sheet_frame_creating = Event()  # action_name, frame
        self.on_sheet_frame_created = Event()   # action_name, frame
    
    def create_sprite(self, param: SpriteParam, hide_other_objects = True, delete_camera = True):

        self.on_sprite_creating.broadcast(param)


        # Store old resolutions
        old_resolution_x = bpy.context.scene.render.resolution_x
        old_resolution_y = bpy.context.scene.render.resolution_y


        # Hide all other objects which are not part of sprite
        hidden_objects = set()
        if(hide_other_objects):
            print(f"[SpriteSheetMaker] Hiding all objects except {param.objects}")
            hidden_objects = hide_visible_objects(param.objects)


        # Setup camera according to bounding box & other parameters
        print(f"[SpriteSheetMaker] Setting up camera to capture all objects")
        camera = param.camera
        if camera is None:
            bbox = get_bounding_box(param.objects, not param.consider_armature_bones)
            bbox = extend_bounding_box(bbox, param.camera_padding)
            camera = setup_camera(bbox, param.camera_direction, param.pixels_per_meter)


        # Make sure camera is being used to render
        bpy.context.scene.camera = camera

        
        # Render image to folder
        print(f"[SpriteSheetMaker] Rendering sprite")
        render(param.output_file_path)

        
        # Pixelate Rendered image
        if param.to_pixelate:
            print(f"[SpriteSheetMaker] Pixelating sprite")
            pixelate_image(param.output_file_path, param.pixelate_param)


        # Unhide previously hidden objects
        if(hide_other_objects):
            print(f"[SpriteSheetMaker] Unhiding the following objects {hidden_objects}")
            unhide_objects(hidden_objects)
        

        # Delete camera after render
        if(delete_camera):
            cam_obj = bpy.data.objects.get(CAMERA_NAME)
            if cam_obj is not None:
                bpy.data.objects.remove(cam_obj, do_unlink=True) 
        

        # Reset old resolutions 
        bpy.context.scene.render.resolution_x = old_resolution_x 
        bpy.context.scene.render.resolution_y = old_resolution_y


        self.on_sprite_created.broadcast(param)
        
    def create_sprite_sheet(self, param: SpriteParam, output_folder_path: str):
        # Create folder
        print(f"[SpriteSheetMaker] Creating temp folder '{TEMP_FOLDER_NAME}'")
        temp_dir = create_folder(output_folder_path, TEMP_FOLDER_NAME)


        # Store original sheet path
        sprite_sheet_path = param.output_file_path


        # Hide all other objects which are not part of sheet
        hidden_objects = hide_visible_objects(param.objects)
        print(f"[SpriteSheetMaker] Following objects were hidden {hidden_objects}")


        # Iterate through actions and capture render for each frame (Each action should have it's own folder (in order) & image names should be 1, 2, 3 for each frame respectively)
        for i, action in enumerate(param.actions):

            # Create folder for action & Notify
            folder_name = f"{i}_{action.name}"
            print(f"[SpriteSheetMaker] Creating folder {folder_name}")
            action_dir = create_folder(temp_dir, folder_name)
            self.on_sheet_row_creating.broadcast(action.name, int(action.frame_range[1]))


            # Assign action to all objects
            for obj in bpy.data.objects:
                if obj.animation_data is None:
                    continue
                
                # Assign action
                anim_data = obj.animation_data
                anim_data.action = action

                # Assign slot
                suitable = anim_data.action_suitable_slots
                if suitable:
                    anim_data.action_slot = suitable[0] if suitable else action.slots[0]  # fallback: pick first slot


            # Iterate through all frames
            frame_start, frame_end = int(action.frame_range[0]), int(action.frame_range[1])
            for frame in range(frame_start, frame_end + 1):

                # Notify starting
                self.on_sheet_frame_creating.broadcast(action.name, frame)
                print(f"[SpriteSheetMaker] Capturing action '{action.name}' at frame {frame}")

                # Set frame
                bpy.context.scene.frame_set(frame)

                # Render a single sprite
                param.output_file_path = f"{action_dir}/{frame}.png"
                self.create_sprite(param, False, False)

                # Notify frame completed
                self.on_sheet_frame_created.broadcast(action.name, frame)
            
            
            # Notify action completed
            self.on_sheet_row_created.broadcast(action.name, int(action.frame_range[1]))


        # Unhide previously hidden objects
        unhide_objects(hidden_objects)


        # Combine images together into single file and paste in output
        from .combine_frames import assemble_sprite_sheet
        assemble_sprite_sheet(temp_dir, sprite_sheet_path, param.label_font_size, param.frame_margin)


        # Delete temp folder
        if param.delete_temp_folder:
            shutil.rmtree(temp_dir)


        # Delete camera after use
        cam_obj = bpy.data.objects.get(CAMERA_NAME)
        if cam_obj is not None:
            bpy.data.objects.remove(cam_obj, do_unlink=True) 


        return sprite_sheet_path