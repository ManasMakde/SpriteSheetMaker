import bpy
import os
import shutil
import weakref
import traceback
import math
from datetime import datetime
import mathutils
from mathutils import Vector, Matrix
from enum import Enum
from .combine_frames import AssembleParam, assemble_images, create_folder
from .logging import *


TEMP_FOLDER_NAME = "SpriteSheetMakerTemp"
AUTO_CAMERA_NAME = "AutoSpriteSheetMakerCamera"
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
    CUSTOM = "custom"


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
        
        self.camera_direction:CameraDirection = CameraDirection.NEG_X
        self.camera_orbit_z:float = 0.0
        self.camera_orbit_x:float = 0.0
        self.camera_roll:float = 0.0

        self.h_center_object = None
        self.h_center_bone:str = ""
        self.v_center_object = None
        self.v_center_bone:str = ""

        self.consider_armature_bones:bool = False
        self.camera_padding_h:float = 0.0
        self.camera_padding_v:float = 0.0
        self.pixels_per_meter:float = 500.0
class PixelateParam:
    def __init__(self):
        self.pixelation_amount:float = 0.9
        self.color_amount:float = 50.0
        self.min_alpha:float = 0.0
        self.alpha_step:float = 0.25  # Ensures alpha of color is rounded down to the nearest multiple of "step" (helps reducing gradients)
class StripParam:
    def __init__(self):
        self.label:str = ""
        self.capture_items = []  # [(Object, Action, Slot), ... ]
        
        self.custom_camera = None
        self.to_auto_capture = False
        self.auto_capture_param = AutoCaptureParam()
        
        self.to_pixelate:bool = False
        self.pixelate_param:PixelateParam = PixelateParam()
        
        self.manual_frames:bool = False
        self.frame_start:int = 0
        self.frame_end:int = 250
class SpriteSheetParam:
    def __init__(self):
        self.animation_strips:list[StripParam] = []
        self.assemble_param:AssembleParam = AssembleParam()
        self.delete_temp_folder:bool = True


# Visualize Methods
def create_sphere(location, radius=0.05, segments=32, ring_count=16, color=(1.0, 1.0, 1.0, 1.0)):

    # Create the UV Sphere mesh geometry
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=radius,
        location=location,
        segments=segments,
        ring_count=ring_count
    )
    
    # Get a reference to the newly created sphere object
    sphere_obj = bpy.context.active_object
    
    # Create a new material for the color
    mat = bpy.data.materials.new(name="Sphere_Material")
    mat.use_nodes = True
    
    # Get the Principled BSDF node to set the color
    nodes = mat.node_tree.nodes
    principled_node = nodes.get("Principled BSDF")
    
    # Set the base color input value if the node exists
    if principled_node:
        principled_node.inputs[0].default_value = color
        
    # Append the material to the object material slots
    if len(sphere_obj.data.materials) == 0:
        sphere_obj.data.materials.append(mat)
    else:
        sphere_obj.data.materials[0] = mat
        
    return sphere_obj


# Auto Camera Methods
def calc_target_loc(target_obj, target_bone:str):

    # If not armature
    if(target_obj.type != 'ARMATURE'):
        return target_obj.location


    # If armature has bone
    pose_bone = target_obj.pose.bones.get(target_bone)
    if pose_bone:
        return pose_bone.head
    

    # If no bone
    return target_obj.location
def calc_orientation_vectors(rotations):

    # Extract all rotations
    (orbit_z, orbit_x, roll) = rotations


    # Given a direction vector (default: facing along positive y axis), a top vector (default: facing along positive z axis) & right vector (default: facing along positive x axis) apply given orbit_z, orbit_x & roll and create all 3 new 3D vectors
    rot_matrix = Matrix.Rotation(orbit_z, 4, 'Z') @ Matrix.Rotation(orbit_x, 4, 'X') @ Matrix.Rotation(roll, 4, 'Y')
    direction = (rot_matrix @ Vector((0, 1, 0, 0))).to_3d().normalized()
    right = (rot_matrix @ Vector((1, 0, 0, 0))).to_3d().normalized()
    up = (rot_matrix @ Vector((0, 0, 1, 0))).to_3d().normalized()

    return rot_matrix, direction, right, up 
def calc_bounding_points(objects, to_consider_armatures = False):

    bbox_corners = []
    for obj in objects:

        # Skip armatures
        if(not obj or (not to_consider_armatures and obj.type == 'ARMATURE')):
            continue

        mat = obj.matrix_world
        corners = [Vector(corner) for corner in obj.bound_box]
        world_corners = [mat @ corner for corner in corners]
        bbox_corners += world_corners
        
    return bbox_corners
