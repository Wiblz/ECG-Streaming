#!/usr/bin/env python3
"""Script to generate Python gRPC code from .proto files."""

import subprocess
import sys
from pathlib import Path


def generate_grpc_code() -> None:
    """Generate Python gRPC code from protocol buffer definitions."""
    # Paths
    proto_dir = Path(__file__).parent / "src" / "ecg_common" / "proto"
    proto_file = proto_dir / "ecg_streaming.proto"
    output_dir = proto_dir.parent  # Output to src/ecg_common/

    if not proto_file.exists():
        print(f"Error: Proto file not found: {proto_file}")
        sys.exit(1)

    print(f"Generating gRPC code from {proto_file}...")
    print(f"Output directory: {output_dir}")

    # Step 1: Generate with protoc
    print("Step 1: Running protoc to generate Python code...")
    protoc_cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={proto_dir.parent}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        f"--pyi_out={output_dir}",
        str(proto_file.relative_to(proto_dir.parent)),
    ]

    try:
        subprocess.run(protoc_cmd, check=True, capture_output=True, text=True)
        print("✓ protoc generation complete")
    except subprocess.CalledProcessError as e:
        print(f"Error running protoc: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)

    # Step 2: Fix imports with protoletariat
    print("Step 2: Fixing imports with protoletariat...")
    protol_cmd = [
        sys.executable,
        "-m",
        "protoletariat",
        f"--python-out={output_dir}",
        "--create-package",
        "--in-place",
        "protoc",
        "-p",
        str(proto_dir.parent),
        str(proto_file.relative_to(proto_dir.parent)),
    ]

    try:
        result = subprocess.run(protol_cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        print("✓ Import fixing complete")
    except subprocess.CalledProcessError as e:
        print(f"Error running protoletariat: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)

    print("\n✓ Successfully generated gRPC code with fixed imports:")
    print(f"  - {proto_dir / 'ecg_streaming_pb2.py'}")
    print(f"  - {proto_dir / 'ecg_streaming_pb2_grpc.py'}")
    print(f"  - {proto_dir / 'ecg_streaming_pb2.pyi'}")


if __name__ == "__main__":
    generate_grpc_code()
