"""Machine-readable v1 contract. Built from the same limits/profiles as runtime."""
import worker_contract as contract
import model_registry


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
        "width": {"type": "integer", "minimum": 256, "maximum": 1536, "multipleOf": 64},
        "height": {"type": "integer", "minimum": 256, "maximum": 1536, "multipleOf": 64},
        "frames": {"type": "integer", "enum": list(range(9, contract.MAX_FRAMES + 1, 8))},
        "fps": {"type": "integer", "minimum": 8, "maximum": 60},
        "duration_seconds": {"type": "number", "exclusiveMinimum": 0,
                             "description": "Mutually exclusive with frames; maximum 257/fps. Rounded UP to 8n+1 frames, minimum 9. No silent trimming."},
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
        "Error": {"type": "object", "required": ["error"], "properties": {
            "error": {"type": "string"}, "code": {"type": "string"}, "retry_after_seconds": {"type": "integer"}}},
        "External": {"type": "object", "additionalProperties": False,
                     "description": "Optional opaque tracking labels, never authorization or a required project dependency.",
                     "properties": {key: {"type": "string", "pattern": r"^[\w.:-]{1,120}$"}
                                    for key in ("project_id", "asset_id", "shot_id", "request_id")}},
        "JobRequest": {"type": "object", "required": ["prompt"], "additionalProperties": False,
                       "properties": request_properties,
                       "allOf": [{"not": {"required": ["frames", "duration_seconds"]}},
                                 {"if": {"properties": {"mode": {"const": "i2v"}}, "required": ["mode"]},
                                  "then": {"required": ["image_id"]},
                                  "else": {"not": {"anyOf": [{"required": ["image_id"]}, {"required": ["image_strength"]}]}}}]},
        "ResolvedParameters": {"type": "object", "properties": {
            **{key: {"anyOf": [value, {"type": "null"}]} for key, value in request_properties.items() if key in contract.PARAMETERS},
            "image_id": nullable_string, "image_strength": nullable_number}},
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
            "kind": {"enum": ["image", "video"]}, "content_type": {"type": "string"}, "size_bytes": {"type": "integer"}}},
        "Capabilities": {"type": "object", "required": ["contract_version", "models", "limits", "profiles"],
                         "additionalProperties": True},
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
                                "409": response("worker_busy (Retry-After: 5) or idempotency_conflict", ref("Error"))})
    binary = {"description": "Authenticated file; Range and HEAD supported", "content": {
        "video/mp4": {"schema": {"type": "string", "format": "binary"}}}}
    download = {"summary": "Download output MP4", "responses": {"200": binary, "206": binary,
                 "416": {"description": "Unsatisfiable byte range"}, "default": response("Artifact not ready or missing", ref("Error"))},
                 "parameters": [{"name": "Range", "in": "header", "schema": {"type": "string"}},
                                {"name": "download", "in": "query", "schema": {"enum": ["1"]}}]}
    cancel = operation("Request cancellation; GPU slot remains occupied until stopped", ref("Job"), "202")
    cancel["responses"]["200"] = response("Already terminal; unchanged (idempotent)", ref("Job"))
    reference_binary = {**binary, "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                                             for mime in ("image/png", "image/jpeg", "image/webp", "video/mp4")}}
    reference_download = {**download, "summary": "Download reference upload", "responses": {
        **download["responses"], "200": reference_binary, "206": reference_binary}}
    artifact_binary = {**binary, "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                                           for mime in ("video/mp4", "image/png", "text/plain")}}
    artifact_download = {**download, "summary": "Download generated media", "responses": {
        **download["responses"], "200": artifact_binary, "206": artifact_binary}}
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
                "/api/v1/jobs/{id}": {"parameters": [job_id], "get": operation("Poll status, technical QC and artifact", ref("Job"))},
                "/api/v1/jobs/{id}/cancel": {"parameters": [job_id], "post": cancel},
                "/api/v1/jobs/{id}/video": {"parameters": [job_id], "get": download, "head": download},
                "/api/v1/jobs/{id}/artifact": {"parameters": [job_id], "get": artifact_download, "head": artifact_download},
                "/api/v1/assets": {"get": operation("List authorized reference uploads", {"type": "object", "properties": {
                    "assets": {"type": "array", "items": ref("Asset")}, "shared": {"type": "boolean"}}}),
                    "post": operation("Upload raw bytes (not multipart), maximum 50 MiB", ref("Asset"), "201",
                                      requestBody={"required": True, "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                                                   for mime in ("image/png", "image/jpeg", "image/webp", "video/mp4")}},
                                      parameters=[{"name": "name", "in": "query", "schema": {"type": "string", "maxLength": 180}}])},
                "/api/v1/assets/{id}/file": {"parameters": [{**job_id, "schema": schemas["Asset"]["properties"]["id"]}],
                                             "get": reference_download, "head": reference_download},
            }}