def ideal_persp_sensor_fit(camera, bounding_points, param: AutoCaptureParam):
    
    # Return if sensor fit is already 'HORIZONTAL' or 'VERTICAL' 
    if(camera.data.sensor_fit != 'AUTO'):
        log("Warning: camera.data.sensor_fit is not 'AUTO'. Returning early.")
        return camera.data.sensor_fit
    


    # Get all orientation vectors
    _, direction, right, up = calc_orientation_vectors((param.camera_orbit_z, param.camera_orbit_x, param.camera_roll))
    
    # Calculate an angle gamma = camera FOV using focal length of camera & sensor width
    focal_length = camera.data.lens
    sensor_width = camera.data.sensor_width
    gamma = 2 * math.atan(sensor_width / (2 * focal_length))



    ### HORIZONTAL CHECK
    # Convert all points using up and right vector into 2D points such that they appear to be "top view"
    top_points_2d = [Vector((p.dot(right), p.dot(direction))) for p in bounding_points]

    ## If h_center_object not given:
    if param.h_center_object is None:

        # Find two points whose gamma/2 directional projection lines create a horizontal FOV that encompasses all other points
        half_alpha = gamma / 2
        cos_h = math.cos(half_alpha)
        sin_h = math.sin(half_alpha)
        tan_h = sin_h / cos_h
        p_r = max(top_points_2d, key=lambda p: p.x * cos_h - p.y * sin_h)
        p_l = max(top_points_2d, key=lambda p: -p.x * cos_h - p.y * sin_h)
        s_r =  p_r.x * cos_h - p_r.y * sin_h
        s_l = -p_l.x * cos_h - p_l.y * sin_h

        # Find the intersection point (I_h) of those 2 projection lines
        ih_x = (s_r - s_l) / (2 * cos_h)
        ih_y = -(s_r + s_l) / (2 * sin_h)
        I_h = Vector((ih_x, ih_y))

    ## If h_center_object is given:
    else:

        # Find a point whose gamma/2 directional projection line & the mirror image of that line both encompasses all other points
        th_loc = calc_target_loc(param.h_center_object, param.h_center_bone)
        th_2d = Vector((th_loc.dot(right), th_loc.dot(direction)))
        half_alpha = gamma / 2
        sin_h = math.sin(half_alpha)
        tan_h = math.tan(half_alpha)

        # Find the intersection point (I_h) of those 2 projection lines
        ih_x = th_2d.x
        ih_y = min(p.y - abs(p.x - ih_x) / tan_h for p in top_points_2d)
        I_h = Vector((ih_x, ih_y))

    # Move back camera such that capture_width is increased by padding_h/2 on both sides
    h_padding_delta = param.camera_padding_h / (2 * tan_h)
    I_h = Vector((I_h.x, I_h.y - h_padding_delta))

    # Calculate width spanned by FOV cone at furthest_h_dist
    furthest_h_dist = max(p.y - I_h.y for p in top_points_2d)
    capture_width = (2 * furthest_h_dist * tan_h)



    ### VERTICAL CHECK
    # Convert all points using up and direction vector into 2D points such that they appear to be "side view"
    side_points_2d = [Vector((p.dot(up), p.dot(direction))) for p in bounding_points]

    ## If v_center_object not given:
    if param.v_center_object is None:

        # Find two points whose gamma/2 directional projection lines create a vertical FOV that encompasses all other points
        half_beta = gamma / 2
        cos_v = math.cos(half_beta)
        sin_v = math.sin(half_beta)
        tan_v = sin_v / cos_v
        p_u = max(side_points_2d, key=lambda p: p.x * cos_v - p.y * sin_v)
        p_d = max(side_points_2d, key=lambda p: -p.x * cos_v - p.y * sin_v)
        s_u =  p_u.x * cos_v - p_u.y * sin_v
        s_d = -p_d.x * cos_v - p_d.y * sin_v

        # Find the intersection point (I_v) of those 2 projection lines
        iv_x = (s_u - s_d) / (2 * cos_v)
        iv_y = -(s_u + s_d) / (2 * sin_v)
        I_v = Vector((iv_x, iv_y))

    ## If v_center_object is given:
    else:

        # Find a point whose gamma/2 directional projection line & the mirror image of that line both encompasses all other points
        tv_loc = calc_target_loc(param.v_center_object, param.v_center_bone)
        tv_2d = Vector((tv_loc.dot(up), tv_loc.dot(direction)))
        half_beta = gamma / 2
        sin_v = math.sin(half_beta)
        tan_v = math.tan(half_beta)

        # Find the intersection point (I_v) of those 2 projection lines
        iv_x = tv_2d.x
        iv_y = min(p.y - abs(p.x - iv_x) / tan_v for p in side_points_2d)
        I_v = Vector((iv_x, iv_y))

    # Move back camera such that capture_height is increased by padding_v/2 on both sides
    v_padding_delta = param.camera_padding_v / (2 * tan_v)
    I_v = Vector((I_v.x, I_v.y - v_padding_delta))

    # Calculate height spanned by FOV cone at furthest_v_dist
    furthest_v_dist = max(p.y - I_v.y for p in side_points_2d)
    capture_height = (2 * furthest_v_dist * tan_v)



    # Resolve based on height & width
    return 'HORIZONTAL' if capture_width > capture_height else 'VERTICAL'
