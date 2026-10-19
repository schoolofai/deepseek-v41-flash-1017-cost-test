import json
import os

from .models import Task


class Store:
    def __init__(self, path: str):
        self.path = path
        self.tasks: list[Task] = []
        self.next_id = 1
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self.tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
            self.next_id = data.get("next_id", len(self.tasks) + 1)

    def add(self, title: str) -> Task:
        task = Task(id=self.next_id, title=title)
        self.next_id += 1
        self.tasks.append(task)
        return task

    def get(self, task_id: int) -> Task:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    def save(self) -> None:
        data = {"next_id": self.next_id, "tasks": [t.to_dict() for t in self.tasks]}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)
