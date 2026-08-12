from pydantic import BaseModel, Field


class Structure(BaseModel):
    tldr: str = Field(description="One-sentence summary of the core contribution.")
    research_relevance: str = Field(
        description="Relevance to onboard remote-sensing object detection and model efficiency."
    )
    task_and_scene: str = Field(
        description="Task, application scene, sensor/modality, and target classes."
    )
    model_architecture: str = Field(
        description="Model architecture, key modules, and the central technical design."
    )
    lightweight_method: str = Field(
        description="Compression, acceleration, pruning, quantization, distillation, NAS, or lightweight design."
    )
    onboard_deployability: str = Field(
        description="Deployment evidence such as parameters, FLOPs, latency, memory, energy, hardware, and real-time capability."
    )
    datasets_and_metrics: str = Field(
        description="Datasets, metrics, and experimental setting reported by the source text."
    )
    experiments: str = Field(
        description="Main results, baselines, and ablations reported by the source text."
    )
    limitations: str = Field(
        description="Limitations, risks, and missing evidence. State 'Abstract unavailable' or 'Abstract does not specify' when appropriate."
    )
    ideas_for_my_research: str = Field(
        description="Concrete, bounded ideas relevant to the user's research direction."
    )
    reading_priority: str = Field(
        description="Reading priority from 1 to 5 with a concise reason."
    )
