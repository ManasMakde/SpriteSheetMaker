import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from enum import Enum
from .logging import *


# Constants
DEFAULT_COLOR_MODE = "RGBA"
DEFAULT_FILE_FORMAT = "PNG"
PIL_MAX_CHANNEL_VALUE = 255
DEFAULT_ALPHA_CHANNEL_VALUE = 255


# Enums
class SpriteAlign(Enum):
    TOP_LEFT = "Top Left"
    TOP_CENTER = "Top Center"
    TOP_RIGHT = "Top Right"
    MIDDLE_LEFT = "Middle Left"
    MIDDLE_CENTER = "Middle Center"
    MIDDLE_RIGHT = "Middle Right"
    BOTTOM_LEFT = "Bottom Left"
    BOTTOM_CENTER = "Bottom Center"
    BOTTOM_RIGHT = "Bottom Right"
class SpriteConsistency(Enum):
    INDIVIDUAL = "Individual Consistent"
    ROW = "Row Consistent"
    ALL = "All Consistent"
class CombineMode(Enum):
    IMAGES = "Images"
    STRIPS = "Strips"
    SHEET = "Sheet"


# Classes
class RowData:
    def __init__(self):
        self.label_text:str = "Untitled"
        self.label_width:int = 0
        self.label_height:int = 0
        self.label_offset:tuple[int, int] = (0, 0)
        self.images = []
        self.img_accum_width:int = 0  # Combined
        self.img_widest:int = 0  # width of the widest image in the row
        self.img_tallest:int = 0  # height of the tallest image in the row
class AssembleParam:
    def __init__(self):
        self.font_size:int = 24
        self.label_color:tuple = (1.0, 1.0, 1.0, 1.0)  # RGBA normalized 0 to 1
        self.background_color:tuple = (0.0, 0.0, 0.0, 0.0)  # RGBA normalized 0 to 1
        self.surrounding_margin:int = (15, 15, 15, 15)  # top, right, bottom, left
        self.label_margin:int = 15
        self.image_margin:int = 15
        self.consistency:SpriteConsistency = SpriteConsistency.INDIVIDUAL
        self.align:SpriteAlign = SpriteAlign.BOTTOM_CENTER
        self.combine_mode:CombineMode = CombineMode.SHEET


# Methods
def unique_path(target_path:str, count_limit:int = 100000):

    # Return if path already exists
    if not os.path.exists(target_path):
        return target_path

    
    # Get essentials
    parent_dir, name = os.path.split(target_path)
    base_name, ext = os.path.splitext(name)


    # Keep changing prefix until path doesn't exist
    counter = 1
    while os.path.exists(target_path) and counter < count_limit:
        new_name = f"{base_name}_{counter}{ext}"
        target_path = os.path.join(parent_dir, new_name)
        counter += 1
    

    return target_path
def create_folder(at_path, folder_name=""):

    # Make sure the name is safe for folder creation
    folder_path = os.path.join(at_path, folder_name)
    folder_path = unique_path(folder_path)


    # Create folder
    if(not os.path.exists(folder_path)):
        os.makedirs(folder_path)


    return folder_path
def color_to_pil(color, mode):

    # Warn and fallback if color data is invalid
    if color is None or len(color) < 3:
        log("Invalid color provided to color_to_pil, falling back to black", True, "ERROR")
        return (0, 0, 0, 0) if mode == "RGBA" else (0, 0, 0)


    # Convert normalized 0 to 1 channels into 0 to 255 int values
    r = int(round(color[0] * PIL_MAX_CHANNEL_VALUE))
    g = int(round(color[1] * PIL_MAX_CHANNEL_VALUE))
    b = int(round(color[2] * PIL_MAX_CHANNEL_VALUE))
    a = int(round(color[3] * PIL_MAX_CHANNEL_VALUE)) if len(color) > 3 else DEFAULT_ALPHA_CHANNEL_VALUE

    return (r, g, b, a) if mode == "RGBA" else (r, g, b)
