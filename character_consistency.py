"""Character identity constraints and angle-aware reference selection."""

REFERENCE_VIEWS = {
    "front",
    "left_three_quarter",
    "right_three_quarter",
    "left_profile",
    "right_profile",
    "back",
    "full_body",
}
MAX_REFERENCES = 8


def normalize_character(raw, primary_image_id, asset_lookup):
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - {"name", "description", "references"}:
        raise ValueError("character accepts name, description and references only")
    name = raw.get("name", "")
    description = raw.get("description", "")
    references = raw.get("references")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError("character.name must be 1–80 characters")
    if not isinstance(description, str) or not description.strip() or len(description.strip()) > 1200:
        raise ValueError("character.description must be 1–1200 characters")
    if not isinstance(references, list) or not 1 <= len(references) <= MAX_REFERENCES:
        raise ValueError(f"character.references must contain 1–{MAX_REFERENCES} images")
    clean = []
    seen_ids = set()
    seen_views = set()
    for reference in references:
        if not isinstance(reference, dict) or set(reference) != {"image_id", "view"}:
            raise ValueError("Each character reference requires image_id and view only")
        image_id = reference.get("image_id")
        view = reference.get("view")
        if not isinstance(image_id, str) or image_id in seen_ids:
            raise ValueError("Character reference image IDs must be unique")
        if not isinstance(view, str) or view not in REFERENCE_VIEWS or view in seen_views:
            raise ValueError("Character reference views must be supported and unique")
        if asset_lookup(image_id).get("kind") != "image":
            raise ValueError("Character references must be image assets")
        clean.append({"image_id": image_id, "view": view})
        seen_ids.add(image_id)
        seen_views.add(view)
    if primary_image_id not in seen_ids:
        raise ValueError("The primary image_id must be included in character.references")
    return {"name": name.strip(), "description": description.strip(), "references": clean}


def apply_identity_prompt(prompt, character):
    if not character:
        return prompt
    identity = (
        f"Character identity lock for {character['name']}: {character['description']} "
        "The subject is the exact same person in every shot: preserve facial geometry, "
        "hair, skin tone, body proportions, age, wardrobe identity and distinguishing features."
    )
    result = identity + " " + prompt
    if len(result) > 5200:
        raise ValueError("Character description and prompt are too long together")
    return result


def reference_ids(character, primary_image_id):
    if not character:
        return [primary_image_id] if primary_image_id else []
    return [item["image_id"] for item in character["references"]]


def select_reference(character, directing, primary_image_id):
    if not character:
        return primary_image_id
    by_view = {item["view"]: item["image_id"] for item in character["references"]}
    angle = (directing or {}).get("angle")
    candidates = {
        "front": ("front",),
        "three_quarter": ("left_three_quarter", "right_three_quarter", "front"),
        "left_three_quarter": ("left_three_quarter", "front"),
        "right_three_quarter": ("right_three_quarter", "front"),
        "profile": ("left_profile", "right_profile", "left_three_quarter", "right_three_quarter"),
        "left_profile": ("left_profile", "left_three_quarter", "front"),
        "right_profile": ("right_profile", "right_three_quarter", "front"),
        "back": ("back", "full_body"),
        "over_shoulder": ("back", "left_three_quarter", "right_three_quarter"),
        "low": ("front", "left_three_quarter", "right_three_quarter"),
        "high": ("front", "left_three_quarter", "right_three_quarter"),
    }.get(angle, ())
    if (directing or {}).get("shot_size") == "full":
        candidates = (*candidates, "full_body")
    return next((by_view[view] for view in candidates if view in by_view), primary_image_id)


def segment_seed(seed, index, character):
    """Identity-locked shots share noise; ordinary sequences retain shot variation."""
    return seed if character else (seed + index) % 2**32
