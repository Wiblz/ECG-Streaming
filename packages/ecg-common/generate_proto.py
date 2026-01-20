#!/usr/bin/env python3
"""Script to generate Python gRPC code from .proto files."""

import shutil
import subprocess
import sys
from pathlib import Path


def generate_grpc_code() -> None:
    """Generate Python gRPC code from protocol buffer definitions."""
    # Paths
    proto_dir = Path(__file__).parent / "src" / "ecg_common" / "proto"
    proto_file = proto_dir / "ecg_streaming.proto"
    output_dir = proto_dir.parent  # Output to src/ecg_common/
    repo_root = Path(__file__).resolve().parents[2]
    nanopb_out_dir = repo_root / "esp32" / "components" / "ecg_proto"
    nanopb_options = proto_dir / "ecg_streaming.options"

    if not proto_file.exists():
        print(f"Error: Proto file not found: {proto_file}")
        sys.exit(1)

    if not nanopb_options.exists():
        print(f"Error: Nanopb options file not found: {nanopb_options}")
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

    # Step 3: Generate nanopb C code for ESP32
    print("Step 3: Generating nanopb C code for ESP32...")
    nanopb_out_dir.mkdir(parents=True, exist_ok=True)

    protoc_path = shutil.which("protoc")
    nanopb_plugin = shutil.which("protoc-gen-nanopb")
    if protoc_path is None:
        print("Error: protoc not found on PATH. Install protoc to generate nanopb files.")
        sys.exit(1)
    if nanopb_plugin is None:
        print("Error: protoc-gen-nanopb not found on PATH. Install nanopb to enable this step.")
        sys.exit(1)

    nanopb_cmd = [
        protoc_path,
        f"--proto_path={proto_dir.parent}",
        f"--nanopb_out={nanopb_out_dir}",
        f"--nanopb_opt=--options-file={nanopb_options}",
        f"--nanopb_opt=--proto-path={proto_dir}",
        "--nanopb_opt=--strip-path",
        str(proto_file.relative_to(proto_dir.parent)),
    ]

    try:
        subprocess.run(nanopb_cmd, check=True, capture_output=True, text=True)
        print("✓ Nanopb generation complete")
    except subprocess.CalledProcessError as e:
        print(f"Error running nanopb_generator: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)

    nanopb_files_dir = nanopb_out_dir / "proto"
    print("\n✓ Nanopb files:")
    print(f"  - {nanopb_files_dir / 'ecg_streaming.pb.c'}")
    print(f"  - {nanopb_files_dir / 'ecg_streaming.pb.h'}")


if __name__ == "__main__":
    generate_grpc_code()
