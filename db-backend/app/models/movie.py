"""
电影相关 Pydantic 模型
"""
from typing import Optional, List
from pydantic import BaseModel


class MovieBrief(BaseModel):
    mid: str
    title: str
    rating: Optional[float] = None
    year: Optional[int] = None
    cover: Optional[str] = None
    genres: Optional[List[str]] = None


class PersonRef(BaseModel):
    pid: str
    name: str
    order: Optional[int] = None


class MovieDetail(BaseModel):
    mid: str
    title: str
    rating: Optional[float] = None
    year: Optional[int] = None
    content_type: Optional[str] = None
    genres: Optional[List[str]] = None
    regions: Optional[str] = None
    cover: Optional[str] = None
    storyline: Optional[str] = None
    url: Optional[str] = None
    directors: Optional[List[PersonRef]] = None
    actors: Optional[List[PersonRef]] = None


class MovieCredits(BaseModel):
    mid: str
    directors: List[PersonRef] = []
    actors: List[PersonRef] = []


class MovieListResponse(BaseModel):
    items: List[MovieBrief] = []
    total: int = 0
    page: int = 1
    size: int = 20
