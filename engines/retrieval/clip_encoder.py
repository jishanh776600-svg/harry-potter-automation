"""
STORY FORGE — OpenCLIP Visual & Text Feature Encoder (Phase 1D & 1E)
====================================================================
Integrates OpenCLIP ViT-B/32 (OpenAI pretrained, 512d) for dense multimodal
embeddings of video frames, shots, and natural language retrieval queries.

Features:
  1. Offline & Local: Runs strictly locally with zero external network calls.
  2. Multi-Frame Shot Representation: Samples keyframes (start, midpoint, end)
     per shot to represent dynamic cinematic events rather than static single frames.
  3. L2 Unit Normalization: Ensures all text and image vectors lie on the unit hypersphere
     so dot-product corresponds directly to cosine similarity.
  4. Hardware Optimized: CPU execution with fast batch tensorization; CUDA auto-detection.
"""

import os
import cv2
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from PIL import Image

import torch
import open_clip

logger = logging.getLogger("OpenCLIPVisualEncoder")

DEFAULT_MODEL_NAME = "ViT-B-32"
DEFAULT_PRETRAINED = "openai"
EMBEDDING_DIM = 512


class OpenCLIPVisualEncoder:
    """
    Singleton-pattern OpenCLIP encoder wrapper for video keyframes and text queries.
    """
    _instance: Optional["OpenCLIPVisualEncoder"] = None

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        pretrained: str = DEFAULT_PRETRAINED,
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.pretrained = pretrained
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        os.environ["HF_HUB_OFFLINE"] = "1"
        self.weights_source = self._resolve_local_weights(self.pretrained)
        logger.info(f"Loading OpenCLIP ({model_name} / {self.weights_source}) on device: {self.device}...")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            self.model_name,
            pretrained=self.weights_source,
            device=self.device,
        )
        self.tokenizer = open_clip.get_tokenizer(self.model_name)
        self.model.eval()
        self.fingerprint = f"open_clip_{self.model_name.lower()}_512d"
        logger.info(f"OpenCLIP loaded successfully (fingerprint: {self.fingerprint})")

    @staticmethod
    def _resolve_local_weights(pretrained_tag: str) -> str:
        # Check standard local HuggingFace cache snapshots
        hub_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--timm--vit_base_patch32_clip_224.openai" / "snapshots"
        if hub_dir.exists():
            for snap in hub_dir.iterdir():
                sf = snap / "open_clip_model.safetensors"
                if sf.exists():
                    return str(sf)
        return pretrained_tag

    @classmethod
    def get_instance(cls) -> "OpenCLIPVisualEncoder":
        if cls._instance is None:
            cls._instance = OpenCLIPVisualEncoder()
        return cls._instance

    def encode_text(self, text: str) -> np.ndarray:
        """
        Encodes a text prompt into a normalized 512-dimensional vector.
        """
        clean_text = text.strip()
        tokens = self.tokenizer([clean_text]).to(self.device)
        with torch.no_grad():
            feat = self.model.encode_text(tokens)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.cpu().numpy()[0].astype(np.float32)

    def encode_image(self, image: Union[np.ndarray, Image.Image]) -> np.ndarray:
        """
        Encodes a single RGB image/frame into a normalized 512-dimensional vector.
        """
        if isinstance(image, np.ndarray):
            # Check BGR vs RGB (assuming BGR if from cv2)
            if len(image.shape) == 3 and image.shape[2] == 3:
                # If uint8 numpy array from cv2, convert to RGB PIL
                pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            else:
                pil_img = Image.fromarray(image)
        else:
            pil_img = image.convert("RGB")

        tensor = self.preprocess(pil_img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            feat = self.model.encode_image(tensor)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            return feat.cpu().numpy()[0].astype(np.float32)

    def encode_batch_images(self, images: List[Union[np.ndarray, Image.Image]]) -> List[np.ndarray]:
        """
        Encodes a batch of images in a single forward pass.
        """
        if not images:
            return []

        tensors = []
        for img in images:
            if isinstance(img, np.ndarray):
                pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            else:
                pil_img = img.convert("RGB")
            tensors.append(self.preprocess(pil_img))

        batch = torch.stack(tensors).to(self.device)
        with torch.no_grad():
            feats = self.model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            return [vec.astype(np.float32) for vec in feats.cpu().numpy()]

    @staticmethod
    def sample_shot_keyframes(
        video_path: Union[str, Path],
        start_time: float,
        end_time: float,
        max_samples: int = 3,
    ) -> List[Tuple[float, int, np.ndarray]]:
        """
        Extracts representative multi-frame observations across a video shot interval.
        Samples start (+0.2s), midpoint, and end (-0.2s) to capture temporal evolution
        without indexing redundant consecutive frames.
        Returns list of (timestamp_sec, frame_index, bgr_frame_array).
        """
        vpath = str(video_path)
        cap = cv2.VideoCapture(vpath)
        if not cap.isOpened():
            logger.warning(f"Could not open video file: {vpath}")
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = total_frames / fps if total_frames > 0 else end_time

        s_time = max(0.0, min(start_time, duration))
        e_time = max(s_time + 0.1, min(end_time, duration))
        shot_len = e_time - s_time

        # Determine target timestamps
        if max_samples == 1 or shot_len < 0.8:
            sample_times = [s_time + shot_len / 2.0]
        elif max_samples == 2:
            sample_times = [s_time + shot_len * 0.25, s_time + shot_len * 0.75]
        else:
            # 3 or more samples: start, midpoint, end
            sample_times = [
                s_time + min(0.3, shot_len * 0.2),
                s_time + shot_len * 0.5,
                e_time - min(0.3, shot_len * 0.2),
            ]

        results: List[Tuple[float, int, np.ndarray]] = []
        for ts in sample_times:
            f_idx = int(round(ts * fps))
            if total_frames > 0 and f_idx >= total_frames:
                f_idx = max(0, total_frames - 1)

            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                actual_ts = f_idx / fps
                results.append((actual_ts, f_idx, frame))

        cap.release()
        return results