def persp_cam_horizontal_fit(camera, bounding_points, param: AutoCaptureParam):

    # Convert all points using up and right vector into 2D points such that they appear to be "top view"
    rot_matrix, direction, right, up = calc_orientation_vectors((param.camera_orbit_z, param.camera_orbit_x, param.camera_roll))


    # Calculate an angle alpha = camera horizontal FOV using focal length of camera & sensor width
    focal_length = camera.data.lens
    sensor_width = camera.data.sensor_width
    alpha = 2 * math.atan(sensor_width / (2 * focal_length))


    # Convert all points using up and right vector into 2D points such that they appear to be "top view"
    top_points_2d = [Vector((p.dot(right), p.dot(direction))) for p in bounding_points]


    ## If h_center_object not given:
    if param.h_center_object is None:

        # Find two points whose alpha/2 directional projection lines create a horizontal FOV that encompasses all other points
        half_alpha = alpha / 2
        cos_h = math.cos(half_alpha)
        sin_h = math.sin(half_alpha)
        tan_h = sin_h / cos_h
        p_r = max(top_points_2d, key=lambda p: p.x * cos_h - p.y * sin_h)
        p_l = max(top_points_2d, key=lambda p: -p.x * cos_h - p.y * sin_h)
        s_r =  p_r.x * cos_h - p_r.y * sin_h
        s_l = -p_l.x * cos_h - p_l.y * sin_h

        # Find the intersection point (I_h) of those 2 projection lines
        ih_x = (s_r - s_l) / (2 * cos_h)
        ih_y = -(s_r + s_l) / (2 * sin_h)
        I_h = Vector((ih_x, ih_y))

    ## If h_center_object is given:
    else:

        # Find a point whose alpha/2 directional projection line & the mirror image of that line both encompasses all other points
        th_loc = calc_target_loc(param.h_center_object, param.h_center_bone)
        th_2d = Vector((th_loc.dot(right), th_loc.dot(direction)))
        half_alpha = alpha / 2
        sin_h = math.sin(half_alpha)
        tan_h = math.tan(half_alpha)

        # Find the intersection point (I_h) of those 2 projection lines
        ih_x = th_2d.x
        ih_y = min(p.y - abs(p.x - ih_x) / tan_h for p in top_points_2d)
        I_h = Vector((ih_x, ih_y))


    # Move back camera such that capture_width is increased by padding_h/2 on both sides
    h_padding_delta = param.camera_padding_h / (2 * tan_h)
    I_h = Vector((I_h.x, I_h.y - h_padding_delta))


    # Calculate width spanned by FOV cone at furthest_h_dist
    furthest_h_dist = max(p.y - I_h.y for p in top_points_2d)
    capture_width = (2 * furthest_h_dist * tan_h)


    # Convert all points into 2D points such that they appear to be "side view"
    side_points_2d = [Vector((p.dot(up), p.dot(direction))) for p in bounding_points]


    ## If v_center_object not given:
    if param.v_center_object is None:

        # Assume a vertical line passing through I_h tangential to direction vector, Find a point (I_v) on that line whose FOV encompasses all side_points_2d
        up_vals = [p.x for p in side_points_2d]
        lo, hi = min(up_vals), max(up_vals)
        for _ in range(64):
            mid = (lo + hi) / 2
            angs = [math.atan2(p.x - mid, p.y - I_h.y) for p in side_points_2d]
            if max(angs) + min(angs) > 0:
                lo = mid
            else:
                hi = mid
        iv_x = (lo + hi) / 2
        I_v = Vector((iv_x, I_h.y))

    ## If v_center_object is given:
    else:

        # Assume a vertical line passing through I_h tangential to direction vector and another tangential target line, Find the intersection point (I_v) of both lines 
        tv_loc = calc_target_loc(param.v_center_object, param.v_center_bone)
        tv_2d = Vector((tv_loc.dot(up), tv_loc.dot(direction)))
        I_v = Vector((tv_2d.x, I_h.y))
    

    # Calculate height spanned by vertical FOV cone at furthest_h_dist
    half_beta = max(math.atan2(abs(p.x - I_v.x) + param.camera_padding_v / 2, p.y - I_v.y) for p in side_points_2d)
    capture_height = 2 * furthest_h_dist * math.tan(half_beta)


    # Assign resolution x & resolution y 
    resolution_x = math.ceil(capture_width * param.pixels_per_meter)
    resolution_y = math.ceil(resolution_x * capture_height / capture_width)
    bpy.context.scene.render.resolution_x = resolution_x
    bpy.context.scene.render.resolution_y = resolution_y


    # Assign camera rotation
    cam_correction = Matrix.Rotation(math.radians(90), 4, 'X')
    camera.rotation_euler = (rot_matrix @ cam_correction).to_euler('XYZ')


    # Assign camera location
    camera.location = I_h.x * right + I_h.y * direction + I_v.x * up
