from dataclasses import dataclass


@dataclass
class Task:
    id: int
    title: str
    done: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "done": self.done}

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(id=d["id"], title=d["title"], done=d.get("done", False))

    def render(self) -> str:
        mark = "x" if self.done else " "
        return f"[{mark}] {self.id} {self.title}"
