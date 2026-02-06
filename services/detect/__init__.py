from .model import (
    ANIMAL_CLASSES,
    ANNOTATION_COLORS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    annotate_frame,
    detect_frame,
    get_device,
    load_model,
    process_image,
    process_video,
)
from .worker import start_worker
