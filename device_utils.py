"""
Cross-platform device detection and management utilities for PyTorch.

Supports automatic detection of CUDA (NVIDIA), MPS (Apple Silicon), and CPU fallback.
"""

import torch
import logging
from typing import Tuple, Optional
from enum import Enum


class DeviceType(Enum):
    """Enumeration of supported device types."""
    CUDA = "cuda"
    MPS = "mps"
    CPU = "cpu"


class DeviceManager:
    """
    Manages device detection and allocation for cross-platform PyTorch applications.

    Automatically detects the best available device (CUDA > MPS > CPU) and provides
    utilities for safe device operations.
    """

    def __init__(self, force_cpu: bool = False):
        """
        Initialize the device manager.

        Args:
            force_cpu: If True, forces CPU usage regardless of available accelerators
        """
        self.logger = logging.getLogger(__name__)
        self.force_cpu = force_cpu
        self.device = self._detect_device()
        self.device_type = self._get_device_type()

        self._log_device_info()

    def _detect_device(self) -> torch.device:
        """
        Detect the best available device for computation.

        Priority: CUDA > MPS > CPU

        Returns:
            torch.device: The detected device
        """
        if self.force_cpu:
            return torch.device("cpu")

        # Check for CUDA (NVIDIA GPUs)
        if torch.cuda.is_available():
            return torch.device("cuda")

        # Check for MPS (Apple Silicon)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            try:
                # Verify MPS is actually usable
                test_tensor = torch.zeros(1, device="mps")
                del test_tensor
                return torch.device("mps")
            except Exception as e:
                self.logger.warning(f"MPS available but not usable: {e}")
                return torch.device("cpu")

        # Fallback to CPU
        return torch.device("cpu")

    def _get_device_type(self) -> DeviceType:
        """Get the device type enumeration."""
        device_str = str(self.device.type)
        for dtype in DeviceType:
            if dtype.value == device_str:
                return dtype
        return DeviceType.CPU

    def _log_device_info(self) -> None:
        """Log detailed device information."""
        self.logger.info(f"Using device: {self.device}")

        if self.device_type == DeviceType.CUDA:
            self.logger.info(f"CUDA Device: {torch.cuda.get_device_name(0)}")
            self.logger.info(f"CUDA Version: {torch.version.cuda}")
            self.logger.info(
                f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB"
            )
        elif self.device_type == DeviceType.MPS:
            self.logger.info("MPS (Apple Silicon) acceleration enabled")
        else:
            self.logger.warning("Running on CPU - training may be slow")

    def get_device(self) -> torch.device:
        """Get the current device."""
        return self.device

    def is_cuda(self) -> bool:
        """Check if using CUDA."""
        return self.device_type == DeviceType.CUDA

    def is_mps(self) -> bool:
        """Check if using MPS."""
        return self.device_type == DeviceType.MPS

    def is_cpu(self) -> bool:
        """Check if using CPU."""
        return self.device_type == DeviceType.CPU

    def move_to_device(self, *tensors_or_models):
        """
        Move tensors or models to the detected device.

        Args:
            *tensors_or_models: Variable number of tensors or nn.Module objects

        Returns:
            Tuple of moved objects (or single object if only one provided)
        """
        moved = []
        for obj in tensors_or_models:
            if isinstance(obj, torch.nn.Module):
                moved.append(obj.to(self.device))
            elif isinstance(obj, torch.Tensor):
                moved.append(obj.to(self.device))
            else:
                raise TypeError(f"Expected Tensor or Module, got {type(obj)}")

        return moved[0] if len(moved) == 1 else tuple(moved)

    def synchronize(self) -> None:
        """Synchronize device operations (for CUDA)."""
        if self.is_cuda():
            torch.cuda.synchronize()

    def empty_cache(self) -> None:
        """Clear device cache to free memory."""
        if self.is_cuda():
            torch.cuda.empty_cache()
        elif self.is_mps():
            # MPS doesn't have explicit cache clearing in PyTorch yet
            # This is a safe no-op
            pass

    def get_memory_stats(self) -> Optional[dict]:
        """
        Get memory statistics for the current device.

        Returns:
            dict with memory stats if available, None otherwise
        """
        if self.is_cuda():
            return {
                "allocated": torch.cuda.memory_allocated(0) / 1e9,
                "reserved": torch.cuda.memory_reserved(0) / 1e9,
                "max_allocated": torch.cuda.max_memory_allocated(0) / 1e9,
            }
        elif self.is_mps():
            # MPS doesn't expose memory stats yet
            return None
        else:
            return None
