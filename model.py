"""
Neural network models for cross-platform PyTorch training.

All models are designed to work seamlessly across CUDA, MPS, and CPU.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple


class ConvolutionalClassifier(nn.Module):
    """
    A simple CNN classifier for image classification tasks.

    Architecture:
        - Conv2d (32 filters, 3x3 kernel)
        - ReLU + MaxPool2d
        - Conv2d (64 filters, 3x3 kernel)
        - ReLU + MaxPool2d
        - Fully connected layers
        - Dropout for regularization

    Compatible with CUDA, MPS, and CPU backends.
    """

    def __init__(
        self,
        input_channels: int = 1,
        num_classes: int = 10,
        dropout_rate: float = 0.5,
    ):
        """
        Initialize the convolutional classifier.

        Args:
            input_channels: Number of input channels (1 for grayscale, 3 for RGB)
            num_classes: Number of output classes
            dropout_rate: Dropout probability for regularization
        """
        super(ConvolutionalClassifier, self).__init__()

        self.input_channels = input_channels
        self.num_classes = num_classes

        # Convolutional layers
        self.conv1 = nn.Conv2d(input_channels, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)

        # Pooling layer
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)

        # Fully connected layers
        # Assumes input image size of 28x28 (like MNIST)
        # After 2 pooling operations: 28 -> 14 -> 7
        self.fc1 = nn.Linear(64 * 7 * 7, 128)
        self.fc2 = nn.Linear(128, num_classes)

        # Dropout for regularization
        self.dropout = nn.Dropout(dropout_rate)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the network.

        Args:
            x: Input tensor of shape (batch_size, channels, height, width)

        Returns:
            Output logits of shape (batch_size, num_classes)
        """
        # First convolutional block
        x = self.conv1(x)
        x = F.relu(x)
        x = self.pool(x)

        # Second convolutional block
        x = self.conv2(x)
        x = F.relu(x)
        x = self.pool(x)

        # Flatten for fully connected layers
        x = x.view(x.size(0), -1)

        # Fully connected layers with dropout
        x = self.fc1(x)
        x = F.relu(x)
        x = self.dropout(x)
        x = self.fc2(x)

        return x

    def get_num_parameters(self) -> int:
        """Get total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class ResidualBlock(nn.Module):
    """
    A simple residual block for deeper networks.

    Implements skip connections to enable better gradient flow.
    """

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1):
        """
        Initialize the residual block.

        Args:
            in_channels: Number of input channels
            out_channels: Number of output channels
            stride: Stride for convolution
        """
        super(ResidualBlock, self).__init__()

        self.conv1 = nn.Conv2d(
            in_channels, out_channels, kernel_size=3, stride=stride, padding=1
        )
        self.bn1 = nn.BatchNorm2d(out_channels)

        self.conv2 = nn.Conv2d(
            out_channels, out_channels, kernel_size=3, stride=1, padding=1
        )
        self.bn2 = nn.BatchNorm2d(out_channels)

        # Skip connection for dimension matching
        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride),
                nn.BatchNorm2d(out_channels),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass with residual connection."""
        identity = self.shortcut(x)

        out = self.conv1(x)
        out = self.bn1(out)
        out = F.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        out += identity
        out = F.relu(out)

        return out


class SimpleResNet(nn.Module):
    """
    A simplified ResNet architecture for demonstration.

    Uses residual blocks for improved training stability.
    """

    def __init__(self, input_channels: int = 1, num_classes: int = 10):
        """
        Initialize the simple ResNet.

        Args:
            input_channels: Number of input channels
            num_classes: Number of output classes
        """
        super(SimpleResNet, self).__init__()

        self.conv1 = nn.Conv2d(input_channels, 32, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(32)

        self.layer1 = ResidualBlock(32, 32)
        self.layer2 = ResidualBlock(32, 64, stride=2)
        self.layer3 = ResidualBlock(64, 128, stride=2)

        self.avg_pool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(128, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass through the network."""
        x = self.conv1(x)
        x = self.bn1(x)
        x = F.relu(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)

        x = self.avg_pool(x)
        x = x.view(x.size(0), -1)
        x = self.fc(x)

        return x

    def get_num_parameters(self) -> int:
        """Get total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
