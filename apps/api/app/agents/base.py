from abc import ABC
from typing import Generic, TypeVar

from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseAgent(ABC, Generic[InputT, OutputT]):
    name: str
    responsibility: str

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
