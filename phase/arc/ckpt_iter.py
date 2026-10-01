"""Print a villa checkpoint's completed_iterations (runs inside villa_spiral.sif). mmap keeps multi-GB files cheap."""
import sys

import torch

ck = torch.load(sys.argv[1], map_location="cpu", weights_only=False, mmap=True)
print(int(ck.get("completed_iterations", -1)))
