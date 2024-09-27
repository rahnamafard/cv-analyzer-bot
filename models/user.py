class User:
    def __init__(self, user_id, username, is_premium=False, cv_count=0):
        self.user_id = user_id
        self.username = username
        self.is_premium = is_premium
        self.cv_count = cv_count

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "is_premium": self.is_premium,
            "cv_count": self.cv_count
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            is_premium=data["is_premium"],
            cv_count=data["cv_count"]
        )