def calc_align_offset(align:SpriteAlign, large_width:int, large_height:int, small_width:int, small_height:int):

    x_offset = 0.0
    y_offset = 0.0


    # Get X Offset
    if(align in [SpriteAlign.TOP_LEFT, SpriteAlign.MIDDLE_LEFT, SpriteAlign.BOTTOM_LEFT]):
        x_offset = 0.0
    elif(align in [SpriteAlign.TOP_CENTER, SpriteAlign.MIDDLE_CENTER, SpriteAlign.BOTTOM_CENTER]):
        x_offset = (large_width - small_width) / 2.0
    elif(align in [SpriteAlign.TOP_RIGHT, SpriteAlign.MIDDLE_RIGHT, SpriteAlign.BOTTOM_RIGHT]):
        x_offset = (large_width - small_width)
    

    # Get Y Offset
    if(align in [SpriteAlign.TOP_LEFT, SpriteAlign.TOP_CENTER, SpriteAlign.TOP_RIGHT]):
        y_offset = 0.0
    elif(align in [SpriteAlign.MIDDLE_LEFT, SpriteAlign.MIDDLE_CENTER, SpriteAlign.MIDDLE_RIGHT]):
        y_offset = (large_height - small_height) / 2.0
    elif(align in [SpriteAlign.BOTTOM_LEFT, SpriteAlign.BOTTOM_CENTER, SpriteAlign.BOTTOM_RIGHT]):
        y_offset = (large_height - small_height)


    return int(x_offset), int(y_offset)
def combine_into_sheet(param:AssembleParam, rows:list[RowData], global_img_widest:int, global_img_tallest:int, output_path:str):

    # Extract from param
    surrounding_margin = param.surrounding_margin
    label_margin = param.label_margin
    image_margin = param.image_margin
    font_size = param.font_size


    # Calculate sheet dimensions based on sprite consistency
    sheet_width = 0
    sheet_height = 0
    for row_count, row_data in enumerate(rows):

        # Calculate row height & width
        img_count = len(row_data.images)
        gaps = image_margin * (img_count - 1)
        if(param.consistency == SpriteConsistency.INDIVIDUAL):
            row_width = row_data.img_accum_width + gaps
            row_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ROW):
            row_width = (row_data.img_widest * img_count) + gaps
            row_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ALL):
            row_width = (global_img_widest * img_count) + gaps
            row_height = global_img_tallest


        # Add to height & width
        sheet_width = max(sheet_width, row_width, row_data.label_width)
        sheet_height += row_height + ((row_data.label_height + label_margin) if font_size!=0 else 0)


        # Additional top label margin 
        if(row_count != 0 and font_size != 0):
            sheet_height += label_margin


    # Add margins to sheet dimensions
    sheet_width += surrounding_margin[1] + surrounding_margin[3]
    sheet_height += surrounding_margin[0] + surrounding_margin[2]


# Create sheet
    log(f"Creating sprite sheet {sheet_width}x{sheet_height}")
    images = rows[0].images
    img_mode = images[0].mode if len(images)!=0 else DEFAULT_COLOR_MODE
    bg_color = color_to_pil(param.background_color, img_mode)
    sheet = Image.new(img_mode, (int(sheet_width), int(sheet_height)), bg_color)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(param.font_size) if param.font_size !=0 else None


    # Paste labels & images into sheet
    paste_height = surrounding_margin[0]
    for row_data in rows:

        # Reset paste width
        paste_width = surrounding_margin[3]


        # Paste label
        if(font_size != 0):
            label_location_x = paste_width + row_data.label_offset[0]
            label_location_y = paste_height + row_data.label_offset[1]
            label_fill = color_to_pil(param.label_color, img_mode)
            draw.text((label_location_x, label_location_y), row_data.label_text, fill=label_fill, font=font, spacing = 0)
            paste_height += row_data.label_height + label_margin
            log(f"Addded label '{row_data.label_text}' at ({label_location_x},{label_location_y})")


        # Paste images
        for i, img in enumerate(row_data.images):
            
            # Get cell size
            large_width, large_height = img.width, row_data.img_tallest
            if(param.consistency == SpriteConsistency.ROW):
                large_width, large_height = row_data.img_widest, row_data.img_tallest
            elif(param.consistency == SpriteConsistency.ALL):
                large_width, large_height = global_img_widest, global_img_tallest
            

            # Calculate offset based on alignment & consistency
            offset_x, offset_y = calc_align_offset(param.align, large_width, large_height, img.width, img.height)


            # Paste image
            img_location_x = paste_width + offset_x
            img_location_y = paste_height + offset_y
            paste_mask = img if img.mode == DEFAULT_COLOR_MODE else None
            sheet.paste(img, (int(img_location_x), int(img_location_y)), paste_mask)
            paste_width += large_width + image_margin
            log(f"Addded image of frame {i + 1} at ({img_location_x},{img_location_y})")

        

        # Increase paste height
        if(param.consistency == SpriteConsistency.INDIVIDUAL):
            paste_height += row_data.img_tallest + label_margin
        elif(param.consistency == SpriteConsistency.ROW):
            paste_height += row_data.img_tallest + label_margin
        elif(param.consistency == SpriteConsistency.ALL):
            paste_height += global_img_tallest + label_margin
        

    # Save the final output sprite sheet
    log(f"Saving sprite sheet to '{output_path}' ...")
    sheet.save(output_path)
    log(f"Successfully saved sprite sheet to {output_path}")
