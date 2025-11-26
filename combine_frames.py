from PIL import Image, ImageDraw, ImageFont
import os


def assemble_sprite_sheet(root_folder, output_path="sprite_sheet.png", font_size=24, margin=15):

    print(f"[SpriteSheetMaker] Creating sprite sheet for folder '{root_folder}'")


    # Clean path
    output_path = os.path.normpath(output_path)


    # Load font
    font = ImageFont.load_default(font_size)


    # Get all action sub folders & sort them
    action_folders = [folder for folder in os.listdir(root_folder) if os.path.isdir(os.path.join(root_folder, folder))]
    action_folders.sort(key=lambda x: int(x.split('_')[0]))
    print(f"[SpriteSheetMaker] Found {len(action_folders)} action sub folders")


    # Assign labels & images to each row -> Calculate row dimensions -> Add to total sheet dimensions
    total_width = 0
    total_height = margin
    rows = []  # [(labelA, [imageA1, imageA2, ...]), ... ]
    for action_folder in action_folders:
        print(f"[SpriteSheetMaker] Processing action sub folder '{action_folder}'")

        # Get top label name
        label = action_folder.split('_', 1)[1]

        # Get sorted images name
        action_folder_path = os.path.join(root_folder, action_folder)
        img_names = os.listdir(action_folder_path)
        img_names.sort(key=lambda x: int(x.split('.')[0]))

        # Store images
        img_objects = []
        for img_name in img_names:
            img_path = os.path.join(action_folder_path, img_name)
            try:
                img_obj = Image.open(img_path)
                img_objects.append(img_obj)
            except Exception as e:
                print(f"[SpriteSheetMaker] Failed to open {img_path} {e}")

        # Add to a complete row
        rows.append((label, img_objects))

        # Get label height & width
        bbox = font.getbbox(label)
        label_height = (bbox[3] - bbox[1]) + (margin * 2)
        label_width = (bbox[2] - bbox[0]) + (margin * 2)

        # Get height of tallest sprite & combined width of all sprites 
        max_frame_height = max(img.height for img in img_objects)
        total_frames_width = sum(img.width for img in img_objects) + (len(img_objects) + 1) * margin

        # Calculate row height & width
        row_height = max_frame_height + label_height  # Bottom margin added
        row_width = max(label_width, total_frames_width)

        # Add to total height & width of sprite sheet
        total_width = max(total_width, row_width)
        total_height += row_height


        print(f"[SpriteSheetMaker] '{label}' row dimensions will be {row_width}x{row_height} with {len(img_objects)} frames")


    # Create sprite sheet of appropriate size
    print(f"[SpriteSheetMaker] Creating sprite sheet canvas: {total_width}x{total_height}")
    sheet = Image.new("RGBA", (total_width, total_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)


    # Paste each image and label into rows respectively
    y_offset = 0
    for label, imgs in rows:

        # Skip if no images
        if not imgs:
            continue

        # Add margin above label
        y_offset += margin

        # Draw label
        bbox = font.getbbox(label)
        label_height = bbox[3] - bbox[1] 
        draw.text((margin, y_offset - bbox[1]), label, fill="white", font=font, spacing = 0)
        print(f"[SpriteSheetMaker] Drawing label '{label}' at y={y_offset}")
        y_offset += label_height

        # Add margin below label
        y_offset += margin

        # Paste images horizontally (bottom aligned)
        x_offset = margin
        max_frame_height = max(img.height for img in imgs)
        img_y_base = y_offset + max_frame_height
        for img in imgs:
            img_y = img_y_base - img.height  # bottom align
            sheet.paste(img, (x_offset, img_y))
            print(f"[SpriteSheetMaker] Pasting image frame at ({x_offset}, {img_y})")
            x_offset += img.width + margin

        # Add sprite row height and margin
        y_offset += max_frame_height
        print(f"[SpriteSheetMaker] Finished row '{label}', next y_offset is {y_offset}")


    # Save the final output sprite sheet
    print(f"[SpriteSheetMaker] Saving sprite sheet to '{output_path}' ...")
    sheet.save(output_path)
    print(f"[SpriteSheetMaker] Successfully saved sprite sheet to {output_path}")
