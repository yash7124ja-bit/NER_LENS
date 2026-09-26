"""Verify the configured private object store without retaining test objects."""

import os
from uuid import uuid4

from ner_lens.media import S3MediaStorage


def main() -> int:
    names = ("ENDPOINT", "BUCKET", "REGION", "ACCESS_KEY", "SECRET_KEY")
    if not all(os.getenv(f"MEDIA_S3_{name}") for name in names):
        print("R2 smoke test: missing configuration")
        return 2

    storage = S3MediaStorage(*(os.environ[f"MEDIA_S3_{name}"] for name in names))
    key = f"smoke-test/{uuid4().hex}"
    body = b"ner-lens-r2-smoke-test"
    passed = False
    try:
        storage.put(key, body, body, "image/jpeg")
        if storage.get(key, "raw") != body or storage.get(key, "derivative") != body:
            raise ValueError("read_mismatch")
        passed = True
    except Exception as exc:
        print(f"R2 put/get: FAIL ({type(exc).__name__})")
    finally:
        for suffix in ("raw", "derivative"):
            try:
                storage.client.delete_object(Bucket=storage.bucket, Key=f"{key}/{suffix}")
            except Exception:
                passed = False
                print("R2 test object cleanup: FAIL")
    if passed:
        print("R2 put/get/delete: PASS")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
