/** Server-side only. Never bundle worker or Cloudflare credentials in a browser. */
export class WorkerError extends Error {
  constructor(message, status, code, retryAfter) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

export class LTXWorker {
  constructor({baseUrl, apiKey, accessClientId, accessClientSecret}) {
    const url = new URL(baseUrl);
    if (url.username || url.password || url.search || url.hash || url.pathname !== "/") {
      throw new Error("Use a trusted origin without credentials, path, query or fragment");
    }
    if (url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname))) {
      throw new Error("HTTPS is required outside loopback");
    }
    if (!apiKey || apiKey.length < 32) throw new Error("Missing worker API key");
    if (Boolean(accessClientId) !== Boolean(accessClientSecret)) throw new Error("Both Cloudflare service credentials are required together");
    this.origin = url.origin;
    this.headers = {Authorization: `Bearer ${apiKey}`};
    if (accessClientId) {
      this.headers["CF-Access-Client-Id"] = accessClientId;
      this.headers["CF-Access-Client-Secret"] = accessClientSecret;
    }
  }

  async request(path, {method = "GET", headers = {}, body, timeoutMs = 30000} = {}) {
    if (!path.startsWith("/api/v1/") || path.includes("..") || path.includes("\\")) throw new Error("Invalid worker path");
    // Never forward credentials to a redirect (including a login page).
    const response = await fetch(this.origin + path, {method, body, redirect: "error",
      headers: {...headers, ...this.headers}, signal: AbortSignal.timeout(timeoutMs)});
    if (!response.ok) {
      const error = response.headers.get("Content-Type")?.includes("application/json") ? await response.json() : {};
      throw new WorkerError(error.error || "Worker or Cloudflare authentication failed", response.status,
        error.code, Number(response.headers.get("Retry-After")) || error.retry_after_seconds);
    }
    return response;
  }

  async json(path, options) {
    const response = await this.request(path, options);
    if (!response.headers.get("Content-Type")?.includes("application/json")) {
      throw new Error("Expected API JSON, not a login page. Check Cloudflare service authentication.");
    }
    return response.json();
  }

  capabilities() { return this.json("/api/v1/capabilities"); }
  schema() { return this.json("/api/v1/openapi.json"); }
  validate(payload) {
    return this.json("/api/v1/validate", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
  }
  cancel(id) { return this.json(`/api/v1/jobs/${this.jobId(id)}/cancel`, {method: "POST"}); }
  jobs({limit = 30, offset = 0} = {}) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100 || !Number.isInteger(offset) || offset < 0) throw new Error("Invalid pagination");
    return this.json(`/api/v1/jobs?limit=${limit}&offset=${offset}`);
  }
  submit(payload, idempotencyKey) {
    if (!/^[A-Za-z0-9._:-]{8,128}$/.test(idempotencyKey || "")) throw new Error("A stable idempotency key is required");
    return this.json("/api/v1/jobs", {method: "POST", headers: {"Content-Type": "application/json", "Idempotency-Key": idempotencyKey}, body: JSON.stringify(payload)});
  }
  job(id) { return this.json(`/api/v1/jobs/${this.jobId(id)}`); }
  upload(bytes, {name = "reference.png", contentType = "image/png"} = {}) {
    return this.json(`/api/v1/assets?name=${encodeURIComponent(name)}`, {method: "POST", headers: {"Content-Type": contentType}, body: bytes, timeoutMs: 180000});
  }
  async video(id, range) {
    const response = await this.request(`/api/v1/jobs/${this.jobId(id)}/video?download=1`, {headers: range ? {Range: range} : {}, timeoutMs: 300000});
    if (!response.headers.get("Content-Type")?.startsWith("video/mp4")) throw new Error("Expected MP4 artifact");
    return response; // Stream response.body into the calling project's asset store.
  }
  jobId(id) {
    if (!/^[a-f0-9]{12,32}$/.test(id)) throw new Error("Invalid job ID");
    return id;
  }
}
