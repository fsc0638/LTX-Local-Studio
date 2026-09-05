"""Machine-readable v1 contract. Built from the same limits/profiles as runtime."""
import worker_contract as contract
import factory_store
import model_registry
import mv_timeline
import character_consistency
from media_store import FORMATS


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def response(description, schema):
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def operation(summary, schema, status="200", **extra):
    return {"summary": summary, "responses": {status: response(summary, schema),
            "default": response("Request/authentication/store error", ref("Error"))}, **extra}


def openapi_document():
    request_properties = {
        "prompt": {"type": "string", "minLength": 1, "maxLength": 4000, "description": "Must contain non-whitespace characters."},
        "model": {"type": "string", "enum": ["ltx23-distilled"], "default": "ltx23-distilled"},
        "profile": {"type": "string", "enum": list(contract.PROFILES), "default": "compat-v1",
                    "description": "Versioned base defaults; explicit fields take precedence. Profiles do not guarantee visual quality or memory capacity."},
        "mode": {"type": "string", "enum": ["t2v", "i2v"], "default": "t2v"},
        "image_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
        "image_strength": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.8},
        "reference_background": {"enum": ["source", "alpha_neutral"], "default": "source", "description": "alpha_neutral requires transparent PNG references and composites the subject on neutral gray to reduce source-background conditioning."},
        "character": ref("Character"),
        "width": {"type": "integer", "minimum": 256, "maximum": 1536, "multipleOf": 64},
        "height": {"type": "integer", "minimum": 256, "maximum": 1536, "multipleOf": 64},
        "aspect_ratio": {"type": "string", "enum": [*contract.ASPECT_RATIOS, "source"], "description": "Preset or source image ratio; mutually exclusive with width/height. Source may require letterboxing on the 64px grid."},
        "render_mode": {"enum": ["single", "sequence"], "default": "single"},
        "segment_seconds": {"type": "number", "minimum": 2, "maximum": 20, "default": 10},
        "directing": ref("Directing"),
        "timeline": ref("Timeline"),
        "negative_prompt": {"type": "string", "pattern": r"^\s*$", "description": "Installed distilled model does NOT support negative conditioning. Non-empty input is rejected, never silently ignored."},
        "frames": {"type": "integer", "enum": list(range(9, contract.MAX_FRAMES + 1, 8))},
        "fps": {"type": "integer", "minimum": 8, "maximum": 60},
        "duration_seconds": {"type": "number", "exclusiveMinimum": 0,
                             "description": f"Single: maximum {contract.MAX_FRAMES}/fps, rounded UP to 8n+1. Sequence: maximum 180 seconds, rounded UP to one output frame and assembled from short generated shots."},
        "seed": {"type": "integer", "minimum": 0, "maximum": 2**32 - 1, "default": 42},
        "audio": {"type": "boolean", "description": "Include generated audio. False skips audio decoder/export, not all joint audio inference."},
        "offload": {"type": "boolean", "default": False},
        "timeout_seconds": {"type": "integer", "minimum": 30, "maximum": contract.MAX_TIMEOUT,
                            "description": "Generation + QC deadline. Default from capabilities; no automatic retry on timeout."},
        "external": ref("External"),
    }
    nullable_number = {"type": ["number", "null"]}
    nullable_string = {"type": ["string", "null"]}
    arbitrary_nullable = {"type": ["object", "null"], "additionalProperties": True}
    schemas = {
        "CharacterReference": {"type": "object", "additionalProperties": False,
                               "required": ["image_id", "view"], "properties": {
                                   "image_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                                   "view": {"enum": sorted(character_consistency.REFERENCE_VIEWS)}}},
        "Character": {"type": "object", "additionalProperties": False,
                      "required": ["name", "description", "references"], "properties": {
                          "name": {"type": "string", "minLength": 1, "maxLength": 80},
                          "description": {"type": "string", "minLength": 1, "maxLength": 1200},
                          "references": {"type": "array", "minItems": 1, "maxItems": 8,
                                         "items": ref("CharacterReference")}}},
        "Directing": {"type": "object", "additionalProperties": False, "properties": {
            key: {"type": "string", "enum": list(values)} for key, values in mv_timeline.DIRECTING.items()}},
        "Timeline": {"type": "object", "additionalProperties": False, "properties": {
            "audio_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
            "audio_start_seconds": {"type": "number", "minimum": 0, "maximum": 600},
            "audio_mode": {"enum": ["soundtrack", "condition"], "default": "soundtrack", "description": "condition is experimental frozen audio conditioning, not guaranteed precise lip sync"},
            "lrc": {"type": "string", "maxLength": 16000, "description": "UTF-8 line LRC timestamps relative to output start; offset supported. Not phoneme alignment."},
            "lrc_timebase": {"enum": ["output", "music"], "default": "output", "description": "music subtracts audio_start_seconds from original-song timestamps; lines before the selected start are skipped."},
            "cues": {"type": "array", "maxItems": 60, "items": {"type": "object", "additionalProperties": False,
                "required": ["time"], "properties": {"time": {"type": "number", "minimum": 0, "exclusiveMaximum": 180},
                "action": {"type": "string", "maxLength": 600}, "directing": ref("Directing")}}}}},
        "Error": {"type": "object", "required": ["error"], "properties": {
            "error": {"type": "string"}, "code": {"type": "string"}, "retry_after_seconds": {"type": "integer"}}},
        "External": {"type": "object", "additionalProperties": False,
                     "description": "Optional opaque tracking labels, never authorization or a required project dependency.",
                     "properties": {key: {"type": "string", "pattern": r"^[\w.:-]{1,120}$"}
                                    for key in ("project_id", "asset_id", "shot_id", "request_id")}},
        "JobRequest": {"type": "object", "required": ["prompt"], "additionalProperties": False,
                       "properties": request_properties,
                       "allOf": [{"not": {"required": ["frames", "duration_seconds"]}},
                                 {"if": {"properties": {"render_mode": {"const": "sequence"}}, "required": ["render_mode"]},
                                  "then": {"required": ["duration_seconds"], "not": {"required": ["frames"]},
                                           "properties": {"duration_seconds": {"minimum": 0.125, "maximum": 180}}},
                                  "else": {"not": {"anyOf": [{"required": ["timeline"]}, {"required": ["segment_seconds"]}]}}},
                                 {"if": {"properties": {"aspect_ratio": {"const": "source"}}, "required": ["aspect_ratio"]},
                                  "then": {"required": ["image_id"], "properties": {"mode": {"const": "i2v"}}}},
                                 {"not": {"required": ["aspect_ratio", "width"]}},
                                 {"not": {"required": ["aspect_ratio", "height"]}},
                                 {"if": {"properties": {"mode": {"const": "i2v"}}, "required": ["mode"]},
                                  "then": {"required": ["image_id"]},
                                  "else": {"not": {"anyOf": [{"required": ["image_id"]}, {"required": ["image_strength"]}, {"required": ["reference_background"]}, {"required": ["character"]}]}}}]},
        "ResolvedParameters": {"type": "object", "properties": {
            **{key: {"anyOf": [value, {"type": "null"}]} for key, value in request_properties.items() if key in contract.PARAMETERS},
            "image_id": nullable_string, "image_strength": nullable_number,
            "frames": {"type": ["integer", "null"], "maximum": 10800},
            "timeline": arbitrary_nullable,
            "segments": {"type": ["array", "null"], "items": {"type": "object"}}, "source_geometry": arbitrary_nullable}},
        "Artifact": {"type": "object", "required": ["kind", "content_type", "url"], "properties": {
            "kind": {"enum": ["video", "image", "text"]}, "content_type": {"type": "string"},
            "url": {"type": "string"}, "sha256": nullable_string, "size_bytes": nullable_number}},
        "QualityControl": {"type": ["object", "null"], "properties": {
            "version": {"enum": ["full-decode-v1", "media-technical-v1"]}, "passed": {"type": "boolean"},
            "visual_review_required": {"type": "boolean"}, "human_review_required": {"type": "boolean"},
            "errors": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "metrics": {"type": "object", "additionalProperties": True}, "detail": {"type": "string"}}},
        "Job": {"type": "object", "required": ["id", "status", "status_url", "artifacts", "resolved_parameters"], "properties": {
            "id": {"type": "string", "pattern": "^[a-f0-9]{12,32}$"},
            "status": {"enum": ["queued", "running", "succeeded", "failed", "interrupted", "cancelled"]},
            "status_url": {"type": "string"}, "contract_version": {"type": "string"},
            "progress": {"type": "number", "minimum": 0, "maximum": 100},
            "phase": nullable_string, "message": nullable_string,
            "external": {"anyOf": [ref("External"), {"type": "null"}]},
            "resolved_parameters": ref("ResolvedParameters"), "cancel_requested": {"type": "boolean"},
            "idempotent_replay": {"type": "boolean"}, "artifacts": {"type": "array", "items": ref("Artifact")},
            "quality_control": ref("QualityControl"), "measured_media": arbitrary_nullable,
            "error": arbitrary_nullable, "provenance": arbitrary_nullable,
            **{key: nullable_number for key in ("created_at", "started_at", "finished_at", "runtime_seconds", "elapsed_seconds",
                                               "requested_duration_seconds", "configured_duration_seconds", "width", "height", "frames", "fps")}}},
        "Validation": {"type": "object", "required": ["valid", "resolved_parameters", "configured_duration_seconds"], "properties": {
            "valid": {"const": True}, "contract_version": {"type": "string"}, "resolved_parameters": ref("ResolvedParameters"),
            "external": ref("External"), "requested_duration_seconds": nullable_number,
            "configured_duration_seconds": nullable_number, "warnings": {"type": "array", "items": {"type": "string"}}}},
        "Asset": {"type": "object", "required": ["id", "url", "kind", "content_type", "size_bytes"], "properties": {
            "id": {"type": "string", "pattern": "^[a-f0-9]{32}$"}, "url": {"type": "string"},
            "kind": {"enum": ["image", "video", "audio"]}, "content_type": {"type": "string"}, "size_bytes": {"type": "integer"}}},
        "Capabilities": {"type": "object", "required": ["contract_version", "models", "limits", "profiles"],
                         "additionalProperties": True},
        # The v2 work order. This is the same shape the browser exports and imports, so an
        # upstream project can build a plan offline and post it without a second format.
        "FactoryShot": {"type": "object", "required": ["title", "request"], "properties": {
            "id": {"type": "string", "format": "uuid", "description": "Server-assigned; omit when creating."},
            "title": {"type": "string", "minLength": 1, "maxLength": factory_store.MAX_TITLE},
            "request": {**ref("JobRequest"), "description": "A complete /api/v1/jobs body. Sent through the same validation as a direct submission."},
            "pinned": {"type": "array", "items": {"type": "string"},
                       "description": "Request fields edited by hand; reprojecting the Bible leaves them alone."},
            "status": {"enum": list(factory_store.SHOT_STATES), "readOnly": True},
            "idempotencyKey": {"type": "string", "readOnly": True,
                               "description": "Unique per shot. Retrying a shot replays its job instead of spending a second GPU run."},
            "jobId": {"type": "string", "readOnly": True},
            "outputUrl": {"type": "string", "readOnly": True},
            "posterUrl": {"type": "string", "readOnly": True},
            "error": {"type": "string", "readOnly": True}}},
        "FactoryPlan": {"type": "object", "required": ["format", "version", "id", "title", "status", "shots"], "properties": {
            "format": {"const": factory_store.FORMAT}, "version": {"const": factory_store.VERSION},
            "id": {"type": "string", "format": "uuid"},
            "title": {"type": "string", "minLength": 1, "maxLength": factory_store.MAX_TITLE},
            "bible": {"type": "object", "additionalProperties": True,
                      "description": "Character, music, output format and directing defaults every shot inherits."},
            "status": {"enum": list(factory_store.RUN_STATES)},
            "createdAt": {"type": "string", "format": "date-time"},
            "updatedAt": {"type": "string", "format": "date-time"},
            "shots": {"type": "array", "maxItems": factory_store.MAX_SHOTS, "items": ref("FactoryShot")}}},
        "FactoryTake": {"type": "object", "required": ["id", "verdict", "createdAt"], "properties": {
            "id": {"type": "string", "format": "uuid"}, "jobId": {"type": ["string", "null"]},
            "outputUrl": {"type": ["string", "null"]}, "posterUrl": {"type": ["string", "null"]},
            "scores": {"type": ["object", "null"], "additionalProperties": True,
                       "description": "Written by the consistency, style and motion judges. Null until those run."},
            "verdict": {"enum": list(factory_store.VERDICTS)},
            "reason": {"type": ["string", "null"]}, "createdAt": {"type": "number"}}},
    }
    # Preserve LTX's original fields and add installed adapters as strict variants.
    schemas["LtxJobRequest"] = schemas["JobRequest"]
    variants = [ref("LtxJobRequest")]
    for index, adapter in enumerate(model_registry.ADAPTERS.values()):
        if adapter.id == "ltx23-distilled":
            continue
        parameters = {name: {k: v for k, v in rule.items() if k != "required"}
                      for name, rule in adapter.parameters.items()}
        required = [name for name, rule in adapter.parameters.items() if rule.get("required") and "default" not in rule]
        name = f"AdapterRequest{index}"
        schemas[name] = {"type": "object", "required": ["model", "prompt"] + (["parameters"] if required else []),
                         "additionalProperties": False, "properties": {
            "model": {"const": adapter.id}, "prompt": request_properties["prompt"],
            "mode": {"enum": list(adapter.modes)}, "image_id": request_properties["image_id"],
            "parameters": {"type": "object", "properties": parameters, "required": required, "additionalProperties": False},
            "timeout_seconds": request_properties["timeout_seconds"], "external": ref("External")}}
        if not adapter.accepts_image:
            schemas[name]["properties"].pop("image_id")
        elif "i2v" in adapter.modes:
            schemas[name]["allOf"] = [{"if": {"properties": {"mode": {"const": "i2v"}}, "required": ["mode"]}, "then": {"required": ["image_id"]}}]
        variants.append(ref(name))
    schemas["JobRequest"] = {"type": "object", "required": ["prompt"], "oneOf": variants}
    schemas["ResolvedParameters"]["properties"].update({
        "model": nullable_string, "mode": nullable_string, "parameters": arbitrary_nullable,
        "media_type": {"enum": ["video", "image", "text", None]},
        **{name: nullable_number for name in ("width", "height", "frames", "fps", "seed")}})
    job_id = {"name": "id", "in": "path", "required": True, "schema": schemas["Job"]["properties"]["id"]}
    body = {"required": True, "description": "1–32000 bytes; only supported fields accepted.",
            "content": {"application/json": {"schema": ref("JobRequest")}}}
    submit = operation("Accept asynchronous generation (one GPU slot)", ref("Job"), "202", requestBody=body,
                       parameters=[{"name": "Idempotency-Key", "in": "header", "required": True,
                                    "schema": {"type": "string", "pattern": "^[A-Za-z0-9._:-]{8,128}$"}}])
    submit["responses"].update({"200": response("Same payload/key replays original job", ref("Job")),
                                "410": response("job_deleted: original job was deleted; use a NEW key to generate again", ref("Error")),
                                "409": response("worker_busy (Retry-After: 5) or idempotency_conflict", ref("Error"))})
    binary = {"description": "Authenticated file; Range and HEAD supported", "content": {
        "video/mp4": {"schema": {"type": "string", "format": "binary"}}}}
    download = {"summary": "Download output MP4", "responses": {"200": binary, "206": binary,
                 "416": {"description": "Unsatisfiable byte range"}, "default": response("Artifact not ready or missing", ref("Error"))},
                 "parameters": [{"name": "Range", "in": "header", "schema": {"type": "string"}},
                                {"name": "download", "in": "query", "schema": {"enum": ["1"]}}]}
    cancel = operation("Request cancellation; GPU slot remains occupied until stopped", ref("Job"), "202")
    cancel["responses"]["200"] = response("Already terminal; unchanged (idempotent)", ref("Job"))
    deletion = operation("Remove owned media and invalidate downloads; private recoverable archive retained", {
        "type": "object", "required": ["deleted", "recoverable"], "properties": {
            "deleted": {"const": True}, "recoverable": {"const": True}, "cleanup_pending": {"type": "boolean"}}})
    deletion["description"] = "No request body. Account cookie + X-CSRF-Token or privileged WorkerBearer required. Does not reset generation quota or idempotency history. Admin-only offline recovery; not permanent disk erasure."
    deletion["responses"].update({"404": response("Missing or inaccessible media", ref("Error")),
                                    "409": response("job_active or asset_in_use; finish/cancel generation first", ref("Error"))})
    reference_binary = {**binary, "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                                             for mime in FORMATS}}
    reference_download = {**download, "summary": "Download reference upload", "responses": {
        **download["responses"], "200": reference_binary, "206": reference_binary}}
    artifact_binary = {**binary, "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                                           for mime in ("video/mp4", "image/png", "text/plain")}}
    artifact_download = {**download, "summary": "Download generated media", "responses": {
        **download["responses"], "200": artifact_binary, "206": artifact_binary}}
    project_id = {"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
    factory_body = {"required": True, "content": {"application/json": {"schema": ref("FactoryPlan")}}}
    factory_run = operation("Queue every unfinished shot and start the line", ref("FactoryPlan"))
    factory_run["description"] = ("The host schedules the shots: one GPU job at a time, in order, surviving a closed "
                                  "browser and an API restart. Each shot is admitted through /api/v1/validate and "
                                  "/api/v1/jobs exactly as a direct submission would be.")
    factory_run["responses"]["429"] = response("factory_queue_limit: too much work already in flight for this account", ref("Error"))
    return {"openapi": "3.1.0", "info": {"title": "Local Media Worker API", "version": contract.CONTRACT_VERSION,
            "description": "Project-independent API. Browser accounts are owner-isolated; WorkerBearer is privileged host access. Cookie-authenticated mutations require X-CSRF-Token from /api/auth/session and a configured Origin. Email verification never creates a session. Unknown response fields must be ignored."},
            "servers": [{"url": "/"}], "security": [{"WorkerBearer": []}, {"BrowserSession": []}],
            "components": {"securitySchemes": {"WorkerBearer": {"type": "http", "scheme": "bearer"},
                "BrowserSession": {"type": "apiKey", "in": "cookie", "name": "__Host-ltx_session",
                                   "description": "HTTPS host-only session; loopback HTTP development uses ltx_session."}}, "schemas": schemas},
            "paths": {
                "/api/v1/openapi.json": {"get": operation("Read this contract", {"type": "object"})},
                "/api/v1/capabilities": {"get": operation("Read available models, profiles and machine limits", ref("Capabilities"))},
                "/api/v1/models": {"get": operation("Read installed adapter IDs and parameter schemas", {"type": "object", "additionalProperties": True})},
                "/api/v1/validate": {"post": operation("Validate and resolve parameters without GPU or job creation", ref("Validation"), requestBody=body)},
                "/api/v1/jobs": {"post": submit, "get": operation("List authorized job history", {"type": "object", "properties": {
                    "jobs": {"type": "array", "items": ref("Job")}, "total": {"type": "integer"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}},
                    parameters=[{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30}},
                                {"name": "offset", "in": "query", "schema": {"type": "integer", "minimum": 0, "default": 0}}])},
                "/api/v1/jobs/{id}": {"parameters": [job_id], "get": operation("Poll status, technical QC and artifact", ref("Job")), "delete": deletion},
                "/api/v1/jobs/{id}/cancel": {"parameters": [job_id], "post": cancel},
                "/api/v1/jobs/{id}/video": {"parameters": [job_id], "get": download, "head": download},
                "/api/v1/jobs/{id}/artifact": {"parameters": [job_id], "get": artifact_download, "head": artifact_download},
                "/api/v1/assets": {"get": operation("List authorized reference uploads", {"type": "object", "properties": {
                    "assets": {"type": "array", "items": ref("Asset")}, "shared": {"type": "boolean"}}}),
                    "post": operation("Upload raw bytes (not multipart), maximum 50 MiB", ref("Asset"), "201",
                                      requestBody={"required": True, "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                                                   for mime in FORMATS}},
                                      parameters=[{"name": "name", "in": "query", "schema": {"type": "string", "maxLength": 180}}])},
                "/api/v1/assets/{id}": {"parameters": [{**job_id, "schema": schemas["Asset"]["properties"]["id"]}], "delete": deletion},
                "/api/v1/assets/{id}/file": {"parameters": [{**job_id, "schema": schemas["Asset"]["properties"]["id"]}],
                                             "get": reference_download, "head": reference_download},
                "/api/v1/factory/projects": {
                    "get": operation("List this account's production projects", {"type": "object", "properties": {
                        "projects": {"type": "array", "items": {"type": "object", "properties": {
                            "id": {"type": "string", "format": "uuid"}, "title": {"type": "string"},
                            "status": {"enum": list(factory_store.RUN_STATES)},
                            "shots": {"type": "integer"}, "updatedAt": {"type": "number"}}}}}}),
                    "post": operation("Create a project, optionally importing a v2 work order", ref("FactoryPlan"), "201",
                                      requestBody=factory_body)},
                "/api/v1/factory/projects/{id}": {"parameters": [project_id],
                    "get": operation("Read the project as a v2 work order", ref("FactoryPlan")),
                    "post": operation("Update title, Bible or run state", ref("FactoryPlan"), requestBody=factory_body),
                    "delete": operation("Delete the project with its shots and takes", {"type": "object", "properties": {"deleted": {"const": True}}})},
                "/api/v1/factory/projects/{id}/shots": {"parameters": [project_id],
                    "post": operation("Replace the whole shot list", ref("FactoryPlan"), requestBody={
                        "required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["shots"],
                        "properties": {"shots": {"type": "array", "maxItems": factory_store.MAX_SHOTS, "items": ref("FactoryShot")}}}}}})},
                "/api/v1/factory/projects/{id}/run": {"parameters": [project_id],
                    "post": factory_run},
                "/api/v1/factory/projects/{id}/pause": {"parameters": [project_id],
                    "post": operation("Stop feeding the line. A shot already on the GPU finishes; queued shots return to draft.", ref("FactoryPlan"))},
                "/api/v1/factory/shots/{id}/takes": {"parameters": [{**project_id, "description": "Shot id"}],
                    "get": operation("List every take this shot produced, newest first", {"type": "object", "properties": {
                        "takes": {"type": "array", "items": ref("FactoryTake")}}})},
            }}
