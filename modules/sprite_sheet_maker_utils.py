import bpy
import os
import shutil
import weakref
import traceback
import math
from datetime import datetime
from mathutils import Vector
from enum import Enum
from .combine_frames import AssembleParam, assemble_images, create_folder, unique_path


TEMP_FOLDER_NAME = "SpriteSheetMakerTemp"
CAMERA_NAME = "SpriteSheetMakerCamera"
PIXELATE_SCENE_NAME = "SpriteSheetMakerPixelateScene"
SPRITE_SHEET_MAKER_BLEND_FILE = "../blend_files/SpriteSheetMaker.blend"
IMAGE_INPUT_NODE = "ImageInput"
PIXELATION_AMOUNT_NODE = "PixelationAmount"
COLOR_AMOUNT_NODE = "ColorAmount"
MIN_ALPHA_NODE = "MinAlpha"
ALPHA_STEP_NODE = "AlphaStep"
UNTITLED_FOLDER_NAME = "Untitled"


# Enums
class CameraDirection(Enum):
    X = "x"
    Y = "y"
    Z = "z"
    NEG_X = "-x"
    NEG_Y = "-y"
    NEG_Z = "-z"


# Classes
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

class AutoCaptureParam:
    def __init__(self):
        self.objects:set = set({})
        self.consider_armature_bones:bool = False
        self.camera_direction:CameraDirection = CameraDirection.NEG_X
        self.pixels_per_meter:float = 500.0
        self.camera_padding:float = 0.05

class PixelateParam:
    def __init__(self):
        self.pixelation_amount:float = 0.9
        self.color_amount:float = 50.0
        self.min_alpha:float = 0.0
        self.alpha_step:float = 0.25  # Ensures alpha of color is rounded down to the nearest multiple of "step" (helps reducing gradients)

class SpriteParam:
    def __init__(self):
        self.output_file_path:str = ""
        self.camera = None
        self.to_auto_capture = False
        self.auto_capture_param = AutoCaptureParam()
        self.to_pixelate:bool = False
        self.pixelate_param:PixelateParam = PixelateParam()

class StripParam:
    def __init__(self):
        self.label:str = ""
        self.capture_items = []  # [(Object, Action, Slot), ... ]
        self.manual_frames:bool = False
        self.frame_start:int = 0
        self.frame_end:int = 250

class SpriteSheetParam:
    def __init__(self):
        self.animation_strips:list[StripParam] = [] 
        self.delete_temp_folder:bool = True
        self.sprite_param :SpriteParam = SpriteParam()
        self.assemble_param:AssembleParam = AssembleParam()


# Methods
def get_bounding_box(objects, ignore_armatures = True):

    # Return if no objects
    if(len(objects) == 0):
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    

    # Iterate through all objects and get min/max corners
    min_corner = Vector((float('inf'), float('inf'), float('inf')))
    max_corner = Vector((float('-inf'), float('-inf'), float('-inf')))
    for obj in objects:

        # Skip armature
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


    # Safe guard against infinite values
    if(any(math.isinf(v) for v in min_corner) or any(math.isinf(v) for v in max_corner)):
        min_corner = Vector((0, 0, 0))
        max_corner = Vector((0, 0, 0))


    return min_corner, max_corner

def extend_bounding_box(bounding_box:tuple[Vector, Vector], extend_by):

    # Get corners of bounding box
    min_corner, max_corner = bounding_box
    

    # Create the extension vector
    extension_vector = Vector((extend_by, extend_by, extend_by))
    

    # Apply the extension/shrinking
    extended_min_corner = min_corner - extension_vector
    extended_max_corner = max_corner + extension_vector
    

    return extended_min_corner, extended_max_corner

