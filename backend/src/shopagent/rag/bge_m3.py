"""BGE-M3 registration for fastembed, kept free of project imports so the Docker build can bake the model.

fastembed does not ship BGE-M3 in its catalogue; the official repository carries an ONNX export of its dense
head (CLS pooling, normalised, 1024 dimensions).
"""

from __future__ import annotations

MODEL = "BAAI/bge-m3"
DIM = 1024


def register() -> None:
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if any(m["model"] == MODEL for m in TextEmbedding.list_supported_models()):
        return
    TextEmbedding.add_custom_model(
        model=MODEL,
        pooling=PoolingType.CLS,
        normalization=True,
        sources=ModelSource(hf=MODEL),
        dim=DIM,
        model_file="onnx/model.onnx",
        additional_files=["onnx/model.onnx_data"],
        size_in_gb=2.27,
    )


def prefetch() -> None:
    """Download the model into the fastembed cache (used at image build time)."""
    from fastembed import TextEmbedding

    register()
    TextEmbedding(model_name=MODEL)
