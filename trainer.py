"""
Training and evaluation utilities for cross-platform PyTorch models.

Provides a unified training interface that works across CUDA, MPS, and CPU.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from typing import Tuple, Optional, Callable, Dict, List
import time
import logging
from pathlib import Path

from device_utils import DeviceManager


class Trainer:
    """
    Universal trainer for PyTorch models with cross-platform support.

    Handles training loops, validation, checkpointing, and metrics tracking
    with automatic device management.
    """

    def __init__(
        self,
        model: nn.Module,
        device_manager: DeviceManager,
        criterion: Optional[nn.Module] = None,
        optimizer: Optional[optim.Optimizer] = None,
        learning_rate: float = 0.001,
    ):
        """
        Initialize the trainer.

        Args:
            model: PyTorch model to train
            device_manager: Device manager for cross-platform support
            criterion: Loss function (defaults to CrossEntropyLoss)
            optimizer: Optimizer (defaults to Adam)
            learning_rate: Learning rate for optimizer
        """
        self.logger = logging.getLogger(__name__)
        self.device_manager = device_manager
        self.device = device_manager.get_device()

        # Move model to device
        self.model = device_manager.move_to_device(model)

        # Set up loss function
        self.criterion = criterion or nn.CrossEntropyLoss()

        # Set up optimizer
        self.optimizer = optimizer or optim.Adam(
            self.model.parameters(), lr=learning_rate
        )

        # Training metrics
        self.train_losses: List[float] = []
        self.val_losses: List[float] = []
        self.train_accuracies: List[float] = []
        self.val_accuracies: List[float] = []

        self.logger.info(f"Trainer initialized on device: {self.device}")
        if hasattr(self.model, "get_num_parameters"):
            self.logger.info(
                f"Model parameters: {self.model.get_num_parameters():,}"
            )

    def train_epoch(
        self, train_loader: DataLoader, epoch: int
    ) -> Tuple[float, float]:
        """
        Train the model for one epoch.

        Args:
            train_loader: DataLoader for training data
            epoch: Current epoch number

        Returns:
            Tuple of (average_loss, accuracy)
        """
        self.model.train()
        total_loss = 0.0
        correct = 0
        total = 0

        start_time = time.time()

        for batch_idx, (data, target) in enumerate(train_loader):
            # Move data to device
            data = data.to(self.device)
            target = target.to(self.device)

            # Zero gradients
            self.optimizer.zero_grad()

            # Forward pass
            output = self.model(data)
            loss = self.criterion(output, target)

            # Backward pass
            loss.backward()
            self.optimizer.step()

            # Track metrics
            total_loss += loss.item()
            _, predicted = output.max(1)
            total += target.size(0)
            correct += predicted.eq(target).sum().item()

            # Log progress
            if (batch_idx + 1) % 10 == 0:
                self.logger.debug(
                    f"Epoch {epoch} [{batch_idx + 1}/{len(train_loader)}] "
                    f"Loss: {loss.item():.4f}"
                )

        avg_loss = total_loss / len(train_loader)
        accuracy = 100.0 * correct / total
        epoch_time = time.time() - start_time

        self.logger.info(
            f"Epoch {epoch} Training - "
            f"Loss: {avg_loss:.4f}, Accuracy: {accuracy:.2f}%, "
            f"Time: {epoch_time:.2f}s"
        )

        self.train_losses.append(avg_loss)
        self.train_accuracies.append(accuracy)

        return avg_loss, accuracy

    def validate(self, val_loader: DataLoader, epoch: int) -> Tuple[float, float]:
        """
        Validate the model.

        Args:
            val_loader: DataLoader for validation data
            epoch: Current epoch number

        Returns:
            Tuple of (average_loss, accuracy)
        """
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0

        with torch.no_grad():
            for data, target in val_loader:
                # Move data to device
                data = data.to(self.device)
                target = target.to(self.device)

                # Forward pass
                output = self.model(data)
                loss = self.criterion(output, target)

                # Track metrics
                total_loss += loss.item()
                _, predicted = output.max(1)
                total += target.size(0)
                correct += predicted.eq(target).sum().item()

        avg_loss = total_loss / len(val_loader)
        accuracy = 100.0 * correct / total

        self.logger.info(
            f"Epoch {epoch} Validation - "
            f"Loss: {avg_loss:.4f}, Accuracy: {accuracy:.2f}%"
        )

        self.val_losses.append(avg_loss)
        self.val_accuracies.append(accuracy)

        return avg_loss, accuracy

    def train(
        self,
        train_loader: DataLoader,
        val_loader: Optional[DataLoader] = None,
        num_epochs: int = 10,
        checkpoint_dir: Optional[Path] = None,
        early_stopping_patience: Optional[int] = None,
    ) -> Dict[str, List[float]]:
        """
        Train the model for multiple epochs.

        Args:
            train_loader: DataLoader for training data
            val_loader: Optional DataLoader for validation data
            num_epochs: Number of epochs to train
            checkpoint_dir: Directory to save model checkpoints
            early_stopping_patience: Stop if validation doesn't improve for N epochs

        Returns:
            Dictionary containing training history
        """
        self.logger.info(f"Starting training for {num_epochs} epochs")

        best_val_loss = float("inf")
        patience_counter = 0

        for epoch in range(1, num_epochs + 1):
            # Train for one epoch
            train_loss, train_acc = self.train_epoch(train_loader, epoch)

            # Validate if validation loader provided
            if val_loader is not None:
                val_loss, val_acc = self.validate(val_loader, epoch)

                # Early stopping
                if early_stopping_patience is not None:
                    if val_loss < best_val_loss:
                        best_val_loss = val_loss
                        patience_counter = 0

                        # Save best model
                        if checkpoint_dir is not None:
                            self.save_checkpoint(
                                checkpoint_dir / "best_model.pt", epoch
                            )
                    else:
                        patience_counter += 1
                        if patience_counter >= early_stopping_patience:
                            self.logger.info(
                                f"Early stopping triggered at epoch {epoch}"
                            )
                            break

            # Save checkpoint
            if checkpoint_dir is not None and epoch % 5 == 0:
                self.save_checkpoint(
                    checkpoint_dir / f"checkpoint_epoch_{epoch}.pt", epoch
                )

            # Clear cache periodically
            if epoch % 5 == 0:
                self.device_manager.empty_cache()

        self.logger.info("Training completed")

        # Log memory stats if available
        mem_stats = self.device_manager.get_memory_stats()
        if mem_stats:
            self.logger.info(f"Peak GPU memory: {mem_stats['max_allocated']:.2f} GB")

        return {
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
            "train_accuracies": self.train_accuracies,
            "val_accuracies": self.val_accuracies,
        }

    def save_checkpoint(self, path: Path, epoch: int) -> None:
        """
        Save model checkpoint.

        Args:
            path: Path to save checkpoint
            epoch: Current epoch number
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "train_losses": self.train_losses,
            "val_losses": self.val_losses,
            "train_accuracies": self.train_accuracies,
            "val_accuracies": self.val_accuracies,
        }

        torch.save(checkpoint, path)
        self.logger.info(f"Checkpoint saved to {path}")

    def load_checkpoint(self, path: Path) -> int:
        """
        Load model checkpoint.

        Args:
            path: Path to checkpoint file

        Returns:
            Epoch number from checkpoint
        """
        checkpoint = torch.load(path, map_location=self.device)

        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.train_losses = checkpoint.get("train_losses", [])
        self.val_losses = checkpoint.get("val_losses", [])
        self.train_accuracies = checkpoint.get("train_accuracies", [])
        self.val_accuracies = checkpoint.get("val_accuracies", [])

        epoch = checkpoint["epoch"]
        self.logger.info(f"Checkpoint loaded from {path} (epoch {epoch})")

        return epoch

    def evaluate(self, test_loader: DataLoader) -> Tuple[float, float]:
        """
        Evaluate the model on test data.

        Args:
            test_loader: DataLoader for test data

        Returns:
            Tuple of (average_loss, accuracy)
        """
        self.logger.info("Evaluating model on test data")
        return self.validate(test_loader, epoch=0)
