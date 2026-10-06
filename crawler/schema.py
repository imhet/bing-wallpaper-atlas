"""壁纸记录 JSON Schema。字段与 spec §6 一一对应，additionalProperties 关闭。"""

import jsonschema

SCHEMA = {
    "type": "object",
    "required": [
        "id", "market", "date", "urlbase", "imageKey", "title", "desc",
        "location", "region", "photographer", "gallery",
        "copyrightlink", "quiz", "resolutions", "tags",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z]{2}-[a-z]{2}-\\d{4}-\\d{2}-\\d{2}$"},
        "market": {"type": "string", "pattern": "^[a-z]{2}-[a-z]{2}$"},
        "date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "urlbase": {"type": "string", "pattern": "^/th"},
        "imageKey": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "desc": {"type": "string"},
        "location": {"type": "array", "items": {"type": "string"}},
        "region": {"type": ["string", "null"]},
        "photographer": {"type": ["string", "null"]},
        "gallery": {"type": ["string", "null"]},
        "copyrightlink": {"type": ["string", "null"]},
        "quiz": {"type": ["string", "null"]},
        "resolutions": {"type": "object", "additionalProperties": {"type": "boolean"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_record(rec):
    jsonschema.validate(rec, SCHEMA)
