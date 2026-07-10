from abc import ABC

from pydantic import BaseModel, ConfigDict


class KISBaseModel(BaseModel, ABC):
    model_config = ConfigDict(serialize_by_alias=True)
