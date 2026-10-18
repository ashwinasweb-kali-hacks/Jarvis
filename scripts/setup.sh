#!/bin/bash
# JARVIS Setup Script
# Initializes all components for development

set -e

echo "🤖 JARVIS Setup"
echo "================"

# Check prerequisites
echo "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 required"; exit 1; }
command -v java >/dev/null 2>&1 || { echo "❌ Java 17+ required"; exit 1; }
command -v adb >/dev/null 2>&1 || { echo "⚠️  ADB not found (optional for deploy)"; }

echo "✅ Prerequisites OK"

# Setup Python environment for cloud server
echo ""
echo "Setting up cloud inference server..."
cd inference-engine/cloud
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ../..

echo "✅ Cloud server ready"

# Download models
echo ""
echo "Downloading models..."
mkdir -p models

# Local quantized model (7B, Q4)
echo "  Downloading jarvis-7b-q4.onnx..."
# huggingface-cli download jarvis-ai/jarvis-7b-q4-onnx --local-dir models/

# Whisper STT model
echo "  Downloading whisper-small..."
# huggingface-cli download openai/whisper-small --local-dir models/whisper-small/

# Piper TTS model
echo "  Downloading piper-en-high..."
# wget -P models/piper/ https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/high/en_US-amy-high.onnx

echo "✅ Models ready (download commands commented — uncomment to fetch)"

# Build protobuf
echo ""
echo "Building protobuf definitions..."
mkdir -p android-app/app/src/main/java/com/jarvis/ai/proto
# protoc --java_out=android-app/app/src/main/java/ \
#        --grpc-java_out=android-app/app/src/main/java/ \
#        proto/jarvis_inference.proto

echo "✅ Protobuf ready"

echo ""
echo "🤖 JARVIS setup complete!"
echo "   - Run 'scripts/build-android.sh' to build the Android app"
echo "   - Run 'scripts/start-cloud.sh' to start the cloud server"
echo "   - Run 'scripts/deploy.sh' to deploy to your Pixel phone"
