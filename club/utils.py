import io

from PIL import Image


MAX_PROFILE_SIZE = 300
MAX_FILE_SIZE = 2 * 1024 * 1024


def resize_profile_picture(image_field):
    img = Image.open(image_field)
    img = img.convert('RGB')
    img = img.resize((MAX_PROFILE_SIZE, MAX_PROFILE_SIZE), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)
    return buffer


def validate_image_size(file):
    if file.size > MAX_FILE_SIZE:
        return False
    return True