def persp_cam_vertical_fit(camera, bounding_points, param: AutoCaptureParam, use_width:bool = False):

    # Convert all points using up and right vector into 2D points such that they appear to be "top view"
    rot_matrix, direction, right, up = calc_orientation_vectors((param.camera_orbit_z, param.camera_orbit_x, param.camera_roll))
    

    # Calculate an angle beta = camera vertical FOV using focal length of camera & sensor height
    focal_length = camera.data.lens
    sensor_height = camera.data.sensor_width if use_width else camera.data.sensor_height
    beta = 2 * math.atan(sensor_height / (2 * focal_length))


    # Convert all points using up and direction vector into 2D points such that they appear to be "side view"
    side_points_2d = [Vector((p.dot(up), p.dot(direction))) for p in bounding_points]


    ## If v_center_object not given:
    if param.v_center_object is None:

        # Find two points whose beta/2 directional projection lines create a vertical FOV that encompasses all other points
        half_beta = beta / 2
        cos_v = math.cos(half_beta)
        sin_v = math.sin(half_beta)
        tan_v = sin_v / cos_v
        p_u = max(side_points_2d, key=lambda p: p.x * cos_v - p.y * sin_v)
        p_d = max(side_points_2d, key=lambda p: -p.x * cos_v - p.y * sin_v)
        s_u =  p_u.x * cos_v - p_u.y * sin_v
        s_d = -p_d.x * cos_v - p_d.y * sin_v

        # Find the intersection point (I_v) of those 2 projection lines
        iv_x = (s_u - s_d) / (2 * cos_v)
        iv_y = -(s_u + s_d) / (2 * sin_v)
        I_v = Vector((iv_x, iv_y))

    ## If v_center_object is given:
    else:

        # Find a point whose beta/2 directional projection line & the mirror image of that line both encompasses all other points
        tv_loc = calc_target_loc(param.v_center_object, param.v_center_bone)
        tv_2d = Vector((tv_loc.dot(up), tv_loc.dot(direction)))
        half_beta = beta / 2
        sin_v = math.sin(half_beta)
        tan_v = math.tan(half_beta)

        # Find the intersection point (I_v) of those 2 projection lines
        iv_x = tv_2d.x
        iv_y = min(p.y - abs(p.x - iv_x) / tan_v for p in side_points_2d)
        I_v = Vector((iv_x, iv_y))


    # Move back camera such that capture_height is increased by padding_v/2 on both sides
    v_padding_delta = param.camera_padding_v / (2 * tan_v)
    I_v = Vector((I_v.x, I_v.y - v_padding_delta))


    # Calculate height spanned by FOV cone at furthest_v_dist
    furthest_v_dist = max(p.y - I_v.y for p in side_points_2d)
    capture_height = (2 * furthest_v_dist * tan_v)


    # Convert all points into 2D points such that they appear to be "top view"
    top_points_2d = [Vector((p.dot(right), p.dot(direction))) for p in bounding_points]


    ## If h_center_object not given:
    if param.h_center_object is None:

        # Assume a horizontal line passing through I_v tangential to direction vector, Find a point (I_h) on that line whose FOV encompasses all top_points_2d
        iv_y_ref = I_v.y
        right_vals = [p.x for p in top_points_2d]
        lo, hi = min(right_vals), max(right_vals)
        for _ in range(64):
            mid = (lo + hi) / 2
            angs = [math.atan2(p.x - mid, p.y - iv_y_ref) for p in top_points_2d]
            if max(angs) + min(angs) > 0:
                lo = mid
            else:
                hi = mid
        ih_x = (lo + hi) / 2
        I_h = Vector((ih_x, I_v.y))

    ## If h_center_object is given:
    else:

        # Assume a horizontal line passing through I_v tangential to direction vector and another tangential target line, Find the intersection point (I_h) of both lines 
        th_loc = calc_target_loc(param.h_center_object, param.h_center_bone)
        th_2d = Vector((th_loc.dot(right), th_loc.dot(direction)))
        ih_x = th_2d.x
        I_h = Vector((ih_x, I_v.y))


    # Calculate width spanned by horizontal FOV cone at furthest_v_dist
    half_alpha = max(math.atan2(abs(p.x - I_h.x) + param.camera_padding_h / 2, p.y - I_h.y) for p in top_points_2d)
    capture_width = 2 * furthest_v_dist * math.tan(half_alpha)


    # Assign resolution x & resolution y
    resolution_y = math.ceil(capture_height * param.pixels_per_meter)
    resolution_x = math.ceil(resolution_y * capture_width / capture_height)
    bpy.context.scene.render.resolution_x = resolution_x
    bpy.context.scene.render.resolution_y = resolution_y


    # Assign camera rotation
    cam_correction = Matrix.Rotation(math.radians(90), 4, 'X')
    camera.rotation_euler = (rot_matrix @ cam_correction).to_euler('XYZ')


    # Assign camera location
    camera.location = I_h.x * right + I_v.y * direction + I_v.x * up
