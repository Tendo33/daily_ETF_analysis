from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    snippet: str
    published_at: datetime | None
    source: str


class NewsProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, max_results: int = 5, days: int = 3) -> list[NewsItem]:
        raise NotImplementedError