def setup_auto_camera(param:AutoCaptureParam, existing_camera = None):

    # Get & extend bounding box
    bbox = get_bounding_box(param.objects, not param.consider_armature_bones)
    bbox_extended = extend_bounding_box(bbox, param.camera_padding)


    # Split bounding box into min & max vertices
    min_v, max_v = bbox_extended


    # Calculate camera properties based on direction
    direction = param.camera_direction
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


    # Get existing camera if camera not given
    cam_obj = existing_camera
    if cam_obj is None:
        cam_obj = bpy.data.objects.get(CAMERA_NAME)
    

    # If no existing camera found then create one
    if cam_obj is None:
        cam_data = bpy.data.cameras.new(name=CAMERA_NAME)
        cam_obj = bpy.data.objects.new(CAMERA_NAME, cam_data)
        bpy.context.collection.objects.link(cam_obj)


    # Get camera data
    cam_data = cam_obj.data


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
    unit_scale = bpy.context.scene.unit_settings.scale_length
    res_x = int(width * param.pixels_per_meter * unit_scale) 
    res_y = int(height * param.pixels_per_meter * unit_scale)
    bpy.context.scene.render.resolution_x = res_x
    bpy.context.scene.render.resolution_y = res_y
    bpy.context.scene.render.resolution_percentage = 100 # Ensuring complete resolution

    return cam_obj

def delete_auto_camera():
    cam_obj = bpy.data.objects.get(CAMERA_NAME)
    if cam_obj is not None:
        bpy.data.objects.remove(cam_obj, do_unlink=True) 

def render(output_file_path:str):

    # Set Output File Location
    bpy.context.scene.render.filepath = os.path.normpath(output_file_path)


    # Start Render
    bpy.ops.render.render(write_still=True)

def pixelate_images(image_paths:dict[str, str], param:PixelateParam):  # images = { "input/path/to/image.png" : "output/path/to/images.png" }
    
    # Get pixelate scene
    pixelate_scene = bpy.data.scenes.get(PIXELATE_SCENE_NAME)


    # If pixelate scene does not exist then import from blender file
    if not pixelate_scene:

        # Check if blend file exists
        current_dir = os.path.dirname(os.path.abspath(__file__))
        blend_file_path = os.path.join(current_dir, SPRITE_SHEET_MAKER_BLEND_FILE)
        if not os.path.exists(blend_file_path):
            raise Exception(f"[SpriteSheetMaker {datetime.now()}] Blend file for importing pixelate scene not found: {blend_file_path}")
            return


        # Import pixelate scene
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            if PIXELATE_SCENE_NAME in data_from.scenes:  # If scene found
                print(f"[SpriteSheetMaker {datetime.now()}] Importing scene '{PIXELATE_SCENE_NAME}' from '{blend_file_path}'")
                data_to.scenes = [PIXELATE_SCENE_NAME]
            else:  # If scene not found
                raise Exception(f"[SpriteSheetMaker {datetime.now()}] scene '{PIXELATE_SCENE_NAME}' not found in {blend_file_path}")
                return


        # return If still no pixelate scene exists 
        pixelate_scene = data_to.scenes[0]
        if not pixelate_scene:
            raise Exception(f"[SpriteSheetMaker {datetime.now()}] scene '{PIXELATE_SCENE_NAME}' is invalid!")
            return
    
    
    # Save old scene
    original_scene = bpy.context.scene


    # Set pixelate scene as active
    bpy.context.window.scene = pixelate_scene
    pixelate_scene.use_nodes = True


    # Intentionally kept inside try so that temp scene is deleted even incase of failure
    exception = None
    try:
        # Remove and existing nodes from compositor
        tree = pixelate_scene.node_tree
       

        # Assign pixelation amount
        pixel_node = tree.nodes.get(PIXELATION_AMOUNT_NODE)
        if pixel_node is not None:
            pixel_node.outputs[0].default_value = (1.0 - param.pixelation_amount)


        # Assign color amount
        color_amount_node = tree.nodes.get(COLOR_AMOUNT_NODE)
        if color_amount_node is not None:
            color_amount_node.outputs[0].default_value = param.color_amount


        # Assign minimum alpha
        min_alpha_node = tree.nodes.get(MIN_ALPHA_NODE)
        if min_alpha_node is not None:
            min_alpha_node.outputs[0].default_value = param.min_alpha


        # Assign alpha step
        alpha_step_node = tree.nodes.get(ALPHA_STEP_NODE)
        if alpha_step_node is not None:
            alpha_step_node.outputs[0].default_value = param.alpha_step


        # Get image input node
        image_node = tree.nodes.get(IMAGE_INPUT_NODE)
        if image_node is None:
            raise Exception(f"[SpriteSheetMaker {datetime.now()}] Failed to find '{IMAGE_INPUT_NODE}' node")


        # Iterate through all images & render pixelated version
        for input_path in image_paths:
            print(f"[SpriteSheetMaker {datetime.now()}] Pixelating '{input_path}'")

            # Skip if image not found
            image = bpy.data.images.load(input_path)
            if image is None:
                print(f"[SpriteSheetMaker {datetime.now()}] Failed to load image '{input_path}'")
                continue

            # Assign image to pixelate
            image_node.image = image
            
            # Assign Render settings
            width, height = image.size
            pixelate_scene.render.resolution_x = int(width * (1.0 - param.pixelation_amount))
            pixelate_scene.render.resolution_y = int(height * (1.0 - param.pixelation_amount))

            # Assign output path
            output_path = image_paths[input_path]
            output_path = output_path if (output_path != "" and output_path != None) else input_path
            pixelate_scene.render.filepath = output_path  # Override existing if no output path is given
            
            # Render pixelated version
            print(f"[SpriteSheetMaker {datetime.now()}] Rendering pixelated sprite")
            bpy.ops.render.render(scene=pixelate_scene.name, write_still=True)

            # Unload image from memory
            bpy.data.images.remove(image)

            print(f"[SpriteSheetMaker {datetime.now()}] Pixelated to '{output_path}'")

    except Exception as e:
        exception = e
        print(f"[SpriteSheetMaker {datetime.now()}] Failed to pixelate image: {e} \n {traceback.format_exc()}")


    # Set back old values
    bpy.context.window.scene = original_scene
    bpy.data.scenes.remove(pixelate_scene)


    # Throw exception incase of failure
    if(exception != None):
        raise exception

