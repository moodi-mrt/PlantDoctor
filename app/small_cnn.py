"""4-conv-block baseline CNN (~399K params) for from-scratch ablation."""
import torch
import torch.nn as nn


class ConvBlock(nn.Sequential):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__(
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(kernel_size=2, stride=2),
        )


class SmallCNN(nn.Module):
    def __init__(self, num_classes: int, dropout: float = 0.3):
        super().__init__()
        self.features = nn.Sequential(
            ConvBlock(3, 32),     # 224 -> 112
            ConvBlock(32, 64),    # 112 -> 56
            ConvBlock(64, 128),   # 56 -> 28
            ConvBlock(128, 256),  # 28 -> 14
        )
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.pool(x).flatten(1)
        return self.classifier(x)
