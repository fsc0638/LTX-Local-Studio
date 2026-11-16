"""Character identity constraints and angle-aware reference selection."""

import re

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
MAX_VISUAL_STYLE = 1200


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


def normalize_visual_style(raw):
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip() or len(raw.strip()) > MAX_VISUAL_STYLE:
        raise ValueError(f"visual_style must contain 1–{MAX_VISUAL_STYLE} characters")
    return raw.strip()


def apply_style_prompt(prompt, visual_style=None, preserve_reference=False):
    style = normalize_visual_style(visual_style)
    if style:
        lock = (
            f"Visual style lock: {style} Match this medium, line treatment, shading method, "
            "surface texture, colour palette and level of detail in every frame."
        )
    elif preserve_reference:
        lock = (
            "Visual style lock: render in exactly the same visual medium and art style as the "
            "source reference, matching its line treatment, shading method, surface texture, "
            "colour palette and level of detail in every frame."
        )
    else:
        return prompt
    result = lock + " " + prompt
    if len(result) > 7200:
        raise ValueError("Visual style and prompt are too long together")
    return result


def apply_identity_prompt(prompt, character, visual_style=None):
    result = apply_style_prompt(prompt, visual_style, preserve_reference=bool(character))
    if not character:
        return result
    identity = (
        f"Character identity lock for {character['name']}: {character['description']} "
        "The subject is the exact same person in every shot: preserve facial geometry, "
        "hair, skin tone, body proportions, age, wardrobe identity and distinguishing features."
    )
    result = identity + " " + result
    if len(result) > 7200:
        raise ValueError("Character, visual style and prompt are too long together")
    return result


def reference_ids(character, primary_image_id):
    if not character:
        return [primary_image_id] if primary_image_id else []
    return [item["image_id"] for item in character["references"]]


def infer_angle(prompt):
    """Recover a structured angle from legacy director prompts that stored camera prose only."""
    text = str(prompt or "").lower()
    aliases = (
        (r"left[^.]{0,40}(?:profile|side view)|(?:profile|side view)[^.]{0,40}left", "left_profile"),
        (r"right[^.]{0,40}(?:profile|side view)|(?:profile|side view)[^.]{0,40}right", "right_profile"),
        (r"left[^.]{0,40}(?:three[- ]quarter|3/4)|(?:three[- ]quarter|3/4)[^.]{0,40}left", "left_three_quarter"),
        (r"right[^.]{0,40}(?:three[- ]quarter|3/4)|(?:three[- ]quarter|3/4)[^.]{0,40}right", "right_three_quarter"),
        (r"over[- ]the[- ]shoulder|over shoulder", "over_shoulder"),
        (r"three[- ]quarter|3/4", "three_quarter"),
        (r"\bprofile\b|\bside view\b", "profile"),
        (r"\bback view\b|\bfrom behind\b", "back"),
        (r"\blow[- ]angle\b", "low"),
        (r"\bhigh[- ]angle\b|\boverhead\b|bird.?s[- ]eye", "high"),
        (r"\bfront view\b|\bfrontal\b|\bhead[- ]on\b", "front"),
    )
    return next((angle for pattern, angle in aliases if re.search(pattern, text)), None)


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
