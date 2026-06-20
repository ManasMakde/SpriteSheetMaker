import bpy
from datetime import datetime


def log(message, show_popup = False, icon="INFO"):

    print(f"[SpriteSheetMaker {datetime.now()}] {message}")

    if(show_popup):
        bpy.ops.spritesheetmaker.message_popup('INVOKE_DEFAULT', **{ "message_heading": message,  "message_icon" : icon })
