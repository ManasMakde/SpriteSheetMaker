import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from enum import Enum


# Constants
DEFAULT_COLOR_MODE = "RGBA"
DEFAULT_FILE_FORMAT = "PNG"


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
        self.input_folder_path:str = ""
        self.output_path:str = ""  # file path if combine_mode is sheet otherwise folder path
        self.font_size:int = 24
        self.margin:int = 15
        self.consistency:SpriteConsistency = SpriteConsistency.INDIVIDUAL
        self.align:SpriteAlign = SpriteAlign.BOTTOM_CENTER
        self.combine_mode:CombineMode = CombineMode.SHEET


# Methods
def unique_path(target_path:str, is_file:bool=False, count_limit:int = 100000):

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

def assemble_images(param:AssembleParam):

    # Load font and Get all sorted action sub folders
    font = ImageFont.load_default(param.font_size) if param.font_size !=0 else None
    action_folders = sorted(
        [folder for folder in os.listdir(param.input_folder_path) if os.path.isdir(os.path.join(param.input_folder_path, folder))],
        key=lambda x: int(x.split('_')[0])
    )
    print(f"[SpriteSheetMaker {datetime.now()}] Found {len(action_folders)} action sub folders")


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
        abs_action_folder = os.path.join(param.input_folder_path, action_folder)
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
        combine_into_sheet(param, rows, global_img_widest, global_img_tallest)
    elif(param.combine_mode == CombineMode.STRIPS):
        combine_into_strips(param, rows, global_img_widest, global_img_tallest)
    elif(param.combine_mode == CombineMode.IMAGES):
        combine_into_images(param, rows, global_img_widest, global_img_tallest)

