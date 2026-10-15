import assert from "node:assert/strict";
import { File } from "node:buffer";
import test from "node:test";
import { uploadDocuments } from "../src/api.js";

function mockRequests(t) {
  const originalFetch = globalThis.fetch;
  const originalStorage = globalThis.localStorage;
  const calls = [];
  globalThis.localStorage = { getItem: () => null };
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return new Response(JSON.stringify(
      url.endsWith("/upload-limits")
        ? { max_file_bytes: 20 * 1024 * 1024 }
        : { id: "uploaded-document" }
    ), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  t.after(() => {
    globalThis.fetch = originalFetch;
    globalThis.localStorage = originalStorage;
  });
  return calls;
}

test("oversize files are rejected before any upload POST", async (t) => {
  const calls = mockRequests(t);
  await assert.rejects(
    uploadDocuments([{ name: "big.txt", size: 100 * 1024 * 1024 }]),
    /Maximum file size is 20 MiB/
  );
  assert.equal(calls.length, 1);
  assert.ok(calls[0].url.endsWith("/upload-limits"));
});

test("a mixed batch is checked before uploading its first file", async (t) => {
  const calls = mockRequests(t);
  await assert.rejects(
    uploadDocuments([
      new File(["valid"], "small.txt"),
      { name: "big.txt", size: 21 * 1024 * 1024 },
    ]),
    /big.txt is too large/
  );
  assert.equal(calls.length, 1);
});

test("valid files still use one multipart POST per file", async (t) => {
  const calls = mockRequests(t);
  const file = new File(["valid content"], "small.txt");
  const rows = await uploadDocuments([file]);
  assert.deepEqual(rows, [{ id: "uploaded-document" }]);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.body.get("file").name, "small.txt");
  assert.equal(calls[1].options.body.get("file").size, file.size);
  assert.ok(calls[1].options.headers.get("Idempotency-Key"));
});

test("retrying the same selected File keeps its request key", async (t) => {
  const calls = mockRequests(t);
  const file = new File(["policy text"], "policy.txt");
  await uploadDocuments([file]);
  await uploadDocuments([file]);
  assert.equal(calls[1].options.headers.get("Idempotency-Key"),
    calls[3].options.headers.get("Idempotency-Key"));
});
