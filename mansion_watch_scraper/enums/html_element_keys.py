from enum import Enum


class ElementKeys(str, Enum):
    """HTML element keys for scraping."""

    PROPERTY_NAME = "property_name"
    PROPERTY_NAME_LIBRARY = "property_name_library"
    LARGE_PROP_DESC = "large_prop_desc"
    SMALL_PROP_DESC = "small_prop_desc"
    IMAGE_URLS = "image_urls"
    PROPERTY_OVERVIEW = "property_overview"
    COMMON_OVERVIEW = "common_overview"