def combine_into_strips(param:AssembleParam, rows:list[RowData], global_img_widest:int, global_img_tallest:int, output_path:str):
    
    # Extract from param
    surrounding_margin_top = param.surrounding_margin[0]
    surrounding_margin_right = param.surrounding_margin[1]
    surrounding_margin_bottom = param.surrounding_margin[2]
    surrounding_margin_left = param.surrounding_margin[3]
    label_margin = param.label_margin
    image_margin = param.image_margin
    font_size = param.font_size


    # Create font
    font = ImageFont.load_default(param.font_size) if param.font_size !=0 else None

    
    # Make sure folder exists
    create_folder(output_path)


    # Iterate and create strips
    for _, row_data in enumerate(rows):
        img_count = len(row_data.images)
        gaps = image_margin * (img_count - 1)
        if(param.consistency == SpriteConsistency.INDIVIDUAL):
            row_width = row_data.img_accum_width + gaps
            img_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ROW):
            row_width = row_data.img_widest * img_count + gaps
            img_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ALL):
            row_width = global_img_widest * img_count + gaps
            img_height = global_img_tallest

    
        # Assign strip height & width
        strip_width = surrounding_margin_left + max(row_width, row_data.label_width) + surrounding_margin_right
        strip_height = surrounding_margin_top + row_data.label_height + label_margin + img_height + surrounding_margin_bottom


        # Create strip
        log(f"Creating strip {strip_width}x{strip_height}")
        img_mode = row_data.images[0].mode if len(row_data.images)!=0 else DEFAULT_COLOR_MODE
        bg_color = color_to_pil(param.background_color, img_mode)
        strip = Image.new(img_mode, (int(strip_width), int(strip_height)), bg_color)
        draw = ImageDraw.Draw(strip)


        # Paste label
        paste_height = surrounding_margin_top
        if(font_size != 0):
            label_location_x = surrounding_margin_left + row_data.label_offset[0]
            label_location_y = surrounding_margin_top + row_data.label_offset[1]
            label_fill = color_to_pil(param.label_color, img_mode)
            draw.text((label_location_x, label_location_y), row_data.label_text, fill=label_fill, font=font, spacing = 0)
            paste_height += row_data.label_height + label_margin


        # Paste images
        paste_width = surrounding_margin_left
        for img in row_data.images:
            
            # Get cell size
            large_width, large_height = img.width, row_data.img_tallest
            if(param.consistency == SpriteConsistency.ROW):
                large_width, large_height = row_data.img_widest, row_data.img_tallest
            elif(param.consistency == SpriteConsistency.ALL):
                large_width, large_height = global_img_widest, global_img_tallest
            

            # Calculate offset based on alignment & consistency
            offset_x, offset_y = calc_align_offset(param.align, large_width, large_height, img.width, img.height)


            # Paste image
            img_location_x = paste_width + offset_x
            img_location_y = paste_height + offset_y
            paste_mask = img if img.mode == DEFAULT_COLOR_MODE else None
            strip.paste(img, (int(img_location_x), int(img_location_y)), paste_mask)
            paste_width += large_width + image_margin


        # Save strip
        ext = row_data.images[0].format if len(row_data.images) != 0 else DEFAULT_FILE_FORMAT
        strip_output_path = os.path.join(output_path, f"{row_data.label_text}.{ext.lower()}")
        log(f"Saving strip to '{strip_output_path}' ...")
        strip.save(strip_output_path)
        log(f"Successfully saved sprite strip to {strip_output_path}")
