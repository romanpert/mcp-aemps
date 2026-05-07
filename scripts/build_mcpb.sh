#!/usr/bin/env bash
# Build an .mcpb bundle for the current pyproject.toml version.
#
# Output: dist/mcp-aemps-${VERSION}.mcpb at the repo root.
#
# Requirements: bash, python (poetry), npx (Node ≥ 20). Runs locally and
# in .github/workflows/release.yml.
#
# The bundle wrapper at mcpb/ pulls mcp-aemps==${VERSION} from PyPI at
# host runtime via uv — we never vendor dependencies, so the .mcpb stays
# small (manifest + entry shim + icons + pyproject pinning).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

VERSION="$(python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])")"
[[ -n "${VERSION}" ]] || { echo "✖ could not read project version"; exit 1; }
echo "▶ building MCPB bundle for mcp-aemps v${VERSION}"

OUT_DIR="dist"
mkdir -p "${OUT_DIR}"

# Sync the bundled pyproject + manifest to the same version we are building.
# UTF-8 is set explicitly so this also works on Windows shells (default
# cp1252 would mojibake non-ASCII glyphs in display_name / long_description).
python - <<EOF
import json, pathlib, re
version = "${VERSION}"

manifest_path = pathlib.Path("mcpb/manifest.json")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["version"] = version
manifest_path.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

pyproject_path = pathlib.Path("mcpb/pyproject.toml")
text = pyproject_path.read_text(encoding="utf-8")
text = re.sub(r'^version = ".*"$', f'version = "{version}"', text, count=1, flags=re.MULTILINE)
text = re.sub(r'"mcp-aemps==[^"]+"', f'"mcp-aemps=={version}"', text)
pyproject_path.write_text(text, encoding="utf-8")
EOF

# mcpb pack writes <name>-<version>.mcpb in CWD; run it from the bundle dir.
( cd mcpb && npx -y @anthropic-ai/mcpb pack . "../${OUT_DIR}/mcp-aemps-${VERSION}.mcpb" )

echo "✓ wrote ${OUT_DIR}/mcp-aemps-${VERSION}.mcpb"
ls -lh "${OUT_DIR}/mcp-aemps-${VERSION}.mcpb"
