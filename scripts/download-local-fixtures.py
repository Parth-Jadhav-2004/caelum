#!/usr/bin/env python3
"""Explicitly fetch three public speech samples; never runs as part of unit tests."""

import argparse
import hashlib
import json
from pathlib import Path

import httpx

ZIPFORMER = (
    "https://huggingface.co/csukuangfj/sherpa-onnx-zipformer-en-2023-06-26/"
    "resolve/11a70a47ec5fd969c17b8d0818681d222a147781/test_wavs/"
)
FIXTURES = [
    {
        "id": "parakeet-sample",
        "url": (
            "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/"
            "resolve/84b478d541cdbf0c296a7ab5f1e20a6f8f998114/test_wavs/0.wav"
        ),
        "sha256": "5fceacff0315d49cb59fcc505bcecf1ed5f2f35c2897b1e65a59f30e5d922150",
        "bytes": 237964,
    },
    {
        "id": "librispeech-0",
        "url": ZIPFORMER + "0.wav",
        "sha256": "6bc58a4efdf20daac252b6b1502632601a71efe0308f6757dc1eda34891a7e4f",
        "bytes": 212044,
        "text": (
            "AFTER EARLY NIGHTFALL THE YELLOW LAMPS WOULD LIGHT UP HERE AND THERE "
            "THE SQUALID QUARTER OF THE BROTHELS"
        ),
    },
    {
        "id": "librispeech-1",
        "url": ZIPFORMER + "1.wav",
        "sha256": "5143a6ba93c4b274e2c4ac22deb75c2c48936c853f0519add1de828b6c79cc5a",
        "bytes": 534924,
        "text": (
            "GOD AS A DIRECT CONSEQUENCE OF THE SIN WHICH MAN THUS PUNISHED HAD GIVEN "
            "HER A LOVELY CHILD WHOSE PLACE WAS ON THAT SAME DISHONOURED BOSOM TO CONNECT "
            "HER PARENT FOR EVER WITH THE RACE AND DESCENT OF MORTALS AND TO BE FINALLY "
            "A BLESSED SOUL IN HEAVEN"
        ),
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Store public samples outside the repository")
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    manifest = []
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        for fixture in FIXTURES:
            path = args.directory / (fixture["id"] + ".wav")
            if path.exists():
                payload = path.read_bytes()
            else:
                response = client.get(fixture["url"])
                response.raise_for_status()
                payload = response.content
            if len(payload) != fixture["bytes"] or (
                hashlib.sha256(payload).hexdigest() != fixture["sha256"]
            ):
                raise ValueError(f"Fixture checksum mismatch: {fixture['id']}")
            if not path.exists():
                path.write_bytes(payload)
            row = {"id": fixture["id"], "audio": path.name}
            if "text" in fixture:
                reference = path.with_suffix(".txt")
                reference.write_text(fixture["text"] + "\n")
                row["reference"] = reference.name
            manifest.append(row)
    (args.directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(args.directory / "manifest.json")


if __name__ == "__main__":
    main()
