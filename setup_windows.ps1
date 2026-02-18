# Quick setup script for Windows (NVIDIA GPU with CUDA support)

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Cross-Platform PyTorch Setup - Windows (CUDA)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
python --version

# Create virtual environment
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
python -m venv venv

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install PyTorch with CUDA support
Write-Host "Installing PyTorch with CUDA support (this may take a few minutes)..." -ForegroundColor Yellow
Write-Host "Detecting CUDA version..." -ForegroundColor Gray

# Try to detect CUDA version
try {
    $nvidiaSmi = nvidia-smi
    if ($nvidiaSmi -match "CUDA Version: (\d+\.\d+)") {
        $cudaVersion = $matches[1]
        Write-Host "Detected CUDA Version: $cudaVersion" -ForegroundColor Green
    }
} catch {
    Write-Host "Could not detect CUDA version automatically" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Installing PyTorch for CUDA 11.8 (change if needed)..." -ForegroundColor Yellow
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# For other CUDA versions, use:
# CUDA 12.1: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
# CPU only: pip install torch torchvision

# Verify installation
Write-Host ""
Write-Host "Verifying installation..." -ForegroundColor Yellow
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}' if torch.cuda.is_available() else 'CPU only'); print(f'GPU: {torch.cuda.get_device_name(0)}' if torch.cuda.is_available() else 'No GPU')"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To activate the environment in the future, run:" -ForegroundColor Yellow
Write-Host "  venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host ""
Write-Host "To start training, run:" -ForegroundColor Yellow
Write-Host "  python main.py" -ForegroundColor White
Write-Host ""
Write-Host "For verbose output with device info:" -ForegroundColor Yellow
Write-Host "  python main.py --verbose" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
