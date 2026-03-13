"""
影人相关 Pydantic 模型
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class PersonBrief(BaseModel):
    pid: str
    name: str
    profession: Optional[str] = None


class PersonDetail(BaseModel):
    pid: str
    name: str
    sex: Optional[str] = None
    birth: Optional[str] = None
    birthplace: Optional[str] = None
    profession: Optional[str] = None
    biography: Optional[str] = None
    movie_count: int = 0
    directed_count: int = 0


class PersonMovieItem(BaseModel):
    mid: str
    title: str
    rating: Optional[float] = None
    year: Optional[int] = None
    role: Optional[str] = None  # "director" | "actor"
    roles: List[str] = Field(default_factory=list)


class PersonMovies(BaseModel):
    pid: str
    name: str
    movies: List[PersonMovieItem] = Field(default_factory=list)


class CollaboratorItem(BaseModel):
    pid: str
    name: str
    collaboration_count: int = 0
