"""
Cross-Platform PyTorch Training System

Main entry point demonstrating device detection and model training
that works seamlessly on CUDA (NVIDIA), MPS (Apple Silicon), and CPU.

Usage:
    python main.py              # Auto-detect device
    python main.py --cpu        # Force CPU mode
    python main.py --epochs 20  # Train for 20 epochs
"""

import torch
from torch.utils.data import DataLoader, TensorDataset
import logging
import argparse
from pathlib import Path
import sys

from device_utils import DeviceManager
from model import ConvolutionalClassifier, SimpleResNet
from trainer import Trainer


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def create_synthetic_dataset(
    num_samples: int = 1000,
    image_size: int = 28,
    num_classes: int = 10,
) -> TensorDataset:
    """
    Create a synthetic dataset for demonstration.

    Args:
        num_samples: Number of samples to generate
        image_size: Size of square images (e.g., 28 for 28x28)
        num_classes: Number of classes

    Returns:
        TensorDataset with synthetic data
    """
    # Generate random images
    images = torch.randn(num_samples, 1, image_size, image_size)

    # Generate random labels
    labels = torch.randint(0, num_classes, (num_samples,))

    return TensorDataset(images, labels)


def create_data_loaders(
    batch_size: int = 64,
    num_train: int = 1000,
    num_val: int = 200,
    num_test: int = 200,
) -> tuple:
    """
    Create train, validation, and test data loaders.

    Args:
        batch_size: Batch size for data loaders
        num_train: Number of training samples
        num_val: Number of validation samples
        num_test: Number of test samples

    Returns:
        Tuple of (train_loader, val_loader, test_loader)
    """
    logger = logging.getLogger(__name__)

    logger.info("Creating synthetic datasets")
    train_dataset = create_synthetic_dataset(num_train)
    val_dataset = create_synthetic_dataset(num_val)
    test_dataset = create_synthetic_dataset(num_test)

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,  # Set to 0 for cross-platform compatibility
        pin_memory=False,  # Disable for MPS compatibility
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    logger.info(
        f"Data loaders created - "
        f"Train: {num_train}, Val: {num_val}, Test: {num_test}"
    )

    return train_loader, val_loader, test_loader


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Cross-Platform PyTorch Training System"
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU usage (disable GPU acceleration)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=10,
        help="Number of training epochs (default: 10)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size for training (default: 64)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.001,
        help="Learning rate (default: 0.001)",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["cnn", "resnet"],
        default="cnn",
        help="Model architecture to use (default: cnn)",
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="checkpoints",
        help="Directory for saving checkpoints (default: checkpoints)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--num-train",
        type=int,
        default=1000,
        help="Number of training samples (default: 1000)",
    )
    parser.add_argument(
        "--num-val",
        type=int,
        default=200,
        help="Number of validation samples (default: 200)",
    )
    parser.add_argument(
        "--num-test",
        type=int,
        default=200,
        help="Number of test samples (default: 200)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Cross-Platform PyTorch Training System")
    logger.info("=" * 60)

    try:
        # Initialize device manager
        logger.info("Initializing device manager...")
        device_manager = DeviceManager(force_cpu=args.cpu)

        # Create data loaders
        train_loader, val_loader, test_loader = create_data_loaders(
            batch_size=args.batch_size,
            num_train=args.num_train,
            num_val=args.num_val,
            num_test=args.num_test,
        )

        # Create model
        logger.info(f"Creating {args.model.upper()} model...")
        if args.model == "cnn":
            model = ConvolutionalClassifier(
                input_channels=1,
                num_classes=10,
                dropout_rate=0.5,
            )
        else:  # resnet
            model = SimpleResNet(
                input_channels=1,
                num_classes=10,
            )

        logger.info(f"Model created with {model.get_num_parameters():,} parameters")

        # Create trainer
        logger.info("Initializing trainer...")
        trainer = Trainer(
            model=model,
            device_manager=device_manager,
            learning_rate=args.learning_rate,
        )

        # Train model
        logger.info(f"Starting training for {args.epochs} epochs...")
        checkpoint_dir = Path(args.checkpoint_dir)

        history = trainer.train(
            train_loader=train_loader,
            val_loader=val_loader,
            num_epochs=args.epochs,
            checkpoint_dir=checkpoint_dir,
            early_stopping_patience=5,
        )

        # Evaluate on test set
        logger.info("Evaluating on test set...")
        test_loss, test_accuracy = trainer.evaluate(test_loader)

        # Print final results
        logger.info("=" * 60)
        logger.info("Training Complete!")
        logger.info("=" * 60)
        logger.info(f"Final Test Loss: {test_loss:.4f}")
        logger.info(f"Final Test Accuracy: {test_accuracy:.2f}%")
        logger.info(f"Device Used: {device_manager.get_device()}")

        # Print memory statistics if available
        mem_stats = device_manager.get_memory_stats()
        if mem_stats:
            logger.info(f"Peak GPU Memory: {mem_stats['max_allocated']:.2f} GB")

        logger.info(f"Checkpoints saved to: {checkpoint_dir.absolute()}")
        logger.info("=" * 60)

        return 0

    except KeyboardInterrupt:
        logger.warning("Training interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
