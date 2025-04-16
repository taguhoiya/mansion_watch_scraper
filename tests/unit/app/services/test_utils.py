"""Tests for the utils module."""

from bson import ObjectId

from app.services.utils import to_json_serializable, translate_keys


def test_to_json_serializable_object_id():
    """Test converting ObjectId to string."""
    obj_id = ObjectId()
    result = to_json_serializable(obj_id)
    assert isinstance(result, str)
    assert result == str(obj_id)


def test_to_json_serializable_list():
    """Test converting list with ObjectIds."""
    obj_id = ObjectId()
    data = [obj_id, "string", 123]
    result = to_json_serializable(data)

    assert isinstance(result, list)
    assert result[0] == str(obj_id)
    assert result[1] == "string"
    assert result[2] == 123


def test_to_json_serializable_dict():
    """Test converting dict with ObjectIds."""
    obj_id = ObjectId()
    data = {"id": obj_id, "name": "test", "nested": {"id": obj_id}}
    result = to_json_serializable(data)

    assert isinstance(result, dict)
    assert result["id"] == str(obj_id)
    assert result["name"] == "test"
    assert result["nested"]["id"] == str(obj_id)


def test_to_json_serializable_primitive():
    """Test converting primitive values."""
    assert to_json_serializable("string") == "string"
    assert to_json_serializable(123) == 123
    assert to_json_serializable(True) is True
    assert to_json_serializable(None) is None


def test_translate_keys():
    """Test translating keys in a dictionary."""
    data = {"key1": "value1", "key2": "value2", "key3": "value3"}
    translation_map = {"key1": "translated1", "key3": "translated3"}

    result = translate_keys(data, translation_map)

    assert "translated1" in result
    assert "key2" in result
    assert "translated3" in result
    assert result["translated1"] == "value1"
    assert result["key2"] == "value2"
    assert result["translated3"] == "value3"


def test_translate_keys_empty_map():
    """Test translating keys with empty translation map."""
    data = {"key1": "value1", "key2": "value2"}

    result = translate_keys(data, {})

    assert result == data