def combine_into_sheet(param:AssembleParam, rows:list[RowData], global_img_widest:int, global_img_tallest:int):


    # Extract from param
    margin = param.margin
    font_size = param.font_size


    # Calculate sheet dimensions based on sprite consistency
    sheet_width = 0
    sheet_height = 0
    for row_data in rows:
        img_count = len(row_data.images)
        gaps = margin * (img_count - 1)
        if(param.consistency == SpriteConsistency.INDIVIDUAL):
            row_width = row_data.img_accum_width + margin + gaps
            img_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ROW):
            row_width = (row_data.img_widest * img_count) + margin + gaps
            img_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ALL):
            row_width = (global_img_widest * img_count)  + margin + gaps
            img_height = global_img_tallest

        sheet_width = max(sheet_width, row_width, row_data.label_width)
        sheet_height += row_data.label_height + margin + img_height

    
    # Add margins to sheet dimensions
    sheet_width += margin * 2
    sheet_height += margin * 2


    # Create sheet
    print(f"[SpriteSheetMaker {datetime.now()}] Creating sprite sheet {sheet_width}x{sheet_height}")
    images = rows[0].images
    img_mode = images[0].mode if len(images)!=0 else DEFAULT_COLOR_MODE
    sheet = Image.new(img_mode, (int(sheet_width), int(sheet_height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(param.font_size) if param.font_size !=0 else None


    # Paste labels & images into sheet
    paste_height = margin
    for row_data in rows:

        # Reset paste width
        paste_width = margin


        # Paste label
        if(font_size != 0):
            label_location_x = paste_width + row_data.label_offset[0]
            label_location_y = paste_height + row_data.label_offset[1]
            draw.text((label_location_x, label_location_y), row_data.label_text, fill="white", font=font, spacing = 0)
            paste_height += row_data.label_height + margin
            print(f"[SpriteSheetMaker {datetime.now()}] Addded label '{row_data.label_text}' at ({label_location_x},{label_location_y})")


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
            sheet.paste(img, (int(img_location_x), int(img_location_y)))
            paste_width += large_width + margin
            print(f"[SpriteSheetMaker {datetime.now()}] Addded image of frame {i + 1} at ({img_location_x},{img_location_y})")
        

        # Increase paste height
        if(param.consistency == SpriteConsistency.INDIVIDUAL):
            paste_height += row_data.img_tallest + margin
        elif(param.consistency == SpriteConsistency.ROW):
            paste_height += row_data.img_tallest + margin
        elif(param.consistency == SpriteConsistency.ALL):
            paste_height += global_img_tallest + margin
        

    # Save the final output sprite sheet
    print(f"[SpriteSheetMaker {datetime.now()}] Saving sprite sheet to '{param.output_path}' ...")
    sheet.save(param.output_path)
    print(f"[SpriteSheetMaker {datetime.now()}] Successfully saved sprite sheet to {param.output_path}")

def combine_into_strips(param:AssembleParam, rows:list[RowData], global_img_widest:int, global_img_tallest:int):
    
    # Extract from param
    margin = param.margin
    font_size = param.font_size


    # Create font
    font = ImageFont.load_default(param.font_size) if param.font_size !=0 else None

    
    # Make sure folder exists
    create_folder(param.output_path)


    # Iterate and create strips
    for row_data in rows:
        img_count = len(row_data.images)
        gaps = margin * (img_count - 1)
        if(param.consistency == SpriteConsistency.INDIVIDUAL):
            row_width = row_data.img_accum_width + margin * gaps
            img_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ROW):
            row_width = row_data.img_widest * img_count + margin * gaps
            img_height = row_data.img_tallest
        elif(param.consistency == SpriteConsistency.ALL):
            row_width = global_img_widest * img_count  + margin * gaps
            img_height = global_img_tallest
    
        
        # Assign strip height & width
        strip_width = margin + max(row_width, row_data.label_width) + margin 
        strip_height = margin + row_data.label_height + margin + img_height + margin
        

        # Create strip
        print(f"[SpriteSheetMaker {datetime.now()}] Creating strip {strip_width}x{strip_height}")
        img_mode = row_data.images[0].mode if len(row_data.images)!=0 else DEFAULT_COLOR_MODE
        strip = Image.new(img_mode, (int(strip_width), int(strip_height)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(strip)


        # Paste label
        paste_height = margin
        if(font_size != 0):
            label_location_x = margin + row_data.label_offset[0]
            label_location_y = row_data.label_offset[1]
            draw.text((label_location_x, label_location_y), row_data.label_text, fill="white", font=font, spacing = 0)
            paste_height += row_data.label_height + margin


        # Paste images
        paste_width = margin
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
            strip.paste(img, (int(img_location_x), int(img_location_y)))
            paste_width += large_width + margin


        # Save strip
        ext = row_data.images[0].format if len(row_data.images) != 0 else DEFAULT_FILE_FORMAT
        strip_output_path = os.path.join(param.output_path, f"{row_data.label_text}.{ext.lower()}")
        print(f"[SpriteSheetMaker {datetime.now()}] Saving strip to '{strip_output_path}' ...")
        strip.save(strip_output_path)
        print(f"[SpriteSheetMaker {datetime.now()}] Successfully saved sprite strip to {strip_output_path}")

def combine_into_images(param:AssembleParam, rows:list[RowData], global_img_widest:int, global_img_tallest:int):
    
    # Extract from param
    margin = param.margin
    font_size = param.font_size


    # Create font
    font = ImageFont.load_default(param.font_size) if param.font_size !=0 else None

    
    # Make sure folder exists
    create_folder(param.output_path)


    # Iterate and create strips
    for row_count, row_data in enumerate(rows):

        # Create row folder
        row_folder = os.path.join(param.output_path, f"{row_count}_{row_data.label_text}")
        create_folder(row_folder)
        row_count += 1


        # Save images
        for img_count, img in enumerate(row_data.images):

            # Get cell size
            large_width, large_height = img.width, img.height
            if(param.consistency == SpriteConsistency.ROW):
                large_width, large_height = row_data.img_widest, row_data.img_tallest
            elif(param.consistency == SpriteConsistency.ALL):
                large_width, large_height = global_img_widest, global_img_tallest
            

            # Add margins
            new_img_width = large_width + margin * 2
            new_img_height = large_height + margin * 2


            # Create new image
            print(f"[SpriteSheetMaker {datetime.now()}] Creating image {new_img_width}x{new_img_height}")
            new_img = Image.new(img.mode, (int(new_img_width), int(new_img_height)), (0, 0, 0, 0))
            draw = ImageDraw.Draw(new_img)
            

            # Calculate offset based on alignment & consistency
            offset_x, offset_y = calc_align_offset(param.align, large_width, large_height, img.width, img.height)


            # Paste image
            new_img.paste(img, (int(offset_x), int(offset_y)))


            # Save new image
            ext = img.format if img.format is not None else DEFAULT_FILE_FORMAT
            img_output_path = os.path.join(row_folder, f"{img_count}.{ext.lower()}")
            print(f"[SpriteSheetMaker {datetime.now()}] Saving image to '{img_output_path}' ...")
            new_img.save(img_output_path)
            print(f"[SpriteSheetMaker {datetime.now()}] Successfully saved sprite strip to {img_output_path}")

