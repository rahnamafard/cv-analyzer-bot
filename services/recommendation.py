from models import CV

class RecommendationService:
    def __init__(self, storage_service):
        self.storage_service = storage_service

    def get_similar_cvs(self, job_position, limit=5):
        all_cvs = self.storage_service.get_all_cvs()
        similar_cvs = [cv for cv in all_cvs if job_position.lower() in cv.labels]
        return sorted(similar_cvs, key=lambda x: x.created_at, reverse=True)[:limit]

    def classify_cv(self, cv_data):
        # Implement CV classification logic here
        # This is a placeholder implementation
        labels = ["software engineer", "data scientist", "project manager"]
        return labels
