"""Check a local clamd with a clean image and EICAR's harmless test signature."""

import io
import os

from PIL import Image

from ner_lens.media import ClamdScanner

EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def main():
    host = os.environ["CLAMD_HOST"]
    port = int(os.getenv("CLAMD_PORT", "3310"))
    scanner = ClamdScanner(host, port)
    image = io.BytesIO()
    Image.new("RGB", (2, 2), "white").save(image, format="JPEG")
    assert scanner(image.getvalue()) == "clean"
    assert scanner(EICAR) == "rejected"
    print("ClamAV trial passed: clean JPEG accepted; EICAR rejected")


if __name__ == "__main__":
    main()
