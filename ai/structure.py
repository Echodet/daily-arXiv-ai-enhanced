from pydantic import BaseModel, Field


class Structure(BaseModel):
    tldr: str = Field(description="一句话概括论文核心贡献")
    research_relevance: str = Field(description="说明论文与遥感卫星在轨目标检测及轻量化方向的相关性")
    task_and_scene: str = Field(description="任务类型、应用场景、传感器类型、目标类别")
    model_architecture: str = Field(description="模型结构、关键模块、网络设计")
    lightweight_method: str = Field(description="剪枝、量化、蒸馏、NAS、轻量网络等模型压缩或加速方法")
    onboard_deployability: str = Field(description="星上/边缘部署可行性，包括参数量、FLOPs、延迟、显存、能耗、实时性")
    datasets_and_metrics: str = Field(description="数据集、评价指标、实验设置")
    experiments: str = Field(description="主要实验结果、对比方法、消融实验")
    limitations: str = Field(description="局限性、潜在问题、摘要未说明的关键缺口")
    ideas_for_my_research: str = Field(description="对本人课题可借鉴的想法、可复现方向或可改进点")
    reading_priority: str = Field(description="1-5 分阅读优先级，并简述理由")