def ortho_cam_fit(camera, bounding_points, param: AutoCaptureParam):

    # Get all orientation vectors
    rot_matrix, direction, right, up = calc_orientation_vectors((param.camera_orbit_z, param.camera_orbit_x, param.camera_roll))


    # Find the point (F) in bounding_points which at furtest distance opposite to direction vector
    F = min(bounding_points, key=lambda p: Vector(p).dot(direction))
    # create_sphere(location=F)


    ### HORIZONTAL
    # Convert all points using right and direction vector into 2D points that appear to be "top view"
    top_points_2d = [Vector((Vector(p).dot(right), Vector(p).dot(direction))) for p in bounding_points]
    # for point_2d in top_points_2d:
    #     create_sphere(location=Vector((point_2d.x, point_2d.y, 0.0)))
    

    # Create a 2D line tangential to direction in "top view" plane passing through F
    F_line_top = Vector(F).dot(direction)

    ## If h_center_object not given:
    if param.h_center_object is None:
        
        # Find the two 2D points (A & B) that are horizontally furthest from each other and Find their 2 projection points on the line A' & B'
        A_x = min(p.x for p in top_points_2d)
        B_x = max(p.x for p in top_points_2d)

        # Find a point (I_h) on the 2D line which is equidistant between A' & B' points
        I_h = Vector(((A_x + B_x) / 2, F_line_top))

        # Store distance between A' & B' as capture_width
        capture_width = B_x - A_x

    ## If h_center_object is given:
    else:

        # create a 2D line passing through h_center_object at direction
        target_loc = calc_target_loc(param.h_center_object, param.h_center_bone)
        target_x = Vector(target_loc).dot(right)

        # Find the intersection point (I_h) between target line & F 2D line
        I_h = Vector((target_x, F_line_top))

        # Calculate which 2D point is furthest away from target line, Multiply the distance from line by 2 and store as capture_width
        max_dist = max(abs(p.x - target_x) for p in top_points_2d)
        capture_width = max_dist * 2


    ### VERTICAL
    # Convert all points using up and direction vector into 2D points that appear to be "side view"
    side_points_2d = [Vector((Vector(p).dot(up), Vector(p).dot(direction))) for p in bounding_points]
    # for point_2d in side_points_2d:
    #     create_sphere(location=Vector((0.0, point_2d.y, point_2d.x)))
    

    # Create a 2D line tangential to direction in "side view" plane passing through F
    F_line_side = Vector(F).dot(direction)


    ## If v_center_object not given:
    if param.v_center_object is None:

        # Find the two 2D points (A & B) that are vertically furthest from each other and Find their 2 projection points on the line A' & B'
        A_y = min(p.x for p in side_points_2d)
        B_y = max(p.x for p in side_points_2d)

        # Find a point (I_v) on the 2D line which is equidistant between A' & B' points
        I_v = Vector(((A_y + B_y) / 2, F_line_side))

        # Store distance between A' & B' as capture_height
        capture_height = B_y - A_y

    ## If v_center_object is given:
    else:

        # create a 2D line passing through v_center_object at direction
        target_loc = calc_target_loc(param.v_center_object, param.v_center_bone)
        target_y = Vector(target_loc).dot(up)

        # Find the intersection point (I_v) between target line & F 2D line
        I_v = Vector((target_y, F_line_side))

        # Calculate which 2D point is furthest away from target line, Multiply the distance from line by 2 and store as capture_height
        max_dist_v = max(abs(p.x - target_y) for p in side_points_2d)
        capture_height = max_dist_v * 2
    
    
    # Apply padding to capture dimensions
    capture_width += param.camera_padding_h
    capture_height += param.camera_padding_v


    # Assign resolution
    res_x = math.ceil(capture_width * param.pixels_per_meter)
    res_y = math.ceil(capture_height * param.pixels_per_meter)
    bpy.context.scene.render.resolution_x = res_x
    bpy.context.scene.render.resolution_y = res_y


    # Assign ortho scale (Allowing deadspace but not cropping out)
    if camera.data.sensor_fit == 'HORIZONTAL':
        camera.data.ortho_scale = max(capture_width, capture_height * res_x / res_y)
    elif camera.data.sensor_fit == 'VERTICAL':
        camera.data.ortho_scale = max(capture_width * res_y / res_x, capture_height)
    elif camera.data.sensor_fit == 'AUTO':
        camera.data.ortho_scale = max(capture_width, capture_height, capture_height * res_x / res_y, capture_width  * res_y / res_x)


    # Assign camera rotation & location
    cam_correction = Matrix.Rotation(math.radians(90), 4, 'X')
    camera.rotation_euler = (rot_matrix @ cam_correction).to_euler('XYZ')
    camera.location = I_h.x * right + I_v.x * up + I_h.y * direction


    # Viewport correction
    camera.location -= direction * camera.data.display_size


