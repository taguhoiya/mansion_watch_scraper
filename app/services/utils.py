from bson import ObjectId


def to_json_serializable(doc):
    """Convert MongoDB document to JSON serializable format."""
    if isinstance(doc, list):
        return [to_json_serializable(item) for item in doc]
    if isinstance(doc, dict):
        return {key: to_json_serializable(value) for key, value in doc.items()}
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc


def translate_keys(data: dict, translation_map: dict) -> dict:
    translated_data = {}
    for key, value in data.items():
        translated_key = translation_map.get(key, key)
        translated_data[translated_key] = value
    return translated_data
