import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from enum import Enum


# Constants
DEFAULT_COLOR_MODE = "RGBA"


# Classes
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

class LabelParam():
    text:str = "Untitled"
    font_size:int = 24
    margin:int = 15

class AssembleParam():
    input_folder_path: str = ""
    output_file_path : str = ""
    label_param: LabelParam = LabelParam()
    consistency: SpriteConsistency = SpriteConsistency.INDIVIDUAL
    align: SpriteAlign = SpriteAlign.BOTTOM_CENTER


# Methods
def calc_align_offset(align: SpriteAlign, large_width:int, large_height:int, small_width:int, small_height:int):

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

def assemble_sprite_sheet(param:AssembleParam):
    print(f"[SpriteSheetMaker {datetime.now()}] Creating sprite sheet for folder '{param.input_folder_path}'")

    # Load font and Get all sorted action sub folders
    font_size = param.label_param.font_size
    margin = param.label_param.margin
    font = ImageFont.load_default(font_size) if font_size !=0 else None
    action_folders = sorted(
        [folder for folder in os.listdir(param.input_folder_path) if os.path.isdir(os.path.join(param.input_folder_path, folder))],
        key=lambda x: int(x.split('_')[0])
    )
    print(f"[SpriteSheetMaker {datetime.now()}] Found {len(action_folders)} action sub folders")


    # Get all images from every folder & calculate max height & width 
    global_widest_img_width = 0
    global_tallest_img_height = 0
    row_data = []  # [ ("label_text", (row_widest_img_width, row_tallest_img_height), [ImageA1, ImageA2, ... ]), ... ]
    for action_folder in action_folders:

        # Iterate through all images in a folder/row
        img_row = []
        row_widest_img_width = 0
        row_tallest_img_height = 0
        action_folder_path = os.path.join(param.input_folder_path, action_folder)
        img_names = sorted(os.listdir(action_folder_path), key=lambda x: int(x.split('.')[0]))
        for img_name in img_names:
            try:
                img_path = os.path.join(action_folder_path, img_name)
                img = Image.open(img_path)
                img_row.append(img)
                width, height = img.size
                global_widest_img_width, global_tallest_img_height = max(global_widest_img_width, width), max(global_tallest_img_height, height)
                row_widest_img_width, row_tallest_img_height = max(row_widest_img_width, width), max(row_tallest_img_height, height)
            except Exception:
                img_row.append(None)
        

        # Store images
        label_text = action_folder.split('_', 1)[1]
        row_data.append((label_text, (row_widest_img_width, row_tallest_img_height), img_row))


    # Calculate image and label locations & total sheet dimensions
    total_width = 0.0
    total_height = 0.0
    sheet_data = []  #  [ (("label_text", x, y), [(imageA, x, y), (imageB, x, y), ... ]), ... ] 
    for row in row_data:

        # Get all row data
        label_text, (row_max_width, row_max_height), row_images = row
        print(f"[SpriteSheetMaker {datetime.now()}] Processing action '{label_text}' ")


        # Calculate label location
        label_bbox = (0, 0, 0, 0) if font_size == 0 else font.getbbox(label_text)
        label_height = (label_bbox[3] - label_bbox[1])
        label_width = (label_bbox[2] - label_bbox[0])
        label_location = (margin, total_height + margin - label_bbox[1]) # `label_bbox[1]` kept intentionally DO NOT REMOVE
        label_data = (label_text, label_location[0], label_location[1])


        # Increase total height & total width from label
        total_width = max(total_width, margin + label_width + margin)  
        total_height += margin + label_height + margin


        # Calculate image locations
        images_data = []
        row_width = margin
        row_height = 0.0
        for img in row_images:

            # Calculate offset based on alignment & consistency
            large_width, large_height = img.width, row_max_height
            if(param.consistency == SpriteConsistency.ROW):
                large_width, large_height = row_max_width, row_max_height
            elif(param.consistency == SpriteConsistency.ALL):
                large_width, large_height = global_widest_img_width, global_tallest_img_height
            offset_x, offset_y = calc_align_offset(param.align, large_width, large_height, img.width, img.height)


            # Calculate image location
            image_location = (row_width + offset_x, total_height + offset_y)
            images_data.append((img, image_location[0], image_location[1]))


            # Increase row height & row width from image
            row_width += large_width + margin 
            row_height = max(row_height, large_height)


        # Increase total height & total width from row
        total_width = max(total_width, row_width)  
        total_height += row_height


        # Add to sheet data
        sheet_data.append((label_data, images_data))


    # Ending margins
    total_height += margin
    

    # Create sprite sheet
    print(f"[SpriteSheetMaker {datetime.now()}] Creating sprite sheet {total_width}x{total_height}")
    label, images = sheet_data[0]
    img_mode = images[0][0].mode if len(images)!=0 else DEFAULT_COLOR_MODE
    sheet = Image.new(img_mode, (int(total_width), int(total_height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)


    # Paste all labels and images into sprite sheet
    for data in sheet_data:

        # Get row and images data
        row_data, images_data = data


        # Paste label
        if(font_size != 0):
            label_name, label_location_x, label_location_y = row_data
            draw.text((int(label_location_x), int(label_location_y)), label_name, fill="white", font=font, spacing = 0)


        # Paste images
        for img_data in images_data:
            img, img_location_x, img_location_y = img_data
            sheet.paste(img, (int(img_location_x), int(img_location_y)))


    # Save the final output sprite sheet
    print(f"[SpriteSheetMaker {datetime.now()}] Saving sprite sheet to '{param.output_file_path}' ...")
    sheet.save(param.output_file_path)
    print(f"[SpriteSheetMaker {datetime.now()}] Successfully saved sprite sheet to {param.output_file_path}")

def add_label_to_image(img_path:str, param:LabelParam, img_output_path:str = ""):

    # Notify
    print(f"[SpriteSheetMaker {datetime.now()}] Adding label and margin to {img_path} ...")


    # Get essentials
    font_size = param.font_size
    margin = param.margin


    # Get label data
    font = ImageFont.load_default(font_size) if font_size !=0 else None
    label_bbox = (0, 0, 0, 0) if font_size == 0 else font.getbbox(param.text)
    label_width = (label_bbox[2] - label_bbox[0])
    label_height = (label_bbox[3] - label_bbox[1])


    # Get image data
    img = Image.open(img_path)
    img_width, img_height = img.size
    img_mode = img.mode


    # Dimensions & Locations
    img_location = (0, 0)
    label_location = (0, 0)


    # Calculate new width and height 
    total_width = img_width + margin * 2
    total_height = img_height + margin * 2
    if(font_size != 0):
        total_width = max(total_width, label_width + margin * 2)
        total_height += label_height + margin


    # Calculate locations
    img_location = (margin, margin + (0 if font_size == 0 else (label_height + margin)))
    label_location = (margin, margin - label_bbox[1])


    # Create new image
    new_img = Image.new(img_mode, (int(total_width), int(total_height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(new_img)


    # Paste in new image
    new_img.paste(img, (int(img_location[0]), int(img_location[1])))
    if(font_size != 0):
        draw.text((int(label_location[0]), int(label_location[1])), param.text, fill="white", font=font, spacing = 0)


    # Save new image
    new_img.save(img_output_path if (img_output_path != "" and img_output_path != None) else img_path)
    print(f"[SpriteSheetMaker {datetime.now()}] Successfully added label and margin to {img_path}")