# Methods
def create_auto_camera(param:AutoCaptureParam):
    cam_data = bpy.data.cameras.new(name=AUTO_CAMERA_NAME)
    cam_data.type = 'ORTHO'
    cam_obj = bpy.data.objects.new(AUTO_CAMERA_NAME, cam_data)
    bpy.context.scene.camera = cam_obj
    bpy.context.collection.objects.link(cam_obj)
    return cam_obj
def setup_auto_camera(cam_obj, param:AutoCaptureParam):
    
    # Return If no camera provided
    if cam_obj is None:
        cam_obj = create_auto_camera(param)


    # Incase of pre-defined direction
    direction = param.camera_direction
    if direction.value == CameraDirection.X.value:
        param.camera_orbit_z = math.radians(90.0)  # In Degrees
        param.camera_orbit_x = math.radians(0.0)
        param.camera_roll = math.radians(0.0)
    elif direction.value == CameraDirection.Y.value:
        param.camera_orbit_z = math.radians(180.0)
        param.camera_orbit_x = math.radians(0.0)
        param.camera_roll = math.radians(0.0)
    elif direction.value == CameraDirection.Z.value:
        param.camera_orbit_z = math.radians(0.0)
        param.camera_orbit_x = math.radians(-90.0)
        param.camera_roll = math.radians(180.0)
    elif direction.value == CameraDirection.NEG_X.value:
        param.camera_orbit_z = math.radians(-90.0)
        param.camera_orbit_x = math.radians(0.0)
        param.camera_roll = math.radians(0.0)
    elif direction.value == CameraDirection.NEG_Y.value:
        param.camera_orbit_z = math.radians(0.0)
        param.camera_orbit_x = math.radians(0.0)
        param.camera_roll = math.radians(0.0)
    elif direction.value == CameraDirection.NEG_Z.value:
        param.camera_orbit_z = math.radians(0.0)
        param.camera_orbit_x = math.radians(90.0)
        param.camera_roll = math.radians(0.0)
    
    
    # Get prerequisites
    is_auto = cam_obj.data.sensor_fit == 'AUTO'
    valid_objects = [item for item in param.objects if item is not None]
    bounding_points = calc_bounding_points(valid_objects, param.consider_armature_bones)


    # Based on type alter camera to fit bounding points within view
    if(cam_obj.data.type == 'ORTHO'):
        ortho_cam_fit(cam_obj, bounding_points, param)
    else:
        
        # Resolve 'AUTO' to either 'HORIZONTAL' or 'VERTICAL' based on bounding points
        sensor_fit = ideal_persp_sensor_fit(cam_obj, bounding_points, param)

        # Setup camera based on sensor type
        if(sensor_fit == 'HORIZONTAL'):
            persp_cam_horizontal_fit(cam_obj, bounding_points, param)
        elif(sensor_fit == 'VERTICAL'):
            persp_cam_vertical_fit(cam_obj, bounding_points, param, is_auto)
