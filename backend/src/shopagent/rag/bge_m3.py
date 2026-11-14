"""BGE-M3 registration for fastembed, kept free of project imports so the Docker build can bake the model.

fastembed does not ship BGE-M3 in its catalogue. Two variants of the dense head are registered:

- ``BAAI/bge-m3``: the official ONNX export, full precision (2.27 GB on disk, about 1.8 GB of RAM).
- ``Xenova/bge-m3-int8``: an int8-quantized export of the same model (0.57 GB, about 1.1 GB of RAM, ~40% faster).
  Measured on the policy benchmark it retrieves as accurately as the full model (dense-only Recall@1 0.714 against
  0.738, Recall@4 0.881 for both: one question apart), so it is the default.

Both use CLS pooling, normalised, 1024 dimensions.
"""

from __future__ import annotations

FULL = "BAAI/bge-m3"
INT8 = "Xenova/bge-m3-int8"
DEFAULT = INT8
DIM = 1024

# model name -> (Hugging Face repository, ONNX file, extra files, size in GB)
_VARIANTS: dict[str, tuple[str, str, list[str], float]] = {
    FULL: ("BAAI/bge-m3", "onnx/model.onnx", ["onnx/model.onnx_data"], 2.27),
    INT8: ("Xenova/bge-m3", "onnx/model_int8.onnx", [], 0.57),
}


def is_bge_m3(model_name: str) -> bool:
    return model_name in _VARIANTS


def register(model_name: str = DEFAULT) -> None:
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if any(m["model"] == model_name for m in TextEmbedding.list_supported_models()):
        return
    repository, model_file, extra_files, size_gb = _VARIANTS[model_name]
    TextEmbedding.add_custom_model(
        model=model_name,
        pooling=PoolingType.CLS,
        normalization=True,
        sources=ModelSource(hf=repository),
        dim=DIM,
        model_file=model_file,
        additional_files=extra_files or None,
        size_in_gb=size_gb,
    )


def prefetch(model_name: str = DEFAULT) -> None:
    """Download the model into the fastembed cache (used at image build time)."""
    from fastembed import TextEmbedding

    register(model_name)
    TextEmbedding(model_name=model_name)
