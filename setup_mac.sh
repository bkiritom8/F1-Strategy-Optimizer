#!/bin/bash
# Quick setup script for macOS (Apple Silicon with MPS support)

set -e  # Exit on error

echo "=================================================="
echo "Cross-Platform PyTorch Setup - macOS (MPS)"
echo "=================================================="

# Check Python version
echo "Checking Python version..."
python3 --version

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install PyTorch with MPS support
echo "Installing PyTorch (this may take a few minutes)..."
pip install "torch>=2.0.0"

# Verify installation
echo ""
echo "Verifying installation..."
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'MPS available: {torch.backends.mps.is_available()}'); print(f'MPS built: {torch.backends.mps.is_built()}')"

echo ""
echo "=================================================="
echo "Setup complete!"
echo "=================================================="
echo ""
echo "To activate the environment in the future, run:"
echo "  source venv/bin/activate"
echo ""
echo "To start training, run:"
echo "  python main.py"
echo ""
echo "For verbose output with device info:"
echo "  python main.py --verbose"
echo "=================================================="