def delete_auto_camera():
    cam_obj = bpy.data.objects.get(AUTO_CAMERA_NAME)
    if cam_obj is not None:
        bpy.data.objects.remove(cam_obj, do_unlink=True) 
def render(output_file_path:str):

    # Set Output File Location
    bpy.context.scene.render.filepath = os.path.normpath(output_file_path)


    # Start Render
    bpy.ops.render.render(write_still=True)
def get_node_groups(node_tree, collected=None):

    # Create set
    if collected is None:
        collected = set()
        collected.add(node_tree)


    # Iterate through all nodes in tree
    for node in node_tree.nodes:

        # Skip if not a group node or has no assigned tree
        if node.type != 'GROUP' or node.node_tree is None or node.node_tree in collected:
            continue

        # Add to collected and recurse into it for further nested groups
        collected.add(node.node_tree)
        get_node_groups(node.node_tree, collected)


    return collected
def pixelate_images(image_paths:dict[str, str], param:PixelateParam):  # images = { "input/path/to/image.png" : "output/path/to/images.png" }
    
    # Get pixelate scene
    pixelate_scene = bpy.data.scenes.get(PIXELATE_SCENE_NAME)


    # If pixelate scene does not exist then import from blender file
    if not pixelate_scene:

        # Check if blend file exists
        current_dir = os.path.dirname(os.path.abspath(__file__))
        blend_file_path = os.path.join(current_dir, SPRITE_SHEET_MAKER_BLEND_FILE)
        if not os.path.exists(blend_file_path):
            raise Exception(f"Blend file for importing pixelate scene not found: {blend_file_path}")
            return


        # Import pixelate scene
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            if PIXELATE_SCENE_NAME in data_from.scenes:  # If scene found
                log(f"Importing scene '{PIXELATE_SCENE_NAME}' from '{blend_file_path}'")
                data_to.scenes = [PIXELATE_SCENE_NAME]
            else:  # If scene not found
                raise Exception(f"scene '{PIXELATE_SCENE_NAME}' not found in {blend_file_path}")
                return


        # return If still no pixelate scene exists 
        pixelate_scene = data_to.scenes[0]
        if not pixelate_scene:
            raise Exception(f"scene '{PIXELATE_SCENE_NAME}' is invalid!")
            return
    
    
    # Save old scene
    original_scene = bpy.context.scene


    # Set pixelate scene as active
    bpy.context.window.scene = pixelate_scene


    # Store composition groups
    all_node_groups = get_node_groups(pixelate_scene.compositing_node_group)  #  Storing since removing scene won't remove node groups


    # Intentionally kept inside try so that temp scene is deleted even incase of failure
    exception = None
    try:
        # Remove and existing nodes from compositor
        tree = pixelate_scene.compositing_node_group
       

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
            raise Exception(f"Failed to find '{IMAGE_INPUT_NODE}' node")


        # Iterate through all images & render pixelated version
        for input_path in image_paths:
            log(f"Pixelating '{input_path}'")

            # Skip if image not found
            image = bpy.data.images.load(input_path)
            if image is None:
                log(f"Failed to load image '{input_path}'")
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
            log(f"Rendering pixelated sprite")
            bpy.ops.render.render(scene=pixelate_scene.name, write_still=True)

            # Unload image from memory
            bpy.data.images.remove(image)

            log(f"Pixelated to '{output_path}'")
    except Exception as e:
        exception = e
        log(f"Failed to pixelate image: {e} \n {traceback.format_exc()}")


    # Set back old values
    bpy.context.window.scene = original_scene
    bpy.data.scenes.remove(pixelate_scene)


    # Remove composition groups
    for group in all_node_groups:
        if group is not None:
            bpy.data.node_groups.remove(group)


    # Throw exception incase of failure
    if(exception != None):
        raise exception


