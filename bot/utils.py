def format_cv_analysis(analysis):
    return f"""
    CV Analysis:
    
    Word count: {analysis['word_count']}
    Skills: {', '.join(analysis['skills'])}
    Education: {analysis['education']}
    Experience: {analysis['experience']}
    """

def format_cv_recommendations(cvs):
    recommendations = "Similar CVs:\n\n"
    for cv in cvs:
        recommendations += f"- {cv.labels[0]} (Created: {cv.created_at.strftime('%Y-%m-%d')})\n"
    return recommendations
