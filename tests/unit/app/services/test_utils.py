"""Tests for the utils module."""

from bson import ObjectId

from app.services.utils import to_json_serializable, translate_keys


class TestToJsonSerializable:
    """Tests for the to_json_serializable function."""

    def test_convert_object_id(self):
        """Test converting ObjectId to string."""
        obj_id = ObjectId()
        result = to_json_serializable(obj_id)
        assert isinstance(result, str)
        assert result == str(obj_id)

    def test_convert_list_of_object_ids(self):
        """Test converting a list of ObjectIds."""
        obj_ids = [ObjectId(), ObjectId()]
        result = to_json_serializable(obj_ids)
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in result)
        assert result == [str(x) for x in obj_ids]

    def test_convert_dict_with_object_ids(self):
        """Test converting a dictionary containing ObjectIds."""
        obj_id = ObjectId()
        data = {"id": obj_id, "nested": {"id": obj_id}}
        result = to_json_serializable(data)
        assert isinstance(result, dict)
        assert result["id"] == str(obj_id)
        assert result["nested"]["id"] == str(obj_id)

    def test_convert_mixed_data(self):
        """Test converting data with mixed types."""
        obj_id = ObjectId()
        data = {
            "id": obj_id,
            "list": [obj_id, "string", 123],
            "nested": {"id": obj_id},
            "normal": "string",
        }
        result = to_json_serializable(data)
        assert isinstance(result, dict)
        assert result["id"] == str(obj_id)
        assert result["list"] == [str(obj_id), "string", 123]
        assert result["nested"]["id"] == str(obj_id)
        assert result["normal"] == "string"

    def test_convert_primitive_types(self):
        """Test converting primitive data types."""
        assert to_json_serializable("string") == "string"
        assert to_json_serializable(123) == 123
        assert to_json_serializable(True) is True
        assert to_json_serializable(None) is None


class TestTranslateKeys:
    """Tests for the translate_keys function."""

    def test_basic_translation(self):
        """Test basic key translation."""
        data = {"name": "John", "age": 30}
        translation_map = {"name": "名前", "age": "年齢"}
        result = translate_keys(data, translation_map)
        assert result == {"名前": "John", "年齢": 30}

    def test_partial_translation(self):
        """Test translation with only some keys in the map."""
        data = {"name": "John", "age": 30, "city": "Tokyo"}
        translation_map = {"name": "名前", "age": "年齢"}
        result = translate_keys(data, translation_map)
        assert result == {"名前": "John", "年齢": 30, "city": "Tokyo"}

    def test_empty_translation_map(self):
        """Test translation with empty translation map."""
        data = {"name": "John", "age": 30}
        translation_map = {}
        result = translate_keys(data, translation_map)
        assert result == data

    def test_empty_data(self):
        """Test translation with empty data."""
        data = {}
        translation_map = {"name": "名前", "age": "年齢"}
        result = translate_keys(data, translation_map)
        assert result == {}

    def test_translation_with_none_values(self):
        """Test translation with None values."""
        data = {"name": None, "age": 30}
        translation_map = {"name": "名前", "age": "年齢"}
        result = translate_keys(data, translation_map)
        assert result == {"名前": None, "年齢": 30}
