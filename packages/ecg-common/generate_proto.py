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
    output_dir = proto_dir  # Output to src/ecg_common/proto/
    repo_root = Path(__file__).resolve().parents[2]
    nanopb_out_dir = repo_root / "esp32" / "components" / "ecg_proto"

    # Proto files to compile (order matters for dependencies)
    proto_files = [
        "common.proto",
        "usb_transport.proto",
        "esp_collector.proto",
        "collector_aggregator.proto",
    ]

    # Nanopb files (ESP32 only needs these)
    nanopb_files = [
        ("common.proto", None),  # No options needed
        ("usb_transport.proto", "usb_transport.options"),
        ("esp_collector.proto", "esp_collector.options"),
    ]

    print(f"Generating code from proto files in {proto_dir}...")
    print(f"Output directory: {output_dir}")

    # Step 1: Generate Python code with protoc
    print("\n=== Step 1: Generating Python code with protoc ===")
    for proto_file in proto_files:
        proto_path = proto_dir / proto_file
        if not proto_path.exists():
            print(f"Error: Proto file not found: {proto_path}")
            sys.exit(1)

        print(f"Processing {proto_file}...")
        protoc_cmd = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={proto_dir}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            f"--pyi_out={output_dir}",
            str(proto_path.relative_to(proto_dir)),
        ]

        try:
            subprocess.run(protoc_cmd, check=True, capture_output=True, text=True)
            print(f"  ✓ {proto_file}")
        except subprocess.CalledProcessError as e:
            print(f"Error running protoc on {proto_file}: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            sys.exit(1)

    # Step 2: Fix imports with protoletariat
    print("\n=== Step 2: Fixing imports with protoletariat ===")
    for proto_file in proto_files:
        proto_path = proto_dir / proto_file
        protol_cmd = [
            sys.executable,
            "-m",
            "protoletariat",
            f"--python-out={output_dir}",
            "--create-package",
            "--in-place",
            "protoc",
            "-p",
            str(proto_dir),
            str(proto_path.relative_to(proto_dir)),
        ]

        try:
            subprocess.run(protol_cmd, check=True, capture_output=True, text=True)
            print(f"  ✓ {proto_file}")
        except subprocess.CalledProcessError as e:
            print(f"Error running protoletariat on {proto_file}: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            sys.exit(1)

    print("\n✓ Successfully generated Python gRPC code:")
    for proto_file in proto_files:
        base_name = proto_file.replace(".proto", "")
        print(f"  - {proto_dir / f'{base_name}_pb2.py'}")
        print(f"  - {proto_dir / f'{base_name}_pb2.pyi'}")
        if proto_file == "collector_aggregator.proto":
            print(f"  - {proto_dir / f'{base_name}_pb2_grpc.py'}")

    # Step 3: Generate nanopb C code for ESP32
    print("\n=== Step 3: Generating nanopb C code for ESP32 ===")
    nanopb_proto_dir = nanopb_out_dir / "proto"
    nanopb_proto_dir.mkdir(parents=True, exist_ok=True)

    protoc_path = shutil.which("protoc")
    nanopb_plugin = shutil.which("protoc-gen-nanopb")
    if protoc_path is None:
        print("Error: protoc not found on PATH. Install protoc to generate nanopb files.")
        sys.exit(1)
    if nanopb_plugin is None:
        print("Error: protoc-gen-nanopb not found on PATH. Install nanopb to enable this step.")
        sys.exit(1)

    for proto_file, options_file in nanopb_files:
        proto_path = proto_dir / proto_file
        print(f"Processing {proto_file} for ESP32...")

        nanopb_cmd = [
            protoc_path,
            f"--proto_path={proto_dir}",
            f"--nanopb_out={nanopb_proto_dir}",
        ]

        if options_file:
            options_path = proto_dir / options_file
            if not options_path.exists():
                print(f"Warning: Options file not found: {options_path}")
            else:
                nanopb_cmd.append(f"--nanopb_opt=--options-file={options_path}")

        nanopb_cmd.extend(
            [
                "--nanopb_opt=--strip-path",
                str(proto_path.relative_to(proto_dir)),
            ]
        )

        try:
            subprocess.run(nanopb_cmd, check=True, capture_output=True, text=True)
            print(f"  ✓ {proto_file}")
        except subprocess.CalledProcessError as e:
            print(f"Error running nanopb_generator on {proto_file}: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            sys.exit(1)

    print(f"\n✓ Nanopb files generated in {nanopb_proto_dir}:")
    for proto_file, _ in nanopb_files:
        base_name = proto_file.replace(".proto", "")
        print(f"  - proto/{base_name}.pb.c")
        print(f"  - proto/{base_name}.pb.h")


if __name__ == "__main__":
    generate_grpc_code()