# Classes
class SpriteSheetMaker():
    def __init__(self):
        self.on_sprite_creating = Event()  # param
        self.on_sprite_created = Event()   # param
        self.on_sheet_row_creating = Event()  # strip_label, total_frames
        self.on_sheet_row_created = Event()  # strip_label, total_frames
        self.on_sheet_frame_creating = Event()  # strip_label, frame
        self.on_sheet_frame_created = Event()   # strip_label, frame
    def create_sprite(self, camera, output_path):
        
        # Setup Camera
        old_resolution_x = bpy.context.scene.render.resolution_x
        old_resolution_y = bpy.context.scene.render.resolution_y
        old_camera = bpy.context.scene.camera
        if(camera is not None):
            bpy.context.scene.camera = camera


        # Render a single sprite
        log(f"Rendering sprite")
        self.on_sprite_creating.broadcast()
        render(output_path)
        self.on_sprite_created.broadcast()
        

        # Reset Camera
        bpy.context.scene.render.resolution_x = old_resolution_x 
        bpy.context.scene.render.resolution_y = old_resolution_y
        bpy.context.scene.camera = old_camera
    def create_sprite_sheet(self, param:SpriteSheetParam, output_path:str):
        
        # Create temp folder
        log(f"Creating temp folder '{TEMP_FOLDER_NAME}'")
        temp_dir = create_folder(os.path.dirname(output_path), TEMP_FOLDER_NAME)


        # Iterate through actions and capture render for each frame (Each action should have it's own folder (in order) & image names should be 1, 2, 3 for each frame respectively)
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
            frame_start = 0 if math.isinf(frame_start) else int(frame_start) # Convert to valid int
            frame_end = 0 if math.isinf(frame_end) else int(frame_end)


            # Notify starting row creation
            self.on_sheet_row_creating.broadcast(strip.label, frame_end)


            # Create folder for this strip
            clean_label = bpy.path.clean_name(strip.label.strip())
            folder_name = f"{i}_{clean_label if clean_label !='' else UNTITLED_FOLDER_NAME}"
            log(f"Creating folder {folder_name}")
            action_dir = create_folder(temp_dir, folder_name)
            

            # Assign action to all objects
            old_anim_data = []  # [(obj, old_action, old_slot), ...]
            for (obj, action, slot) in strip.capture_items:

                # Skip if object is invalid or no Action provided or doesn't have attributes
                if obj == None or not hasattr(obj, "animation_data") or not hasattr(obj.animation_data, "action") or not hasattr(obj.animation_data, "action_slot"):
                    continue
                
                # Store old animation data e.g. Action, Slot, etc
                old_anim_data.append((obj, obj.animation_data.action, obj.animation_data.action_slot))

                # Assign action
                obj.animation_data.action = action
                
                # Assign user provided slot else efault slot
                slot_name = f"OB{slot}"
                if slot != "" and action != None and (slot_name in action.slots):
                    obj.animation_data.action_slot = action.slots[slot_name]
                elif hasattr(obj.animation_data, "action_suitable_slots") and len(obj.animation_data.action_suitable_slots) > 0:
                    obj.animation_data.action_slot = obj.animation_data.action_suitable_slots[0]


            # Create auto camera
            camera = create_auto_camera(strip.auto_capture_param) if not strip.custom_camera else strip.custom_camera

            # Iterate through all frames & render sprite frame
            pixelate_dict:dict[str, str] = {}  # { <Input path>: <Output path> } (if value is None then key is used)
            for frame in range(frame_start, frame_end + 1):

                # Notify starting
                log(f"Capturing strip '{strip.label}' at frame {frame}")
                self.on_sheet_frame_creating.broadcast(strip.label, frame)

                # Set frame
                bpy.context.scene.frame_set(frame)

                # Fit auto camera to view
                if(strip.to_auto_capture):
                    setup_auto_camera(camera, strip.auto_capture_param)

                # Render sprite
                sprite_output_file = f"{action_dir}/{frame}.{bpy.context.scene.render.image_settings.file_format.lower()}"
                self.create_sprite(camera, sprite_output_file)

                # Store path to pixelate
                pixelate_dict[sprite_output_file] = None

                # Notify frame completed
                self.on_sheet_frame_created.broadcast(strip.label, frame)


            # Delete auto camera
            if(not strip.custom_camera and camera is not None):
                bpy.data.objects.remove(camera, do_unlink=True) 
            

            # Reset actions to all objects
            for (obj, action, slot) in old_anim_data:
                obj.animation_data.action = action
                if(obj.animation_data.action):  # Cannot set slot without valid action
                    obj.animation_data.action_slot = slot
            
            
            # pixelate if required
            if(strip.to_pixelate):
                pixelate_images(pixelate_dict, strip.pixelate_param)


            # Notify completed row creation
            self.on_sheet_row_created.broadcast(strip.label, frame_end)

        
        # Combine images together into single file and paste in output
        assemble_images(param.assemble_param, temp_dir, output_path)


        # Delete temp folder
        if param.delete_temp_folder:
            shutil.rmtree(temp_dir)


        return True