class SpriteSheetMaker():
    def __init__(self):
        self.on_sprite_creating = Event()  # param
        self.on_sprite_created = Event()   # param
        self.on_sheet_row_creating = Event()  # strip_label, total_frames
        self.on_sheet_row_created = Event()  # strip_label, total_frames
        self.on_sheet_frame_creating = Event()  # strip_label, frame
        self.on_sheet_frame_created = Event()   # strip_label, frame
    
    def create_sprite(self, param:SpriteParam):

        self.on_sprite_creating.broadcast(param)


        # Store old resolutions, Incase of pixelation
        old_resolution_x = bpy.context.scene.render.resolution_x
        old_resolution_y = bpy.context.scene.render.resolution_y


        # Setup camera according to bounding box & other parameters
        print(f"[SpriteSheetMaker {datetime.now()}] Setting up camera to capture all objects")
        camera = param.camera
        if param.to_auto_capture:
            camera = setup_auto_camera(param.auto_capture_param, param.camera)


        # Make sure camera is being used to render
        bpy.context.scene.camera = camera

        
        # Render image to folder
        print(f"[SpriteSheetMaker {datetime.now()}] Rendering sprite")
        render(param.output_file_path)

        
        # Pixelate Rendered image
        if param.to_pixelate:
            pixelate_images({ param.output_file_path : param.output_file_path }, param.pixelate_param)


        # Delete camera after render
        if(param.to_auto_capture and param.camera is None):
            delete_auto_camera()
        

        # Reset old resolutions 
        bpy.context.scene.render.resolution_x = old_resolution_x 
        bpy.context.scene.render.resolution_y = old_resolution_y


        self.on_sprite_created.broadcast(param)
    
    def create_sprite_sheet(self, param:SpriteSheetParam):
        
        # Create temp folder
        print(f"[SpriteSheetMaker {datetime.now()}] Creating temp folder '{TEMP_FOLDER_NAME}'")
        temp_dir = create_folder(os.path.dirname(param.assemble_param.output_path), TEMP_FOLDER_NAME)


        # Store to pixelate
        to_pixelate = param.sprite_param.to_pixelate
        param.sprite_param.to_pixelate = False


        # Create camera
        if(param.sprite_param.camera is None):
            param.sprite_param.camera = setup_auto_camera(param.sprite_param.auto_capture_param, param.sprite_param.camera)


        # Iterate through actions and capture render for each frame (Each action should have it's own folder (in order) & image names should be 1, 2, 3 for each frame respectively)
        pixelate_dict:dict[str, str] = {}
        for i, strip in enumerate(param.animation_strips):

            # Calculate frame range
            frame_start = float('inf')
            frame_end = float('-inf')
            if(strip.manual_frames):
                frame_start = strip.frame_start
                frame_end = strip.frame_end
            else:
                for item in strip.capture_items:
                    obj, action, slot = item
                    if(action != None):
                        frame_start = min(frame_start, action.frame_range[0])
                        frame_end = max(frame_end, action.frame_range[1])


            # Convert to int and make sure they are never infinity
            frame_start = 0 if math.isinf(frame_start) else int(frame_start)
            frame_end = 0 if math.isinf(frame_end) else int(frame_end)


            # Create folder for this strip
            clean_label = bpy.path.clean_name(strip.label.strip())
            folder_name = f"{i}_{clean_label if clean_label !='' else UNTITLED_FOLDER_NAME}"
            print(f"[SpriteSheetMaker {datetime.now()}] Creating folder {folder_name}")
            action_dir = create_folder(temp_dir, folder_name)
            self.on_sheet_row_creating.broadcast(strip.label, frame_end)


            # Assign action to all objects
            for (obj, action, slot) in strip.capture_items:

                # Skip if object is invalid
                if obj == None:
                    continue
                
                # Skip if object doesn't have animation data
                if not hasattr(obj, "animation_data"):
                    continue
                
                # Skip if object doesn't have action
                if not hasattr(obj.animation_data, "action"):
                    continue
                
                # Assign action
                obj.animation_data.action = action
                
                # Skip if no slot
                if not hasattr(obj.animation_data, "action_slot"):
                    continue
                
                # Assign user provided slot
                slot_name = f"OB{slot}"
                if slot != "" and action != None and (slot_name in action.slots):
                    obj.animation_data.action_slot = action.slots[slot_name]

                # Assign default slot
                elif hasattr(obj.animation_data, "action_suitable_slots") and len(obj.animation_data.action_suitable_slots) > 0:
                    obj.animation_data.action_slot = obj.animation_data.action_suitable_slots[0]


            # Iterate through all frames
            for frame in range(frame_start, frame_end + 1):

                # Notify starting
                self.on_sheet_frame_creating.broadcast(strip.label, frame)
                print(f"[SpriteSheetMaker {datetime.now()}] Capturing strip '{strip.label}' at frame {frame}")

                # Set frame
                bpy.context.scene.frame_set(frame)

                # Render a single sprite
                param.sprite_param.output_file_path = f"{action_dir}/{frame}.{bpy.context.scene.render.image_settings.file_format.lower()}"
                self.create_sprite(param.sprite_param)
                pixelate_dict[param.sprite_param.output_file_path] = None

                # Notify frame completed
                self.on_sheet_frame_created.broadcast(strip.label, frame)
            
            
            # Notify action completed
            self.on_sheet_row_created.broadcast(strip.label, frame_end)


        # pixelate all images if required
        if(to_pixelate):
            pixelate_images(pixelate_dict, param.sprite_param.pixelate_param)

        
        # Combine images together into single file and paste in output
        param.assemble_param.input_folder_path = temp_dir
        assemble_images(param.assemble_param)


        # Delete temp folder
        if param.delete_temp_folder:
            shutil.rmtree(temp_dir)


        # Delete camera after use
        delete_auto_camera()


        return True