def combine_into_images(param:AssembleParam, rows:list[RowData], global_img_widest:int, global_img_tallest:int, output_path:str):
    
    # Extract from param
    surrounding_margin_top = param.surrounding_margin[0]
    surrounding_margin_right = param.surrounding_margin[1]
    surrounding_margin_bottom = param.surrounding_margin[2]
    surrounding_margin_left = param.surrounding_margin[3]

    
    # Make sure folder exists
    create_folder(output_path)


    # Iterate and create strips
    for row_count, row_data in enumerate(rows):

        # Create row folder
        row_folder = os.path.join(output_path, f"{row_count}_{row_data.label_text}")
        create_folder(row_folder)


        # Save images
        for img_count, img in enumerate(row_data.images):

            # Get cell size
            large_width, large_height = img.width, img.height
            if(param.consistency == SpriteConsistency.ROW):
                large_width, large_height = row_data.img_widest, row_data.img_tallest
            elif(param.consistency == SpriteConsistency.ALL):
                large_width, large_height = global_img_widest, global_img_tallest
            

            # Add margins
            new_img_width = surrounding_margin_left + large_width + surrounding_margin_right
            new_img_height = surrounding_margin_top + large_height + surrounding_margin_bottom


            # Create new image
            log(f"Creating image {new_img_width}x{new_img_height}")
            bg_color = color_to_pil(param.background_color, img.mode)
            new_img = Image.new(img.mode, (int(new_img_width), int(new_img_height)), bg_color)
            

            # Calculate offset based on alignment & consistency
            offset_x, offset_y = calc_align_offset(param.align, large_width, large_height, img.width, img.height)


            # Paste image
            paste_mask = img if img.mode == DEFAULT_COLOR_MODE else None
            new_img.paste(img, (int(offset_x + surrounding_margin_left), int(offset_y + surrounding_margin_top)), paste_mask)


            # Save new image
            ext = img.format if img.format is not None else DEFAULT_FILE_FORMAT
            img_output_path = os.path.join(row_folder, f"{img_count}.{ext.lower()}")
            log(f"Saving image to '{img_output_path}' ...")
            new_img.save(img_output_path)
            log(f"Successfully saved sprite strip to {img_output_path}")
def assemble_images(param:AssembleParam, input_folder_path:str, output_path:str):

    # Load font and Get all sorted action sub folders
    font = ImageFont.load_default(param.font_size) if param.font_size !=0 else None
    action_folders = sorted(
        [folder for folder in os.listdir(input_folder_path) if os.path.isdir(os.path.join(input_folder_path, folder))],
        key=lambda x: int(x.split('_')[0])
    )
    log(f"Found {len(action_folders)} action sub folders")


    # Assign row data from folders 
    global_img_widest:int = 0
    global_img_tallest:int = 0
    rows:list[RowData] = []
    for action_folder in action_folders:

        # Create row data
        row_data = RowData()


        # Add label to row data
        row_data.label_text = action_folder.split('_', 1)[1]
        label_bbox = (0, 0, 0, 0) if param.font_size == 0 else font.getbbox(row_data.label_text)
        row_data.label_width = (label_bbox[2] - label_bbox[0])
        row_data.label_height = (label_bbox[3] - label_bbox[1]) 
        row_data.label_offset = (0, -label_bbox[1])


        # Images
        abs_action_folder = os.path.join(input_folder_path, action_folder)
        img_names = sorted(os.listdir(abs_action_folder), key=lambda x: int(x.split('.')[0]))
        for img_name in img_names:

            # Add image to row data
            img = Image.open(os.path.join(abs_action_folder, img_name))
            row_data.images.append(img)

            # Add accumulated width, widest img width & tallest img height to row data
            row_data.img_accum_width += img.width
            row_data.img_widest = max(row_data.img_widest, img.width)
            row_data.img_tallest = max(row_data.img_tallest, img.height)

            # Calculate widest & tallest images amongst all
            global_img_widest = max(global_img_widest, img.width)
            global_img_tallest = max(global_img_tallest, img.height)


        # Append row data
        rows.append(row_data)


    # Combine into sheet or strips 
    if(param.combine_mode == CombineMode.SHEET):
        combine_into_sheet(param, rows, global_img_widest, global_img_tallest, output_path)
    elif(param.combine_mode == CombineMode.STRIPS):
        combine_into_strips(param, rows, global_img_widest, global_img_tallest, output_path)
    elif(param.combine_mode == CombineMode.IMAGES):
        combine_into_images(param, rows, global_img_widest, global_img_tallest, output_path)
