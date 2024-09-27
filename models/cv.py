from datetime import datetime

class CV:
    def __init__(self, user_id, file_id, analyzed_data, labels):
        self.user_id = user_id
        self.file_id = file_id
        self.analyzed_data = analyzed_data
        self.labels = labels
        self.created_at = datetime.now()

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "file_id": self.file_id,
            "analyzed_data": self.analyzed_data,
            "labels": self.labels,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data):
        cv = cls(
            user_id=data["user_id"],
            file_id=data["file_id"],
            analyzed_data=data["analyzed_data"],
            labels=data["labels"]
        )
        cv.created_at = datetime.fromisoformat(data["created_at"])
        return cv
